"""用户业务逻辑。"""

import logging
import re
from io import BytesIO

import openpyxl
from django.db.models import Q
from django.utils.dateparse import parse_datetime

from apps.auth.utils.session_utils import invalidate_user_sessions
from apps.system.dept.models import Department
from apps.system.roles.models import Role
from apps.system.users.models import User
from core.exceptions.business import BusinessException
from core.permissions.data_scope import data_permission_required

_logger = logging.getLogger(__name__)


def mask_mobile(mobile: str | None) -> str | None:
    """手机号脱敏。"""
    if not mobile:
        return mobile
    m = str(mobile)
    if len(m) < 7:
        return "***"
    return f"{m[:3]}****{m[-4:]}"


def mask_email(email: str | None) -> str | None:
    """邮箱脱敏。"""
    if not email:
        return email
    e = str(email)
    if "@" not in e:
        return "***"
    name, domain = e.split("@", 1)
    name_masked = (name[:2] + "***") if len(name) >= 2 else "***"
    return f"{name_masked}@{domain}"


def build_page_query(*, keywords: str, status, dept_id, role_ids: str, create_time: str, viewable_users):
    """构建用户分页查询条件。"""
    query = Q(is_deleted=0)

    if viewable_users != "all":
        query &= Q(id__in=viewable_users)

    if keywords:
        query &= Q(username__icontains=keywords) | Q(nickname__icontains=keywords) | Q(mobile__icontains=keywords)

    if status is not None and status != "":
        query &= Q(status=int(status))

    if dept_id:
        query &= Q(dept_id=dept_id)

    if role_ids:
        role_id_list = role_ids.split(",")
        query &= Q(roles__id__in=role_id_list)

    query &= ~Q(roles__code="ROOT")

    if create_time:
        time_range = create_time.split(",")
        if len(time_range) == 2:
            start_time = parse_datetime(time_range[0])
            end_time = parse_datetime(time_range[1])
            if start_time and end_time:
                query &= Q(date_joined__gte=start_time, date_joined__lte=end_time)

    return query


def check_data_permission(*, request, operation: str, target_user_id: int) -> bool:
    """用户对象级数据权限校验。"""
    user = getattr(request, "user", None)
    return bool(data_permission_required(user, operation, target_user_id))


def delete_users(*, ids: str, current_user_id: int, current_user):
    """批量逻辑删除用户。"""
    _logger.info("delete_users start current_user_id=%s ids=%s", current_user_id, ids)
    try:
        id_list = [int(i.strip()) for i in str(ids).split(",") if i.strip()]
    except ValueError:
        _logger.warning("delete_users invalid ids format current_user_id=%s ids=%s", current_user_id, ids)
        raise BusinessException("用户 ID 格式不正确", code="A0400", status=400)

    if not id_list:
        _logger.warning("delete_users empty ids current_user_id=%s", current_user_id)
        raise BusinessException("未指定要删除的用户 ID", code="A0400", status=400)

    if current_user_id in id_list:
        _logger.warning("delete_users attempted to delete self current_user_id=%s", current_user_id)
        raise BusinessException("不能删除当前登录的用户", code="A0400", status=400)

    authorized_ids = []
    unauthorized_ids = []
    for user_id in id_list:
        has_permission = data_permission_required(current_user, "delete", user_id)
        if has_permission:
            authorized_ids.append(user_id)
        else:
            unauthorized_ids.append(user_id)

    if unauthorized_ids:
        _logger.warning(
            "delete_users forbidden current_user_id=%s unauthorized_ids=%s", current_user_id, unauthorized_ids
        )
        raise BusinessException(
            f"您没有权限删除以下用户: {','.join(map(str, unauthorized_ids))}",
            code="A0301",
            status=403,
        )

    users = User.objects.filter(id__in=authorized_ids, is_deleted=0)
    found_ids = list(users.values_list("id", flat=True))

    users.update(is_deleted=1)
    for user_id in found_ids:
        invalidate_user_sessions(user_id)
    _logger.info("delete_users success current_user_id=%s deleted_count=%s", current_user_id, len(found_ids))
    return {"deleted_count": len(found_ids)}


