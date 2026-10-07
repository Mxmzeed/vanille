from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from human_memory import storage
from human_memory.policy import (
    effective_prospective_state,
    episode_effective_state,
    follow_up_eligible,
)
from memory.contracts import (
    MemoryCandidateResult,
    MemoryContext,
    MemoryKind,
    RetrievalMode,
    RetrievalRequest,
)
from memory.helpers.openai_embed import get_embedding

_PROSPECTIVE = re.compile(
    r"\b(?:need|needed|todo|to-do|work on|working on|task|grocery|buy|meeting|"
    r"deadline|plan|planned|upcoming|supposed to)\b",
    re.I,
)
_EPISODIC = re.compile(
    r"\b(?:happened|last time|what did|when did|why did|how did|tried|before|"
    r"earlier|episode|experience|decision|history)\b",
    re.I,
)
_MONTHS = {
    name: index
    for index, name in enumerate(
        (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ),
        1,
    )
}


def query_intent(query: str) -> str:
    prospective = bool(_PROSPECTIVE.search(query))
    episodic = bool(_EPISODIC.search(query))
    if prospective and episodic:
        return "hybrid"
    if prospective:
        return "prospective"
    if episodic:
        return "episodic"
    return "semantic"


def query_time_bounds(
    query: str, owner_local_time: datetime | None
) -> tuple[datetime, datetime] | None:
    if owner_local_time is None:
        return None
    local = owner_local_time
    lowered = query.casefold()
    day = None
    if "yesterday" in lowered:
        day = local.date() - timedelta(days=1)
    elif re.search(r"\btoday\b", lowered):
        day = local.date()
    if day:
        start = datetime.combine(day, datetime.min.time(), local.tzinfo)
        return start, start + timedelta(days=1)
    if "last week" in lowered:
        this_monday = local - timedelta(days=local.weekday())
        start = datetime.combine(
            (this_monday - timedelta(days=7)).date(), datetime.min.time(), local.tzinfo
        )
        return start, start + timedelta(days=7)
    iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", lowered)
    if iso:
        start = datetime(
            int(iso.group(1)), int(iso.group(2)), int(iso.group(3)), tzinfo=local.tzinfo
        )
        return start, start + timedelta(days=1)
    for name, month in _MONTHS.items():
        if re.search(rf"\b{name}\b", lowered):
            year_match = re.search(r"\b(20\d{2})\b", lowered)
            year = int(year_match.group(1)) if year_match else local.year
            if not year_match and month > local.month:
                year -= 1
            start = datetime(year, month, 1, tzinfo=local.tzinfo)
            end = datetime(
                year + (month == 12), (month % 12) + 1, 1, tzinfo=local.tzinfo
            )
            return start, end
    year_match = re.search(r"\b(?:in\s+)?(20\d{2})\b", lowered)
    if year_match:
        year = int(year_match.group(1))
        return datetime(year, 1, 1, tzinfo=local.tzinfo), datetime(
            year + 1, 1, 1, tzinfo=local.tzinfo
        )
    return None


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _merge_rows(
    vector: list[dict[str, Any]], keyword: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    for source, rows in (("vector", vector), ("keyword", keyword)):
        for row in rows:
            candidate = combined.setdefault(row["id"], dict(row))
            candidate["score"] = max(
                float(candidate.get("score", 0)), float(row.get("score", 0))
            )
            candidate.setdefault("candidate_sources", []).append(source)
    return sorted(
        combined.values(),
        key=lambda row: (
            float(row.get("score", 0)) + 0.06 * float(row.get("importance", 0.5)),
            len(row.get("candidate_sources", [])),
        ),
        reverse=True,
    )


async def _search_class(
    index: str,
    label: str,
    id_field: str,
    text_field: str,
    embedding: list[float],
    query: str,
) -> list[dict[str, Any]]:
    vector, keyword = await asyncio.gather(
        asyncio.to_thread(
            storage.search_vector, index, label, id_field, text_field, embedding
        ),
        asyncio.to_thread(storage.search_keywords, label, id_field, text_field, query),
    )
    return _merge_rows(vector, keyword)


def _belief(
    row: dict[str, Any], *, include_historical: bool = False
) -> MemoryCandidateResult | None:
    lifecycle = row.get("lifecycle", "active")
    if lifecycle != "active" and not include_historical:
        return None
    return MemoryCandidateResult(
        memory_id=row["id"],
        text=row["text"],
        score=float(row.get("score", 0)),
        subject=row.get("subject"),
        observed_on=row.get("observed_on"),
        lifecycle=lifecycle,
        sources=tuple(row.get("source_turn_ids", ())),
        kind=MemoryKind.BELIEF,
        selection_reason="semantic_match",
        evidence_ids=tuple(row.get("source_turn_ids", ())),
    )


def _event(row: dict[str, Any]) -> MemoryCandidateResult:
    return MemoryCandidateResult(
        memory_id=row["id"],
        text=row["text"],
        score=float(row.get("score", 0)),
        subject=", ".join(row.get("subjects", ())) or None,
        observed_on=(row.get("observed_at") or "")[:10] or None,
        sources=tuple(row.get("source_turn_ids", ())),
        kind=MemoryKind.EVENT,
        selection_reason="event_match",
        evidence_ids=(row["id"],),
        occurred_start=row.get("occurred_start") or None,
        occurred_end=row.get("occurred_end") or None,
    )


def _episode(row: dict[str, Any], now: datetime) -> MemoryCandidateResult:
    try:
        claims = tuple(json.loads(row.get("summary_claims") or "[]"))
    except (TypeError, json.JSONDecodeError):
        claims = ()
    state = episode_effective_state(
        row.get("assembly_state", "closed"), now, _parse(row.get("inactivity_deadline"))
    )
    return MemoryCandidateResult(
        memory_id=row["id"],
        text=row["text"],
        score=float(row.get("score", 0)),
        observed_on=(row.get("last_event_at") or "")[:10] or None,
        lifecycle=state,
        kind=MemoryKind.EPISODE,
        selection_reason="episode_match",
        evidence_ids=tuple(row.get("event_ids", ())),
        occurred_start=row.get("occurred_start") or None,
        occurred_end=row.get("occurred_end") or None,
        summary_claims=claims,
    )


def _prospective(
    row: dict[str, Any], request: RetrievalRequest, intent: str
) -> MemoryCandidateResult | None:
    now = request.now_utc or datetime.now(timezone.utc)
    due_start = _parse(row.get("due_start"))
    due_end = _parse(row.get("due_end"))
    state = effective_prospective_state(
        evidence_state=row.get("evidence_state", "disputed"),
        now=now,
        due_start=due_start,
        due_end=due_end,
        stale_after=_parse(row.get("stale_after")),
        prospective_type=row.get("prospective_type", "unknown"),
    )
    direct = (
        intent in {"prospective", "hybrid"}
        or request.mode is RetrievalMode.EXPLICIT_RECALL
    )
    if (
        state
        in {"stale_unconfirmed", "completed", "cancelled", "superseded", "disputed"}
        and not direct
    ):
        return None
    eligible = follow_up_eligible(
        effective_state=state, now=now, due_start=due_start, due_end=due_end
    )
    return MemoryCandidateResult(
        memory_id=row["id"],
        text=row["text"],
        score=float(row.get("score", 0)),
        observed_on=(row.get("last_confirmed_at") or "")[:10] or None,
        lifecycle=row.get("evidence_state", "pending"),
        kind=MemoryKind.PROSPECTIVE,
        selection_reason="prospective_match",
        evidence_ids=tuple(row.get("event_ids", ())),
        occurred_start=row.get("due_start") or None,
        occurred_end=row.get("due_end") or None,
        effective_state=state,
        assumption=state in {"presumed_occurred", "stale_unconfirmed"},
        follow_up_eligible=eligible,
    )


def _normalized_take(
    candidates: list[MemoryCandidateResult], count: int
) -> list[MemoryCandidateResult]:
    out = []
    for rank, candidate in enumerate(candidates[:count]):
        normalized = 1.0 / (rank + 1)
        out.append(MemoryCandidateResult(**{**candidate.__dict__, "score": normalized}))
    return out


def _next_cache_boundary(rows: list[dict[str, Any]], now: datetime) -> str | None:
    boundaries: list[datetime] = []
    for row in rows:
        if row.get("evidence_state", "pending") != "pending":
            continue
        due_start = _parse(row.get("due_start"))
        due_end = _parse(row.get("due_end"))
        if due_start is not None:
            occurred_by = due_end or (due_start + timedelta(hours=1))
            boundaries.extend(
                (occurred_by + timedelta(minutes=15), occurred_by + timedelta(hours=72))
            )
        else:
            stale_after = _parse(row.get("stale_after"))
            if stale_after is not None:
                boundaries.append(stale_after)
    future = [boundary for boundary in boundaries if boundary > now]
    return min(future).astimezone(timezone.utc).isoformat() if future else None


def _within_bounds(
    candidate: MemoryCandidateResult, bounds: tuple[datetime, datetime]
) -> bool:
    start = _parse(candidate.occurred_start)
    end = _parse(candidate.occurred_end) or start
    if start is None:
        return False
    bound_start, bound_end = bounds
    return start < bound_end and (end or start) >= bound_start


async def retrieve(request: RetrievalRequest) -> MemoryContext:
    embedding = await asyncio.to_thread(get_embedding, request.query)
    searches = await asyncio.gather(
        _search_class(
            "human_belief_embedding",
            "HumanBelief",
            "belief_id",
            "text",
            embedding,
            request.query,
        ),
        _search_class(
            "memory_event_embedding",
            "MemoryEvent",
            "event_id",
            "text",
            embedding,
            request.query,
        ),
        _search_class(
            "episode_embedding",
            "Episode",
            "episode_id",
            "summary",
            embedding,
            request.query,
        ),
        _search_class(
            "prospective_memory_embedding",
            "ProspectiveMemory",
            "prospective_id",
            "text",
            embedding,
            request.query,
        ),
    )
    now = request.now_utc or datetime.now(timezone.utc)
    intent = query_intent(request.query)
    beliefs = [
        candidate
        for row in searches[0]
        if (
            candidate := _belief(
                row, include_historical=request.mode is RetrievalMode.EXPLICIT_RECALL
            )
        )
    ]
    events = [_event(row) for row in searches[1]]
    episodes = [_episode(row, now) for row in searches[2]]
    prospectives = [
        candidate
        for row in searches[3]
        if (candidate := _prospective(row, request, intent))
    ]
    bounds = query_time_bounds(request.query, request.owner_local_time)
    if bounds:
        events = [
            candidate for candidate in events if _within_bounds(candidate, bounds)
        ]
        episodes = [
            candidate for candidate in episodes if _within_bounds(candidate, bounds)
        ]
        prospectives = [
            candidate for candidate in prospectives if _within_bounds(candidate, bounds)
        ]
    ordering = request.query.casefold()
    if (
        re.search(r"\b(?:latest|last|most recent)\b", ordering)
        and "last week" not in ordering
    ):
        episodes.sort(
            key=lambda item: item.occurred_end or item.occurred_start or "",
            reverse=True,
        )
        events.sort(
            key=lambda item: item.occurred_end or item.occurred_start or "",
            reverse=True,
        )
    elif re.search(r"\b(?:first|earliest)\b", ordering):
        episodes.sort(key=lambda item: item.occurred_start or "9999")
        events.sort(key=lambda item: item.occurred_start or "9999")

    if intent == "semantic":
        order = ((beliefs, 3), (episodes, 2), (events, 1), (prospectives, 1))
    elif intent == "episodic":
        order = ((episodes, 3), (events, 2), (beliefs, 2), (prospectives, 1))
    elif intent == "prospective":
        order = ((prospectives, 4), (episodes, 2), (beliefs, 2), (events, 1))
    else:
        order = ((prospectives, 2), (episodes, 2), (events, 2), (beliefs, 2))
    fused: list[MemoryCandidateResult] = []
    seen: set[str] = set()
    for candidates, count in order:
        for candidate in _normalized_take(candidates, count):
            if candidate.memory_id not in seen:
                fused.append(candidate)
                seen.add(candidate.memory_id)
    fused.sort(key=lambda candidate: candidate.score, reverse=True)
    fused_limit = request.max_results if request.max_results is not None else 8
    fused = fused[:fused_limit]
    cache_valid_until = _next_cache_boundary(searches[3], now)
    metadata: dict[str, Any] = {
        "intent": intent,
        "graph_revision": request.graph_revision,
        "follow_up_ids": [
            candidate.memory_id for candidate in fused if candidate.follow_up_eligible
        ],
        "follow_up_tokens": {
            candidate.memory_id: hashlib.sha256(
                "\x1f".join(candidate.evidence_ids).encode("utf-8")
            ).hexdigest()[:20]
            for candidate in fused
            if candidate.follow_up_eligible
        },
    }
    if cache_valid_until:
        metadata["cache_valid_until"] = cache_valid_until
    return MemoryContext(
        query=request.query,
        candidates=tuple(fused),
        abstained=not fused,
        reason="no_relevant_memory" if not fused else "",
        metadata=metadata,
    )
