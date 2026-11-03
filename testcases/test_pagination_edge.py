"""分页边界：pageIndex 超界、pageSize=0、pageSize 负数、pageSize 超大。"""
import allure

from common.request import ApiClient
from common.response import assert_success


@allure.epic("管理端后台")
@allure.feature("数据查询")
class TestPaginationEdge:

    @allure.story("页码超出总页数")
    def test_page_index_out_of_range(self, admin_client: ApiClient):
        """pageIndex=99999 应不 500。

        实测：PageHelper 在页码超界时静默回退到第 1 页（pageNum=1），
        不返回空 list 也不报错——记录此行为即可。
        """
        resp = admin_client.post("/api/admin/question/page", json={
            "id": None, "questionType": None, "subjectId": None,
            "pageIndex": 99999, "pageSize": 10
        })
        assert_success(resp, "超界页码")
        body = resp["response"]
        assert isinstance(body["list"], list)
        # PageHelper 默认回退到第一页，不报错即可
        assert resp.get("code") == 1

    @allure.story("pageSize=0")
    def test_page_size_zero(self, admin_client: ApiClient):
        """pageSize=0 不应 500。"""
        resp = admin_client.post("/api/admin/question/page", json={
            "id": None, "questionType": None, "subjectId": None,
            "pageIndex": 1, "pageSize": 0
        })
        assert resp.get("code") != 500, f"pageSize=0 导致服务器错误: {resp}"

    @allure.story("pageSize 负数")
    def test_page_size_negative(self, admin_client: ApiClient):
        """pageSize=-1 不应 500。"""
        resp = admin_client.post("/api/admin/question/page", json={
            "id": None, "questionType": None, "subjectId": None,
            "pageIndex": 1, "pageSize": -1
        })
        assert resp.get("code") != 500, f"pageSize=-1 导致服务器错误: {resp}"

    @allure.story("pageSize 超大")
    def test_page_size_huge(self, admin_client: ApiClient):
        """pageSize=10000 不应 500，应正常返回（可能截断）。"""
        resp = admin_client.post("/api/admin/question/page", json={
            "id": None, "questionType": None, "subjectId": None,
            "pageIndex": 1, "pageSize": 10000
        })
        assert resp.get("code") != 500, f"pageSize=10000 导致服务器错误: {resp}"
