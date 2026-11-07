"""平台-代码生成视图。

"""

import json
from datetime import datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile, ZIP_DEFLATED

import airspeed
from django.db import connection, transaction
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from typing import Optional
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ViewSet

from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.codegen.models import GenTable
from apps.system.menus.services import add_menu_for_codegen

from core.ai import chat_json, load_prompt
from core.naming import to_camel_case, to_kebab_case, to_pascal_case, to_plural_kebab, to_upper_snake
from core.response import error, page_success, success
from core.openapi import page_resp, resp

from .constants import (
    CODEGEN_BACKEND_APP_NAME,
    CODEGEN_DOWNLOAD_FILE_NAME,
    CODEGEN_FRONTEND_APP_NAME,
    DEFAULT_AUTHOR,
    DEFAULT_MODULE_NAME,
    DEFAULT_PACKAGE_NAME,
    DEFAULT_REMOVE_TABLE_PREFIX,
    MSG_OK,
    PERMISSION_NAMESPACES,
    TEMPLATE_CONFIGS,
    TemplateConfig,
    CODE_OK,
)


class VStr(str):
    def trim(self):
        return self.strip()


def _table_exists(table: str) -> bool:
    vendor = _db_vendor()
    try:
        with connection.cursor() as cur:
            if vendor == "sqlite":
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", [table])
                return cur.fetchone() is not None
            if vendor == "postgresql":
                cur.execute(
                    """
SELECT COUNT(1)
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = current_schema() AND TABLE_NAME = %s
""",
                    [table],
                )
                return int(cur.fetchone()[0]) > 0
            cur.execute(
                """
SELECT COUNT(1)
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
""",
                [table],
            )
            return int(cur.fetchone()[0]) > 0
    except Exception:
        return False


def _codegen_tables() -> tuple[str, str, str]:
    """Return (cfg_table, column_table, fk_column_name)."""
    if _table_exists("gen_table") and _table_exists("gen_table_column"):
        return "gen_table", "gen_table_column", "table_id"
    return "gen_config", "gen_field_config", "config_id"


def _table_has_column(table: str, column: str) -> bool:
    vendor = _db_vendor()
    try:
        with connection.cursor() as cur:
            if vendor == "sqlite":
                cur.execute(f"PRAGMA table_info({table})")
                return any((row[1] == column) for row in cur.fetchall())
            if vendor == "postgresql":
                cur.execute(
                    """
SELECT COUNT(1)
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = current_schema() AND TABLE_NAME = %s AND COLUMN_NAME = %s
""",
                    [table, column],
                )
                return int(cur.fetchone()[0]) > 0
            cur.execute(
                """
SELECT COUNT(1)
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
""",
                [table, column],
            )
            return int(cur.fetchone()[0]) > 0
    except Exception:
        return False


def _get_gen_config_extra(table_name: str) -> dict:
    cfg_table, _, _ = _codegen_tables()
    extras: dict = {}
    cols = []
    if _table_has_column(cfg_table, "remove_table_prefix"):
        cols.append("remove_table_prefix")
    if _table_has_column(cfg_table, "page_type"):
        cols.append("page_type")
    if not cols:
        return extras

    sql = f"SELECT {', '.join(cols)} FROM {cfg_table} WHERE table_name = %s LIMIT 1"
    try:
        with connection.cursor() as cur:
            cur.execute(sql, [table_name])
            row = cur.fetchone()
            if not row:
                return extras
            for i, c in enumerate(cols):
                extras[c] = row[i]
        return extras
    except Exception:
        return {}


def _update_gen_config_extra(table_name: str, remove_table_prefix: Optional[str], page_type: Optional[str]) -> None:
    cfg_table, _, _ = _codegen_tables()
    sets = []
    params = []
    if remove_table_prefix is not None and _table_has_column(cfg_table, "remove_table_prefix"):
        sets.append("remove_table_prefix = %s")
        params.append(remove_table_prefix)
    if page_type is not None and _table_has_column(cfg_table, "page_type"):
        sets.append("page_type = %s")
        params.append(page_type)
    if not sets:
        return

    params.append(table_name)
    sql = f"UPDATE {cfg_table} SET {', '.join(sets)} WHERE table_name = %s"
    try:
        with connection.cursor() as cur:
            cur.execute(sql, params)
    except Exception:
        return


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _default_entity_name(table_name: str, remove_prefix: str) -> str:
    """按表名推导实体名：先去表前缀再转大驼峰，避免 SysArticle 把模块名重复进实体名。"""
    processed = table_name
    if remove_prefix and processed.startswith(remove_prefix):
        processed = processed[len(remove_prefix):]
    return to_pascal_case(processed)


def _resolve_perm_prefix(module_name: str, entity_name: str) -> str:
    """权限标识前缀（如 sys:article）：后端守卫、前端 v-hasPerm 与菜单按钮权限共用同一个值。"""
    namespace = PERMISSION_NAMESPACES.get(module_name, module_name)
    return f"{namespace}:{to_kebab_case(entity_name)}"


def _has_logic_delete(field_configs) -> bool:
    """字段配置是否包含逻辑删除列，供视图模板决定查询过滤与删除方式。"""
    return any(
        f.get("fieldName") == "isDeleted" or f.get("columnName") == "is_deleted"
        for f in (field_configs or [])
    )


def _normalize_column_type(column_type: str) -> str:
    t = (column_type or "").strip().lower()
    t = t.replace("unsigned", "").replace("zerofill", "").strip()
    if "(" in t:
        t = t.split("(", 1)[0].strip()
    return t


