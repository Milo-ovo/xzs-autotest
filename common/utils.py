import time
import uuid
from typing import Any, Iterable


def unique_suffix() -> str:
    """生成测试数据唯一后缀：时间戳 + 短 uuid，避免同秒并行撞名。

    替代裸 int(time.time())：串行跑看不出差别，一旦 pytest-xdist 并行
    或同一秒内两个用例启动，纯时间戳会撞名导致建数据互相干扰。
    """
    return f"{int(time.time())}_{uuid.uuid4().hex[:6]}"


def must_find(rows: Iterable[dict], **eq: Any) -> dict:
    """从行集合里按字段精确匹配一条，找不到时带上下文断言失败。

    替代裸 next(... for ... if ... == ...)：后者找不到会抛
    RuntimeError: generator raised StopIteration，看不到 rows 到底是什么。
    这里把匹配条件和前 5 条样例行一起打出来，定位"主从延迟/名称没命中"
    类问题快很多。

    用法：
        subject = must_find(subjects, name="自动化_学科_xxx")
        sid = subject["id"]
    """
    rows = list(rows)
    for row in rows:
        if all(row.get(k) == v for k, v in eq.items()):
            return row
    raise AssertionError(
        f"未找到匹配 {eq!r} 的记录；共 {len(rows)} 条，前 5 条样例：{rows[:5]}"
    )


def must_find_id(rows: Iterable[dict], field: str, value: Any) -> Any:
    """must_find 的简写：按 field==value 找一条并返回其 id。"""
    return must_find(rows, **{field: value})["id"]


