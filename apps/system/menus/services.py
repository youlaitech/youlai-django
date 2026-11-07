"""菜单服务：写入规则（层级校验、树路径、按钮权限）、代码生成建菜单、AI 辅助推断。"""
from apps.system.menus.models import Menu
from core.ai import chat_json, load_prompt
from core.naming import to_kebab_case
from django.db.models import Max
from django.utils import timezone
from rest_framework import serializers

SYSTEM_PROMPT_PATH = "menu/system.md"
# 同级菜单取样条数，样本只用于让模型沿用既有命名风格
SIBLING_SAMPLE_LIMIT = 10
MENU_TYPE_LABELS = {"C": "目录", "M": "菜单", "E": "外链", "B": "按钮"}


def ai_fill_menu(name, menu_type=None, parent_id=None):
    """推断菜单配置，命名风格参照同级菜单。"""
    content = chat_json(load_prompt(SYSTEM_PROMPT_PATH), _build_user_prompt(name, menu_type, parent_id))
    icon_keywords = content.get("iconKeywords")
    return {
        "routePath": content.get("routePath") or None,
        "perm": content.get("perm") or None,
        "iconKeywords": [str(item) for item in icon_keywords] if isinstance(icon_keywords, list) else [],
    }


def _build_user_prompt(name, menu_type, parent_id):
    """构造用户提示词，附带同级菜单样本供模型沿用既有命名风格。"""
    parent_id = int(parent_id) if parent_id else 0
    parent = Menu.objects.filter(id=parent_id).first() if parent_id else None

    text = [
        f"菜单名称：{name}",
        f"菜单类型：{menu_type_label(menu_type)}",
        f"上级菜单：{parent.name if parent else '顶级'}",
        "同级菜单示例：",
    ]

    siblings = Menu.objects.filter(parent_id=parent_id).order_by("sort")[:SIBLING_SAMPLE_LIMIT]
    if not siblings:
        text.append("（无）")
    else:
        for menu in siblings:
            # 示例路径只展示当前这一级的路径片段
            route_path = (menu.route_path or "").lstrip("/")
            text.append(
                f"- {menu.name}（类型 {menu_type_label(menu.type)}，"
                f"路径片段 {route_path or '无'}，权限 {menu.perm or '无'}）"
            )
    return "\n".join(text) + "\n"


def menu_type_label(menu_type):
    """菜单类型取中文名称，无匹配时沿用原值。"""
    if not menu_type:
        return "未指定"
    return MENU_TYPE_LABELS.get(menu_type, menu_type)


def validate_menu_parent(menu_type, parent_id, current_parent_id=None):
    """校验上级菜单层级：按钮只能挂在菜单下，其他类型只能挂在顶级或目录下；返回上级菜单供 tree_path 复用

    current_parent_id 为菜单当前父级，与目标父级一致时跳过校验，
    让历史遗留的非法层级仍可编辑其他字段。
    """
    if current_parent_id is not None and str(current_parent_id) == str(parent_id):
        return None

    if not parent_id or str(parent_id) == '0':
        if menu_type == 'B':
            raise serializers.ValidationError({"parentId": "按钮权限只能挂在菜单下"})
        return None

    parent = Menu.objects.filter(id=parent_id).first()
    if parent is None:
        raise serializers.ValidationError({"parentId": "上级菜单不存在"})

    parent_is_menu = parent.type == 'M'
    if menu_type == 'B' and not parent_is_menu:
        raise serializers.ValidationError({"parentId": "按钮权限只能挂在菜单下"})
    if menu_type != 'B' and parent_is_menu:
        raise serializers.ValidationError({"parentId": "菜单下只能挂按钮权限"})
    return parent


def menu_tree_path_of(parent):
    """子节点的父节点ID路径（含父不含己），如顶级目录下的菜单得到 0,1。"""
    return f"{parent.tree_path},{parent.id}" if parent.tree_path else str(parent.id)


def resolve_next_sort(parent_id):
    """同级菜单的最大排序 + 1"""
    max_sort = Menu.objects.filter(parent_id=parent_id).aggregate(Max('sort'))['sort__max']
    return 1 if max_sort is None else max_sort + 1


def create_crud_buttons(menu, perm_prefix):
    """生成增删改查按钮权限"""
    names = ["查询", "新增", "修改", "删除"]
    actions = ["list", "create", "update", "delete"]
    # 按钮的后代路径 = 所属菜单的祖先路径 + 所属菜单ID，删除菜单时据此级联
    button_tree_path = menu_tree_path_of(menu)
    now = timezone.now()

    for index, (name, action) in enumerate(zip(names, actions)):
        Menu.objects.create(
            parent_id=menu.id,
            type="B",
            name=name,
            perm=f"{perm_prefix}:{action}",
            sort=index + 1,
            visible=1,
            tree_path=button_tree_path,
            create_time=now,
        )


def add_menu_for_codegen(parent_menu_id, module_name, business_name, entity_name, perm_prefix):
    """代码生成保存配置时创建页面菜单与增删改查按钮；按路由名去重，重复保存不再挂出多份菜单。"""
    if Menu.objects.filter(route_name=entity_name).exists():
        return

    validate_menu_parent('M', parent_menu_id)
    parent = Menu.objects.get(id=parent_menu_id)
    entity_kebab = to_kebab_case(entity_name)

    menu = Menu.objects.create(
        parent_id=parent_menu_id,
        tree_path=menu_tree_path_of(parent),
        name=business_name,
        type='M',
        route_name=entity_name,
        route_path=entity_kebab,
        component=f"{module_name}/{entity_kebab}/index",
        keep_alive=1,
        visible=1,
        sort=resolve_next_sort(parent_menu_id),
        create_time=timezone.now(),
    )
    create_crud_buttons(menu, perm_prefix)