def _java_type_by_column_type(column_type: str) -> str:
    t = _normalize_column_type(column_type)
    if any(x in t for x in ["char", "varchar", "text", "json", "clob"]):
        return "String"
    if "blob" in t or "binary" in t:
        return "byte[]"
    if any(x in t for x in ["int", "tinyint", "smallint", "mediumint"]):
        return "Integer"
    if "bigint" in t:
        return "Long"
    if "float" in t:
        return "Float"
    if "double" in t:
        return "Double"
    if "decimal" in t or "numeric" in t:
        return "BigDecimal"
    if t == "date":
        return "LocalDate"
    if any(x in t for x in ["datetime", "timestamp"]):
        return "LocalDateTime"
    return "String"


def _ts_type_by_java_type(java_type: str) -> str:
    if java_type in ["Integer", "Long", "Float", "Double", "BigDecimal"]:
        return "number"
    if java_type in ["Boolean"]:
        return "boolean"
    return "string"


def _form_type_name(value: Optional[int]) -> str:
    v = int(value or 1)
    return {
        1: "INPUT",
        2: "SELECT",
        3: "RADIO",
        4: "CHECK_BOX",
        5: "DATE",
        6: "DATE_TIME",
        7: "INPUT_NUMBER",
        8: "SWITCH",
        9: "TEXT_AREA",
    }.get(v, "INPUT")


def _query_type_name(value: Optional[int]) -> str:
    v = int(value or 1)
    return {
        1: "EQ",
        2: "NE",
        3: "GT",
        4: "GE",
        5: "LT",
        6: "LE",
        7: "LIKE",
        8: "BETWEEN",
    }.get(v, "EQ")


def _default_form_type_by_column_type(column_type: str) -> int:
    t = _normalize_column_type(column_type)
    if any(x in t for x in ["tinyint", "smallint", "int", "bigint", "decimal", "numeric", "float", "double"]):
        return 7
    if any(x in t for x in ["datetime", "timestamp"]):
        return 6
    if t == "date":
        return 5
    return 1


def _db_vendor() -> str:
    return connection.vendor


def _sqlite_table_names(keywords: str) -> list[str]:
    with connection.cursor() as cur:
        if keywords:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name LIKE ? ORDER BY name ASC",
                [f"%{keywords}%"],
            )
        else:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name ASC"
            )
        rows = cur.fetchall()
    names = [r[0] for r in rows]
    return [n for n in names if n not in ["gen_config", "gen_field_config", "gen_table", "gen_table_column"]]


def _sqlite_columns(table_name: str) -> list[dict]:
    with connection.cursor() as cur:
        cur.execute(f"PRAGMA table_info({table_name})")
        rows = cur.fetchall()
    cols = []
    for row in rows:
        cid, name, ctype, notnull, dflt_value, pk = row
        cols.append(
            {
                "columnName": name,
                "columnType": ctype or "",
                "columnComment": "",
                "isNullable": "NO" if int(notnull) == 1 else "YES",
                "maxLength": None,
                "ordinalPosition": int(cid) + 1,
                "pk": int(pk) == 1,
            }
        )
    return cols


def _mysql_table_page(keywords: str, limit: int, offset: int) -> tuple[list[dict], int]:
    cfg_table, _, _ = _codegen_tables()

    where = "t.TABLE_SCHEMA = DATABASE()"
    params: list = []
    if _table_has_column(cfg_table, "is_deleted"):
        where += " AND (c.is_deleted = 0 OR c.is_deleted IS NULL OR c.is_deleted = FALSE)"

    if keywords:
        where += " AND t.TABLE_NAME LIKE %s"
        params.append(f"%{keywords}%")

    join_sql = f"LEFT JOIN {cfg_table} c\n  ON c.table_name = t.TABLE_NAME"

    list_sql = f"""
SELECT
  t.TABLE_NAME AS tableName,
  t.TABLE_COMMENT AS tableComment,
  t.TABLE_COLLATION AS tableCollation,
  t.ENGINE AS engine,
  DATE_FORMAT(t.CREATE_TIME, '%%Y-%%m-%%d %%H:%%i:%%s') AS createTime,
  IF(c.table_name IS NULL, 0, 1) AS isConfigured
FROM information_schema.TABLES t
{join_sql}
WHERE {where}
ORDER BY t.CREATE_TIME DESC
LIMIT %s OFFSET %s
"""
    list_params = params + [limit, offset]

    total_sql = f"SELECT COUNT(1) AS total FROM information_schema.TABLES t {join_sql} WHERE {where}"

    with connection.cursor() as cur:
        cur.execute(list_sql, list_params)
        rows = cur.fetchall()
        columns = [c[0] for c in cur.description]
        data = [dict(zip(columns, r)) for r in rows]

        cur.execute(total_sql, params)
        total = cur.fetchone()[0]

    return data, int(total)


def _get_table_comment(table_name: str) -> str:
    if connection.vendor == "sqlite":
        return ""
    if connection.vendor == "postgresql":
        try:
            with connection.cursor() as cur:
                cur.execute(
                    """
SELECT COALESCE(obj_description(c.oid, 'pg_class'), '')
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = current_schema() AND c.relname = %s
LIMIT 1
""",
                    [table_name],
                )
                row = cur.fetchone()
                return row[0] if row else ""
        except Exception:
            return ""
    try:
        with connection.cursor() as cur:
            cur.execute(
                """
SELECT TABLE_COMMENT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
LIMIT 1
""",
                [table_name],
            )
            row = cur.fetchone()
            return row[0] if row else ""
    except Exception:
        return ""


