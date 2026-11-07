"""动态表单业务：规则校验、发布快照、渲染、访问菜单生成、AI 生成。"""
import json
import logging

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from django_redis import get_redis_connection

from apps.system.form.models import FormData, FormDefinition, FormSnapshot
from apps.system.menus.models import Menu
from apps.system.models import RoleMenu
from core.ai import chat, load_prompt
from core.exceptions.business import BusinessException

logger = logging.getLogger(__name__)

STATUS_DRAFT = 0
STATUS_PUBLISHED = 1
STATUS_DISABLED = -1
DEFAULT_CATALOG_NAME = "表单中心"
FORM_ADMIN_CATALOG_NAME = "动态表单"
PUBLIC_SUBMIT_LIMIT = 10
RENDER_CACHE_TTL = 1800
SYSTEM_PROMPT_PATH = "form/system.md"


def to_camel(name):
    """下划线命名转驼峰。"""
    head, *rest = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def camelize(data):
    """字典键递归转驼峰，供出参统一使用。"""
    if isinstance(data, dict):
        return {to_camel(key): camelize(value) for key, value in data.items()}
    if isinstance(data, list):
        return [camelize(item) for item in data]
    return data


def bad(message, code="A0400"):
    return BusinessException(message, code=code)


# --------------------------------------------------------------------------- 规则校验

def validate_rule(form_json):
    """校验表单规则结构，返回原始 JSON 文本。"""
    rules = json.loads(form_json) if isinstance(form_json, str) else form_json
    if not isinstance(rules, list) or not rules:
        raise bad("表单规则格式非法：应为非空数组")
    _check_nodes(rules)
    return json.dumps(rules, ensure_ascii=False)


def _check_nodes(nodes):
    for node in nodes:
        if not isinstance(node, dict):
            raise bad("表单规则格式非法：节点必须为对象")
        if not isinstance(node.get("type"), str):
            raise bad("表单规则格式非法：节点缺少 type")
        children = node.get("children") or []
        if children:
            _check_nodes(children)
        elif not isinstance(node.get("field"), str):
            raise bad("表单规则格式非法：字段节点缺少 field")


def validate_and_filter(form_json, data):
    """按规则白名单过滤表单数据并逐字段校验必填与类型。"""
    rules = form_json if isinstance(form_json, list) else json.loads(form_json or "[]")
    if not isinstance(rules, list):
        raise bad("表单规则格式非法")

    source = data if isinstance(data, dict) else {}
    filtered = {}
    errors = []
    _walk(rules, source, filtered, errors)
    if errors:
        raise bad("；".join(errors))
    return filtered


def _walk(nodes, data, filtered, errors):
    for node in nodes:
        if not isinstance(node, dict):
            continue

        field = node.get("field")
        if isinstance(field, str) and field:
            # 字段白名单：规则未声明的 field 直接丢弃
            if field in data:
                filtered[field] = data[field]
            _validate_field(node, field, data, errors)

        children = node.get("children") or []
        if children:
            _walk(children, data, filtered, errors)


def _validate_field(rule, field, data, errors):
    validates = rule.get("validate") or []
    title = rule.get("title") or field
    value = data.get(field)
    empty = value is None or (isinstance(value, str) and not value.strip()) or (
        isinstance(value, list) and not value
    )

    for item in validates:
        if not isinstance(item, dict):
            continue
        if item.get("required") is True and empty:
            errors.append(item.get("message") or f"「{title}」不能为空")
        if not empty and item.get("type"):
            if not _check_type(item["type"], value):
                errors.append(f"「{title}」数据类型非法")


def _check_type(kind, value):
    if kind in ("number", "integer", "float"):
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return True
        return isinstance(value, str) and value.strip().replace(".", "", 1).isdigit()
    if kind == "array":
        return isinstance(value, list)
    return True


# --------------------------------------------------------------------------- 表单定义

def find_definition(form_id):
    item = FormDefinition.objects.filter(id=form_id, is_deleted=0).first()
    if not item:
        raise bad("表单不存在", code="A0404")
    return item


def find_by_key(form_key):
    item = FormDefinition.objects.filter(form_key=form_key, is_deleted=0).first()
    if not item:
        raise bad("表单不存在", code="A0404")
    return item


