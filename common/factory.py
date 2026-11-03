"""测试数据工厂：把"建学科→建题→建卷→学生交卷"的重复模板抽成可复用函数。

以前 test_cross_student / test_permission / test_time_window 里各写了一遍几乎相同的
建数据代码，改一个接口字段要改三处。这里统一收口。

所有函数：
- 都用 admin_client 做管理端操作
- 名字前缀 "自动化_"，配合 cleanup_test_data.py 兜底清理
- 失败直接 assert，不吞异常
"""
from __future__ import annotations

from typing import Any

from common.request import ApiClient
from common.response import assert_success
from common.utils import unique_suffix


def make_subject(admin: ApiClient, name: str | None = None,
                 level: int = 1, level_name: str = "一年级") -> dict:
    """建一个学科，返回完整学科 dict（含 id）。"""
    name = name or f"自动化_工厂学科_{unique_suffix()}"
    assert_success(admin.post("/api/admin/education/subject/edit", json={
        "id": None, "name": name, "level": level, "levelName": level_name,
    }), f"建学科 {name}")
    # 回查拿 id（edit 接口不一定直接返回 id）
    rows = admin.post("/api/admin/education/subject/list", json={})["response"]
    subj = next(s for s in rows if s["name"] == name)
    return subj


def make_question(admin: ApiClient, subject_id: int,
                  title: str | None = None,
                  question_type: int = 1,
                  correct: str = "A",
                  correct_array: list[str] | None = None,
                  score: int = 1,
                  items: list[dict] | None = None,
                  analyze: str = "自动化解析",
                  **overrides: Any) -> dict:
    """建一道题（默认单选题），返回题目分页行（含 id/shortTitle）。

    返回值会额外带上 items / analyze / correct / correctArray 字段，
    方便后续建卷时 _question_to_paper_item 直接用（分页接口本身不返回这些）。
    """
    title = title or f"自动化_工厂题_{unique_suffix()}"
    items = items if items is not None else [
        {"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"},
    ]
    payload: dict[str, Any] = {
        "id": None, "questionType": question_type, "gradeLevel": 1,
        "subjectId": subject_id, "title": title, "items": items,
        "analyze": analyze, "correct": correct, "correctArray": correct_array,
        "score": score, "difficult": 1,
    }
    payload.update(overrides)
    assert_success(admin.post("/api/admin/question/edit", json=payload), f"建题 {title}")
    page = admin.post("/api/admin/question/page", json={
        "id": None, "questionType": None, "subjectId": subject_id,
        "pageIndex": 1, "pageSize": 50,
    })["response"]["list"]
    row = next(q for q in page if q["shortTitle"] == title)
    # 分页接口不返回 items/analyze/correct 等字段，手动补回去，建卷时要用
    row["items"] = items
    row["analyze"] = analyze
    row["correct"] = correct
    row["correctArray"] = correct_array
    return row


def _question_to_paper_item(q: dict, order: int = 1) -> dict:
    """把分页里的题目行转成建卷时 titleItems 里 questionItems 需要的结构。"""
    return {
        "id": q["id"], "questionType": q["questionType"], "subjectId": q["subjectId"],
        "title": q["shortTitle"], "gradeLevel": 1,
        "items": q.get("items") or [],
        "analyze": q.get("analyze") or "",
        "correct": q.get("correct") or "",
        "correctArray": q.get("correctArray"),
        "score": str(q.get("score", 1)),
        "difficult": q.get("difficult", 1),
        "itemOrder": order,
    }


def make_paper(admin: ApiClient, subject_id: int, questions: list[dict],
               name: str | None = None, paper_type: int = 1,
               limit_datetime: list[str] | None = None) -> dict:
    """建一张试卷，返回分页行（含 id/name）。

    paper_type: 1=固定卷, 4=时段卷, 6=任务卷。
    limit_datetime: paper_type=4 时传 [start, end]。
    """
    name = name or f"自动化_工厂卷_{unique_suffix()}"
    question_items = [_question_to_paper_item(q, i) for i, q in enumerate(questions, 1)]
    payload: dict[str, Any] = {
        "id": None, "level": 1, "subjectId": subject_id, "paperType": paper_type,
        "name": name, "suggestTime": "30",
        "limitDateTime": limit_datetime or [],
        "titleItems": [{"name": name, "questionItems": question_items}],
    }
    assert_success(admin.post("/api/admin/exam/paper/edit", json=payload), f"建卷 {name}")
    page = admin.post("/api/admin/exam/paper/page", json={
        "name": name, "pageIndex": 1, "pageSize": 10,
    })["response"]["list"]
    return next(p for p in page if p["name"] == name)


def student_submit(student: ApiClient, paper_id: int, question_id: int,
                   paper_name: str, content: str = "A") -> dict:
    """学生交卷（默认答对第一道单选），返回答卷列表行（含 id/paperName）。"""
    assert_success(student.post("/api/student/exampaper/answer/answerSubmit", json={
        "questionId": None, "doTime": 1,
        "answerItems": [{"questionId": question_id, "completed": True, "itemOrder": 1,
                         "content": content, "contentArray": []}],
        "id": paper_id,
    }), "学生交卷")
    answers = student.post("/api/student/exampaper/answer/pageList", json={
        "pageIndex": 1, "pageSize": 50
    })["response"]["list"]
    return next(a for a in answers if a.get("paperName") == paper_name)


def cleanup_stack(admin: ApiClient, paper_id: int | None = None,
                  question_id: int | None = None,
                  subject_id: int | None = None) -> None:
    """逆序清理：卷 → 题 → 学科。失败静默，不阻塞用例。"""
    for url in (
        f"/api/admin/exam/paper/delete/{paper_id}" if paper_id else None,
        f"/api/admin/question/delete/{question_id}" if question_id else None,
        f"/api/admin/education/subject/delete/{subject_id}" if subject_id else None,
    ):
        if url is None:
            continue
        try:
            admin.post(url)
        except Exception:
            pass


def setup_mini_exam(admin: ApiClient, student: ApiClient,
                    paper_type: int = 1,
                    limit_datetime: list[str] | None = None) -> dict:
    """一站式：建学科 → 建一道单选题 → 建卷 → 学生 A 交卷。

    返回 dict: {subject_id, question, paper, answer_row}
    用例结束后调 cleanup_stack 清理。
    """
    subj = make_subject(admin)
    q = make_question(admin, subj["id"])
    paper = make_paper(admin, subj["id"], [q], paper_type=paper_type,
                       limit_datetime=limit_datetime)
    # 学生进入并交卷
    student.post(f"/api/student/exam/paper/select/{paper['id']}", json={})
    answer = student_submit(student, paper["id"], q["id"], paper["name"], content="A")
    return {
        "subject_id": subj["id"],
        "question": q,
        "paper": paper,
        "answer_row": answer,
    }