def _postgres_table_page(keywords: str, limit: int, offset: int) -> tuple[list[dict], int]:
    """PostgreSQL 数据表分页（对齐 _mysql_table_page 的返回结构）。"""
    cfg_table, _, _ = _codegen_tables()

    where = "t.TABLE_SCHEMA = current_schema() AND t.TABLE_TYPE = 'BASE TABLE'"
    params: list = []
    if _table_has_column(cfg_table, "is_deleted"):
        where += " AND (c.is_deleted = 0 OR c.is_deleted IS NULL OR c.is_deleted = FALSE)"

    if keywords:
        where += " AND t.TABLE_NAME LIKE %s"
        params.append(f"%{keywords}%")

    join_sql = f"LEFT JOIN {cfg_table} c\n  ON c.table_name = t.TABLE_NAME"

    # PostgreSQL 的 pg_class 不记录表创建时间，createTime 统一返回空串
    list_sql = f"""
SELECT
  t.TABLE_NAME AS "tableName",
  COALESCE(obj_description((quote_ident(t.TABLE_SCHEMA) || '.' || quote_ident(t.TABLE_NAME))::regclass, 'pg_class'), '') AS "tableComment",
  '' AS "tableCollation",
  '' AS engine,
  '' AS "createTime",
  CASE WHEN c.table_name IS NULL THEN 0 ELSE 1 END AS "isConfigured"
FROM information_schema.TABLES t
{join_sql}
WHERE {where}
ORDER BY t.TABLE_NAME ASC
LIMIT %s OFFSET %s
"""
    list_params = params + [limit, offset]

    total_sql = f"SELECT COUNT(1) AS total FROM information_schema.TABLES t {join_sql} WHERE {where}"

    with connection.cursor() as cur:
        cur.execute(list_sql, list_params)
        rows = cur.fetchall()
        columns = [c[0] for c in cur.description]
        data = [dict(zip(columns, r)) for r in rows]

        cur.execute(total_sql, params)
        total = cur.fetchone()[0]

    return data, int(total)


def _normalize_business_name(table_name: str, business_name: str, table_comment: str) -> str:
    name = (business_name or "").strip()
    comment = (table_comment or "").strip()
    if not name or name == table_name:
        name = comment
    if name.endswith("表"):
        name = name[:-1]
    return name or table_name


def _template_root() -> Path:
    return Path(__file__).resolve().parent / "templates"


def _read_template(rel_path: str) -> str:
    root = _template_root()
    path = root / rel_path
    if not path.exists():
        raise FileNotFoundError(f"codegen 模板不存在: {path}")
    return path.read_text(encoding="utf-8")


def _resolve_frontend_template_path(template_name: str, tpl_cfg: TemplateConfig, frontend_type: str) -> str:
    if frontend_type == "js":
        if template_name == "API":
            return "frontend/js/api.js.vm"
        if template_name == "VIEW":
            return "frontend/js/index.js.vue.vm"
        return tpl_cfg.template_path
    return tpl_cfg.template_path


def _resolve_frontend_extension(template_name: str, tpl_cfg: TemplateConfig, frontend_type: str) -> str:
    if frontend_type != "js":
        return tpl_cfg.extension
    if template_name == "API":
        return ".js"
    return tpl_cfg.extension


def _resolve_scope(template_name: str) -> str:
    if template_name in ["API", "API_TYPES", "VIEW"]:
        return "frontend"
    return "backend"


def _resolve_language(file_name: str) -> str:
    suffix = Path(file_name).suffix
    return suffix[1:].lower() if suffix.startswith(".") else ""


def _render_template(
    template_name: str,
    template_path: str,
    subpackage_name: str,
    cfg: dict,
    page_type: str,
) -> str:
    tpl_path = template_path
    if template_name == "VIEW" and page_type == "crud":
        if tpl_path.endswith("frontend/js/index.js.vue.vm"):
            tpl_path = tpl_path.replace("frontend/js/index.js.vue.vm", "frontend/js/index.crud.js.vue.vm")
        elif tpl_path.endswith("frontend/ts/index.vue.vm"):
            tpl_path = tpl_path.replace("frontend/ts/index.vue.vm", "frontend/ts/index.crud.vue.vm")

    content = _read_template(tpl_path)

    ctx = {
        "packageName": cfg.get("packageName"),
        "moduleName": cfg.get("moduleName"),
        "subpackageName": subpackage_name,
        "date": _now_str(),
        "entityName": cfg.get("entityName"),
        "tableName": cfg.get("tableName"),
        "author": cfg.get("author"),
        "entityLowerCamel": to_camel_case(cfg.get("entityName") or ""),
        "entityKebab": to_kebab_case(cfg.get("entityName") or ""),
        "entityKebabPlural": to_plural_kebab(cfg.get("entityName") or ""),
        "entityUpperSnake": to_upper_snake(cfg.get("entityName") or ""),
        "permissionPrefix": _resolve_perm_prefix(cfg.get("moduleName") or "", cfg.get("entityName") or ""),
        "businessName": cfg.get("businessName"),
        "entityComment": cfg.get("businessName"),
        "fieldConfigs": cfg.get("fieldConfigs", []),
        "hasLogicDelete": _has_logic_delete(cfg.get("fieldConfigs")),
    }

    tpl = airspeed.Template(content)
    return tpl.merge(ctx)


def _get_file_name(entity_name: str, tpl_name: str, extension: str) -> str:
    if tpl_name == "DjangoModels":
        return "models.py"
    if tpl_name == "DjangoSerializers":
        return "serializers.py"
    if tpl_name == "DjangoViews":
        return "views.py"
    if tpl_name == "DjangoUrls":
        return "urls.py"
    if tpl_name == "Entity":
        return f"{entity_name}{extension}"
    if tpl_name == "MapperXml":
        return f"{entity_name}Mapper{extension}"
    if tpl_name == "API":
        return f"index{extension}"
    if tpl_name == "API_TYPES":
        return f"types{extension}"
    if tpl_name == "VIEW":
        return "index.vue"
    return f"{entity_name}{tpl_name}{extension}"


