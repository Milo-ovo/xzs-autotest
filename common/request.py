import json
import logging
from typing import Any

import allure
import requests

from config.settings import settings

logger = logging.getLogger(__name__)

# 日志和报告中需要打码的敏感字段
_SENSITIVE_FIELDS = {"password", "oldPassword", "newPassword"}


def _mask_sensitive(payload: Any) -> Any:
    """递归把密码类字段替换为 ******，避免凭据落进日志/Allure 附件。"""
    if isinstance(payload, dict):
        return {
            k: ("******" if k in _SENSITIVE_FIELDS else _mask_sensitive(v))
            for k, v in payload.items()
        }
    if isinstance(payload, list):
        return [_mask_sensitive(v) for v in payload]
    return payload


class ApiClient:
    """带 Cookie 持久化、统一日志和错误处理的 HTTP 客户端。"""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json;charset=UTF-8"})

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{settings.api_base_url}/{path.lstrip('/')}"
        body = kwargs.get("json")
        try:
            response = self.session.request(
                method=method.upper(), url=url, timeout=settings.request_timeout, **kwargs
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            logger.error("%s %s 请求失败：%s", method.upper(), url, exc)
            raise AssertionError(f"接口请求失败：{method.upper()} {url}，错误：{exc}") from exc
        except ValueError as exc:
            logger.error("%s %s 响应非 JSON：%.500s", method.upper(), url, response.text)
            raise AssertionError(
                f"响应不是 JSON：{method.upper()} {url}，内容：{response.text}"
            ) from exc

        safe_body = _mask_sensitive(body)
        # 业务失败（code != 1）打 WARNING，方便从 INFO 日志里直接筛出失败现场
        log_line = "%s %s request=%s response=%s"
        if payload.get("code") != 1:
            logger.warning(log_line, method.upper(), url, safe_body, payload)
        else:
            logger.info(log_line, method.upper(), url, safe_body, payload)
        # 失败现场可在 Allure 报告里直接展开请求/响应（密码已打码）
        try:
            allure.attach(
                f"{method.upper()} {url}\n"
                f"请求: {json.dumps(safe_body, ensure_ascii=False)}\n"
                f"响应: {json.dumps(payload, ensure_ascii=False)}",
                name=f"{method.upper()} {path}",
                attachment_type=allure.attachment_type.TEXT,
            )
        except Exception:
            # allure 未激活（如脱离 pytest 直接调用）时静默跳过
            pass
        return payload

    def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("POST", path, **kwargs)

    def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("GET", path, **kwargs)

    def login(self, role: str = "admin") -> dict[str, Any]:
        username = settings.admin_user if role == "admin" else settings.student_user
        password = settings.admin_password if role == "admin" else settings.student_password
        resp = self.post("/api/user/login", json={"userName": username, "password": password, "remember": False})
        assert resp.get("code") == 1, f"{role} 登录失败: {resp}"
        return resp
