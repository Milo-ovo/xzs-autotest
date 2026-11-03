import logging
import re
from pathlib import Path

import allure
import pytest

from common.request import ApiClient
from common.db import query_one
from common.utils import unique_suffix
from config.settings import settings

logger = logging.getLogger(__name__)

# 用例编号正则：匹配 LOGIN-001、SUBJ-003、D-001、PERM-003、QUES-008 这类
# 注意：D-001 只有 1 个字母，所以下界是 {1,}
_CASE_ID_RE = re.compile(r"\b([A-Z]{1,}-\d{3})\b")


def pytest_configure(config):
    """同时输出到控制台和 reports/test.log，长回归可回溯。"""
    report_dir = Path("reports")
    report_dir.mkdir(exist_ok=True)
    log_file = report_dir / "test.log"

    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # 清掉 basicConfig 可能加过的 handler，避免重复
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(logging.StreamHandler())
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(file_handler)


def pytest_collection_modifyitems(config, items):
    """全局集成开关：RUN_INTEGRATION=false 时跳过所有真实接口用例。

    本项目没有纯单测，全部用例都依赖本地服务，统一在此兜底，
    避免每个用例文件各自挂 skipif 造成遗漏。
    """
    if not settings.run_integration:
        skip = pytest.mark.skip(reason="RUN_INTEGRATION=false，跳过真实接口请求")
        for item in items:
            item.add_marker(skip)


def pytest_runtest_setup(item):
    """从用例 docstring 自动提取用例编号（LOGIN-001 等），打到 Allure 报告。

    这样 Allure 里能按 case_id 筛选，和《测试用例表.csv》双向对得上。
    没写编号的用例不受影响。
    """
    doc = (item.obj.__doc__ or "") + " " + (getattr(item, "originalname", "") or "")
    m = _CASE_ID_RE.search(doc)
    if m:
        case_id = m.group(1)
        item.user_properties.append(("case_id", case_id))
        try:
            allure.dynamic.label("case_id", case_id)
            allure.dynamic.tag(case_id)
        except Exception:
            pass


@pytest.fixture(scope="session", autouse=True)
def _health_check():
    """跑真实用例前先探活：BASE_URL 可达 + 登录业务通 + MySQL 可连，否则快速失败。

    避免服务没起时几十条用例逐个报"请求失败"，错误分散难定位。
    """
    if not settings.run_integration:
        yield
        return
    # 1) HTTP 探活 + 业务探活：用登录接口探，5s 内不通或业务失败直接退出
    import requests as _req
    try:
        resp = _req.post(
            f"{settings.api_base_url}/api/user/login",
            json={"userName": settings.admin_user, "password": settings.admin_password,
                  "remember": False},
            timeout=5,
        )
        payload = resp.json()
    except Exception as exc:
        pytest.exit(
            f"❌ 学之思服务不可达（{settings.api_base_url}）：{exc}\n"
            f"   请先启动后端服务，或把 .env 里 RUN_INTEGRATION 改回 false。",
            returncode=3,
        )
    if payload.get("code") != 1:
        pytest.exit(
            f"❌ 学之思服务虽可达，但管理员登录业务失败：{payload}\n"
            f"   请检查 .env 里 ADMIN_USER/ADMIN_PASSWORD 是否与目标环境一致，或后端 DB 是否正常。",
            returncode=3,
        )
    # 2) DB 探活
    try:
        query_one("SELECT 1")
    except Exception as exc:
        pytest.exit(f"❌ MySQL 不可达（{settings.db_host}:{settings.db_port}/{settings.db_name}）：{exc}",
                    returncode=3)
    yield


# 未登录的裸 client，专供"登录接口本身"的用例使用
@pytest.fixture
def raw_client() -> ApiClient:
    return ApiClient()


# 管理员会话：整个测试会话登录一次，独立 session
@pytest.fixture(scope="session")
def admin_client():
    client = ApiClient()
    resp = client.login("admin")
    assert resp.get("code") == 1, f"管理员登录失败: {resp}"
    return client


# 学生会话：另一个独立 session，不和 admin 共用
@pytest.fixture(scope="session")
def student_client():
    client = ApiClient()
    resp = client.login("student")
    assert resp.get("code") == 1, f"学生登录失败: {resp}"
    return client


# 临时学生 B：建一个全新学生并登录，返回 (client, user_id)。
# 用于横向越权 / 数据隔离类测试（PERM-003/004/005）。每个 module 独立建一个，用完即删。
@pytest.fixture(scope="module")
def second_student(admin_client: ApiClient):
    ts = unique_suffix()
    stu_name = f"autotest_stu_{ts}"
    resp = admin_client.post("/api/admin/user/edit", json={
        "id": None, "userName": stu_name, "password": settings.student_password,
        "realName": f"自动化学生{ts}", "role": 1, "userLevel": 1, "status": 1,
    })
    assert resp.get("code") == 1, f"建第二个学生失败: {resp}"
    stu_id = resp["response"]["id"]

    client = ApiClient()
    login = client.post("/api/user/login", json={
        "userName": stu_name, "password": settings.student_password, "remember": False
    })
    assert login.get("code") == 1, f"第二个学生登录失败: {login}"

    yield client, stu_id
    if stu_id:
        try:
            admin_client.post(f"/api/admin/user/delete/{stu_id}")
        except Exception:
            pass


# 注：会话结束后自动大扫除的逻辑已移到独立脚本 cleanup_test_data.py，
# 需要清理测试数据时手动运行：python cleanup_test_data.py
