"""时段试卷（paperType=4）时间边界。

源码核查（ExamPaperController#select、ExamPaperAnswerServiceImpl#calculateExamPaperAnswer）：
- select/{id} 只调 examPaperToVM 返回试卷，不校验 limitDateTime
- answerSubmit 只检查任务卷是否重复做，也不校验时间窗口
- 时间窗口仅靠学生端 dashboard 列表过滤，绕过前端直接调接口即可进入未开始/已结束的试卷
"""
from common.utils import unique_suffix
import time

import allure
import pytest

from common.request import ApiClient
from common.response import assert_success


@pytest.fixture(scope="module")
def window_setup(admin_client: ApiClient):
    ts = unique_suffix()
    name = f"自动化_时段学科_{ts}"
    assert_success(admin_client.post("/api/admin/education/subject/edit", json={
        "id": None, "name": name, "level": 1, "levelName": "一年级"
    }), "建时段学科")
    sid = next(s["id"] for s in admin_client.post(
        "/api/admin/education/subject/list", json={})["response"] if s["name"] == name)

    admin_client.post("/api/admin/question/edit", json={
        "id": None, "questionType": 1, "gradeLevel": 1, "subjectId": sid,
        "title": f"自动化_时段题_{ts}",
        "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
        "analyze": "x", "correct": "A", "correctArray": None,
        "score": 1, "difficult": 1,
    })
    q = next(q for q in admin_client.post("/api/admin/question/page", json={
        "id": None, "questionType": None, "subjectId": sid,
        "pageIndex": 1, "pageSize": 10
    })["response"]["list"])

    yield sid, q
    try:
        admin_client.post(f"/api/admin/question/delete/{q['id']}")
    except Exception:
        pass
    try:
        admin_client.post(f"/api/admin/education/subject/delete/{sid}")
    except Exception:
        pass


def _create_window_paper(admin: ApiClient, sid: int, q: dict,
                         paper_name: str, start: str, end: str) -> int:
    admin.post("/api/admin/exam/paper/edit", json={
        "id": None, "level": 1, "subjectId": sid, "paperType": 4,
        "name": paper_name, "suggestTime": "30",
        "limitDateTime": [start, end],
        "titleItems": [{"name": paper_name, "questionItems": [{
            "id": q["id"], "questionType": 1, "subjectId": sid,
            "title": q["shortTitle"], "gradeLevel": 1,
            "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
            "analyze": "x", "correct": "A", "correctArray": None,
            "score": "1", "difficult": 1, "itemOrder": 1,
        }]}],
    })
    papers = admin.post("/api/admin/exam/paper/taskExamPage", json={
        "subjectId": sid, "level": 1, "paperType": 4,
        "pageIndex": 1, "pageSize": 20
    })["response"]["list"]
    return next(p["id"] for p in papers if p["name"] == paper_name)


@allure.epic("学生端考试")
@allure.feature("时间窗边界")
class TestTimeWindow:

    @pytest.mark.xfail(reason="D-006：时段试卷接口层不校验 limitDateTime，已结束的卷子学生仍可 select/交卷。P1，strict=True：修复后提醒摘 xfail", strict=True)
    @allure.story("已结束的试卷")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_paper_ended_rejects_entry(self, admin_client: ApiClient,
                                       student_client: ApiClient,
                                       window_setup: tuple[int, dict]) -> None:
        sid, q = window_setup
        paper_name = f"自动化_已结束卷_{unique_suffix()}"
        paper_id = _create_window_paper(admin_client, sid, q, paper_name,
                                        "2020-01-01 00:00:00", "2020-01-02 00:00:00")
        try:
            resp = student_client.post(f"/api/student/exam/paper/select/{paper_id}", json={})
            assert resp.get("code") != 1, \
                f"已结束的时段试卷竟可进入: code={resp.get('code')} resp={resp}"
        finally:
            try:
                admin_client.post(f"/api/admin/exam/paper/delete/{paper_id}")
            except Exception:
                pass

    @pytest.mark.xfail(reason="D-007：时段试卷接口层不校验 limitDateTime，未开始的卷子学生仍可 select/交卷。P1，strict=True：修复后提醒摘 xfail", strict=True)
    @allure.story("未开始的试卷")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_paper_not_started_rejects_entry(self, admin_client: ApiClient,
                                             student_client: ApiClient,
                                             window_setup: tuple[int, dict]) -> None:
        sid, q = window_setup
        paper_name = f"自动化_未开始卷_{unique_suffix()}"
        paper_id = _create_window_paper(admin_client, sid, q, paper_name,
                                        "2099-01-01 00:00:00", "2999-01-01 00:00:00")
        try:
            resp = student_client.post(f"/api/student/exam/paper/select/{paper_id}", json={})
            assert resp.get("code") != 1, \
                f"未开始的时段试卷竟可进入: code={resp.get('code')} resp={resp}"
        finally:
            try:
                admin_client.post(f"/api/admin/exam/paper/delete/{paper_id}")
            except Exception:
                pass

    @pytest.mark.xfail(reason="D-008：已结束时段试卷 answerSubmit 也不校验时间窗口，能真正交卷生成成绩。P1，strict=True：修复后提醒摘 xfail", strict=True)
    @allure.story("已结束的试卷能真正交卷")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_paper_ended_can_still_submit(self, admin_client: ApiClient,
                                          student_client: ApiClient,
                                          window_setup: tuple[int, dict]) -> None:
        """不只是能进入，还要能真正交卷——证明时间窗口漏洞是完整的。"""
        sid, q = window_setup
        paper_name = f"自动化_已结束交卷_{unique_suffix()}"
        paper_id = _create_window_paper(admin_client, sid, q, paper_name,
                                        "2020-01-01 00:00:00", "2020-01-02 00:00:00")
        try:
            # 1) 先进入
            enter = student_client.post(f"/api/student/exam/paper/select/{paper_id}", json={})
            assert enter.get("code") == 1, "前置：已结束卷子应能进入（D-008）"
            # 2) 直接交卷
            resp = student_client.post("/api/student/exampaper/answer/answerSubmit", json={
                "questionId": None, "doTime": 1,
                "answerItems": [{"questionId": q["id"], "completed": True, "itemOrder": 1,
                                 "content": "A", "contentArray": []}],
                "id": paper_id
            })
            # 预期：时间窗口外应禁止交卷（code != 1）。实测 code=1 成功交卷 → 漏洞
            assert resp.get("code") != 1, \
                f"已结束的时段试卷竟可交卷: code={resp.get('code')} resp={resp}"
        finally:
            try:
                admin_client.post(f"/api/admin/exam/paper/delete/{paper_id}")
            except Exception:
                pass
