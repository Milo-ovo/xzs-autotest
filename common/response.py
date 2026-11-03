import logging
from typing import Any

logger = logging.getLogger(__name__)


def assert_success(response: dict[str, Any], message: str = "接口请求成功") -> None:
    """断言业务成功：只认 code==1。

    历史版本会额外断言 message=="成功"，但学之思不同接口成功文案不一致
    （有的返回"成功"，有的返回 null/空串/其他），硬比对会误红。
    message 非空但不等于"成功"时只打 warning，不阻断用例。
    """
    assert response.get("code") == 1, (
        f"{message}，实际 code={response.get('code')}，响应={response}"
    )
    msg = response.get("message")
    if msg and msg != "成功":
        logger.warning("%s 成功响应 message 非标准值：%s（已忽略，不阻断）", message, msg)


def assert_fail(
    response: dict[str, Any], expected_code: int, expected_message: str = ""
) -> None:
    assert response.get("code") == expected_code, (
        f"期望错误码={expected_code}，实际={response.get('code')}，响应={response}"
    )
    if expected_message:
        assert expected_message in str(response.get("message", ""))

