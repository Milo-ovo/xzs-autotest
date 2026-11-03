"""缺陷与异常回归用例：按"合理预期"编写，首次执行暴露问题后再标记 xfail。

覆盖测试用例表中此前未自动化的异常/边界项，以及缺陷记录表中的 BUG。
"""
from common.utils import unique_suffix
import time

import allure
import pytest

from common.request import ApiClient
from common.response import assert_success
from config.settings import settings


@allure.epic("跨模块质量保障")
@allure.feature("已知缺陷回归")
class TestDefects:

    @pytest.mark.xfail(reason="BUG-004：学科名称重复未拦截，允许创建重名学科", strict=False)
    @allure.story("学科名校验")
    @allure.severity(allure.severity_level.NORMAL)
    def test_duplicate_subject_name_should_be_rejected(self, admin_client: ApiClient):
        """SUBJ-003 / BUG-004：学科名称重复时应提示并禁止创建。"""
        name = f"自动化_重名学科_{unique_suffix()}"
        assert_success(admin_client.post("/api/admin/education/subject/edit", json={
            "id": None, "name": name, "level": 1, "levelName": "一年级"
        }), "建第一个学科")
        # 第二次用同名提交，预期被拦截
        resp = admin_client.post("/api/admin/education/subject/edit", json={
            "id": None, "name": name, "level": 1, "levelName": "一年级"
        })
        try:
            assert resp.get("code") != 1, f"重复学科名竟创建成功: {resp}"
        finally:
            # 清理：删掉同名学科
            subs = admin_client.post("/api/admin/education/subject/list", json={})["response"]
            for s in subs:
                if s["name"] == name:
                    admin_client.post(f"/api/admin/education/subject/delete/{s['id']}")

    @allure.story("学科软删留档")
    @allure.severity(allure.severity_level.NORMAL)
    def test_soft_delete_subject_hidden_in_page(self, admin_client: ApiClient):
        """BD-003：学科被题目引用时软删是设计（留档），删除应成功且管理列表不可见。"""
        name = f"自动化_软删学科_{unique_suffix()}"
        assert_success(admin_client.post("/api/admin/education/subject/edit", json={
            "id": None, "name": name, "level": 1, "levelName": "一年级"
        }), "建学科")
        sid = next(s["id"] for s in admin_client.post(
            "/api/admin/education/subject/list", json={})["response"] if s["name"] == name)
        # 在该学科下建一道题，模拟被引用
        assert_success(admin_client.post("/api/admin/question/edit", json={
            "id": None, "questionType": 1, "gradeLevel": 1, "subjectId": sid,
            "title": f"自动化_引用题_{unique_suffix()}",
            "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
            "analyze": "x", "correct": "B", "correctArray": None,
            "score": 1, "difficult": 1
        }), "建引用题")
        # 软删应成功（不拦截引用）
        resp = admin_client.post(f"/api/admin/education/subject/delete/{sid}")
        assert_success(resp, "软删被引用学科（留档设计，应成功）")
        # 管理分页列表（带 deleted=0 过滤）不应再出现
        page = admin_client.post("/api/admin/education/subject/page", json={
            "id": None, "level": None, "pageIndex": 1, "pageSize": 100
        })
        names = [s["name"] for s in page["response"]["list"]]
        try:
            assert name not in names, f"已删学科仍出现在管理列表: {name}"
        finally:
            page_q = admin_client.post("/api/admin/question/page", json={
                "id": None, "questionType": None, "subjectId": sid,
                "pageIndex": 1, "pageSize": 100
            })
            for q in page_q["response"]["list"]:
                try:
                    admin_client.post(f"/api/admin/question/delete/{q['id']}")
                except Exception:
                    pass

    @pytest.mark.xfail(reason="D-004：已删学科仍出现在 /subject/list 下拉（allSubject 未过滤 deleted）。P1，strict=True：修复后提醒摘 xfail", strict=True)
    @allure.story("已删学科下拉过滤")
    @allure.severity(allure.severity_level.NORMAL)
    def test_deleted_subject_still_in_subject_dropdown(self, admin_client: ApiClient):
        """D-001：软删后的学科不应再出现在建题/建卷的学科下拉中。"""
        name = f"自动化_待删下拉学科_{unique_suffix()}"
        assert_success(admin_client.post("/api/admin/education/subject/edit", json={
            "id": None, "name": name, "level": 1, "levelName": "一年级"
        }), "建学科")
        subs = admin_client.post("/api/admin/education/subject/list", json={})["response"]
        sid = next(s["id"] for s in subs if s["name"] == name)
        admin_client.post(f"/api/admin/education/subject/delete/{sid}")
        # 重新拉下数据源，已删学科不应再出现
        after = admin_client.post("/api/admin/education/subject/list", json={})["response"]
        try:
            deleted_still_there = any(s["id"] == sid for s in after)
            assert not deleted_still_there, f"已删学科 {sid} 仍出现在下拉 list 中"
        finally:
            pass

    @allure.story("题目必填校验")
    @allure.severity(allure.severity_level.NORMAL)
    def test_single_question_without_answer_should_be_rejected(self, admin_client: ApiClient):
        """QUES-008：单选题未选正确答案应被拦截。"""
        # 动态建学科，避免硬编码 subjectId=1
        subj_name = f"自动化_无答案学科_{unique_suffix()}"
        assert_success(admin_client.post("/api/admin/education/subject/edit", json={
            "id": None, "name": subj_name, "level": 1, "levelName": "一年级"
        }), "建学科")
        sid = next(s["id"] for s in admin_client.post(
            "/api/admin/education/subject/list", json={})["response"] if s["name"] == subj_name)
        try:
            resp = admin_client.post("/api/admin/question/edit", json={
                "id": None, "questionType": 1, "gradeLevel": 1, "subjectId": sid,
                "title": f"自动化_无答案题_{unique_suffix()}",
                "items": [{"prefix": "A", "content": "A"}],
                "analyze": "x", "correct": "", "correctArray": None,
                "score": 1, "difficult": 1
            })
            assert resp.get("code") != 1, f"未选正确答案竟保存成功: {resp}"
        finally:
            try:
                admin_client.post(f"/api/admin/education/subject/delete/{sid}")
            except Exception:
                pass

    @allure.story("试卷必填校验")
    @allure.severity(allure.severity_level.NORMAL)
    def test_empty_paper_should_be_rejected(self, admin_client: ApiClient):
        """PAPER-003：试卷未选题目直接提交应被拦截。"""
        resp = admin_client.post("/api/admin/exam/paper/edit", json={
            "id": None, "name": f"自动化_空卷_{unique_suffix()}",
            "subjectId": None, "paperType": 1, "level": 1,
            "score": 0, "suggestTime": 60,
            "limitStartTime": settings.time_paper_start,
            "limitEndTime": settings.time_paper_end,
            "questionTextContentId": None, "titleItems": []
        })
        assert resp.get("code") != 1, f"空试卷竟提交成功: {resp}"
