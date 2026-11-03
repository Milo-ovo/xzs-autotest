"""考试规则类用例：任务卷重复作答、空卷交卷。

独立造数：一道单选 + 一张任务试卷 + 发布任务，学生完成作答后验证规则。
"""
from common.utils import unique_suffix
import time
from typing import Any

import allure
import pytest

from common.request import ApiClient
from common.response import assert_success


def _create_minimal_task_paper(admin: ApiClient) -> dict[str, Any]:
    """建一个学科 + 一道单选 + 一张任务卷并发布任务，返回 {paper_id, task_id, question_id}。"""
    ts = unique_suffix()
    subj = f"自动化_规则学科_{ts}"
    admin.post("/api/admin/education/subject/edit", json={
        "id": None, "name": subj, "level": 1, "levelName": "一年级"
    })
    sid = next(s["id"] for s in admin.post(
        "/api/admin/education/subject/list", json={})["response"] if s["name"] == subj)
    admin.post("/api/admin/question/edit", json={
        "id": None, "questionType": 1, "gradeLevel": 1, "subjectId": sid,
        "title": f"自动化_规则题_{ts}",
        "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
        "analyze": "x", "correct": "A", "correctArray": None,
        "score": 1, "difficult": 1
    })
    q = next(q for q in admin.post("/api/admin/question/page", json={
        "id": None, "questionType": None, "subjectId": sid,
        "pageIndex": 1, "pageSize": 10
    })["response"]["list"] if q["shortTitle"].startswith("自动化_规则题_"))
    paper_name = f"自动化_规则任务卷_{ts}"
    admin.post("/api/admin/exam/paper/edit", json={
        "id": None, "level": 1, "subjectId": sid, "paperType": 6,
        "name": paper_name, "suggestTime": "30",
        "limitDateTime": [],
        "titleItems": [{"name": paper_name, "questionItems": [{
            "id": q["id"], "questionType": 1, "subjectId": sid, "title": q["shortTitle"],
            "gradeLevel": 1, "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
            "analyze": "x", "correct": "A", "correctArray": None,
            "score": "1", "difficult": 1, "itemOrder": 1
        }]}]
    })
    paper = next(p for p in admin.post("/api/admin/exam/paper/taskExamPage", json={
        "subjectId": sid, "level": 1, "paperType": 6, "pageIndex": 1, "pageSize": 20
    })["response"]["list"] if p["name"] == paper_name)
    task_resp = admin.post("/api/admin/task/edit", json={
        "id": None, "gradeLevel": 1, "title": f"自动化_规则任务_{ts}", "paperItems": [paper]
    })
    assert_success(task_resp, "发布任务")
    return {"paper_id": paper["id"], "question_id": q["id"], "subject_id": sid,
            "task_id": task_resp["response"]["id"], "name": paper_name}


@allure.epic("学生端考试")
@allure.feature("考试作答")
class TestExamRules:

    @allure.story("空卷交卷")
    def test_submit_empty_answer(self, admin_client: ApiClient, student_client: ApiClient):
        """EXAM-005：学生不作答直接交卷，系统应容错放行（0 分待自评），不应 500。

        模拟真实前端：answerItems 中每题都在，仅 completed=False / 答案为空。
        """
        data = _create_minimal_task_paper(admin_client)
        try:
            resp = student_client.post("/api/student/exampaper/answer/answerSubmit", json={
                "questionId": None, "doTime": 1,
                "answerItems": [{"questionId": data["question_id"], "completed": False,
                                 "itemOrder": 1, "content": "", "contentArray": []}],
                "id": data["paper_id"]
            })
            assert_success(resp, "空卷交卷应被系统容错放行")
        finally:
            admin_client.post(f"/api/admin/task/delete/{data['task_id']}")
            admin_client.post(f"/api/admin/exam/paper/delete/{data['paper_id']}")

    @allure.story("任务卷不可重复作答")
    def test_task_paper_cannot_resubmit(self, admin_client: ApiClient, student_client: ApiClient):
        """EXAM-004：任务试卷同一学生交卷后，再次提交应被拒绝。"""
        data = _create_minimal_task_paper(admin_client)
        try:
            items = [{"questionId": data["question_id"], "completed": True,
                      "itemOrder": 1, "content": "A", "contentArray": []}]
            first = student_client.post("/api/student/exampaper/answer/answerSubmit", json={
                "questionId": None, "doTime": 1, "answerItems": items, "id": data["paper_id"]
            })
            assert_success(first, "首次交卷")
            # 第二次交同一张任务卷
            second = student_client.post("/api/student/exampaper/answer/answerSubmit", json={
                "questionId": None, "doTime": 1, "answerItems": items, "id": data["paper_id"]
            })
            assert second.get("code") != 1, f"任务卷竟允许重复交卷: {second}"
        finally:
            admin_client.post(f"/api/admin/task/delete/{data['task_id']}")
            admin_client.post(f"/api/admin/exam/paper/delete/{data['paper_id']}")
