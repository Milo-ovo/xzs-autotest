from __future__ import annotations

from typing import Any

import pytest
import allure

from common.request import ApiClient
from common.response import assert_success
from common.db import query_one, query_all
from common.utils import unique_suffix
from config.settings import settings


pytestmark = [pytest.mark.integration]


def _data(response: dict[str, Any]) -> Any:
    return response.get("response")


def _items(paper: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for group in paper.get("titleItems", []) for item in group.get("questionItems", [])]


def _find(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for row in rows:
        if row.get("name") == name or row.get("title") == name:
            return row
    raise AssertionError(f"未找到 {name!r}，实际数据：{rows}")


# (题型, 名称, 选项, correct 字符串, correctArray 列表, 分值)
# 入库后分值按 ×10 放大：单选10 + 多选20 + 判断10 + 填空40 + 简答50
PAPER_SPECS: list[tuple] = [
    (1, "单选题", [{"prefix": "A", "content": "选项A"}, {"prefix": "B", "content": "选项B"}], "B", None, 1),
    (2, "多选题", [{"prefix": "A", "content": "选项A"}, {"prefix": "B", "content": "选项B"}, {"prefix": "C", "content": "选项C"}], "A,C", ["A", "C"], 2),
    (3, "判断题", [{"prefix": "A", "content": "正确"}, {"prefix": "B", "content": "错误"}], "A", None, 1),
    (4, "填空题", [{"prefix": "1", "content": "自动化答案", "score": "4", "itemUuid": "fill-1"}], "", ["自动化答案"], 4),
    (5, "简答题", [], "这是简答题的主观参考答案", None, 5),
]
# 后端对题目分值的放大倍数（score=1 → 实际 10 分）
_SCORE_SCALE = 10
# 客观题题型：单选(1)/多选(2)/判断(3)，由系统自动判分
_OBJECTIVE_TYPES = {1, 2, 3}


@pytest.fixture(scope="module")
def prepared_data(admin_client: ApiClient) -> dict[str, Any]:
    suffix = unique_suffix()
    subject_name = f"自动化_链路学科_{suffix}"
    assert_success(admin_client.post("/api/admin/education/subject/edit", json={
        "id": None, "name": subject_name, "level": 1, "levelName": "一年级"
    }), "新建学科")
    subjects = _data(admin_client.post("/api/admin/education/subject/list", json={}))
    subject_id = _find(subjects, subject_name)["id"]

    for question_type, label, items, correct, correct_array, score in PAPER_SPECS:
        assert_success(admin_client.post("/api/admin/question/edit", json={
            "id": None, "questionType": question_type, "gradeLevel": 1,
            "subjectId": subject_id, "title": f"自动化_{label}_{suffix}", "items": items,
            "analyze": "自动化测试解析", "correct": correct, "correctArray": correct_array,
            "score": score, "difficult": 1,
        }), f"新建{label}")

    page = _data(admin_client.post("/api/admin/question/page", json={
        "id": None, "questionType": None, "subjectId": subject_id, "pageIndex": 1, "pageSize": 20
    }))
    assert {q["questionType"] for q in page["list"]} >= {1, 2, 3, 4, 5}
    questions = [_data(admin_client.post(f"/api/admin/question/select/{q['id']}", json={})) for q in page["list"]]
    data = {"subject_id": subject_id, "questions": questions, "suffix": suffix}
    yield data
    # ---- 清理：先删题目，再删学科（逻辑删除，失败不阻塞；零残留由 conftest 对账兜底）----
    for q in questions:
        try:
            admin_client.post(f"/api/admin/question/delete/{q['id']}")
        except Exception:
            pass
    try:
        admin_client.post(f"/api/admin/education/subject/delete/{subject_id}")
    except Exception:
        pass


def _paper_question(q: dict[str, Any], order: int) -> dict[str, Any]:
    return {"id": q["id"], "questionType": q["questionType"], "subjectId": q["subjectId"],
            "title": q["title"], "gradeLevel": q["gradeLevel"], "items": q.get("items", []),
            "analyze": q.get("analyze", ""), "correctArray": q.get("correctArray"),
            "correct": q.get("correct", ""), "score": str(q.get("score", 1)),
            "difficult": q.get("difficult", 1), "itemOrder": order}


def _create_paper(client: ApiClient, name: str, paper_type: int, data: dict[str, Any]) -> dict[str, Any]:
    questions = [_paper_question(q, i) for i, q in enumerate(data["questions"], 1)]
    assert any(q["questionType"] == 5 for q in questions), "试卷必须包含简答主观题"
    response = client.post("/api/admin/exam/paper/edit", json={
        "id": None, "level": 1, "subjectId": data["subject_id"], "paperType": paper_type,
        "limitDateTime": [settings.time_paper_start, settings.time_paper_end] if paper_type == 4 else [],
        "name": name, "suggestTime": "30", "titleItems": [{"name": name, "questionItems": questions}],
    })
    assert_success(response, f"创建{name}")
    paper = _data(response)
    assert paper and paper.get("id")
    return paper


@pytest.fixture(scope="module")
def prepared_papers(admin_client: ApiClient, prepared_data: dict[str, Any]) -> dict[str, Any]:
    suffix = prepared_data["suffix"]
    fixed = _create_paper(admin_client, f"自动化_固定试卷_{suffix}", 1, prepared_data)
    timed = _create_paper(admin_client, f"自动化_时段试卷_{suffix}", 4, prepared_data)
    task_paper = _create_paper(admin_client, f"自动化_任务试卷_{suffix}", 6, prepared_data)
    page = _data(admin_client.post("/api/admin/exam/paper/taskExamPage", json={
        "subjectId": prepared_data["subject_id"], "level": 1, "paperType": 6, "pageIndex": 1, "pageSize": 20
    }))
    task_row = _find(page["list"], task_paper["name"])
    task_response = admin_client.post("/api/admin/task/edit", json={
        "id": None, "gradeLevel": 1, "title": f"自动化_考试任务_{suffix}", "paperItems": [task_row]
    })
    assert_success(task_response, "发布考试任务")
    task = _data(task_response)
    result = {"fixed": fixed, "timed": timed, "task": task_paper, "task_id": task["id"]}
    yield result
    # ---- 清理：先删任务，再删三张试卷 ----
    try:
        admin_client.post(f"/api/admin/task/delete/{result['task_id']}")
    except Exception:
        pass
    for paper in (fixed, timed, task_paper):
        try:
            admin_client.post(f"/api/admin/exam/paper/delete/{paper['id']}")
        except Exception:
            pass


# 试卷满分 = 所有题目分值 × 放大倍数；客观题得分 = 题型属于 {1,2,3} 的分值 × 放大倍数
EXPECTED_PAPER_SCORE = sum(s[5] * _SCORE_SCALE for s in PAPER_SPECS)
EXPECTED_SYSTEM_SCORE = sum(s[5] * _SCORE_SCALE for s in PAPER_SPECS if s[0] in _OBJECTIVE_TYPES)


def _answer_paper(student_client: ApiClient, paper_id: int, expected_type: int) -> None:
    selected = _data(student_client.post(f"/api/student/exam/paper/select/{paper_id}", json={}))
    assert selected["paperType"] == expected_type
    questions = _items(selected)
    assert any(q["questionType"] == 5 for q in questions)
    # 按题型构造答案：后端判分规则——
    #   单选(1)/判断(3) 读 content；多选(2) 读 contentArray；填空(4) 读 contentArray；简答(5) 读 content
    answer_items = []
    for q in questions:
        qtype = q["questionType"]
        correct = q.get("correct", "") or ""
        item = {"questionId": q["id"], "completed": True, "itemOrder": q.get("itemOrder")}
        if qtype == 5:                       # 简答：主观作答
            item.update({"content": "自动化主观题作答", "contentArray": []})
        elif qtype == 2:                     # 多选：选项数组
            item.update({"content": None, "contentArray": [p for p in correct.split(",") if p]})
        elif qtype == 4:                     # 填空：答案数组（取题目详情里的 correctArray）
            fill_answer = q.get("correctArray") or []
            item.update({"content": None, "contentArray": fill_answer})
        else:                                # 单选(1)/判断(3)：content 存答案字符串
            item.update({"content": correct, "contentArray": []})
        answer_items.append(item)
    assert_success(student_client.post("/api/student/exampaper/answer/answerSubmit", json={
        "questionId": None, "doTime": 30, "answerItems": answer_items, "id": paper_id
    }), "提交考试")
    answers = _data(student_client.post("/api/student/exampaper/answer/pageList", json={"pageIndex": 1, "pageSize": 50}))
    answer = next((row for row in answers["list"] if row.get("paperName") == selected["name"]), None)
    assert answer, f"提交后未找到 {selected['name']} 的考试记录"
    read = _data(student_client.post(f"/api/student/exampaper/answer/read/{answer['id']}", json={}))
    editable = read["answer"]
    question_ids = {q["id"] for q in questions}
    assert any(item.get("questionId") in question_ids for item in editable["answerItems"])
    for item in editable["answerItems"]:
        q = next((q for q in questions if q["id"] == item["questionId"]), None)
        if q and q["questionType"] == 5:
            item["doRight"] = True
            item["score"] = item.get("questionScore", item.get("score", "0"))
    assert_success(student_client.post("/api/student/exampaper/answer/edit", json=editable), "主观题自评")

    # ---- 数据库双重断言：答卷主表 + 明细级核对 ----
    db_row = query_one(
        "SELECT id, system_score, user_score, paper_score, status "
        "FROM t_exam_paper_answer WHERE id = %s",
        (answer["id"],),
    )
    assert db_row is not None, f"DB 中未找到答卷记录 id={answer['id']}"
    # 1) 试卷满分固定 130（10+20+10+40+50）
    assert float(db_row["paper_score"]) == EXPECTED_PAPER_SCORE, \
        f"试卷满分应为 {EXPECTED_PAPER_SCORE}，实际={db_row['paper_score']}"
    # 2) 客观题（单选/多选/判断）全对，系统自动判分应为 40
    assert float(db_row["system_score"]) == EXPECTED_SYSTEM_SCORE, \
        f"客观题得分应为 {EXPECTED_SYSTEM_SCORE}，实际={db_row['system_score']}"
    # 3) 主观题（简答 50 分）学生自评给了满分，user_score 应 > 0
    assert float(db_row["user_score"]) > 0, \
        f"主观题自评后 user_score 应 > 0，实际={db_row['user_score']}"
    # 4) 明细 customer_score 求和应与主表 system_score 一致
    detail = query_one(
        "SELECT COALESCE(SUM(customer_score), 0) AS total "
        "FROM t_exam_paper_question_customer_answer WHERE exam_paper_answer_id = %s",
        (answer["id"],),
    )
    assert float(detail["total"]) == float(db_row["system_score"]), \
        f"明细得分总和 {detail['total']} 与主表 system_score {db_row['system_score']} 不一致"
    return answer


@pytest.mark.smoke
@allure.epic("学生端考试")
@allure.feature("考试作答")
@allure.severity(allure.severity_level.BLOCKER)
def test_admin_create_and_student_complete_exam_flow(student_client: ApiClient, prepared_papers: dict[str, Any]) -> None:
    dashboard = _data(student_client.post("/api/student/dashboard/index", json={}))
    fixed = _find(dashboard["fixedPaper"], prepared_papers["fixed"]["name"])
    timed = _find(dashboard["timeLimitPaper"], prepared_papers["timed"]["name"])
    _answer_paper(student_client, fixed["id"], 1)
    _answer_paper(student_client, timed["id"], 4)
    tasks = _data(student_client.post("/api/student/dashboard/task", json={}))
    task_item = next(item for task in tasks for item in task.get("paperItems", [])
                     if item.get("examPaperName") == prepared_papers["task"]["name"])
    _answer_paper(student_client, task_item["examPaperId"], 6)
