"""试卷编辑校验：重复题目入卷、suggestTime 负数/0。

这两条是手动实测确认的缺陷（D-005/D-006），固化为自动化回归。
"""
from common.utils import unique_suffix
import time

import allure
import pytest

from common.request import ApiClient
from common.response import assert_success


def _setup_subject_and_question(admin: ApiClient) -> dict:
    """建学科+一道单选，返回 {subject_id, question}。"""
    ts = unique_suffix()
    subj_name = f"自动化_校验学科_{ts}"
    assert_success(admin.post("/api/admin/education/subject/edit", json={
        "id": None, "name": subj_name, "level": 1, "levelName": "一年级"
    }), "建学科")
    sid = next(s["id"] for s in admin.post(
        "/api/admin/education/subject/list", json={})["response"] if s["name"] == subj_name)

    admin.post("/api/admin/question/edit", json={
        "id": None, "questionType": 1, "gradeLevel": 1, "subjectId": sid,
        "title": f"自动化_校验题_{ts}",
        "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
        "analyze": "x", "correct": "A", "correctArray": None,
        "score": 1, "difficult": 1,
    })
    q = next(q for q in admin.post("/api/admin/question/page", json={
        "id": None, "questionType": None, "subjectId": sid,
        "pageIndex": 1, "pageSize": 10
    })["response"]["list"])
    return {"subject_id": sid, "question": q}


def _cleanup(admin: ApiClient, data: dict) -> None:
    try:
        admin.post(f"/api/admin/question/delete/{data['question']['id']}")
    except Exception:
        pass
    try:
        admin.post(f"/api/admin/education/subject/delete/{data['subject_id']}")
    except Exception:
        pass


@allure.epic("管理端后台")
@allure.feature("试卷管理")
class TestPaperValidation:

    @pytest.mark.xfail(reason="D-005：同一题目可重复加入试卷未去重，总分被重复累加", strict=False)
    @allure.story("重复题目入卷")
    @allure.severity(allure.severity_level.NORMAL)
    def test_duplicate_question_in_paper(self, admin_client: ApiClient):
        """把同一个 questionId 在 questionItems 里放两次，后端应去重或报错。"""
        data = _setup_subject_and_question(admin_client)
        q = data["question"]
        paper_name = f"自动化_重复题卷_{unique_suffix()}"
        try:
            # 同一个 question id 塞两遍
            item = {
                "id": q["id"], "questionType": 1, "subjectId": data["subject_id"],
                "title": q["shortTitle"], "gradeLevel": 1,
                "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
                "analyze": "x", "correct": "A", "correctArray": None,
                "score": "1", "difficult": 1, "itemOrder": 1,
            }
            resp = admin_client.post("/api/admin/exam/paper/edit", json={
                "id": None, "level": 1, "subjectId": data["subject_id"],
                "paperType": 1, "name": paper_name,
                "suggestTime": 30, "limitDateTime": [],
                "titleItems": [{"name": paper_name, "questionItems": [item, item]}],
            })
            # 期望：后端拒绝（code != 1）。实测 code=1 成功，总分被算成 2 分 → 缺陷
            assert resp.get("code") != 1, \
                f"同一题目重复入卷竟成功: code={resp.get('code')} resp={resp}"
        finally:
            papers = admin_client.post("/api/admin/exam/paper/page", json={
                "name": paper_name, "pageIndex": 1, "pageSize": 10
            })["response"]["list"]
            for p in papers:
                if p["name"] == paper_name:
                    try:
                        admin_client.post(f"/api/admin/exam/paper/delete/{p['id']}")
                    except Exception:
                        pass
            _cleanup(admin_client, data)

    @pytest.mark.parametrize("bad_time", [-1, 0], ids=["负数", "零"])
    @pytest.mark.xfail(reason="D-006：suggestTime 负数/0 不拦截，仅校验非整数", strict=False)
    @allure.story("建议时长边界")
    @allure.severity(allure.severity_level.NORMAL)
    def test_suggest_time_invalid(self, admin_client: ApiClient, bad_time: int):
        """suggestTime=-1 或 0 应被拒绝（@NotNull 但无 @Min）。"""
        data = _setup_subject_and_question(admin_client)
        q = data["question"]
        paper_name = f"自动化_时长{bad_time}_{unique_suffix()}"
        try:
            item = {
                "id": q["id"], "questionType": 1, "subjectId": data["subject_id"],
                "title": q["shortTitle"], "gradeLevel": 1,
                "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
                "analyze": "x", "correct": "A", "correctArray": None,
                "score": "1", "difficult": 1, "itemOrder": 1,
            }
            resp = admin_client.post("/api/admin/exam/paper/edit", json={
                "id": None, "level": 1, "subjectId": data["subject_id"],
                "paperType": 1, "name": paper_name,
                "suggestTime": bad_time, "limitDateTime": [],
                "titleItems": [{"name": paper_name, "questionItems": [item]}],
            })
            assert resp.get("code") != 1, \
                f"suggestTime={bad_time} 竟被接受: code={resp.get('code')} resp={resp}"
        finally:
            papers = admin_client.post("/api/admin/exam/paper/page", json={
                "name": paper_name, "pageIndex": 1, "pageSize": 10
            })["response"]["list"]
            for p in papers:
                if p["name"] == paper_name:
                    try:
                        admin_client.post(f"/api/admin/exam/paper/delete/{p['id']}")
                    except Exception:
                        pass
            _cleanup(admin_client, data)
