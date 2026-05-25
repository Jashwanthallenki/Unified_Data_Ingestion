"""Parsing and math helpers shared by all adapters."""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y%m%d",
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%fZ",
]


def parse_date(value: object) -> date | None:
    """Parse a date string in any of several common formats. Returns None on failure."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    if not s:
        return None
    # Try direct ISO first; very common.
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def detect_date_format(samples: list[str]) -> str | None:
    """Return one of {ISO, DMY_DOT, DMY_SLASH, MDY_SLASH, COMPACT} or None if undetermined."""
    counters = {"ISO": 0, "DMY_DOT": 0, "DMY_SLASH": 0, "MDY_SLASH": 0, "COMPACT": 0}
    for s in samples:
        if not s:
            continue
        s = s.strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}", s):
            counters["ISO"] += 1
        elif re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", s):
            counters["DMY_DOT"] += 1
        elif re.match(r"^\d{8}$", s):
            counters["COMPACT"] += 1
        elif re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", s):
            # ambiguous DMY/MDY — leave undecided unless one digit is > 12
            try:
                first, second = s.split("/")[:2]
                if int(first) > 12:
                    counters["DMY_SLASH"] += 1
                elif int(second) > 12:
                    counters["MDY_SLASH"] += 1
            except ValueError:
                pass
    if not any(counters.values()):
        return None
    return max(counters, key=counters.get)


_EU_THOUSANDS_DOT_DECIMAL_COMMA = re.compile(r"^-?\d{1,3}(\.\d{3})+,\d+$")
_US_THOUSANDS_COMMA_DECIMAL_DOT = re.compile(r"^-?\d{1,3}(,\d{3})+\.\d+$")


def parse_decimal(value: object) -> Decimal | None:
    """Parse a number that may be in US, EU, or plain format. Returns None on failure."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    # EU explicit: 5.000,000
    if _EU_THOUSANDS_DOT_DECIMAL_COMMA.match(s):
        s = s.replace(".", "").replace(",", ".")
    # US explicit: 5,000.000
    elif _US_THOUSANDS_COMMA_DECIMAL_DOT.match(s):
        s = s.replace(",", "")
    else:
        # Heuristic: if there is exactly one comma and no decimal point, treat comma as decimal.
        if "," in s and "." not in s:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def calendar_month_overlaps(period_start: date, period_end: date) -> list[tuple[date, int]]:
    """Return [(first_of_month, days_in_month_overlap), ...] for every calendar month
    overlapping [period_start, period_end] inclusive.
    """
    from calendar import monthrange

    if period_start > period_end:
        return []
    result: list[tuple[date, int]] = []
    cursor = date(period_start.year, period_start.month, 1)
    end = date(period_end.year, period_end.month, 1)
    while cursor <= end:
        last_dom = monthrange(cursor.year, cursor.month)[1]
        m_start = cursor
        m_end = date(cursor.year, cursor.month, last_dom)
        ov_start = max(m_start, period_start)
        ov_end = min(m_end, period_end)
        days = (ov_end - ov_start).days + 1
        if days > 0:
            result.append((m_start, days))
        # advance to next month
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return result


def safe_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()
