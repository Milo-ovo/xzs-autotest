"""学生自评边界测试：主观题给分应做范围校验。

背景：D-007 已固化"管理端建题时 score 可为负数"。本文件测镜像问题——
学生端自评 /api/student/exampaper/answer/edit 时，对 doRight==null 的主观题填写 score：
  - 超过题目满分的分数（题目 10 分，传 100）应拒绝
  - 负数分（传 -5）应拒绝
若后端不校验而静默入库，与 D-007 同源，按 xfail 固化为 D-013 / D-014。
"""
from common.utils import unique_suffix
import time
from typing import Any

import allure
import pytest

from common.request import ApiClient
from common.response import assert_success
from common.utils import must_find_id

pytestmark = [pytest.mark.integration]


def _build_paper(admin: ApiClient, subject_id: int, question: dict, paper_name: str) -> int:
    q_item = {
        "id": question["id"], "questionType": 5,
        "subjectId": subject_id, "title": question["title"],
        "gradeLevel": 1, "items": [], "analyze": "自评边界",
        "correct": question.get("correct", ""), "correctArray": None,
        "score": str(question.get("score", 1)), "difficult": 1, "itemOrder": 1,
    }
    assert_success(admin.post("/api/admin/exam/paper/edit", json={
        "id": None, "level": 1, "subjectId": subject_id, "paperType": 1,
        "name": paper_name, "suggestTime": "30", "limitDateTime": [],
        "titleItems": [{"name": paper_name, "questionItems": [q_item]}],
    }), f"建试卷 {paper_name}")
    papers = admin.post("/api/admin/exam/paper/page", json={
        "name": paper_name, "pageIndex": 1, "pageSize": 10
    })["response"]["list"]
    return next(p["id"] for p in papers if p["name"] == paper_name)


@pytest.fixture(scope="module")
def self_grade_setup(admin_client: ApiClient) -> dict[str, Any]:
    """建一个学科 + 一道 10 分简答 + 两张试卷（分别给超分/负分用例，避免同卷重复交卷）。"""
    suffix = unique_suffix()
    subject_name = f"自动化_自评学科_{suffix}"
    assert_success(admin_client.post("/api/admin/education/subject/edit", json={
        "id": None, "name": subject_name, "level": 1, "levelName": "一年级"
    }), "建学科")
    subs = admin_client.post("/api/admin/education/subject/list", json={})["response"]
    subject_id = next(s["id"] for s in subs if s["name"] == subject_name)

    q_title = f"自动化_自评简答_{suffix}"
    assert_success(admin_client.post("/api/admin/question/edit", json={
        "id": None, "questionType": 5, "gradeLevel": 1, "subjectId": subject_id,
        "title": q_title, "items": [], "analyze": "自评边界题",
        "correct": "参考答案", "correctArray": None, "score": 10, "difficult": 1,
    }), "建简答")
    qpage = admin_client.post("/api/admin/question/page", json={
        "id": None, "questionType": 5, "subjectId": subject_id,
        "pageIndex": 1, "pageSize": 20
    })["response"]["list"]
    qid = must_find_id(qpage, "shortTitle", q_title)
    question = admin_client.post(f"/api/admin/question/select/{qid}", json={})["response"]

    paper_over = _build_paper(admin_client, subject_id, question, f"自动化_自评超分卷_{suffix}")
    paper_neg = _build_paper(admin_client, subject_id, question, f"自动化_自评负分卷_{suffix}")

    yield {"subject_id": subject_id, "question": question,
           "paper_over": paper_over, "paper_neg": paper_neg}

    # 清理：先软删两张试卷，再软删题目和学科；失败不阻塞，会话末对账兜底
    for pid in (paper_over, paper_neg):
        try:
            admin_client.post(f"/api/admin/exam/paper/delete/{pid}")
        except Exception:
            pass
    try:
        admin_client.post(f"/api/admin/question/delete/{question['id']}")
    except Exception:
        pass
    try:
        admin_client.post(f"/api/admin/education/subject/delete/{subject_id}")
    except Exception:
        pass


def _submit_and_read(student: ApiClient, paper_id: int) -> dict:
    """学生交卷，返回 read 接口拿到的待自评 editable 对象。"""
    selected = student.post(f"/api/student/exam/paper/select/{paper_id}", json={})["response"]
    q = selected["titleItems"][0]["questionItems"][0]
    assert_success(student.post("/api/student/exampaper/answer/answerSubmit", json={
        "questionId": None, "doTime": 10, "id": paper_id,
        "answerItems": [{"questionId": q["id"], "completed": True,
                         "itemOrder": q.get("itemOrder"),
                         "content": "自动化作答", "contentArray": []}],
    }), "交卷")
    answers = student.post("/api/student/exampaper/answer/pageList", json={
        "pageIndex": 1, "pageSize": 50
    })["response"]["list"]
    row = next(a for a in answers if a["paperName"] == selected["name"])
    return student.post(f"/api/student/exampaper/answer/read/{row['id']}", json={})["response"]["answer"]


@allure.epic("学生端考试")
@allure.feature("判分与成绩")
class TestSelfGradeBoundary:
    """主观题自评分数范围校验（D-007 的学生端镜像）。"""

    @pytest.mark.xfail(
        reason="D-013：学生自评 answer/edit 未校验 score 上限，超题目满分的分数可能静默入库",
        strict=False,
    )
    @allure.story("自评超满分应被拒绝")
    @allure.severity(allure.severity_level.NORMAL)
    def test_self_grade_over_max_rejected(self, student_client: ApiClient, self_grade_setup: dict) -> None:
        """题目满分 10 分，学生自评给 100，后端应拒绝而不是入库。"""
        editable = _submit_and_read(student_client, self_grade_setup["paper_over"])
        for item in editable["answerItems"]:
            if item.get("doRight") is None:
                item["score"] = "100"
        resp = student_client.post("/api/student/exampaper/answer/edit", json=editable)
        assert resp.get("code") != 1, f"自评给超满分 100 竟被接受: {resp}"

    @pytest.mark.xfail(
        reason="D-014：学生自评 answer/edit 未校验 score 下限，负数分可能静默入库",
        strict=False,
    )
    @allure.story("自评负分应被拒绝")
    @allure.severity(allure.severity_level.NORMAL)
    def test_self_grade_negative_rejected(self, student_client: ApiClient, self_grade_setup: dict) -> None:
        """学生自评给 -5 分，后端应拒绝而不是入库。"""
        editable = _submit_and_read(student_client, self_grade_setup["paper_neg"])
        for item in editable["answerItems"]:
            if item.get("doRight") is None:
                item["score"] = "-5"
        resp = student_client.post("/api/student/exampaper/answer/edit", json=editable)
        assert resp.get("code") != 1, f"自评给负分 -5 竟被接受: {resp}"
