"""任务年级隔离：年级1学生能看到 gradeLevel=1 的任务，年级2学生看不到。"""
from common.utils import unique_suffix
import time

import allure
import pytest

from common.request import ApiClient
from common.response import assert_success
from config.settings import settings


def _create_student(admin: ApiClient, name: str, user_level: int) -> tuple[ApiClient, int]:
    """建学生并登录，返回 (student_client, user_id)。"""
    resp = admin.post("/api/admin/user/edit", json={
        "id": None, "userName": name, "password": settings.student_password,
        "realName": f"自动化_{name}", "role": 1, "userLevel": user_level,
        "status": 1,
    })
    assert_success(resp, f"建学生 {name}")
    uid = resp["response"]["id"]

    client = ApiClient()
    login = client.post("/api/user/login", json={
        "userName": name, "password": settings.student_password, "remember": False
    })
    assert_success(login, f"学生 {name} 登录")
    return client, uid


@allure.epic("管理端后台")
@allure.feature("考试任务")
class TestTaskGradeIsolation:

    @allure.story("不同年级互不可见任务")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_task_visible_only_to_same_grade(self, admin_client: ApiClient):
        """TASK-002：发布 gradeLevel=1 的任务，年级1学生可见、年级2学生不可见。"""
        ts = unique_suffix()

        # 1) 建学科 + 题 + 任务卷
        subj_name = f"自动化_隔离学科_{ts}"
        assert_success(admin_client.post("/api/admin/education/subject/edit", json={
            "id": None, "name": subj_name, "level": 1, "levelName": "一年级"
        }), "建学科")
        sid = next(s["id"] for s in admin_client.post(
            "/api/admin/education/subject/list", json={})["response"] if s["name"] == subj_name)

        admin_client.post("/api/admin/question/edit", json={
            "id": None, "questionType": 1, "gradeLevel": 1, "subjectId": sid,
            "title": f"自动化_隔离题_{ts}",
            "items": [{"prefix": "A", "content": "A"}, {"prefix": "B", "content": "B"}],
            "analyze": "x", "correct": "A", "correctArray": None,
            "score": 1, "difficult": 1,
        })
        q = next(q for q in admin_client.post("/api/admin/question/page", json={
            "id": None, "questionType": None, "subjectId": sid,
            "pageIndex": 1, "pageSize": 10
        })["response"]["list"])

        paper_name = f"自动化_隔离卷_{ts}"
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

        task_title = f"自动化_隔离任务_{ts}"
        task_resp = admin_client.post("/api/admin/task/edit", json={
            "id": None, "gradeLevel": 1, "title": task_title, "paperItems": [paper]
        })
        assert_success(task_resp, "发布年级1任务")
        task_id = task_resp["response"]["id"]

        # 2) 建两个学生：年级1 和 年级2
        stu1_name = f"自动化_g1_{ts}"
        stu2_name = f"自动化_g2_{ts}"
        stu1, uid1 = _create_student(admin_client, stu1_name, user_level=1)
        stu2, uid2 = _create_student(admin_client, stu2_name, user_level=2)

        try:
            # 3) 年级1学生应看到任务
            tasks1 = stu1.post("/api/student/dashboard/task", json={})["response"]
            titles1 = [t["title"] for t in tasks1]
            assert task_title in titles1, \
                f"年级1学生看不到本年级任务: 实际={titles1}"

            # 4) 年级2学生不应看到任务
            tasks2 = stu2.post("/api/student/dashboard/task", json={})["response"]
            titles2 = [t["title"] for t in tasks2]
            assert task_title not in titles2, \
                f"年级2学生竟看到了年级1的任务: 实际={titles2}"
        finally:
            # 清理
            for uid in (uid1, uid2):
                try:
                    admin_client.post(f"/api/admin/user/delete/{uid}")
                except Exception:
                    pass
            try:
                admin_client.post(f"/api/admin/task/delete/{task_id}")
            except Exception:
                pass
            try:
                admin_client.post(f"/api/admin/exam/paper/delete/{paper['id']}")
            except Exception:
                pass
            try:
                admin_client.post(f"/api/admin/question/delete/{q['id']}")
            except Exception:
                pass
            try:
                admin_client.post(f"/api/admin/education/subject/delete/{sid}")
            except Exception:
                pass
