"""登录边界与异常矩阵：禁用账号、不存在用户、SQL 注入、超长用户名。"""
from common.utils import unique_suffix
import time

import allure
import pytest

from common.request import ApiClient
from common.response import assert_fail, assert_success
from config.settings import settings


def _create_student(admin: ApiClient, name: str, user_level: int = 1) -> int:
    """建一个学生，返回 user_id。role=1 是学生。"""
    resp = admin.post("/api/admin/user/edit", json={
        "id": None, "userName": name, "password": settings.student_password,
        "realName": f"自动化_{name}", "role": 1, "userLevel": user_level,
        "status": 1,
    })
    assert_success(resp, f"建学生 {name}")
    return resp["response"]["id"]


def _delete_student(admin: ApiClient, user_id: int) -> None:
    try:
        admin.post(f"/api/admin/user/delete/{user_id}")
    except Exception:
        pass


@allure.epic("学生端考试")
@allure.feature("登录认证")
class TestLoginEdge:

    @allure.story("禁用账号")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_disabled_user_cannot_login(self, admin_client: ApiClient):
        """LOGIN-007：建学生→禁用→登录应被拒，提示'用户被禁用'。"""
        ts = unique_suffix()
        stu_name = f"自动化_disabled_{ts}"
        uid = _create_student(admin_client, stu_name)
        try:
            # 禁用：changeStatus 在 Enable(1)/Disable(2) 之间切换
            resp = admin_client.post(f"/api/admin/user/changeStatus/{uid}", json={})
            assert_success(resp, "禁用学生")
            assert resp["response"] == 2, f"禁用后状态应为2，实际={resp['response']}"

            # 被禁用的账号登录
            login = ApiClient().post("/api/user/login", json={
                "userName": stu_name, "password": settings.student_password, "remember": False
            })
            assert_fail(login, expected_code=402, expected_message="禁用")
        finally:
            _delete_student(admin_client, uid)

    @allure.story("不存在的用户")
    def test_login_nonexistent_user(self):
        resp = ApiClient().post("/api/user/login", json={
            "userName": f"自动化_no_such_user_{unique_suffix()}",
            "password": "whatever", "remember": False
        })
        assert_fail(resp, expected_code=402)

    @allure.story("SQL 注入尝试")
    @allure.severity(allure.severity_level.NORMAL)
    def test_login_sql_injection(self):
        """经典注入串应被当作普通用户名处理，不能登录成功。"""
        resp = ApiClient().post("/api/user/login", json={
            "userName": "' or 1=1 --",
            "password": "' or 1=1 --",
            "remember": False
        })
        assert resp.get("code") != 1, f"SQL 注入竟登录成功: {resp}"
        assert resp.get("code") == 402, f"注入应返回402，实际={resp.get('code')}"

    @allure.story("超长用户名")
    def test_login_extremely_long_username(self):
        """1000 字符的用户名不应导致 500，应被拒绝。"""
        resp = ApiClient().post("/api/user/login", json={
            "userName": "a" * 1000,
            "password": "123456", "remember": False
        })
        assert resp.get("code") != 1, f"超长用户名竟登录成功: {resp}"
        # 不应是 500
        assert resp.get("code") != 500, f"超长用户名导致服务器错误: {resp}"