def definition_page(keywords=None, status=None, category=None, page_num=1, page_size=10):
    queryset = FormDefinition.objects.filter(is_deleted=0)
    if keywords:
        queryset = queryset.filter(
            Q(form_name__icontains=keywords) | Q(form_key__icontains=keywords)
        )
    if status is not None and str(status) != "":
        queryset = queryset.filter(status=int(status))
    if category:
        queryset = queryset.filter(category=category)

    total = queryset.count()
    start = max(page_num - 1, 0) * page_size
    rows = queryset.order_by("-create_time")[start:start + page_size]

    items = [{
        "id": str(row.id),
        "formKey": row.form_key,
        "formName": row.form_name,
        "description": row.description,
        "status": row.status,
        "version": row.version,
        "isPublic": row.is_public,
        "category": row.category,
        "createTime": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else None,
    } for row in rows]
    return {"list": items, "total": total}


def definition_form(form_id):
    item = find_definition(form_id)
    return {
        "id": str(item.id),
        "formKey": item.form_key,
        "formName": item.form_name,
        "description": item.description,
        "formJson": item.form_json,
        "optionsJson": item.options_json,
        "isPublic": item.is_public,
        "category": item.category,
    }


def create_definition(validated):
    form_key = (validated.get("formKey") or "").strip()
    if FormDefinition.objects.filter(form_key=form_key, is_deleted=0).exists():
        raise bad("表单标识已存在")

    now = timezone.now()
    return FormDefinition.objects.create(
        form_key=form_key,
        form_name=(validated.get("formName") or "").strip(),
        description=validated.get("description"),
        form_json=validated.get("formJson") or [],
        options_json=validated.get("optionsJson"),
        is_public=validated.get("isPublic") or 0,
        category=validated.get("category") or "normal",
        status=STATUS_DRAFT,
        version=1,
        create_time=now,
        update_time=now,
    )


def update_definition(form_id, validated):
    item = find_definition(form_id)
    form_key = (validated.get("formKey") or "").strip()
    if form_key and form_key != item.form_key:
        raise bad("表单标识创建后不可修改")

    fields = ["update_time"]
    item.form_name = (validated.get("formName") or item.form_name).strip()
    item.description = validated.get("description", item.description)
    if validated.get("formJson") is not None:
        item.form_json = validated["formJson"]
    if "optionsJson" in validated:
        item.options_json = validated.get("optionsJson")
    if validated.get("isPublic") is not None:
        item.is_public = validated["isPublic"]
    if item.status == STATUS_DRAFT and validated.get("category"):
        item.category = validated["category"]
    item.update_time = timezone.now()
    item.save()

    # 已发布表单规则变更后清渲染缓存，保证渲染端即时生效
    if item.status == STATUS_PUBLISHED:
        evict_render_cache(item.form_key)
    return item


def delete_definitions(ids):
    id_list = _parse_ids(ids)
    if not id_list:
        raise bad("删除的表单数据为空")

    forms = list(FormDefinition.objects.filter(id__in=id_list, is_deleted=0))
    for form in forms:
        if form.menu_id:
            Menu.objects.filter(id=form.menu_id).delete()
            RoleMenu.objects.filter(menu_id=form.menu_id).delete()

    now = timezone.now()
    FormDefinition.objects.filter(id__in=id_list).update(is_deleted=1, update_time=now)
    FormData.objects.filter(form_id__in=id_list).update(is_deleted=1, update_time=now)
    FormSnapshot.objects.filter(form_id__in=id_list).update(is_deleted=1, update_time=now)

    for form in forms:
        if form.status == STATUS_PUBLISHED:
            evict_render_cache(form.form_key)


def publish_definition(form_id):
    item = find_definition(form_id)
    FormDefinition.objects.filter(id=form_id).update(
        status=STATUS_PUBLISHED, version=item.version + 1, update_time=timezone.now()
    )

    published = find_definition(form_id)
    # 固化版本快照：数据回显按提交时版本加载，防止规则变更导致历史数据漂移
    now = timezone.now()
    FormSnapshot.objects.create(
        form_id=form_id,
        version=published.version,
        form_json=published.form_json,
        options_json=published.options_json,
        create_time=now,
        update_time=now,
    )
    evict_render_cache(published.form_key)
    return published


def disable_definition(form_id):
    find_definition(form_id)
    FormDefinition.objects.filter(id=form_id).update(
        status=STATUS_DISABLED, update_time=timezone.now()
    )


def render_cache_key(form_key):
    return f"form:render:{form_key}"


def evict_render_cache(form_key):
    cache.delete(render_cache_key(form_key))


def render(form_key):
    """已发布表单的渲染规则（Redis 缓存兜底 30 分钟）。"""
    cached = cache.get(render_cache_key(form_key))
    if cached:
        return cached

    item = FormDefinition.objects.filter(
        form_key=form_key, status=STATUS_PUBLISHED, is_deleted=0
    ).first()
    if not item:
        raise bad("表单不存在或未发布", code="A0404")

    data = _render_payload(item)
    cache.set(render_cache_key(form_key), data, RENDER_CACHE_TTL)
    return data


