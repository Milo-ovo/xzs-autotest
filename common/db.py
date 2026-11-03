"""MySQL 查询工具：用于接口响应之外的数据库双重断言。

采用模块级单例连接，避免每次查询都 TCP 握手；断连自动重连。
进程退出时通过 atexit 自动关闭连接，避免悬挂。
"""
import atexit
import logging
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from config.settings import settings

logger = logging.getLogger(__name__)

_conn: pymysql.connections.Connection | None = None


def _get_conn() -> pymysql.connections.Connection:
    """lazy 建连，断了自动重连。"""
    global _conn
    if _conn is not None and _conn.open:
        try:
            _conn.ping(reconnect=False)
            return _conn
        except pymysql.Error:
            logger.warning("数据库连接断开，准备重连")
    _conn = pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,  # 只读断言为主，省去 commit
        connect_timeout=5,  # MySQL hang 住时别无限等，5s 内连不上直接报错
    )
    return _conn


def _close_conn() -> None:
    """进程退出时关闭连接（atexit 注册）。"""
    global _conn
    if _conn is not None and _conn.open:
        try:
            _conn.close()
        except Exception:
            pass
    _conn = None


atexit.register(_close_conn)


def query_one(sql: str, args: tuple[Any, ...] = ()) -> dict | None:
    with _get_conn().cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone()


def query_all(sql: str, args: tuple[Any, ...] = ()) -> list[dict]:
    with _get_conn().cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()
