"""健壮性 / 异常输入测试：非法枚举、操作不存在资源、软删除一致性。

这些用例不是验证 happy path，而是探测后端容错与校验边界。
其中两条是【已知缺陷】，用 xfail 标记——套件保持绿色，
但在 Allure 报告里能看到"这里存在一个待修复缺陷"，面试时可作为测试发现。
"""
from common.utils import unique_suffix
import time

import allure
import pytest

from common.request import ApiClient
from common.response import assert_success


@pytest.fixture(scope="class")
def probe_subject(admin_client: ApiClient) -> int:
    """建一个真实学科，避免硬编码 subjectId=1 依赖环境。"""
    name = f"自动化_探测学科_{unique_suffix()}"
    assert_success(admin_client.post("/api/admin/education/subject/edit", json={
        "id": None, "name": name, "level": 1, "levelName": "一年级"
    }), "建探测学科")
    subs = admin_client.post("/api/admin/education/subject/list", json={})["response"]
    sid = next(s["id"] for s in subs if s["name"] == name)
    yield sid
    try:
        admin_client.post(f"/api/admin/education/subject/delete/{sid}")
    except Exception:
        pass


@allure.epic("跨模块质量保障")
@allure.feature("健壮性与异常输入")
class TestRobustness:

    @pytest.mark.xfail(reason="已知缺陷：questionType=999 非法枚举未校验，静默入库", strict=False)
    @allure.story("非法枚举值校验")
    @allure.severity(allure.severity_level.NORMAL)
    def test_invalid_question_type_should_be_rejected(self, admin_client: ApiClient, probe_subject: int):
        """传 questionType=999（不存在的题型），后端应拒绝并返回参数错误。

        实测：后端返回 code=1 静默保存，脏数据进库 → 复现"非法枚举零校验"缺陷。
        """
        title = f"自动化_非法题型_{unique_suffix()}"
        resp = admin_client.post("/api/admin/question/edit", json={
            "id": None, "questionType": 999, "gradeLevel": 1, "subjectId": probe_subject,
            "title": title, "items": [{"prefix": "A", "content": "A"}],
            "analyze": "健壮性探测", "correct": "A", "correctArray": None,
            "score": 1, "difficult": 1,
        })
        # 期望：后端应拒绝（code != 1）。若真入库即暴露缺陷。
        try:
            assert resp.get("code") != 1, f"非法题型999竟被接受: {resp}"
        finally:
            # 无论是否触发缺陷，清理这条脏题
            page = admin_client.post("/api/admin/question/page", json={
                "id": None, "questionType": None, "subjectId": probe_subject,
                "pageIndex": 1, "pageSize": 100
            })
            for q in page["response"]["list"]:
                if q.get("shortTitle") == title:
                    admin_client.post(f"/api/admin/question/delete/{q['id']}")

    @pytest.mark.xfail(reason="已知缺陷：编辑不存在的学科 id 静默返回成功，未报'数据不存在'", strict=False)
    @allure.story("操作不存在资源")
    @allure.severity(allure.severity_level.NORMAL)
    def test_edit_nonexistent_subject_should_report_error(self, admin_client: ApiClient):
        """用一个不存在的学科 id（999999）调用编辑接口，后端应提示数据不存在。

        实测：返回 code=1 成功，但库里并无此记录——静默成功、错误码缺失。
        """
        resp = admin_client.post("/api/admin/education/subject/edit", json={
            "id": 999999, "name": "探测不存在", "level": 1, "levelName": "一年级"
        })
        assert resp.get("code") != 1, f"编辑不存在学科竟返回成功: {resp}"

    @allure.story("软删除一致性观察")
    @allure.severity(allure.severity_level.NORMAL)
    def test_select_deleted_subject_still_returns(self, admin_client: ApiClient):
        """软删一个学科后，按 id 详情查询仍能查到（记录型断言，观察现状）。

        观察结论：分页 list 不返回已删数据，但 select/{id} 不过滤 deleted，
        两个通道对"已删除"的处理不一致——是设计特性还是漏过滤，需与开发确认。
        """
        name = f"自动化_软删观察_{unique_suffix()}"
        assert_success(admin_client.post("/api/admin/education/subject/edit", json={
            "id": None, "name": name, "level": 1, "levelName": "一年级"
        }), "建观察学科")
        subs = admin_client.post("/api/admin/education/subject/list", json={})["response"]
        sid = next(s["id"] for s in subs if s["name"] == name)

        # 删除（逻辑删除）
        assert_success(admin_client.post(f"/api/admin/education/subject/delete/{sid}"), "删除学科")

        # 观察：select/{id} 是否仍返回
        read = admin_client.post(f"/api/admin/education/subject/select/{sid}", json={})
        assert read.get("code") == 1, f"软删后 select 应仍能查到（记录现状），实际={read}"
        assert read["response"]["name"] == name, "select 返回的学科名不符"