def _get_file_path(
    tpl_name: str,
    module_name: str,
    package_name: str,
    subpackage_name: str,
    entity_name: str,
    backend_app_name: str,
) -> str:
    backend = backend_app_name
    frontend = CODEGEN_FRONTEND_APP_NAME

    if tpl_name.startswith("Django"):
        parts: list[str] = [backend]
        if package_name:
            parts += [p for p in str(package_name).split(".") if p]
        if module_name:
            parts.append(module_name)
        parts.append(to_kebab_case(entity_name))
        return str(Path(*parts))
    if tpl_name == "API":
        return str(Path(frontend) / "src" / subpackage_name / module_name / to_kebab_case(entity_name))
    if tpl_name == "API_TYPES":
        return str(Path(frontend) / "src" / "api" / module_name / to_kebab_case(entity_name))
    if tpl_name == "VIEW":
        return str(Path(frontend) / "src" / subpackage_name / module_name / to_kebab_case(entity_name))

    return str(Path(backend))


def _int_bool(v) -> int:
    if isinstance(v, bool):
        return 1 if v else 0
    try:
        return 1 if int(v) == 1 else 0
    except Exception:
        return 0


def _build_field_configs_from_db(table_name: str) -> list[dict]:
    vendor = _db_vendor()
    if vendor == "sqlite":
        cols = _sqlite_columns(table_name)
    elif vendor == "postgresql":
        with connection.cursor() as cur:
            # data_type 归一化成 MySQL 风格名称，复用下游的 Java/表单类型映射
            cur.execute(
                """
SELECT
  c.column_name AS "columnName",
  CASE c.data_type
    WHEN 'character varying' THEN 'varchar'
    WHEN 'character' THEN 'char'
    WHEN 'timestamp with time zone' THEN 'timestamp'
    WHEN 'timestamp without time zone' THEN 'timestamp'
    WHEN 'time with time zone' THEN 'time'
    WHEN 'time without time zone' THEN 'time'
    WHEN 'integer' THEN 'int'
    WHEN 'boolean' THEN 'tinyint'
    WHEN 'jsonb' THEN 'json'
    WHEN 'json' THEN 'json'
    WHEN 'double precision' THEN 'double'
    WHEN 'real' THEN 'float'
    ELSE c.data_type
  END AS "columnType",
  COALESCE(col_description(t.oid, c.ordinal_position), '') AS "columnComment",
  c.is_nullable AS "isNullable",
  c.character_maximum_length AS "maxLength",
  c.ordinal_position AS "ordinalPosition"
FROM information_schema.COLUMNS c
JOIN pg_class t ON t.relname = c.table_name
JOIN pg_namespace n ON n.oid = t.relnamespace AND n.nspname = c.table_schema
WHERE c.table_schema = current_schema() AND c.table_name = %s
ORDER BY c.ordinal_position ASC
""",
                [table_name],
            )
            rows = cur.fetchall()
            columns = [c[0] for c in cur.description]
            cols = [dict(zip(columns, r)) for r in rows]
    else:
        with connection.cursor() as cur:
            cur.execute(
                """
SELECT
  COLUMN_NAME AS columnName,
  DATA_TYPE AS columnType,
  COLUMN_COMMENT AS columnComment,
  IS_NULLABLE AS isNullable,
  CHARACTER_MAXIMUM_LENGTH AS maxLength,
  ORDINAL_POSITION AS ordinalPosition
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
ORDER BY ORDINAL_POSITION ASC
""",
                [table_name],
            )
            rows = cur.fetchall()
            columns = [c[0] for c in cur.description]
            cols = [dict(zip(columns, r)) for r in rows]

    out: list[dict] = []
    for idx, col in enumerate(cols):
        java_type = _java_type_by_column_type(col.get("columnType") or "")
        is_required = 1
        if str(col.get("isNullable") or "").upper() == "YES":
            is_required = 0

        field_sort = idx + 1
        out.append(
            {
                "id": 0,
                "columnName": col.get("columnName"),
                "columnType": col.get("columnType"),
                "fieldName": to_camel_case(col.get("columnName") or ""),
                "fieldType": java_type,
                "fieldComment": col.get("columnComment") or "",
                "isShowInList": 1,
                "isShowInForm": 1,
                "isShowInQuery": 0,
                "isRequired": is_required,
                "formType": _default_form_type_by_column_type(col.get("columnType") or ""),
                "queryType": 1,
                "maxLength": col.get("maxLength"),
                "fieldSort": field_sort,
                "dictType": "",
            }
        )
    return out


def _config_to_response(cfg: dict, fields: list[dict]) -> dict:
    return {
        "id": cfg.get("id", 0),
        "tableName": cfg.get("tableName"),
        "businessName": cfg.get("businessName"),
        "moduleName": cfg.get("moduleName"),
        "packageName": cfg.get("packageName"),
        "entityName": cfg.get("entityName"),
        "author": cfg.get("author"),
        "parentMenuId": cfg.get("parentMenuId"),
        "backendAppName": CODEGEN_BACKEND_APP_NAME,
        "frontendAppName": CODEGEN_FRONTEND_APP_NAME,
        "pageType": cfg.get("pageType") or "classic",
        "removeTablePrefix": cfg.get("removeTablePrefix") or DEFAULT_REMOVE_TABLE_PREFIX,
        "fieldConfigs": fields,
    }


def _build_ai_user_prompt(cfg: dict, fields: list[dict], requirement: str) -> str:
    """构造用户提示词，附带表结构与字段清单。"""
    columns = [
        {
            "columnName": field.get("columnName"),
            "columnType": field.get("columnType"),
            "fieldComment": field.get("fieldComment"),
            "isRequired": field.get("isRequired"),
        }
        for field in fields
    ]
    return "\n".join(
        [
            f"表名：{cfg.get('tableName') or ''}",
            f"当前业务名：{cfg.get('businessName') or ''}",
            f"补充说明：{requirement.strip() or '无'}",
            "字段列表：",
            json.dumps(columns, ensure_ascii=False),
        ]
    )


