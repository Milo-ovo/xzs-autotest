"""查询接口测试：过滤条件的双侧证据（阳性+阴性）与分页结构。

借鉴"过滤验证黄金法则"：每个过滤条件既要验证该来的来了（阳性），
也要验证不该来的没来（阴性）。
"""
from common.utils import unique_suffix
import time

import allure
import pytest

from common.request import ApiClient
from common.response import assert_success


@pytest.fixture(scope="class")
def filter_subjects(admin_client: ApiClient):
    """建两个学科（A/B），类结束后连同题目一起清理。"""
    ts = unique_suffix()
    sa, sb = f"自动化_筛选A_{ts}", f"自动化_筛选B_{ts}"
    ids = {}
    for name, key in [(sa, "A"), (sb, "B")]:
        admin_client.post("/api/admin/education/subject/edit", json={
            "id": None, "name": name, "level": 1, "levelName": "一年级"
        })
        subs = admin_client.post("/api/admin/education/subject/list", json={})["response"]
        ids[key] = next(s["id"] for s in subs if s["name"] == name)
    yield ids
    for sid in ids.values():
        page = admin_client.post("/api/admin/question/page", json={
            "id": None, "questionType": None, "subjectId": sid,
            "pageIndex": 1, "pageSize": 100
        })
        for q in page["response"]["list"]:
            try:
                admin_client.post(f"/api/admin/question/delete/{q['id']}")
            except Exception:
                pass
        try:
            admin_client.post(f"/api/admin/education/subject/delete/{sid}")
        except Exception:
            pass


@allure.epic("管理端后台")
@allure.feature("数据查询")
class TestQueryFilter:

    @allure.story("题目按学科筛选")
    def test_question_filter_by_subject(self, admin_client: ApiClient, filter_subjects):
        """QUES-009：按学科筛选题目，结果应只含该学科题目（阴性：不含另一学科）。"""
        sid_a = filter_subjects["A"]
        # 在 A 学科建一道单选
        admin_client.post("/api/admin/question/edit", json={
            "id": None, "questionType": 1, "gradeLevel": 1, "subjectId": sid_a,
            "title": f"自动化_A学科题_{unique_suffix()}",
            "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
            "analyze": "x", "correct": "A", "correctArray": None,
            "score": 1, "difficult": 1
        })
        resp = admin_client.post("/api/admin/question/page", json={
            "id": None, "questionType": None, "subjectId": sid_a,
            "pageIndex": 1, "pageSize": 50
        })
        assert_success(resp, "按学科查题目")
        items = resp["response"]["list"]
        assert len(items) > 0, "A 学科应有题目"
        # 阴性：返回的每条都必须属于 A 学科
        for q in items:
            assert q["subjectId"] == sid_a, f"筛选结果混入了其他学科题目: {q}"

    @allure.story("题目按题型筛选")
    def test_question_filter_by_type(self, admin_client: ApiClient, filter_subjects):
        """QUES-010：按题型筛选，结果每条都应是该题型。"""
        sid_a = filter_subjects["A"]
        # 建一道多选
        admin_client.post("/api/admin/question/edit", json={
            "id": None, "questionType": 2, "gradeLevel": 1, "subjectId": sid_a,
            "title": f"自动化_多选题_{unique_suffix()}",
            "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}, {"prefix": "C", "content": "C"}],
            "analyze": "x", "correct": "A,C", "correctArray": ["A", "C"],
            "score": 2, "difficult": 1
        })
        resp = admin_client.post("/api/admin/question/page", json={
            "id": None, "questionType": 2, "subjectId": sid_a,
            "pageIndex": 1, "pageSize": 50
        })
        assert_success(resp, "按题型查题目")
        items = resp["response"]["list"]
        assert len(items) > 0
        for q in items:
            assert q["questionType"] == 2, f"题型筛选结果混入了其他题型: {q}"

    @allure.story("试卷分页结构")
    def test_paper_page_structure(self, admin_client: ApiClient):
        """PAPER-004：试卷分页返回结构完整。"""
        resp = admin_client.post("/api/admin/exam/paper/page", json={
            "name": None, "pageIndex": 1, "pageSize": 10
        })
        assert_success(resp, "试卷分页")
        body = resp["response"]
        for field in ("list", "total", "pageNum", "pageSize"):
            assert field in body, f"试卷分页缺少字段 {field}"
