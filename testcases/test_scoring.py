"""判分规则测试：多选完全匹配制、填空交卷后待自评。

源码依据（ExamPaperAnswerServiceImpl#setSpecialFromVM）：
- 单选/判断/多选：自动判分，DB customer_score = 题目分（×10 存储）
- 多选：选项排序后拼接字符串 equals 正确答案才得分，漏选/错选均 0 分
- 填空：交卷时 customer_score 强制为 0，不自动判分，需后续自评 edit
"""
from common.utils import unique_suffix
import logging
import time
from typing import Any

import allure
import pytest

from common.db import query_one
from common.request import ApiClient
from common.response import assert_success
from common.utils import must_find_id

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def scoring_subject(admin_client: ApiClient) -> int:
    name = f"自动化_判分学科_{unique_suffix()}"
    assert_success(admin_client.post("/api/admin/education/subject/edit", json={
        "id": None, "name": name, "level": 1, "levelName": "一年级"
    }), "建判分学科")
    subs = admin_client.post("/api/admin/education/subject/list", json={})["response"]
    sid = next(s["id"] for s in subs if s["name"] == name)
    yield sid
    page = admin_client.post("/api/admin/question/page", json={
        "id": None, "questionType": None, "subjectId": sid,
        "pageIndex": 1, "pageSize": 200
    })["response"]["list"]
    for q in page:
        try:
            admin_client.post(f"/api/admin/question/delete/{q['id']}")
        except Exception:
            pass
    papers = admin_client.post("/api/admin/exam/paper/page", json={
        "name": None, "pageIndex": 1, "pageSize": 200
    })["response"]["list"]
    for p in papers:
        if p.get("subjectId") == sid:
            try:
                admin_client.post(f"/api/admin/exam/paper/delete/{p['id']}")
            except Exception:
                pass
    try:
        admin_client.post(f"/api/admin/education/subject/delete/{sid}")
    except Exception:
        pass


def _create_question(admin: ApiClient, subject_id: int, label: str,
                     qtype: int, items: list, correct: str,
                     correct_array: list | None, score: int) -> dict:
    title = f"自动化_{label}_{unique_suffix()}"
    assert_success(admin.post("/api/admin/question/edit", json={
        "id": None, "questionType": qtype, "gradeLevel": 1,
        "subjectId": subject_id, "title": title,
        "items": items, "analyze": "判分规则",
        "correct": correct, "correctArray": correct_array,
        "score": score, "difficult": 1,
    }), f"建{label}")
    page = admin.post("/api/admin/question/page", json={
        "id": None, "questionType": qtype, "subjectId": subject_id,
        "pageIndex": 1, "pageSize": 20
    })["response"]["list"]
    q_id = must_find_id(page, "shortTitle", title)
    return admin.post(f"/api/admin/question/select/{q_id}", json={})["response"]


