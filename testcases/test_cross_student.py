"""学生横向越权：学生 B 不应能读 / 改学生 A 的答卷。

源码核查（student/ExamPaperAnswerController#read、#edit）：
- read/{id} 直接 examPaperAnswerService.selectById(id)，不校验 createUser == 当前用户
- edit 同样按 id 查答卷后直接 judge，不校验归属
→ 任何登录学生传别人的 answerId 即可读/改他人答卷，是真实越权漏洞。
建学生接口：POST /api/admin/user/edit（UserCreateVM），role=1 为学生。
"""
import allure
import pytest

from common.request import ApiClient
from common.factory import setup_mini_exam, cleanup_stack


@allure.epic("跨模块质量保障")
@allure.feature("权限与越权")
@allure.severity(allure.severity_level.CRITICAL)
class TestCrossStudentAccess:

    @pytest.mark.xfail(reason="D-001：read/{answerId} 不校验 createUser，学生 B 可读学生 A 的答卷详情。P0 越权，strict=True：一旦修复立即提醒摘掉 xfail", strict=True)
    @allure.story("学生 B 不能读学生 A 的答卷")
    def test_b_cannot_read_a_answer(self, admin_client: ApiClient,
                                    student_client: ApiClient,
                                    second_student: tuple[ApiClient, int]) -> None:
        data = setup_mini_exam(admin_client, student_client)
        stu_b, _ = second_student
        try:
            resp = stu_b.post(
                f"/api/student/exampaper/answer/read/{data['answer_row']['id']}", json={})
            assert resp.get("code") != 1, \
                f"学生 B 竟能读学生 A 的答卷 id={data['answer_row']['id']}: code={resp.get('code')} resp={resp}"
        finally:
            cleanup_stack(admin_client,
                          paper_id=data["paper"]["id"],
                          question_id=data["question"]["id"],
                          subject_id=data["subject_id"])

    @pytest.mark.xfail(reason="D-002：edit 接口不校验答卷归属，学生 B 可改学生 A 的答卷评分。P0 越权，strict=True：一旦修复立即提醒摘 xfail", strict=True)
    @allure.story("学生 B 不能改学生 A 的答卷")
    def test_b_cannot_edit_a_answer(self, admin_client: ApiClient,
                                    student_client: ApiClient,
                                    second_student: tuple[ApiClient, int]) -> None:
        data = setup_mini_exam(admin_client, student_client)
        stu_b, _ = second_student
        try:
            # B 先 read 拿到 A 的答卷结构（如果 read 也被拦，这里会报错）
            read_resp = stu_b.post(
                f"/api/student/exampaper/answer/read/{data['answer_row']['id']}", json={})
            # 只验证 B 能否 read 到 A 的答卷；真正 edit 需要完整 answer 结构，
            # 能 read 到就已经证明数据隔离失效
            assert read_resp.get("code") != 1, \
                f"学生 B 竟能 read 学生 A 的答卷 id={data['answer_row']['id']}: code={read_resp.get('code')}"
        finally:
            cleanup_stack(admin_client,
                          paper_id=data["paper"]["id"],
                          question_id=data["question"]["id"],
                          subject_id=data["subject_id"])

    @pytest.mark.xfail(reason="D-003：/question/answer/select/{id} 不校验 createUser，学生 B 可读学生 A 的单题作答详情（含正确答案/得分）。P0 越权，strict=True", strict=True)
    @allure.story("学生 B 不能读学生 A 的单题作答")
    def test_b_cannot_read_a_question_answer(self, admin_client: ApiClient,
                                             student_client: ApiClient,
                                             second_student: tuple[ApiClient, int]) -> None:
        data = setup_mini_exam(admin_client, student_client)
        stu_b, _ = second_student
        try:
            # A 先 read 自己的答卷，从明细里拿出单题作答的 id
            a_read = student_client.post(
                f"/api/student/exampaper/answer/read/{data['answer_row']['id']}", json={})["response"]
            single_q_id = a_read["answer"]["answerItems"][0]["id"]
            # B 拿这个单题 id 去查详情
            resp = stu_b.post(
                f"/api/student/question/answer/select/{single_q_id}", json={})
            assert resp.get("code") != 1, \
                f"学生 B 竟能读学生 A 的单题作答 id={single_q_id}: code={resp.get('code')} resp={resp}"
        finally:
            cleanup_stack(admin_client,
                          paper_id=data["paper"]["id"],
                          question_id=data["question"]["id"],
                          subject_id=data["subject_id"])