def _apply_ai_field_configs(fields: list[dict], ai_fields) -> None:
    """按列名匹配回填字段配置。"""
    if not fields or not isinstance(ai_fields, list):
        return

    ai_field_map = {}
    for ai_field in ai_fields:
        if not isinstance(ai_field, dict):
            continue
        column_name = str(ai_field.get("columnName") or "").strip()
        if column_name:
            ai_field_map[column_name] = ai_field

    for field in fields:
        ai_field = ai_field_map.get(str(field.get("columnName") or ""))
        if not ai_field:
            continue

        field_comment = str(ai_field.get("fieldComment") or "").strip()
        if field_comment:
            field["fieldComment"] = field_comment
        dict_type = str(ai_field.get("dictType") or "").strip()
        if dict_type:
            field["dictType"] = dict_type

        form_type = _form_type_value(str(ai_field.get("formType") or ""))
        if form_type is not None:
            field["formType"] = form_type
        query_type = _query_type_value(str(ai_field.get("queryType") or ""))
        if query_type is not None:
            field["queryType"] = query_type

        for key in ("isRequired", "isShowInList", "isShowInForm", "isShowInQuery"):
            if isinstance(ai_field.get(key), int):
                field[key] = ai_field[key]


def _form_type_value(name: str) -> Optional[int]:
    """表单类型枚举名转存储值。"""
    values = {
        "INPUT": 1,
        "SELECT": 2,
        "RADIO": 3,
        "CHECK_BOX": 4,
        "INPUT_NUMBER": 5,
        "SWITCH": 6,
        "TEXT_AREA": 7,
        "DATE": 8,
        "DATE_TIME": 9,
        "HIDDEN": 10,
    }
    return values.get(name.strip().upper())


def _query_type_value(name: str) -> Optional[int]:
    """查询类型枚举名转存储值。"""
    values = {
        "EQ": 1,
        "LIKE": 2,
        "IN": 3,
        "BETWEEN": 4,
        "GT": 5,
        "GE": 6,
        "LT": 7,
        "LE": 8,
        "NE": 9,
        "LIKE_LEFT": 10,
    }
    return values.get(name.strip().upper())


def _get_config_dict(table_name: str) -> tuple[dict, list[dict]]:
    cfg_table, col_table, fk_col = _codegen_tables()

    config = None
    try:
        with connection.cursor() as cur:
            cur.execute(
                f"""
SELECT
  id, table_name, module_name, package_name, business_name, entity_name, author, parent_menu_id, is_deleted
FROM {cfg_table}
WHERE table_name = %s AND (is_deleted = 0 OR is_deleted = FALSE)
LIMIT 1
""",
                [table_name],
            )
            row = cur.fetchone()
            if row:
                config = {
                    "id": row[0],
                    "table_name": row[1],
                    "module_name": row[2],
                    "package_name": row[3],
                    "business_name": row[4],
                    "entity_name": row[5],
                    "author": row[6],
                    "parent_menu_id": row[7],
                }
    except Exception:
        config = None

    if config:
        table_comment = _get_table_comment(table_name)
        config["business_name"] = _normalize_business_name(
            config.get("table_name") or table_name,
            config.get("business_name") or "",
            table_comment,
        )
        extras = _get_gen_config_extra(table_name)
        cfg_id = int(config["id"])

        fields: list[dict] = []
        try:
            with connection.cursor() as cur:
                cur.execute(
                    f"""
SELECT
  id,
  column_name,
  column_type,
  field_name,
  field_type,
  field_sort,
  field_comment,
  max_length,
  is_required,
  is_show_in_list,
  is_show_in_form,
  is_show_in_query,
  query_type,
  form_type,
  dict_type
FROM {col_table}
WHERE {fk_col} = %s
ORDER BY field_sort ASC, id ASC
""",
                    [cfg_id],
                )
                for r in cur.fetchall():
                    fields.append(
                        {
                            "id": r[0],
                            "columnName": r[1] or "",
                            "columnType": r[2] or "",
                            "fieldName": r[3] or "",
                            "fieldType": r[4] or "",
                            "fieldSort": r[5],
                            "fieldComment": r[6] or "",
                            "maxLength": r[7],
                            "isRequired": 1 if int(r[8] or 0) == 1 else 0,
                            "isShowInList": 1 if int(r[9] or 0) == 1 else 0,
                            "isShowInForm": 1 if int(r[10] or 0) == 1 else 0,
                            "isShowInQuery": 1 if int(r[11] or 0) == 1 else 0,
                            "queryType": int(r[12] or 1),
                            "formType": int(r[13] or 1),
                            "dictType": r[14] or "",
                        }
                    )
        except Exception:
            fields = []

        return (
            {
                "id": cfg_id,
                "tableName": config["table_name"],
                "businessName": config["business_name"],
                "moduleName": config["module_name"] or DEFAULT_MODULE_NAME,
                "packageName": config["package_name"] or DEFAULT_PACKAGE_NAME,
                # 存量行可能没填实体名，按表名去前缀兜底，模板与权限前缀才不会落空
                "entityName": config["entity_name"] or _default_entity_name(table_name, DEFAULT_REMOVE_TABLE_PREFIX),
                "author": config["author"],
                "parentMenuId": config["parent_menu_id"],
                "pageType": extras.get("page_type") or "classic",
                "removeTablePrefix": extras.get("remove_table_prefix") or DEFAULT_REMOVE_TABLE_PREFIX,
            },
            fields,
        )

    table_comment = _get_table_comment(table_name)
    business_name = _normalize_business_name(table_name, "", table_comment)
    entity_name = _default_entity_name(table_name, DEFAULT_REMOVE_TABLE_PREFIX)

    fields = _build_field_configs_from_db(table_name)
    cfg = {
        "id": 0,
        "tableName": table_name,
        "businessName": business_name,
        "moduleName": DEFAULT_MODULE_NAME,
        "packageName": DEFAULT_PACKAGE_NAME,
        "entityName": entity_name,
        "author": DEFAULT_AUTHOR,
        "parentMenuId": None,
        "pageType": "classic",
        "removeTablePrefix": DEFAULT_REMOVE_TABLE_PREFIX,
    }
    return cfg, fields