def _build_single_q_paper(admin: ApiClient, subject_id: int,
                          paper_name: str, question: dict) -> int:
    q_item = {
        "id": question["id"], "questionType": question["questionType"],
        "subjectId": subject_id, "title": question["title"],
        "gradeLevel": 1, "items": question.get("items", []),
        "analyze": "x", "correct": question.get("correct", ""),
        "correctArray": question.get("correctArray"),
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


def _submit_and_find_answer(student: ApiClient, paper_id: int,
                            paper_name: str, answer_items: list[dict]) -> int:
    """交卷并按 paperName 精确匹配 answer_id（不靠最新一条，避免串卷）。"""
    assert_success(student.post("/api/student/exampaper/answer/answerSubmit", json={
        "questionId": None, "doTime": 1, "answerItems": answer_items, "id": paper_id
    }), "交卷")
    answers = student.post("/api/student/exampaper/answer/pageList", json={
        "pageIndex": 1, "pageSize": 50
    })["response"]["list"]
    row = next((a for a in answers if a.get("paperName") == paper_name), None)
    assert row, f"交卷后未找到 {paper_name} 的答卷"
    return row["id"]


def _question_customer_score(answer_id: int, question_id: int) -> float:
    row = query_one(
        "SELECT customer_score FROM t_exam_paper_question_customer_answer "
        "WHERE exam_paper_answer_id = %s AND question_id = %s",
        (answer_id, question_id),
    )
    assert row is not None, f"DB 中未找到答卷 {answer_id} 的题目 {question_id} 明细"
    return float(row["customer_score"])


def _self_judge(student: ApiClient, answer_id: int) -> None:
    """学生自评：对未判题（doRight=null）给满分。

    后端 judge() 只处理 doRight==null 的项，并按 score==questionScore 自动判定 doRight。
    这里只填 score，不碰 doRight，避免把题过滤掉导致 updateScore(空list) 500。
    """
    read = student.post(f"/api/student/exampaper/answer/read/{answer_id}", json={})["response"]
    editable = read["answer"]
    for item in editable["answerItems"]:
        if item.get("doRight") is None:
            item["score"] = item.get("questionScore", "0")
    assert_success(student.post("/api/student/exampaper/answer/edit", json=editable), "自评")


# ---------- 多选题（自动判分，完全匹配制） ----------

@allure.epic("学生端考试")
@allure.feature("判分与成绩")
@allure.story("多选题")
class TestMultiSelectScoring:

    @allure.title("多选全对：得满分（DB 分 = 题目分 ×10）")
    def test_multi_all_correct(self, admin_client: ApiClient, student_client: ApiClient,
                               scoring_subject: int) -> None:
        q = _create_question(admin_client, scoring_subject, "多选全对", 2,
            [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"},
             {"prefix": "C", "content": "C"}],
            "A,C", ["A", "C"], 4)
        paper_name = f"自动化_多选全对卷_{unique_suffix()}"
        paper_id = _build_single_q_paper(admin_client, scoring_subject, paper_name, q)
        items = [{"questionId": q["id"], "completed": True, "itemOrder": 1,
                  "content": None, "contentArray": ["A", "C"]}]
        answer_id = _submit_and_find_answer(student_client, paper_id, paper_name, items)
        score = _question_customer_score(answer_id, q["id"])
        assert score == 40, f"多选全对应得 40（DB×10），实际={score}"

    @allure.title("多选含错误选项：0 分")
    def test_multi_with_wrong_option(self, admin_client: ApiClient, student_client: ApiClient,
                                     scoring_subject: int) -> None:
        q = _create_question(admin_client, scoring_subject, "多选错选", 2,
            [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"},
             {"prefix": "C", "content": "C"}, {"prefix": "D", "content": "D"}],
            "A,C", ["A", "C"], 4)
        paper_name = f"自动化_多选错选卷_{unique_suffix()}"
        paper_id = _build_single_q_paper(admin_client, scoring_subject, paper_name, q)
        items = [{"questionId": q["id"], "completed": True, "itemOrder": 1,
                  "content": None, "contentArray": ["A", "D"]}]
        answer_id = _submit_and_find_answer(student_client, paper_id, paper_name, items)
        score = _question_customer_score(answer_id, q["id"])
        assert score == 0, f"多选含错误选项应得 0，实际={score}"

    @allure.title("多选漏选（无错误项但没选全）：0 分（完全匹配制，无部分分）")
    def test_multi_miss_one(self, admin_client: ApiClient, student_client: ApiClient,
                            scoring_subject: int) -> None:
        q = _create_question(admin_client, scoring_subject, "多选漏选", 2,
            [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"},
             {"prefix": "C", "content": "C"}],
            "A,C", ["A", "C"], 4)
        paper_name = f"自动化_多选漏选卷_{unique_suffix()}"
        paper_id = _build_single_q_paper(admin_client, scoring_subject, paper_name, q)
        items = [{"questionId": q["id"], "completed": True, "itemOrder": 1,
                  "content": None, "contentArray": ["A"]}]
        answer_id = _submit_and_find_answer(student_client, paper_id, paper_name, items)
        score = _question_customer_score(answer_id, q["id"])
        logger.info("多选漏选（正确 A,C，学生选 A）实际得分=%s", score)
        # 源码：customerAnswer.equals(question.getCorrect()) 才得分，漏选不 equals → 0
        assert score == 0, f"多选漏选应得 0（完全匹配制），实际={score}"


# ---------- 填空题（交卷时不自动判分，需自评） ----------

@allure.epic("学生端考试")
@allure.feature("判分与成绩")
@allure.story("填空题")
class TestFillBlankScoring:

    @allure.title("填空交卷时系统不自动判分（customer_score=0，待自评）")
    def test_fill_submit_waits_judge(self, admin_client: ApiClient, student_client: ApiClient,
                                     scoring_subject: int) -> None:
        """源码：GapFilling 分支 customer_score 强制为 0。"""
        q = _create_question(admin_client, scoring_subject, "填空待判", 4,
            [{"prefix": "1", "content": "答案一", "score": "2", "itemUuid": "f1"},
             {"prefix": "2", "content": "答案二", "score": "2", "itemUuid": "f2"}],
            "", ["答案一", "答案二"], 4)
        paper_name = f"自动化_填空待判卷_{unique_suffix()}"
        paper_id = _build_single_q_paper(admin_client, scoring_subject, paper_name, q)
        items = [{"questionId": q["id"], "completed": True, "itemOrder": 1,
                  "content": None, "contentArray": ["答案一", "答案二"]}]
        answer_id = _submit_and_find_answer(student_client, paper_id, paper_name, items)
        score = _question_customer_score(answer_id, q["id"])
        assert score == 0, f"填空交卷时应待自评（customer_score=0），实际={score}"

    @allure.title("填空自评给满分后，分数正确累加（DB×10）")
    def test_fill_self_judge_full_score(self, admin_client: ApiClient, student_client: ApiClient,
                                        scoring_subject: int) -> None:
        q = _create_question(admin_client, scoring_subject, "填空自评", 4,
            [{"prefix": "1", "content": "答案一", "score": "2", "itemUuid": "f3"},
             {"prefix": "2", "content": "答案二", "score": "2", "itemUuid": "f4"}],
            "", ["答案一", "答案二"], 4)
        paper_name = f"自动化_填空自评卷_{unique_suffix()}"
        paper_id = _build_single_q_paper(admin_client, scoring_subject, paper_name, q)
        items = [{"questionId": q["id"], "completed": True, "itemOrder": 1,
                  "content": None, "contentArray": ["答案一", "答案二"]}]
        answer_id = _submit_and_find_answer(student_client, paper_id, paper_name, items)
        _self_judge(student_client, answer_id)
        score = _question_customer_score(answer_id, q["id"])
        assert score == 40, f"自评满分后应得 40，实际={score}"