def public_render(form_key):
    """公开表单渲染规则：直查库不走缓存，避免命中缓存绕过 is_public 校验。"""
    item = FormDefinition.objects.filter(
        form_key=form_key, status=STATUS_PUBLISHED, is_public=1, is_deleted=0
    ).first()
    if not item:
        raise bad("表单不存在或未开放公开访问", code="A0404")
    return _render_payload(item)


def _render_payload(item):
    return {
        "formKey": item.form_key,
        "formName": item.form_name,
        "version": item.version,
        "formJson": item.form_json,
        "optionsJson": item.options_json,
    }


def workflow_options():
    items = FormDefinition.objects.filter(
        category="workflow", status=STATUS_PUBLISHED, is_deleted=0
    ).order_by("create_time")
    return [{"value": item.form_key, "label": item.form_name} for item in items]


# --------------------------------------------------------------------------- 访问菜单

def get_menu(form_id):
    form = find_definition(form_id)
    if not form.menu_id:
        return None

    menu = Menu.objects.filter(id=form.menu_id).first()
    if not menu:
        return None

    role_ids = list(RoleMenu.objects.filter(menu_id=menu.id).values_list("role_id", flat=True))
    return {
        "menuId": str(menu.id),
        "menuName": menu.name,
        "parentId": str(menu.parent_id),
        "roleIds": [str(role_id) for role_id in role_ids],
    }


def save_menu(form_id, validated):
    form = find_definition(form_id)
    parent_id = validated.get("parentId")
    if parent_id:
        parent = Menu.objects.filter(id=parent_id).first()
        if not parent:
            raise bad("上级菜单不存在", code="A0404")
        if parent.type != "C":
            raise bad("上级菜单必须为目录类型")
    else:
        parent = _ensure_default_catalog()

    route_name = "FormRender" + _to_upper_camel(form.form_key)
    now = timezone.now()
    tree_path = _catalog_tree_path(parent)

    # 已生成过时走更新语义（幂等）
    if form.menu_id and Menu.objects.filter(id=form.menu_id).exists():
        Menu.objects.filter(id=form.menu_id).update(
            parent_id=parent.id,
            name=validated.get("menuName").strip(),
            route_name=route_name,
            route_path=form.form_key,
            component="dynamic-form/render",
            params={"formKey": form.form_key},
            tree_path=tree_path,
            update_time=now,
        )
        menu_id = form.menu_id
    else:
        menu = Menu.objects.create(
            parent_id=parent.id,
            name=validated.get("menuName").strip(),
            type="M",
            route_name=route_name,
            route_path=form.form_key,
            component="dynamic-form/render",
            params={"formKey": form.form_key},
            visible=1,
            sort=1,
            keep_alive=0,
            tree_path=tree_path,
            create_time=now,
            update_time=now,
        )
        menu_id = menu.id

    # 回写 menu_id：下次发布走更新语义，防重复生成菜单
    FormDefinition.objects.filter(id=form_id).update(menu_id=menu_id, update_time=now)

    role_ids = validated.get("roleIds") or []
    if role_ids:
        _assign_menu_to_roles(menu_id, role_ids)


def _ensure_default_catalog():
    """确保默认挂载目录"表单中心"存在，不存在则创建。"""
    catalog = Menu.objects.filter(name=DEFAULT_CATALOG_NAME, type="C").first()
    if catalog:
        return catalog

    admin_catalog = Menu.objects.filter(
        parent_id=0, name=FORM_ADMIN_CATALOG_NAME, type="C"
    ).first()
    now = timezone.now()
    if admin_catalog:
        parent_id = admin_catalog.id
        tree_path = f"{admin_catalog.tree_path},{admin_catalog.id}" if admin_catalog.tree_path else str(admin_catalog.id)
        route_path = "center"
    else:
        parent_id = 0
        tree_path = "0"
        route_path = "/form-center"

    return Menu.objects.create(
        parent_id=parent_id,
        name=DEFAULT_CATALOG_NAME,
        type="C",
        route_path=route_path,
        component="Layout",
        visible=1,
        sort=5,
        icon="el-icon-EditPen",
        tree_path=tree_path,
        create_time=now,
        update_time=now,
    )


def _catalog_tree_path(parent):
    return f"{parent.tree_path},{parent.id}" if parent.tree_path else str(parent.id)


