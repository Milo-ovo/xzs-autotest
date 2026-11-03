"""题目管理模块测试：参数化覆盖 5 种题型，必填项校验。

每个用例类共用一个学科，建题完统一清理学科和题目。
"""
from common.utils import unique_suffix
import time

import pytest
import allure

from common.request import ApiClient
from common.response import assert_success


@pytest.fixture(scope="class")
def question_subject(admin_client: ApiClient):
    """为本测试类建一个学科，类结束后连题带学科一起删。"""
    name = f"自动化_题目学科_{unique_suffix()}"
    admin_client.post("/api/admin/education/subject/edit", json={
        "id": None, "name": name, "level": 1, "levelName": "一年级"
    })
    resp = admin_client.post("/api/admin/education/subject/list", json={})
    subject = next(s for s in resp["response"] if s["name"] == name and not s.get("deleted"))
    yield subject["id"]
    # 清理：先删该学科下所有题，再删学科
    page = admin_client.post("/api/admin/question/page", json={
        "id": None, "questionType": None, "subjectId": subject["id"],
        "pageIndex": 1, "pageSize": 100
    })
    for q in page["response"]["list"]:
        try:
            admin_client.post(f"/api/admin/question/delete/{q['id']}")
        except Exception:
            pass
    try:
        admin_client.post(f"/api/admin/education/subject/delete/{subject['id']}")
    except Exception:
        pass


# (questionType, label, items, correct, correctArray)
QUESTION_SPECS = [
    pytest.param(1, "单选题",
                 [{"prefix": "A", "content": "选项A"}, {"prefix": "B", "content": "选项B"}],
                 "B", None, id="单选题"),
    pytest.param(2, "多选题",
                 [{"prefix": "A", "content": "选项A"}, {"prefix": "B", "content": "选项B"}, {"prefix": "C", "content": "选项C"}],
                 "A,C", ["A", "C"], id="多选题"),
    pytest.param(3, "判断题",
                 [{"prefix": "A", "content": "正确"}, {"prefix": "B", "content": "错误"}],
                 "A", None, id="判断题"),
    pytest.param(4, "填空题",
                 [{"prefix": "1", "content": "标准答案", "score": "2", "itemUuid": "fill-t1"}],
                 "", ["标准答案"], id="填空题"),
    pytest.param(5, "简答题",
                 [], "主观参考答案", None, id="简答题"),
]


@pytest.mark.parametrize("qtype,label,items,correct,correct_array", QUESTION_SPECS)
@allure.epic("管理端后台")
@allure.feature("题目管理")
@allure.story("多题型建题")
class TestCreateQuestion:
    """参数化建 5 种题型，每种都应创建成功。"""

    def test_create_question_by_type(self, admin_client: ApiClient, question_subject,
                                     qtype, label, items, correct, correct_array):
        title = f"自动化_{label}_{unique_suffix()}"
        resp = admin_client.post("/api/admin/question/edit", json={
            "id": None, "questionType": qtype, "gradeLevel": 1,
            "subjectId": question_subject, "title": title,
            "items": items, "analyze": "自动化解析",
            "correct": correct, "correctArray": correct_array,
            "score": 2, "difficult": 1,
        })
        assert_success(resp, f"新建{label}")

        # 确认能查到
        page = admin_client.post("/api/admin/question/page", json={
            "id": None, "questionType": qtype, "subjectId": question_subject,
            "pageIndex": 1, "pageSize": 50
        })
        titles = [q["shortTitle"] for q in page["response"]["list"]]
        assert title in titles, f"{label}建完后分页查不到"


@allure.epic("管理端后台")
@allure.feature("题目管理")
@allure.story("边界校验")
class TestQuestionValidation:
    """题目必填项/边界校验。"""

    def test_create_question_missing_title_fails(self, admin_client: ApiClient, question_subject):
        """题目标题为空应失败。"""
        resp = admin_client.post("/api/admin/question/edit", json={
            "id": None, "questionType": 1, "gradeLevel": 1,
            "subjectId": question_subject, "title": "", "items": [],
            "analyze": "", "correct": "A", "correctArray": None,
            "score": 1, "difficult": 1
        })
        assert resp.get("code") != 1, f"空标题竟然创建成功: {resp}"

    @pytest.mark.xfail(reason="D-005：题目分值允许负数(-5/-1/0)，未做 >=0 校验；客观题答对会判负分。P1，strict=True：修复后提醒摘 xfail", strict=True)
    def test_create_question_negative_score_fails(self, admin_client: ApiClient, question_subject):
        """题目分值为负数应被拒绝（analyze 等其余字段合法，确保打到 score 校验本身）。"""
        resp = admin_client.post("/api/admin/question/edit", json={
            "id": None, "questionType": 1, "gradeLevel": 1,
            "subjectId": question_subject, "title": f"自动化_负分题_{unique_suffix()}",
            "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
            "analyze": "x", "correct": "A", "correctArray": None,
            "score": -5, "difficult": 1
        })
        assert resp.get("code") != 1, f"负分值竟然创建成功: {resp}"
