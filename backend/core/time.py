"""统一时间工具。

后端持久化仍以 naive UTC datetime 兼容现有 DateTime 字段；对外接口使用带 Z 的 UTC ISO 字符串。
"""

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

APP_TIMEZONE_NAME = "Asia/Shanghai"
APP_TIMEZONE = ZoneInfo(APP_TIMEZONE_NAME)
UTC_MAX_NAIVE = datetime.max.replace(tzinfo=None)


def utc_now() -> datetime:
    """返回带时区信息的 UTC 当前时间。"""
    return datetime.now(UTC)


def normalize_to_utc(value: datetime) -> datetime:
    """将 aware 或 naive UTC datetime 归一为带时区的 UTC 时间。"""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def utc_now_naive() -> datetime:
    """返回 naive UTC 当前时间，用于兼容现有数据库 DateTime 字段。"""
    return utc_now().replace(tzinfo=None)


def utc_max_naive() -> datetime:
    """返回 naive UTC 最大时间，用作排序兜底哨兵值。"""
    return UTC_MAX_NAIVE


def utc_now_iso() -> str:
    """返回 API 友好的 UTC ISO 字符串。"""
    return to_utc_iso(utc_now())


def to_utc_iso(value: datetime) -> str:
    """将 aware 或 naive UTC datetime 统一转为带 Z 的 ISO 字符串。"""
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.isoformat().replace("+00:00", "Z")


def to_utc_iso_or_none(value: datetime | None) -> str | None:
    """将可空 datetime 统一转为带 Z 的 ISO 字符串。"""
    if value is None:
        return None
    return to_utc_iso(value)


def normalize_api_datetime(value: Any) -> Any:
    """递归把 API 响应中的 datetime 统一转为 UTC ISO Z 字符串。"""
    if isinstance(value, datetime):
        return to_utc_iso(value)
    if isinstance(value, list):
        return [normalize_api_datetime(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_api_datetime(item) for key, item in value.items()}
    return value


def app_now() -> datetime:
    """返回平台当前时区时间。"""
    return datetime.now(APP_TIMEZONE)


def app_day_start_as_utc_naive(value: datetime | None = None) -> datetime:
    """返回平台当前日零点对应的 naive UTC 时间，用于现有 DB 查询边界。"""
    local_value = value.astimezone(APP_TIMEZONE) if value else app_now()
    local_start = local_value.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(UTC).replace(tzinfo=None)