def _build_template_field_configs(field_configs: list[dict]) -> list[dict]:
    out = []
    for f in field_configs:
        java_type = f.get("fieldType") or _java_type_by_column_type(f.get("columnType") or "")
        out.append(
            SimpleNamespace(
                columnName=f.get("columnName"),
                columnType=f.get("columnType"),
                fieldName=f.get("fieldName"),
                fieldType=java_type,
                fieldComment=f.get("fieldComment") or "",
                isShowInList=int(f.get("isShowInList") or 0),
                isShowInForm=int(f.get("isShowInForm") or 0),
                isShowInQuery=int(f.get("isShowInQuery") or 0),
                isRequired=int(f.get("isRequired") or 0),
                formType=_form_type_name(f.get("formType")),
                queryType=_query_type_name(f.get("queryType")),
                maxLength=f.get("maxLength"),
                fieldSort=f.get("fieldSort"),
                dictType=VStr(f.get("dictType") or ""),
                javaType=java_type,
                tsType=_ts_type_by_java_type(java_type),
            )
        )
    return out


def _generate_previews(table_name: str, page_type: str) -> list[dict]:
    backend_app_name = CODEGEN_BACKEND_APP_NAME
    frontend_type = "ts"
    if isinstance(page_type, dict):
        type_param = (page_type.get("type") or "ts").strip().lower()
        frontend_type = "js" if type_param == "js" else "ts"
        page_type = page_type.get("pageType") or "classic"

    cfg, fields = _get_config_dict(table_name)
    template_fields = _build_template_field_configs(fields)

    merged_cfg = {
        "tableName": cfg.get("tableName"),
        "businessName": cfg.get("businessName"),
        "moduleName": cfg.get("moduleName"),
        "packageName": cfg.get("packageName"),
        "entityName": cfg.get("entityName"),
        "author": cfg.get("author"),
        "fieldConfigs": template_fields,
    }

    template_configs = TEMPLATE_CONFIGS

    previews = []
    for tpl_name, tpl_cfg in template_configs.items():
        if frontend_type == "js" and tpl_name == "API_TYPES":
            continue

        template_path = _resolve_frontend_template_path(tpl_name, tpl_cfg, frontend_type)
        extension = _resolve_frontend_extension(tpl_name, tpl_cfg, frontend_type)
        file_name = _get_file_name(merged_cfg["entityName"], tpl_name, extension)
        file_path = _get_file_path(
            tpl_name,
            merged_cfg["moduleName"],
            merged_cfg["packageName"],
            tpl_cfg.subpackage_name,
            merged_cfg["entityName"],
            backend_app_name,
        )
        content = _render_template(tpl_name, template_path, tpl_cfg.subpackage_name, merged_cfg, page_type)
        previews.append(
            {
                "path": file_path,
                "fileName": file_name,
                "content": content,
                "scope": _resolve_scope(tpl_name),
                "language": _resolve_language(file_name),
            }
        )

    return previews


def _generate_zip(table_names: list[str], page_type: str, frontend_type: str) -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as zf:
        for table in table_names:
            for item in _generate_previews(
                table,
                {"pageType": page_type, "type": frontend_type},
            ):
                rel = str(Path(item["path"]) / item["fileName"])
                zf.writestr(rel.replace("\\", "/"), item["content"])
    return buf.getvalue()


