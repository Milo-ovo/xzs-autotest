"""学科管理模块测试：新建、查询、删除、必填校验。

每个用例自行造数据、自行清理，不依赖其他用例。
"""
from common.utils import unique_suffix
import time
import allure

from common.request import ApiClient
from common.response import assert_success


def _find_subject(client: ApiClient, name: str) -> dict | None:
    """按名称在学科列表里找学科，返回 dict 或 None。"""
    resp = client.post("/api/admin/education/subject/list", json={})
    assert_success(resp, "查询学科列表")
    for s in resp["response"]:
        if s["name"] == name and not s.get("deleted"):
            return s
    return None


@allure.epic("管理端后台")
@allure.feature("学科管理")
class TestSubject:
    def test_create_subject_success(self, admin_client: ApiClient):
        """新建学科后能在列表里查到。"""
        name = f"自动化_学科_{unique_suffix()}"
        resp = admin_client.post("/api/admin/education/subject/edit", json={
            "id": None, "name": name, "level": 1, "levelName": "一年级"
        })
        assert_success(resp, "新建学科")

        created = _find_subject(admin_client, name)
        assert created is not None, f"新建后列表查不到学科: {name}"
        assert created["level"] == 1

        # 清理
        admin_client.post(f"/api/admin/education/subject/delete/{created['id']}")

    def test_create_subject_empty_name_fails(self, admin_client: ApiClient):
        """学科名为空应创建失败，code != 1。"""
        resp = admin_client.post("/api/admin/education/subject/edit", json={
            "id": None, "name": "", "level": 1, "levelName": "一年级"
        })
        assert resp.get("code") != 1, f"空学科名竟然创建成功: {resp}"

    def test_delete_subject(self, admin_client: ApiClient):
        """新建学科后删除，列表里不再出现。"""
        name = f"自动化_待删学科_{unique_suffix()}"
        admin_client.post("/api/admin/education/subject/edit", json={
            "id": None, "name": name, "level": 1, "levelName": "一年级"
        })
        created = _find_subject(admin_client, name)
        assert created is not None

        resp = admin_client.post(f"/api/admin/education/subject/delete/{created['id']}")
        assert_success(resp, "删除学科")

        # 确认已删（deleted=true 或不在未删除列表里）
        resp2 = admin_client.post("/api/admin/education/subject/list", json={})
        still = [s for s in resp2["response"] if s["name"] == name and not s.get("deleted")]
        assert len(still) == 0, f"删除后学科仍在未删除列表: {name}"

    def test_subject_list_returns_structure(self, admin_client: ApiClient):
        """学科列表返回结构包含必要字段。先自建一条，避免空库误失败。"""
        name = f"自动化_结构校验_{unique_suffix()}"
        assert_success(admin_client.post("/api/admin/education/subject/edit", json={
            "id": None, "name": name, "level": 1, "levelName": "一年级"
        }), "建结构校验学科")
        try:
            resp = admin_client.post("/api/admin/education/subject/list", json={})
            assert_success(resp, "查询学科列表")
            items = resp["response"]
            assert isinstance(items, list)
            assert len(items) > 0, "列表不应为空（刚建了一条）"
            sample = next((s for s in items if s["name"] == name), None)
            assert sample is not None, f"刚建的学科 {name} 不在列表里"
            for field in ("id", "name", "level", "levelName"):
                assert field in sample, f"学科列表缺少字段 {field}: {sample}"
        finally:
            created = _find_subject(admin_client, name)
            if created:
                admin_client.post(f"/api/admin/education/subject/delete/{created['id']}")
