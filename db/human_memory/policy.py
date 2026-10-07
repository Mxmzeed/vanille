from __future__ import annotations

from datetime import datetime, timedelta


CLOSED_STATES = {"completed", "cancelled", "superseded", "disputed"}


def stale_after_for(prospective_type: str, observed_at: datetime) -> datetime:
    normalized = prospective_type.casefold()
    if normalized in {"grocery", "list", "need", "shopping"}:
        days = 7
    elif normalized in {"work", "commitment", "task", "deadline"}:
        days = 30
    else:
        days = 14
    return observed_at + timedelta(days=days)


def effective_prospective_state(
    *,
    evidence_state: str,
    now: datetime,
    due_start: datetime | None,
    due_end: datetime | None,
    stale_after: datetime | None,
    prospective_type: str,
    default_duration: timedelta = timedelta(hours=1),
    grace: timedelta = timedelta(minutes=15),
) -> str:
    if evidence_state in CLOSED_STATES:
        return evidence_state
    if evidence_state != "pending":
        return "disputed"
    if due_start is not None:
        transition = (due_end or (due_start + default_duration)) + grace
        if now >= transition:
            return "presumed_occurred"
        return "pending"
    if stale_after is not None and now >= stale_after:
        return "stale_unconfirmed"
    return "pending"


def follow_up_eligible(
    *, effective_state: str, now: datetime, due_start: datetime | None, due_end: datetime | None
) -> bool:
    if effective_state != "presumed_occurred" or due_start is None:
        return False
    occurred_by = due_end or (due_start + timedelta(hours=1))
    return now <= occurred_by + timedelta(hours=72)


def episode_effective_state(
    assembly_state: str, now: datetime, inactivity_deadline: datetime | None
) -> str:
    if assembly_state == "open" and inactivity_deadline and now >= inactivity_deadline:
        return "closed"
    return assembly_state
