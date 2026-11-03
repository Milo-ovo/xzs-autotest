"""编辑接口回归：题目编辑、试卷编辑、任务编辑。"""
from common.utils import unique_suffix
import time

import allure

from common.request import ApiClient
from common.response import assert_success


@allure.epic("管理端后台")
@allure.feature("编辑与更新")
class TestEditInterfaces:

    @allure.story("编辑题目：改正确答案后生效")
    def test_edit_question_answer(self, admin_client: ApiClient):
        """建一道单选（答案A）→ 改成答案B → select 详情应显示新答案。"""
        # 建学科
        subj_name = f"自动化_编辑学科_{unique_suffix()}"
        assert_success(admin_client.post("/api/admin/education/subject/edit", json={
            "id": None, "name": subj_name, "level": 1, "levelName": "一年级"
        }), "建学科")
        sid = next(s["id"] for s in admin_client.post(
            "/api/admin/education/subject/list", json={})["response"] if s["name"] == subj_name)

        try:
            # 建题（答案 A）
            title = f"自动化_编辑题_{unique_suffix()}"
            admin_client.post("/api/admin/question/edit", json={
                "id": None, "questionType": 1, "gradeLevel": 1, "subjectId": sid,
                "title": title, "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
                "analyze": "x", "correct": "A", "correctArray": None,
                "score": 1, "difficult": 1,
            })
            q_id = next(q["id"] for q in admin_client.post("/api/admin/question/page", json={
                "id": None, "questionType": None, "subjectId": sid,
                "pageIndex": 1, "pageSize": 10
            })["response"]["list"])

            # 改成答案 B
            admin_client.post("/api/admin/question/edit", json={
                "id": q_id, "questionType": 1, "gradeLevel": 1, "subjectId": sid,
                "title": title, "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
                "analyze": "x", "correct": "B", "correctArray": None,
                "score": 1, "difficult": 1,
            })
            detail = admin_client.post(f"/api/admin/question/select/{q_id}", json={})["response"]
            assert detail["correct"] == "B", f"改答案后未生效: correct={detail['correct']}"
        finally:
            try:
                admin_client.post(f"/api/admin/education/subject/delete/{sid}")
            except Exception:
                pass

    @allure.story("编辑试卷：改名字后生效")
    def test_edit_paper_name(self, admin_client: ApiClient):
        """建试卷 → 改名字 → 分页查询应显示新名字。"""
        subj_name = f"自动化_改卷学科_{unique_suffix()}"
        assert_success(admin_client.post("/api/admin/education/subject/edit", json={
            "id": None, "name": subj_name, "level": 1, "levelName": "一年级"
        }), "建学科")
        sid = next(s["id"] for s in admin_client.post(
            "/api/admin/education/subject/list", json={})["response"] if s["name"] == subj_name)
        try:
            # 先建一道题
            admin_client.post("/api/admin/question/edit", json={
                "id": None, "questionType": 1, "gradeLevel": 1, "subjectId": sid,
                "title": f"自动化_改卷题_{unique_suffix()}",
                "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
                "analyze": "x", "correct": "A", "correctArray": None,
                "score": 1, "difficult": 1,
            })
            q = next(q for q in admin_client.post("/api/admin/question/page", json={
                "id": None, "questionType": None, "subjectId": sid,
                "pageIndex": 1, "pageSize": 10
            })["response"]["list"])

            old_name = f"自动化_旧卷名_{unique_suffix()}"
            new_name = f"自动化_新卷名_{unique_suffix()}"
            # 建卷（titleItems 不能为空，否则 @Size(min=1) 报 501）
            admin_client.post("/api/admin/exam/paper/edit", json={
                "id": None, "level": 1, "subjectId": sid, "paperType": 1,
                "name": old_name, "suggestTime": "30", "limitDateTime": [],
                "titleItems": [{"name": old_name, "questionItems": [{
                    "id": q["id"], "questionType": 1, "subjectId": sid,
                    "title": q["shortTitle"], "gradeLevel": 1,
                    "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
                    "analyze": "x", "correct": "A", "correctArray": None,
                    "score": "1", "difficult": 1, "itemOrder": 1,
                }]}],
            })
            papers = admin_client.post("/api/admin/exam/paper/page", json={
                "name": old_name, "pageIndex": 1, "pageSize": 10
            })["response"]["list"]
            paper_id = next(p["id"] for p in papers if p["name"] == old_name)

            # 改名（保持题目不变）
            admin_client.post("/api/admin/exam/paper/edit", json={
                "id": paper_id, "level": 1, "subjectId": sid, "paperType": 1,
                "name": new_name, "suggestTime": "30", "limitDateTime": [],
                "titleItems": [{"name": new_name, "questionItems": [{
                    "id": q["id"], "questionType": 1, "subjectId": sid,
                    "title": q["shortTitle"], "gradeLevel": 1,
                    "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
                    "analyze": "x", "correct": "A", "correctArray": None,
                    "score": "1", "difficult": 1, "itemOrder": 1,
                }]}],
            })
            after = admin_client.post("/api/admin/exam/paper/page", json={
                "name": new_name, "pageIndex": 1, "pageSize": 10
            })["response"]["list"]
            assert any(p["id"] == paper_id for p in after), \
                f"改名后分页查不到新名字: {new_name}"
        finally:
            try:
                admin_client.post(f"/api/admin/education/subject/delete/{sid}")
            except Exception:
                pass

    @allure.story("编辑任务：改标题后生效")
    def test_edit_task_title(self, admin_client: ApiClient):
        """建任务 → 改标题 → select 返回新标题。"""
        ts = unique_suffix()
        old_title = f"自动化_旧任务_{ts}"
        new_title = f"自动化_新任务_{ts}"
        # 建任务（paperItems 为空会 @Size(min=1) 报错，需要一个假 paperItems）
        # 这里只测 edit 改标题，直接建一个最简任务
        subj_name = f"自动化_任务学科_{ts}"
        assert_success(admin_client.post("/api/admin/education/subject/edit", json={
            "id": None, "name": subj_name, "level": 1, "levelName": "一年级"
        }), "建学科")
        sid = next(s["id"] for s in admin_client.post(
            "/api/admin/education/subject/list", json={})["response"] if s["name"] == subj_name)
        try:
            # 建一道题+一张任务卷作为任务的 paperItems
            admin_client.post("/api/admin/question/edit", json={
                "id": None, "questionType": 1, "gradeLevel": 1, "subjectId": sid,
                "title": f"自动化_任务题_{ts}",
                "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
                "analyze": "x", "correct": "A", "correctArray": None,
                "score": 1, "difficult": 1,
            })
            q = next(q for q in admin_client.post("/api/admin/question/page", json={
                "id": None, "questionType": None, "subjectId": sid,
                "pageIndex": 1, "pageSize": 10
            })["response"]["list"])
            paper_name = f"自动化_任务卷_{ts}"
            admin_client.post("/api/admin/exam/paper/edit", json={
                "id": None, "level": 1, "subjectId": sid, "paperType": 6,
                "name": paper_name, "suggestTime": "30", "limitDateTime": [],
                "titleItems": [{"name": paper_name, "questionItems": [{
                    "id": q["id"], "questionType": 1, "subjectId": sid,
                    "title": q["shortTitle"], "gradeLevel": 1,
                    "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
                    "analyze": "x", "correct": "A", "correctArray": None,
                    "score": "1", "difficult": 1, "itemOrder": 1,
                }]}],
            })
            paper = next(p for p in admin_client.post("/api/admin/exam/paper/taskExamPage", json={
                "subjectId": sid, "level": 1, "paperType": 6, "pageIndex": 1, "pageSize": 20
            })["response"]["list"] if p["name"] == paper_name)

            create = admin_client.post("/api/admin/task/edit", json={
                "id": None, "gradeLevel": 1, "title": old_title, "paperItems": [paper]
            })
            assert_success(create, "建任务")
            task_id = create["response"]["id"]

            # 改标题
            admin_client.post("/api/admin/task/edit", json={
                "id": task_id, "gradeLevel": 1, "title": new_title, "paperItems": [paper]
            })
            detail = admin_client.post(f"/api/admin/task/select/{task_id}", json={})["response"]
            assert detail["title"] == new_title, f"改标题后未生效: {detail['title']}"

            # 清理
            admin_client.post(f"/api/admin/task/delete/{task_id}")
            admin_client.post(f"/api/admin/exam/paper/delete/{paper['id']}")
            admin_client.post(f"/api/admin/question/delete/{q['id']}")
        finally:
            try:
                admin_client.post(f"/api/admin/education/subject/delete/{sid}")
            except Exception:
                pass
