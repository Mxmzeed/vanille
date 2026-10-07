from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from human_memory.models import TemporalPrecision, TemporalResolution


_ISO_DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_CLOCK = re.compile(
    r"(?:\bat\s+(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\b|"
    r"\b(\d{1,2}):(\d{2})\s*(a\.?m\.?|p\.?m\.?)?\b|"
    r"\b(\d{1,2})\s*(a\.?m\.?|p\.?m\.?)\b)",
    re.I,
)
_RELATIVE_DAYS = {
    "yesterday": -1,
    "today": 0,
    "tomorrow": 1,
    "tmrw": 1,
    "tmw": 1,
    "tonight": 0,
}
_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _clock(expression: str) -> time | None:
    match = _CLOCK.search(expression)
    if match is None:
        return None
    hour = int(match.group(1) or match.group(4) or match.group(7))
    minute = int(match.group(2) or match.group(5) or 0)
    suffix = (match.group(3) or match.group(6) or match.group(8) or "").casefold().replace(".", "")
    if minute > 59 or hour > 23:
        return None
    if suffix:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if suffix == "pm" else 0)
    return time(hour, minute)


def resolve_temporal_expression(
    expression: str,
    observed_at: datetime,
    timezone_name: str,
    *,
    future_facing: bool = False,
) -> TemporalResolution:
    if not expression.strip():
        return TemporalResolution(None, None, TemporalPrecision.UNKNOWN, 0.0)
    zone = ZoneInfo(timezone_name)
    local_observed = observed_at.astimezone(zone)
    lowered = expression.casefold()
    target_date = None
    precision = TemporalPrecision.UNKNOWN

    iso = _ISO_DATE.search(expression)
    if iso:
        try:
            target_date = datetime(
                int(iso.group(1)), int(iso.group(2)), int(iso.group(3)), tzinfo=zone
            ).date()
            precision = TemporalPrecision.DAY
        except ValueError:
            return TemporalResolution(None, None, TemporalPrecision.UNKNOWN, 0.0)
    else:
        for token, delta in _RELATIVE_DAYS.items():
            if re.search(rf"\b{token}\b", lowered):
                target_date = (local_observed + timedelta(days=delta)).date()
                precision = TemporalPrecision.RELATIVE_RESOLVED
                break

    if target_date is None:
        weekday_match = re.search(
            r"\b(?:(last|next)\s+)?(" + "|".join(_WEEKDAYS) + r")\b", lowered
        )
        if weekday_match:
            direction = weekday_match.group(1)
            weekday = _WEEKDAYS[weekday_match.group(2)]
            current = local_observed.weekday()
            if direction == "last":
                delta = -((current - weekday) % 7 or 7)
            elif direction == "next" or future_facing:
                delta = (weekday - current) % 7 or 7
            else:
                delta = -((current - weekday) % 7)
            target_date = (local_observed + timedelta(days=delta)).date()
            precision = TemporalPrecision.RELATIVE_RESOLVED

    parsed_clock = _clock(expression)
    if target_date is None and parsed_clock is not None and future_facing:
        target_date = local_observed.date()
        candidate = datetime.combine(target_date, parsed_clock, zone)
        if candidate <= local_observed:
            target_date += timedelta(days=1)
        precision = TemporalPrecision.RELATIVE_RESOLVED

    if target_date is None:
        return TemporalResolution(None, None, TemporalPrecision.UNKNOWN, 0.0)
    if parsed_clock is not None:
        start = datetime.combine(target_date, parsed_clock, zone)
        return TemporalResolution(start, None, TemporalPrecision.INSTANT, 0.95)
    start = datetime.combine(target_date, time.min, zone)
    end = datetime.combine(target_date, time.max, zone)
    return TemporalResolution(start, end, precision, 0.9)