@extend_schema(tags=["11.代码生成"])
class CodegenTablePageView(ViewSet):
    """平台-代码生成视图。"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="代码生成-表分页",
        parameters=[
            OpenApiParameter(
                name="keywords",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="关键词（表名/注释模糊匹配）",
            ),
            OpenApiParameter(
                name="pageNum",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="页码（默认 1）",
            ),
            OpenApiParameter(
                name="pageSize",
                location=OpenApiParameter.QUERY,
                required=False,
                type=int,
                description="每页记录数（默认 10，最大 100）",
            ),
        ],
        responses=page_resp(
            "CodegenTablePageResult",
            serializers.ListField(child=serializers.DictField()),
        ),
    )
    def page(self, request, *args, **kwargs):
        keywords = request.query_params.get("keywords", "")
        try:
            page_num = int(request.query_params.get("pageNum", "1"))
            page_size = int(request.query_params.get("pageSize", "10"))
        except ValueError:
            return error("页码或每页记录数格式不正确", code="A0400", status=400)

        page_num = max(page_num, 1)
        page_size = max(min(page_size, 100), 1)
        offset = (page_num - 1) * page_size

        vendor = _db_vendor()
        if vendor == "sqlite":
            names = _sqlite_table_names(keywords)
            total = len(names)
            names = names[offset : offset + page_size]

            configured = set(
                GenTable.objects.filter(table_name__in=names, is_deleted=0).values_list("table_name", flat=True)
            )

            rows = []
            for n in names:
                table_collation = ""
                charset = ""
                if table_collation and "_" in table_collation:
                    charset = table_collation.split("_", 1)[0]
                rows.append(
                    {
                        "tableName": n,
                        "tableComment": "",
                        "engine": "",
                        "tableCollation": table_collation,
                        "charset": charset,
                        "createTime": "",
                        "isConfigured": 1 if n in configured else 0,
                    }
                )
        elif vendor == "postgresql":
            rows, total = _postgres_table_page(keywords, page_size, offset)
            for r in rows:
                r["charset"] = ""
        else:
            rows, total = _mysql_table_page(keywords, page_size, offset)

            for r in rows:
                if "charset" not in r:
                    coll = (r.get("tableCollation") or "")
                    r["charset"] = coll.split("_", 1)[0] if "_" in coll else ""

        return page_success(rows, total, page_num, page_size, msg=MSG_OK, code=CODE_OK)


@extend_schema(tags=["11.代码生成"])
class CodegenConfigView(ViewSet):
    """平台-代码生成视图。"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="代码生成-配置",
        responses=resp("CodegenConfigResult", serializers.DictField(required=False)),
    )
    def retrieve(self, request, table_name: str, *args, **kwargs):
        cfg, fields = _get_config_dict(table_name)
        return success(_config_to_response(cfg, fields), msg=MSG_OK, code=CODE_OK)

    @extend_schema(
        summary="AI 填充代码生成配置",
        request=serializers.DictField(required=False),
        responses=resp("CodegenAiConfigResult", serializers.DictField(required=False)),
    )
    def ai_fill(self, request, table_name: str, *args, **kwargs):
        requirement = ""
        if isinstance(request.data, dict):
            requirement = str(request.data.get("requirement") or "")

        cfg, fields = _get_config_dict(table_name)
        content = chat_json(load_prompt("codegen/system.md"), _build_ai_user_prompt(cfg, fields, requirement))

        business_name = str(content.get("businessName") or "").strip()
        if business_name:
            cfg["businessName"] = business_name
        _apply_ai_field_configs(fields, content.get("fieldConfigs"))

        return success(_config_to_response(cfg, fields), msg=MSG_OK, code=CODE_OK)

    @extend_schema(
        summary="代码生成-保存配置",
        request=serializers.DictField(),
        responses=resp("CodegenConfigSaveResult", serializers.JSONField(required=False, allow_null=True)),
    )
    def create(self, request, table_name: str, *args, **kwargs):
        try:
            body = request.data if isinstance(request.data, dict) else json.loads(request.body.decode("utf-8"))
        except Exception:
            return error("参数错误", code="A0400", status=400)

        field_configs = body.get("fieldConfigs") or []
        if not isinstance(field_configs, list):
            return error("参数错误", code="A0400", status=400)

        remove_table_prefix = body.get("removeTablePrefix")
        page_type = body.get("pageType")

        module_name = body.get("moduleName") or DEFAULT_MODULE_NAME
        package_name = body.get("packageName") or DEFAULT_PACKAGE_NAME
        business_name = body.get("businessName") or table_name
        # 实体名兜底先去表前缀，否则 sys_article 会推导成 SysArticle，权限串跟着变成 sys:sys-article
        entity_name = body.get("entityName") or _default_entity_name(
            table_name, remove_table_prefix or DEFAULT_REMOVE_TABLE_PREFIX
        )
        author = body.get("author") or DEFAULT_AUTHOR
        parent_menu_id = body.get("parentMenuId")

        with transaction.atomic():
            cfg_table, col_table, fk_col = _codegen_tables()

            cfg_id = None
            with connection.cursor() as cur:
                cur.execute(f"SELECT id FROM {cfg_table} WHERE table_name = %s LIMIT 1", [table_name])
                row = cur.fetchone()
                if row:
                    cfg_id = int(row[0])

            now = datetime.now()

            if cfg_id is None:
                cols = [
                    "table_name",
                    "module_name",
                    "package_name",
                    "business_name",
                    "entity_name",
                    "author",
                    "parent_menu_id",
                ]
                vals = [table_name, module_name, package_name, business_name, entity_name, author, parent_menu_id]

                if _table_has_column(cfg_table, "remove_table_prefix"):
                    cols.append("remove_table_prefix")
                    vals.append(remove_table_prefix)
                if _table_has_column(cfg_table, "page_type"):
                    cols.append("page_type")
                    vals.append(page_type)
                if _table_has_column(cfg_table, "create_time"):
                    cols.append("create_time")
                    vals.append(now)
                if _table_has_column(cfg_table, "update_time"):
                    cols.append("update_time")
                    vals.append(now)
                if _table_has_column(cfg_table, "is_deleted"):
                    cols.append("is_deleted")
                    vals.append(0)

                placeholders = ",".join(["%s"] * len(cols))
                cur_sql = f"INSERT INTO {cfg_table} ({', '.join(cols)}) VALUES ({placeholders})"
                with connection.cursor() as cur:
                    cur.execute(cur_sql, vals)
                    cur.execute(f"SELECT id FROM {cfg_table} WHERE table_name = %s LIMIT 1", [table_name])
                    cfg_id = int(cur.fetchone()[0])
            else:
                sets = [
                    "module_name = %s",
                    "package_name = %s",
                    "business_name = %s",
                    "entity_name = %s",
                    "author = %s",
                    "parent_menu_id = %s",
                ]
                vals = [module_name, package_name, business_name, entity_name, author, parent_menu_id]

                if _table_has_column(cfg_table, "remove_table_prefix"):
                    sets.append("remove_table_prefix = %s")
                    vals.append(remove_table_prefix)
                if _table_has_column(cfg_table, "page_type"):
                    sets.append("page_type = %s")
                    vals.append(page_type)
                if _table_has_column(cfg_table, "update_time"):
                    sets.append("update_time = %s")
                    vals.append(now)
                if _table_has_column(cfg_table, "is_deleted"):
                    sets.append("is_deleted = %s")
                    vals.append(0)

                vals.append(cfg_id)
                with connection.cursor() as cur:
                    cur.execute(f"UPDATE {cfg_table} SET {', '.join(sets)} WHERE id = %s", vals)

            _update_gen_config_extra(table_name, remove_table_prefix, page_type)

            with connection.cursor() as cur:
                cur.execute(f"DELETE FROM {col_table} WHERE {fk_col} = %s", [cfg_id])

            for f in field_configs:
                col_cols = [fk_col, "column_name", "column_type", "field_name", "field_type", "field_sort", "field_comment", "max_length",
                            "is_required", "is_show_in_list", "is_show_in_form", "is_show_in_query", "query_type", "form_type", "dict_type"]
                col_vals = [
                    cfg_id,
                    f.get("columnName"),
                    f.get("columnType"),
                    f.get("fieldName") or "",
                    f.get("fieldType"),
                    f.get("fieldSort"),
                    f.get("fieldComment"),
                    f.get("maxLength"),
                    _int_bool(f.get("isRequired")),
                    _int_bool(f.get("isShowInList")),
                    _int_bool(f.get("isShowInForm")),
                    _int_bool(f.get("isShowInQuery")),
                    f.get("queryType"),
                    f.get("formType"),
                    f.get("dictType"),
                ]

                if _table_has_column(col_table, "create_time"):
                    col_cols.append("create_time")
                    col_vals.append(now)
                if _table_has_column(col_table, "update_time"):
                    col_cols.append("update_time")
                    col_vals.append(now)

                placeholders = ",".join(["%s"] * len(col_cols))
                with connection.cursor() as cur:
                    cur.execute(
                        f"INSERT INTO {col_table} ({', '.join(col_cols)}) VALUES ({placeholders})",
                        col_vals,
                    )

            # 选了上级菜单就同步生成页面菜单与增删改查按钮，权限前缀与生成代码的守卫同源；
            # 失败随事务回滚，不留「有配置无权限」的半成品，重试时按路由名去重
            menu_parent_id = int(parent_menu_id) if str(parent_menu_id or "").isdigit() else 0
            if menu_parent_id > 0:
                add_menu_for_codegen(
                    menu_parent_id,
                    module_name,
                    business_name,
                    entity_name,
                    _resolve_perm_prefix(module_name, entity_name),
                )

        return success(None, msg="成功", code=CODE_OK)

    @extend_schema(
        summary="代码生成-删除配置",
        responses=resp("CodegenConfigDeleteResult", serializers.JSONField(required=False, allow_null=True)),
    )
    def delete(self, request, table_name: str, *args, **kwargs):
        cfg_table, col_table, fk_col = _codegen_tables()
        cfg_id = None
        with connection.cursor() as cur:
            cur.execute(f"SELECT id FROM {cfg_table} WHERE table_name = %s AND (is_deleted = 0 OR is_deleted = FALSE) LIMIT 1", [table_name])
            row = cur.fetchone()
            if row:
                cfg_id = int(row[0])

        if not cfg_id:
            return success(None, msg=MSG_OK, code=CODE_OK)

        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(f"DELETE FROM {col_table} WHERE {fk_col} = %s", [cfg_id])

                sets = []
                vals = []
                if _table_has_column(cfg_table, "is_deleted"):
                    sets.append("is_deleted = %s")
                    vals.append(1)
                if _table_has_column(cfg_table, "update_time"):
                    sets.append("update_time = %s")
                    vals.append(datetime.now())

                if sets:
                    vals.append(cfg_id)
                    cur.execute(f"UPDATE {cfg_table} SET {', '.join(sets)} WHERE id = %s", vals)

        return success(None, msg=MSG_OK, code=CODE_OK)