def build_import_template_excel_bytes():
    """构建用户导入 Excel 模板。"""
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "用户导入"

    headers = ["用户名", "昵称", "性别", "手机号", "邮箱", "角色", "部门"]
    for col_num, header in enumerate(headers, 1):
        cell = worksheet.cell(row=1, column=col_num)
        cell.value = header

    excel_file = BytesIO()
    workbook.save(excel_file)
    excel_file.seek(0)
    return excel_file.getvalue()


def import_from_excel(*, file):
    """从 Excel 导入用户。"""
    _logger.info("import_users_from_excel start")
    try:
        workbook = openpyxl.load_workbook(file, data_only=True)
        worksheet = workbook.active
    except Exception as e:
        _logger.exception("import_users_from_excel openpyxl load_workbook failed")
        raise BusinessException(f"读取 Excel 文件失败: {str(e)}", code="A0400", status=400)

    required_columns = ["用户名", "昵称", "性别", "手机号", "邮箱", "角色", "部门"]
    header_row = next(worksheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
    header_row = list(header_row or [])
    header_index = {str(name).strip(): idx for idx, name in enumerate(header_row) if name is not None}

    missing_columns = [col for col in required_columns if col not in header_index]
    if missing_columns:
        _logger.warning("import_users_from_excel missing_columns=%s", missing_columns)
        raise BusinessException(f"缺少必填列: {', '.join(missing_columns)}", code="A0400", status=400)

    def _get_cell_value(row_values, key: str):
        idx = header_index.get(key)
        if idx is None or idx >= len(row_values):
            return None
        return row_values[idx]

    def _to_opt_str(v):
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    dept_map = {}
    for d in Department.objects.all():
        dept_map[d.name] = d
        if d.code:
            dept_map[d.code] = d
    role_map = {}
    for r in Role.objects.all():
        role_map[r.name] = r
        if r.code:
            role_map[r.code] = r
    existing_usernames = set(User.objects.values_list("username", flat=True))

    valid_count = 0
    invalid_count = 0
    message_list = []

    _logger.info(
        "import_users_from_excel parsed_header columns=%s data_rows=%s",
        list(header_index.keys()),
        max((worksheet.max_row or 1) - 1, 0),
    )

    for index, row_values in enumerate(worksheet.iter_rows(min_row=2, values_only=True)):
        try:
            username = _to_opt_str(_get_cell_value(row_values, "用户名")) or ""
            nickname = _to_opt_str(_get_cell_value(row_values, "昵称")) or ""

            gender_value = _get_cell_value(row_values, "性别")
            if gender_value is None or str(gender_value).strip() == "":
                gender = 1
            else:
                gender_str = str(gender_value).strip()
                if gender_str in ["0", "保密"]:
                    gender = 0
                elif gender_str in ["1", "男"]:
                    gender = 1
                elif gender_str in ["2", "女"]:
                    gender = 2
                else:
                    try:
                        gender = int(gender_str)
                    except ValueError:
                        message_list.append(
                            f"第{index + 2}行 性别值\"{gender_str}\"不正确，应为 0(保密)/1(男)/2(女)"
                        )
                        invalid_count += 1
                        continue

            mobile = _to_opt_str(_get_cell_value(row_values, "手机号"))
            email = _to_opt_str(_get_cell_value(row_values, "邮箱"))
            role_names = _to_opt_str(_get_cell_value(row_values, "角色"))
            dept_name = _to_opt_str(_get_cell_value(row_values, "部门"))

            if not username or not nickname:
                _logger.warning("import_users_from_excel invalid_row row=%s reason=empty_username_or_nickname", index + 2)
                message_list.append(f"第{index + 2}行 用户名和昵称不能为空")
                invalid_count += 1
                continue

            if username in existing_usernames:
                _logger.warning("import_users_from_excel invalid_row row=%s reason=username_exists", index + 2)
                message_list.append(f"第{index + 2}行 用户名\"{username}\"已存在")
                invalid_count += 1
                continue

            if mobile and not re.match(r"^1[3-9]\d{9}$", mobile):
                _logger.warning(
                    "import_users_from_excel invalid_row row=%s reason=invalid_mobile mobile=%s",
                    index + 2,
                    mask_mobile(mobile),
                )
                message_list.append(f"第{index + 2}行 手机号\"{mobile}\"格式不正确")
                invalid_count += 1
                continue

            if email and not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
                _logger.warning(
                    "import_users_from_excel invalid_row row=%s reason=invalid_email email=%s",
                    index + 2,
                    mask_email(email),
                )
                message_list.append(f"第{index + 2}行 邮箱\"{email}\"格式不正确")
                invalid_count += 1
                continue

            if gender not in [0, 1, 2]:
                message_list.append(f"第{index + 2}行 性别值\"{gender}\"不正确，应为 0(保密)/1(男)/2(女)")
                invalid_count += 1
                continue

            dept = None
            if dept_name:
                dept = dept_map.get(dept_name)
                if dept is None:
                    message_list.append(f"第{index + 2}行 部门\"{dept_name}\"不存在")
                    invalid_count += 1
                    continue

            roles = []
            if role_names:
                role_name_list = [name.strip() for name in role_names.split(",") if name.strip()]
                missing_roles = [name for name in role_name_list if name not in role_map]
                if missing_roles:
                    for role_name in missing_roles:
                        message_list.append(f"第{index + 2}行 角色\"{role_name}\"不存在")
                    invalid_count += 1
                    continue
                roles = [role_map[name] for name in role_name_list]

            user = User.objects.create(
                username=username,
                nickname=nickname,
                gender=gender,
                mobile=mobile,
                email=email,
                dept=dept,
                status=1,
                is_deleted=0,
            )
            user.set_password("123456")
            user.save()

            if roles:
                user.roles.set(roles)

            existing_usernames.add(username)
            valid_count += 1
        except Exception as e:
            _logger.exception("import_users_from_excel unexpected_row_error row=%s", index + 2)
            message_list.append(f"第{index + 2}行 导入失败 - {str(e)}")
            invalid_count += 1

    return {
        "data": {
            "validCount": valid_count,
            "invalidCount": invalid_count,
            "messageList": message_list,
        },
        "msg": f"导入完成，成功导入{valid_count}条数据，失败{invalid_count}条",
    }


def export_to_excel_bytes(*, keywords: str, status, dept_id, role_ids: str, create_time: str, field: str, direction: str):
    """导出用户列表为 Excel。"""
    query = build_page_query(
        keywords=keywords,
        status=status,
        dept_id=dept_id,
        role_ids=role_ids,
        create_time=create_time,
        viewable_users="all",
    )

    order_field = field if (direction or "DESC").upper() == "ASC" else f"-{field}"
    users = User.objects.filter(query).distinct().order_by(order_field)

    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "用户列表"

    headers = ["用户名", "昵称", "部门", "性别", "手机号", "邮箱", "创建时间"]
    for col_num, header in enumerate(headers, 1):
        cell = worksheet.cell(row=1, column=col_num)
        cell.value = header

    for row_num, user in enumerate(users, 2):
        dept_name = user.dept.name if user.dept else ""
        gender_text = ""
        if user.gender == 0:
            gender_text = "保密"
        elif user.gender == 1:
            gender_text = "男"
        elif user.gender == 2:
            gender_text = "女"
        create_time_str = user.date_joined.strftime("%Y/%m/%d %H:%M:%S") if user.date_joined else ""

        worksheet.cell(row=row_num, column=1, value=user.username)
        worksheet.cell(row=row_num, column=2, value=user.nickname)
        worksheet.cell(row=row_num, column=3, value=dept_name)
        worksheet.cell(row=row_num, column=4, value=gender_text)
        worksheet.cell(row=row_num, column=5, value=user.mobile)
        worksheet.cell(row=row_num, column=6, value=user.email)
        worksheet.cell(row=row_num, column=7, value=create_time_str)

    for col in worksheet.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))
        adjusted_width = max_length + 2
        worksheet.column_dimensions[column].width = adjusted_width

    excel_file = BytesIO()
    workbook.save(excel_file)
    excel_file.seek(0)
    return excel_file.getvalue()
