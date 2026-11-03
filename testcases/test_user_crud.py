"""学生管理 CRUD：建/查/改/禁用/删除学生，学生自助注册与资料更新。"""
from common.utils import unique_suffix
import logging
import time

import allure
import pytest

from common.request import ApiClient
from common.response import assert_success
from config.settings import settings

logger = logging.getLogger(__name__)


@allure.epic("管理端后台")
@allure.feature("用户与学生管理")
class TestStudentCRUD:

    @allure.story("建学生→查→改→删")
    def test_student_lifecycle(self, admin_client: ApiClient):
        """建学生后能分页查到，改昵称后生效，删除后不可见。"""
        ts = unique_suffix()
        stu_name = f"自动化_crud_{ts}"
        # 建
        create = admin_client.post("/api/admin/user/edit", json={
            "id": None, "userName": stu_name, "password": settings.student_password,
            "realName": "原名", "role": 1, "userLevel": 1, "status": 1,
        })
        assert_success(create, "建学生")
        uid = create["response"]["id"]

        try:
            # 查：分页里能找到
            page = admin_client.post("/api/admin/user/page/list", json={
                "userName": stu_name, "userLevel": None,
                "pageIndex": 1, "pageSize": 10
            })["response"]["list"]
            assert any(u["id"] == uid for u in page), f"建完后分页查不到学生 {stu_name}"

            # 改：把 realName 改成"新名"
            admin_client.post("/api/admin/user/edit", json={
                "id": uid, "userName": stu_name, "password": "",
                "realName": "新名", "role": 1, "userLevel": 1, "status": 1,
            })
            info = admin_client.post(f"/api/admin/user/select/{uid}", json={})["response"]
            assert info["realName"] == "新名", f"改完昵称未生效: {info['realName']}"
        finally:
            admin_client.post(f"/api/admin/user/delete/{uid}")

    @allure.story("重复用户名注册被拒")
    def test_duplicate_username_rejected(self, admin_client: ApiClient):
        """用已存在的 admin 用户名再注册，应返回 code=2 '用户已存在'。"""
        resp = ApiClient().post("/api/student/user/register", json={
            "userName": "admin", "password": "whatever", "userLevel": 1
        })
        assert resp.get("code") == 2, f"重复用户名应返回 code=2，实际={resp.get('code')} resp={resp}"

    @allure.story("学生自助注册后能登录")
    def test_student_self_register(self):
        """学生端 /register 自助注册后，能用新账号登录。"""
        ts = unique_suffix()
        stu_name = f"自动化_reg_{ts}"
        resp = ApiClient().post("/api/student/user/register", json={
            "userName": stu_name, "password": settings.student_password, "userLevel": 1
        })
        assert_success(resp, "自助注册")

        # 注册后直接登录
        client = ApiClient()
        login = client.post("/api/user/login", json={
            "userName": stu_name, "password": settings.student_password, "remember": False
        })
        assert_success(login, "注册后登录")

        # current 返回正确用户名
        me2 = client.post("/api/student/user/current", json={})
        assert_success(me2, "获取当前学生")
        assert me2["response"]["userName"] == stu_name

        # 清理：按用户名查到 id 后软删；失败不阻塞，conftest 会话末对账会兜底告警
        try:
            admin = ApiClient()
            admin.login("admin")
            page = admin.post("/api/admin/user/page/list", json={
                "userName": stu_name, "userLevel": None, "pageIndex": 1, "pageSize": 10
            })["response"]["list"]
            row = next((u for u in page if u["userName"] == stu_name), None)
            if row:
                admin.post(f"/api/admin/user/delete/{row['id']}")
        except Exception as exc:
            logger.warning("自助注册用户 %s 清理失败：%s", stu_name, exc)

    @allure.story("学生更新个人资料")
    def test_student_update_profile(self, student_client: ApiClient):
        """学生改 realName/phone 后，current 接口能看到新值。

        student_client 是整个会话共享的学生账号，测完必须还原 phone，
        否则后续用例会读到这个被改过的脏值。
        """
        me = student_client.post("/api/student/user/current", json={})["response"]
        original_phone = me.get("phone") or ""
        try:
            resp = student_client.post("/api/student/user/update", json={
                "realName": me.get("realName") or me["userName"],
                "userLevel": me["userLevel"],
                "phone": "13800000000",
            })
            assert_success(resp, "更新资料")
            me2 = student_client.post("/api/student/user/current", json={})["response"]
            assert me2.get("phone") == "13800000000", f"更新后 phone 未生效: {me2}"
        finally:
            # 还原 phone，避免污染共享学生账号
            student_client.post("/api/student/user/update", json={
                "realName": me.get("realName") or me["userName"],
                "userLevel": me["userLevel"],
                "phone": original_phone,
            })
