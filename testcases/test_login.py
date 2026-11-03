import pytest
import allure
from common.request import ApiClient
from common.response import assert_fail, assert_success
from config.settings import settings


pytestmark = [pytest.mark.integration, pytest.mark.smoke]

@allure.epic("认证与会话")
@allure.feature("登录认证")
@allure.severity(allure.severity_level.BLOCKER)
class TestLogin:
    def test_admin_login_success(self):
        """LOGIN-001：管理员正确账号密码登录成功。"""
        response = ApiClient().post("/api/user/login", json={
            "userName": settings.admin_user,
            "password": settings.admin_password,
            "remember": False,
        })
        assert_success(response, "管理员登录")
        assert response.get("response", {}).get("userName") == settings.admin_user

    def test_student_login_success(self):
        """LOGIN-002：学生正确账号密码登录成功。"""
        response = ApiClient().post(
            "/api/user/login",
            json={"userName": settings.student_user, "password": settings.student_password, "remember": False},
        )
        assert_success(response, "学生登录")

    def test_login_wrong_password(self):
        response = ApiClient().post(
            "/api/user/login",
            json={"userName": settings.admin_user, "password": "wrong_password", "remember": False},
        )
        assert_fail(response, expected_code=402, expected_message="用户名或密码错误")

    def test_login_empty_username(self):
        """LOGIN-004：用户名为空应被拦截。"""
        resp = ApiClient().post("/api/user/login", json={
            "userName": "", "password": "123456", "remember": False
        })
        assert resp.get("code") != 1, f"空用户名竟登录成功: {resp}"

    def test_login_empty_password(self):
        """LOGIN-005：密码为空应被拦截。"""
        resp = ApiClient().post("/api/user/login", json={
            "userName": "admin", "password": "", "remember": False
        })
        assert resp.get("code") != 1, f"空密码竟登录成功: {resp}"

    def test_logout_invalidates_session(self):
        """LOGIN-006：退出登录后，原会话再访问受保护接口应失效。"""
        client = ApiClient()
        client.login("admin")
        # 退出前能访问管理端
        ok = client.post("/api/admin/education/subject/list", json={})
        assert_success(ok, "退出前访问管理端")
        # 退出
        client.post("/api/user/logout", json={})
        # 退出后再访问应被拦截（401）
        after = client.post("/api/admin/education/subject/list", json={})
        assert after.get("code") == 401, f"退出后会话未失效: code={after.get('code')} {after}"

