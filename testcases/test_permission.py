"""权限隔离测试：验证学生不能访问管理端接口、未登录不能访问受保护接口。

错误码约定（源码+抓包实测）：
  code=401 未登录（JSESSIONID 缺失/失效）
  code=502 已登录但越权（学生访问 /api/admin/**）
"""
import pytest
import allure

from common.request import ApiClient
from common.response import assert_success, assert_fail
from common.factory import setup_mini_exam, cleanup_stack


@allure.epic("跨模块质量保障")
@allure.feature("权限与越权")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.smoke
class TestPermission:
    """角色越权防护（P0 安全测试场景）。纳入冒烟：每次回归必跑。"""

    def test_student_cannot_list_admin_subjects(self, student_client: ApiClient):
        """学生会话请求管理端学科列表，应被拒绝（502）。"""
        resp = student_client.post("/api/admin/education/subject/list", json={})
        assert_fail(resp, 502)

    def test_student_cannot_page_admin_questions(self, student_client: ApiClient):
        """学生会话请求管理端题目分页，应被拒绝（502）。"""
        resp = student_client.post("/api/admin/question/page", json={
            "id": None, "questionType": None, "subjectId": None,
            "pageIndex": 1, "pageSize": 10
        })
        assert_fail(resp, 502)

    def test_student_cannot_edit_question(self, student_client: ApiClient):
        """学生会话尝试新建题目（写操作），应被拒绝（502）。

        subjectId 传 None：这是越权测试，后端应在鉴权层就拦，
        不依赖环境里某个具体学科 id 存在。
        """
        resp = student_client.post("/api/admin/question/edit", json={
            "id": None, "questionType": 1, "gradeLevel": 1,
            "subjectId": None, "title": "越权题目", "items": [],
            "analyze": "", "correct": "A", "correctArray": None,
            "score": 1, "difficult": 1
        })
        assert_fail(resp, 502)

    def test_anonymous_cannot_access_admin_api(self, raw_client: ApiClient):
        """未登录裸会话请求管理端接口，应返回 401。"""
        resp = raw_client.post("/api/admin/education/subject/list", json={})
        assert_fail(resp, 401)

    def test_anonymous_cannot_access_student_exam(self, raw_client: ApiClient):
        """未登录裸会话请求学生端考试接口，应返回 401。"""
        resp = raw_client.post("/api/student/dashboard/task", json={})
        assert_fail(resp, 401)

    def test_admin_can_access_admin_api(self, admin_client: ApiClient):
        """对照组：管理员请求管理端接口正常返回。"""
        resp = admin_client.post("/api/admin/education/subject/list", json={})
        assert_success(resp, "管理员查询学科列表")

    @allure.story("数据隔离")
    def test_student_answer_list_is_scoped_to_self(self, admin_client: ApiClient,
                                                   student_client: ApiClient,
                                                   second_student: tuple):
        """PERM-003：学生 B 查考试记录只能看到自己的，看不到学生 A 交的卷。

        对照组：A 交卷后能在自己列表看到；B（全新学生）查自己列表，
        不应出现 A 的卷名。之前只断言"返回是 list"，没有真隔离验证。
        """
        stu_b, _ = second_student
        data = setup_mini_exam(admin_client, student_client)
        paper_name = data["paper"]["name"]
        try:
            # 对照组：A 能在自己列表看到这张卷
            a_list = student_client.post("/api/student/exampaper/answer/pageList", json={
                "pageIndex": 1, "pageSize": 50
            })["response"]["list"]
            assert any(a.get("paperName") == paper_name for a in a_list), \
                f"A 交卷后应在自己列表里看到 {paper_name}"
            # B 查自己列表，不应出现 A 的卷
            b_list = stu_b.post("/api/student/exampaper/answer/pageList", json={
                "pageIndex": 1, "pageSize": 50
            })["response"]["list"]
            assert not any(a.get("paperName") == paper_name for a in b_list), \
                f"B 竟在自己答卷列表里看到了 A 的卷 {paper_name}: {b_list}"
        finally:
            cleanup_stack(admin_client,
                          paper_id=data["paper"]["id"],
                          question_id=data["question"]["id"],
                          subject_id=data["subject_id"])