def _assign_menu_to_roles(menu_id, role_ids):
    menu = Menu.objects.filter(id=menu_id).first()
    if not menu:
        return

    # 授权集合 = 菜单本身 + tree_path 祖先目录（根节点 0 排除）
    menu_ids = {menu_id}
    for part in (menu.tree_path or "").split(","):
        part = part.strip()
        if part and part != "0":
            menu_ids.add(int(part))

    existing = set(
        RoleMenu.objects.filter(menu_id__in=menu_ids, role_id__in=role_ids)
        .values_list("role_id", "menu_id")
    )
    for role_id in role_ids:
        for grant_id in menu_ids:
            if (role_id, grant_id) not in existing:
                RoleMenu.objects.create(role_id=role_id, menu_id=grant_id)


def _to_upper_camel(value):
    return "".join(part[:1].upper() + part[1:] for part in value.split("_") if part)


# --------------------------------------------------------------------------- 表单数据

def save_data(form_key, data, user_id=None):
    form = find_by_key(form_key)
    if form.status != STATUS_PUBLISHED:
        raise bad("表单未发布或已停用")
    return _persist(form, data, user_id)


def save_public_data(form_key, data, ip):
    form = find_by_key(form_key)
    if form.status != STATUS_PUBLISHED or form.is_public != 1:
        raise bad("表单不存在或未开放公开访问", code="A0404")

    if not _check_public_submit_limit(form_key, ip):
        raise bad("提交过于频繁，请稍后再试")

    logger.info("公开表单匿名提交 formKey=%s ip=%s", form_key, ip)
    return _persist(form, data, None)


def _persist(form, data, user_id):
    filtered = validate_and_filter(form.form_json, data)
    now = timezone.now()
    FormData.objects.create(
        form_id=form.id,
        form_version=form.version,
        data_json=filtered,
        create_by=user_id,
        create_time=now,
        update_time=now,
    )


def _check_public_submit_limit(form_key, ip):
    """公开表单按 formKey + IP 限流（固定窗口计数，Redis 异常时放行）。"""
    key = f"form:public:submit:{form_key}:{ip}"
    try:
        conn = get_redis_connection("default")
        count = conn.incr(key)
        if count == 1:
            conn.expire(key, 60)
        return count <= PUBLIC_SUBMIT_LIMIT
    except Exception as exc:  # noqa: BLE001 Redis 异常不阻断业务
        logger.warning("公开表单限流 Redis 异常，放行 formKey=%s: %s", form_key, exc)
        return True


def data_page(form_key, page_num, page_size):
    form = find_by_key(form_key)
    queryset = FormData.objects.filter(form_id=form.id, is_deleted=0).order_by("-create_time")

    total = queryset.count()
    start = max(page_num - 1, 0) * page_size
    rows = queryset[start:start + page_size]

    user_ids = [row.create_by for row in rows if row.create_by]
    nickname_map = {}
    if user_ids:
        from apps.system.users.models import User

        nickname_map = {
            user.id: user.nickname for user in User.objects.filter(id__in=user_ids)
        }

    items = []
    for row in rows:
        items.append({
            "id": str(row.id),
            "formVersion": row.form_version,
            "dataJson": row.data_json,
            "createBy": str(row.create_by) if row.create_by else None,
            "createByName": nickname_map.get(row.create_by),
            "createTime": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else None,
        })
    return {"list": items, "total": total}


def data_detail(data_id):
    row = FormData.objects.filter(id=data_id, is_deleted=0).first()
    if not row:
        raise bad("表单数据不存在", code="A0404")

    # 命中版本快照用快照规则，否则回退当前定义（兼容快照表启用前提交的历史数据）
    snapshot = FormSnapshot.objects.filter(
        form_id=row.form_id, version=row.form_version, is_deleted=0
    ).first()
    if snapshot:
        form_json, options_json = snapshot.form_json, snapshot.options_json
    else:
        form = FormDefinition.objects.filter(id=row.form_id).first()
        form_json = form.form_json if form else None
        options_json = form.options_json if form else None

    return {
        "id": str(row.id),
        "formVersion": row.form_version,
        "dataJson": row.data_json,
        "formJson": form_json,
        "optionsJson": options_json,
        "createBy": str(row.create_by) if row.create_by else None,
        "createTime": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else None,
    }


def delete_data(ids):
    id_list = _parse_ids(ids)
    if not id_list:
        raise bad("删除的表单数据为空")
    FormData.objects.filter(id__in=id_list, is_deleted=0).update(
        is_deleted=1, update_time=timezone.now()
    )


def _parse_ids(ids):
    result = []
    for part in str(ids or "").split(","):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return result


# --------------------------------------------------------------------------- AI

def ai_generate_rule(description):
    """用 AI 把需求描述转成 form-create 规则，产出经结构校验后才返回。"""
    content = chat(load_prompt(SYSTEM_PROMPT_PATH), f"需求描述：\n{description}")
    return validate_rule(content)