@extend_schema(tags=["11.代码生成"])
class CodegenPreviewView(ViewSet):
    """平台-代码生成视图。"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="代码生成-预览",
        parameters=[
            OpenApiParameter(
                name="pageType",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="页面类型（如 classic 等；默认 classic）",
            ),
            OpenApiParameter(
                name="type",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="前端类型（ts/js；默认 ts）",
            ),
        ],
        responses=resp("CodegenPreviewResult", serializers.ListField(child=serializers.DictField())),
    )
    def retrieve(self, request, table_name: str, *args, **kwargs):
        page_type = request.query_params.get("pageType", "classic")
        frontend_type = request.query_params.get("type", "ts")
        previews = _generate_previews(
            table_name,
            {"pageType": page_type, "type": frontend_type},
        )
        return success(previews, msg=MSG_OK, code=CODE_OK)


@extend_schema(tags=["11.代码生成"])
class CodegenDownloadView(ViewSet):
    """平台-代码生成视图。"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="代码生成-下载",
        parameters=[
            OpenApiParameter(
                name="pageType",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="页面类型（如 classic 等；默认 classic）",
            ),
            OpenApiParameter(
                name="type",
                location=OpenApiParameter.QUERY,
                required=False,
                type=str,
                description="前端类型（ts/js；默认 ts）",
            ),
        ],
        responses={200: bytes},
    )
    def retrieve(self, request, table_name: str, *args, **kwargs):
        page_type = request.query_params.get("pageType", "classic")
        frontend_type = request.query_params.get("type", "ts")
        tables = [t.strip() for t in (table_name or "").split(",") if t.strip()]
        if not tables:
            return error("参数错误", code="A0400", status=400)

        data = _generate_zip(tables, page_type, frontend_type)
        resp = HttpResponse(data, content_type="application/octet-stream")
        resp["Content-Disposition"] = f'attachment; filename="{CODEGEN_DOWNLOAD_FILE_NAME}"'
        return resp
