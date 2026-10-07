from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from human_memory.models import ValidatedEvent, EventModality
from human_memory.policy import stale_after_for
from memory.actions import session
from memory.agents import run_episode_summary_agent, run_linking_agent
from memory.helpers.openai_embed import get_embedding, get_embeddings_batch


PROVIDER = "human_memory"
EMBEDDING_DIMENSIONS = 1536


def _iso(value: datetime | None) -> str:
    return value.astimezone(timezone.utc).isoformat() if value else ""


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif hasattr(value, "to_native"):
        parsed = value.to_native()
    else:
        parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _synthesize_episode(ordered: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Return (summary, claims) for an ordered event list.

    Uses the episode-summary model when available and falls back to a
    deterministic join that preserves every event_id when the model fails,
    returns an incomplete claim set, or omits any supplied event id.
    """
    def fallback_text(row: dict[str, Any]) -> str:
        text = row["text"]
        if row.get("modality") == EventModality.INTENDED.value:
            return f"Pending: {text}"
        if row.get("modality") == EventModality.EXPECTED.value:
            return f"Expected: {text}"
        return text

    fallback_claims = [
        {"text": fallback_text(row), "event_ids": [row["event_id"]]}
        for row in ordered
    ]
    fallback_summary = " ".join(claim["text"] for claim in fallback_claims)
    # Future-state summaries are rendered deterministically from authoritative
    # event modality. A prose model must never turn a pending task into a
    # completed occurrence merely to make the episode read more smoothly.
    if any(
        row.get("modality") in {
            EventModality.INTENDED.value,
            EventModality.EXPECTED.value,
        }
        for row in ordered
    ):
        return fallback_summary, fallback_claims
    try:
        result = run_episode_summary_agent(
            [
                {
                    "event_id": row["event_id"],
                    "modality": row.get("modality", "unknown"),
                    "text": row["text"],
                }
                for row in ordered
            ]
        )
    except Exception:
        return fallback_summary, fallback_claims
    summary = (result.get("summary") or "").strip()
    claims = result.get("claims") or []
    if not summary or not claims:
        return fallback_summary, fallback_claims
    covered: set[str] = set()
    clean_claims: list[dict[str, Any]] = []
    for claim in claims:
        text = (claim.get("text") or "").strip()
        ids = [eid for eid in (claim.get("event_ids") or []) if eid]
        if not text or not ids:
            continue
        clean_claims.append({"text": text, "event_ids": ids})
        covered.update(ids)
    expected = {row["event_id"] for row in ordered}
    if not clean_claims or not expected.issubset(covered):
        return fallback_summary, fallback_claims
    return summary, clean_claims


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:20]}"


def setup_schema() -> None:
    statements = [
        "CREATE CONSTRAINT human_belief_id IF NOT EXISTS FOR (n:HumanBelief) REQUIRE n.belief_id IS UNIQUE",
        "CREATE CONSTRAINT memory_event_id IF NOT EXISTS FOR (n:MemoryEvent) REQUIRE n.event_id IS UNIQUE",
        "CREATE CONSTRAINT memory_event_key IF NOT EXISTS FOR (n:MemoryEvent) REQUIRE n.idempotency_key IS UNIQUE",
        "CREATE CONSTRAINT episode_id IF NOT EXISTS FOR (n:Episode) REQUIRE n.episode_id IS UNIQUE",
        "CREATE CONSTRAINT prospective_memory_id IF NOT EXISTS FOR (n:ProspectiveMemory) REQUIRE n.prospective_id IS UNIQUE",
        "CREATE VECTOR INDEX human_belief_embedding IF NOT EXISTS FOR (n:HumanBelief) ON n.embedding OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
        "CREATE VECTOR INDEX memory_event_embedding IF NOT EXISTS FOR (n:MemoryEvent) ON n.embedding OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
        "CREATE VECTOR INDEX episode_embedding IF NOT EXISTS FOR (n:Episode) ON n.embedding OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
        "CREATE VECTOR INDEX prospective_memory_embedding IF NOT EXISTS FOR (n:ProspectiveMemory) ON n.embedding OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}",
    ]
    with session() as neo:
        for statement in statements:
            neo.run(statement).consume()
        neo.run("CALL db.awaitIndexes(60)").consume()
        # Register optional-property tokens before the first event/episode exists.
        # This avoids Neo4j warnings on valid empty-label retrieval queries.
        neo.run(
            """MERGE (schema:HumanMemorySchema {provider: $provider})
            SET schema.injectable = true, schema.summary = ''""",
            provider=PROVIDER,
        ).consume()
        neo.run(
            "MERGE (:MemoryMetadata {provider: $provider})", provider=PROVIDER
        ).consume()


def _find_similar_belief(
    subject: str, embedding: list[float], current_belief_id: str,
    *, text: str = "",
) -> bool:
    """Check if an existing HumanBelief with high vector similarity already
    exists. Prevents re-extracted paraphrases from creating duplicate beliefs
    across turns.

    Two tiers of matching:
    - Same subject + score >= 0.88: classic paraphrase dedup.
    - Any subject + score >= 0.85: cross-subject semantic duplicate (e.g.,
      "The User is owed compensation from Javaz5" vs "The User is supposed to
      receive $500 USD in compensation from Javaz5" — different subjects but
      the same underlying fact).

    A text-based exact match fallback catches duplicates when the vector index
    has not yet refreshed (Neo4j vector indexes are asynchronous).
    """
    with session() as neo:
        result = neo.run(
            """CALL db.index.vector.queryNodes("human_belief_embedding", 5, $embedding)
            YIELD node, score
            WHERE node:HumanBelief AND node.provider = $provider
              AND node.belief_id <> $current_id
              AND coalesce(node.lifecycle, "active") = "active"
              AND (
                (node.subject = $subject AND score >= 0.88)
                OR score >= 0.85
              )
            RETURN count(node) AS cnt, collect({id: node.belief_id, subject: node.subject, score: score}) AS hits
            """,
            embedding=embedding,
            provider=PROVIDER,
            current_id=current_belief_id,
            subject=subject,
        ).single()
        vec_cnt = result["cnt"] if result else 0
        if vec_cnt > 0:
            return True
        if text:
            text_result = neo.run(
                """MATCH (n:HumanBelief {provider: $provider})
                WHERE n.belief_id <> $current_id
                  AND coalesce(n.lifecycle, "active") = "active"
                  AND toLower(trim(n.text)) = toLower(trim($text))
                RETURN count(n) AS cnt, collect(n.belief_id) AS ids
                """,
                provider=PROVIDER,
                current_id=current_belief_id,
                text=text,
            ).single()
            text_cnt = text_result["cnt"] if text_result else 0
            if text_cnt > 0:
                return True
    return False


def _cosine_from_embeddings(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def graph_revision() -> int:
    with session() as neo:
        record = neo.run(
            "MATCH (m:MemoryMetadata {provider: $provider}) RETURN coalesce(m.revision, 0) AS revision",
            provider=PROVIDER,
        ).single()
    return int(record["revision"]) if record else 0


def _belief_key(fact: dict[str, Any]) -> str:
    identity = " ".join(
        re.findall(r"[a-z0-9]+", fact["text"].casefold())
    )
    return hashlib.sha256(
        f"{fact.get('subject', '').casefold()}\x1f{identity}".encode("utf-8")
    ).hexdigest()


def store_beliefs(facts: list[dict[str, Any]]) -> tuple[int, int, list[str]]:
    if not facts:
        return 0, 0, []
    embeddings = get_embeddings_batch([fact["text"] for fact in facts])
    rows = []
    for fact, embedding in zip(facts, embeddings):
        key = _belief_key(fact)
        rows.append(
            {
                **fact,
                "belief_id": "bel_" + key[:20],
                "belief_key": key,
                "embedding": embedding,
            }
        )

    deduped_rows = []
    for row in rows:
        existing = _find_similar_belief(row["subject"], row["embedding"], row["belief_id"], text=row["text"])
        if existing:
            continue
        is_intra_batch_dup = False
        for kept in deduped_rows:
            sim = _cosine_from_embeddings(row["embedding"], kept["embedding"])
            if sim >= 0.85:
                is_intra_batch_dup = True
                break
        if is_intra_batch_dup:
            continue
        deduped_rows.append(row)
    rows = deduped_rows
    if not rows:
        return 0, len(facts), []

    token = uuid.uuid4().hex
    with session() as neo:
        records = neo.run(
            """UNWIND $rows AS row
            MERGE (b:HumanBelief {belief_id: row.belief_id, provider: $provider})
            ON CREATE SET b.created_token = $token, b.created_at = datetime()
            SET b.text = row.text, b.subject = row.subject,
                b.provider = $provider,
                b.evidence = row.evidence, b.observed_on = row.observed_on,
                b.source_turn_ids = row.source_turn_ids,
                b.memory_type = row.memory_type, b.importance = row.importance,
                b.lifecycle = row.lifecycle, b.operation = row.operation,
                b.conflict_key = row.conflict_key,
                b.extraction_version = row.extraction_version,
                b.embedding = row.embedding, b.updated_at = datetime()
            WITH collect(b) AS beliefs
            WITH beliefs, size([b IN beliefs WHERE b.created_token = $token]) AS created
            FOREACH (b IN beliefs | REMOVE b.created_token)
            MERGE (meta:MemoryMetadata {provider: $provider})
            SET meta.revision = coalesce(meta.revision, 0) + CASE WHEN size(beliefs) > 0 THEN 1 ELSE 0 END
            RETURN created, size(beliefs) - created AS duplicates""",
            rows=rows,
            token=token,
            provider=PROVIDER,
        ).single()
        neo.run(
            """UNWIND $rows AS row
            MATCH (new:HumanBelief {belief_id: row.belief_id, provider: $provider})
            WITH new, row
            WHERE trim(coalesce(row.conflict_key, "")) <> ""
            MATCH (old:HumanBelief {provider: $provider, conflict_key: row.conflict_key})
            WHERE old.belief_id <> new.belief_id
              AND coalesce(old.lifecycle, "active") = "active"
            SET old.lifecycle = CASE WHEN row.operation = "dispute" THEN "disputed" ELSE "superseded" END,
                old.superseded_at = datetime()
            MERGE (new)-[:SUPERSEDES]->(old)""",
            rows=rows,
            provider=PROVIDER,
        ).consume()
    created_count = int(records["created"]) if records else 0
    new_ids = [r["belief_id"] for r in rows] if created_count > 0 else []
    return (created_count, int(records["duplicates"]) if records else 0, new_ids)


def _event_row(event: ValidatedEvent, embedding: list[float]) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "idempotency_key": event.idempotency_key,
        "text": event.text,
        "event_type": event.event_type,
        "modality": event.modality.value,
        "observed_at": _iso(event.observed_at),
        "occurred_start": _iso(event.occurred_start),
        "occurred_end": _iso(event.occurred_end),
        "temporal_precision": event.temporal_precision.value,
        "temporal_expression": event.temporal_expression,
        "temporal_confidence": event.temporal_confidence,
        "evidence_authority": "owner_statement",
        "evidence": event.evidence,
        "evidence_spans": [
            json.dumps(
                {
                    "turn_id": event.evidence_span.turn_id,
                    "start": event.evidence_span.start,
                    "end": event.evidence_span.end,
                },
                separators=(",", ":"),
            )
        ],
        "source_turn_ids": [event.evidence_span.turn_id],
        "source": event.source,
        "scope_id": event.scope_id,
        "subjects": list(event.subjects),
        "importance": event.importance,
        "extraction_version": event.extraction_version,
        "embedding": embedding,
        "corrects_event_id": event.corrects_event_id,
        "prospective_type": event.prospective_type,
        "prospective_action": event.prospective_action,
        "prospective_key": event.prospective_key,
        "due_start": _iso(event.due_start),
        "due_end": _iso(event.due_end),
    }


def store_events(events: list[ValidatedEvent]) -> tuple[int, int, list[str]]:
    if not events:
        return 0, 0, []
    embeddings = get_embeddings_batch([event.text for event in events])
    rows = [_event_row(event, embedding) for event, embedding in zip(events, embeddings)]
    token = uuid.uuid4().hex
    with session() as neo:
        record = neo.run(
            """UNWIND $rows AS row
            MERGE (e:MemoryEvent {idempotency_key: row.idempotency_key, provider: $provider})
            ON CREATE SET e.event_id = row.event_id, e.created_token = $token,
                e.created_at = datetime(), e.provider = $provider, e.text = row.text,
                e.event_type = row.event_type, e.modality = row.modality,
                e.observed_at = row.observed_at,
                e.occurred_start = row.occurred_start,
                e.occurred_end = row.occurred_end,
                e.temporal_precision = row.temporal_precision,
                e.temporal_expression = row.temporal_expression,
                e.temporal_confidence = row.temporal_confidence,
                e.evidence_authority = row.evidence_authority,
                e.evidence = row.evidence, e.evidence_spans = row.evidence_spans,
                e.source_turn_ids = row.source_turn_ids, e.source = row.source,
                e.scope_id = row.scope_id, e.subjects = row.subjects,
                e.importance = row.importance,
                e.extraction_version = row.extraction_version,
                e.embedding = row.embedding,
                e.prospective_type = row.prospective_type,
                e.prospective_action = row.prospective_action,
                e.prospective_key = row.prospective_key,
                e.due_start = row.due_start, e.due_end = row.due_end,
                e.injectable = true
            WITH collect(e) AS events, $rows AS rows
            WITH events, rows,
                 size([e IN events WHERE e.created_token = $token]) AS created
            FOREACH (e IN events | REMOVE e.created_token)
            FOREACH (row IN [r IN rows WHERE r.corrects_event_id <> ""] |
                MERGE (new:MemoryEvent {idempotency_key: row.idempotency_key, provider: $provider})
                MERGE (old:MemoryEvent {event_id: row.corrects_event_id, provider: $provider})
                MERGE (new)-[:CORRECTS]->(old))
            MERGE (meta:MemoryMetadata {provider: $provider})
            SET meta.revision = coalesce(meta.revision, 0) + CASE WHEN size(events) > 0 THEN 1 ELSE 0 END
            RETURN created, size(events) - created AS duplicates""",
            rows=rows,
            token=token,
            provider=PROVIDER,
        ).single()
    created_count = int(record["created"]) if record else 0
    new_ids = [r["event_id"] for r in rows] if created_count > 0 else []
    return (created_count, int(record["duplicates"]) if record else 0, new_ids)


def derive_prospectives(events: Iterable[ValidatedEvent]) -> int:
    rows = []
    for event in events:
        if event.prospective_action == "none" or not event.prospective_key:
            continue
        prospective_id = _stable_id(
            "pro", event.scope_id, event.prospective_key.casefold()
        )
        state = {
            "create": "pending",
            "update": "pending",
            "complete": "completed",
            "cancel": "cancelled",
            "supersede": "superseded",
            "dispute": "disputed",
        }[event.prospective_action]
        stale = stale_after_for(event.prospective_type, event.observed_at)
        pro_text = event.prospective_text.strip() or event.text
        rows.append(
            {
                "prospective_id": prospective_id,
                "text": pro_text,
                "prospective_type": event.prospective_type or "unknown",
                "prospective_key": event.prospective_key,
                "evidence_state": state,
                "state_changed_at": _iso(event.observed_at),
                "due_start": _iso(event.due_start),
                "due_end": _iso(event.due_end),
                "temporal_precision": event.temporal_precision.value,
                "last_confirmed_at": _iso(event.observed_at),
                "stale_after": _iso(stale),
                "follow_up_until": _iso(
                    (event.due_end or event.due_start) + timedelta(hours=72)
                    if (event.due_end or event.due_start)
                    else None
                ),
                "importance": event.importance,
                "embedding": get_embedding(event.text),
                "event_id": event.event_id,
                "scope_id": event.scope_id,
                "prospective_action": event.prospective_action,
                "subjects": list(event.subjects),
            }
        )
    if not rows:
        return 0

    rows = _dedupe_prospective_rows(rows)
    rows = _merge_with_existing_prospectives(rows)

    with session() as neo:
        record = neo.run(
            """UNWIND $rows AS row
            MATCH (e:MemoryEvent {event_id: row.event_id, provider: $provider})
            MERGE (p:ProspectiveMemory {prospective_id: row.prospective_id, provider: $provider})
            ON CREATE SET p.created_at = datetime()
            SET p.provider = $provider, p.text = row.text, p.prospective_type = row.prospective_type,
                p.prospective_key = row.prospective_key,
                p.evidence_state = row.evidence_state,
                p.injectable = true,
                p.state_changed_at = row.state_changed_at,
                p.due_start = CASE WHEN row.due_start <> "" THEN row.due_start ELSE p.due_start END,
                p.due_end = CASE WHEN row.due_end <> "" THEN row.due_end ELSE p.due_end END,
                p.temporal_precision = row.temporal_precision,
                p.last_confirmed_at = row.last_confirmed_at,
                p.stale_after = row.stale_after,
                p.follow_up_until = row.follow_up_until,
                p.importance = row.importance, p.embedding = row.embedding,
                p.event_ids = CASE
                    WHEN p.event_ids IS NULL THEN [row.event_id]
                    WHEN NOT row.event_id IN p.event_ids THEN p.event_ids + row.event_id
                    ELSE p.event_ids END,
                p.scope_id = row.scope_id, p.updated_at = datetime()
            MERGE (p)-[:SUPPORTED_BY]->(e)
            WITH p, row
            FOREACH (extra_id IN coalesce(row._extra_event_ids, []) |
                MERGE (extra:MemoryEvent {event_id: extra_id, provider: $provider})
                MERGE (p)-[:SUPPORTED_BY]->(extra))
            WITH count(DISTINCT p) AS changed
            MERGE (meta:MemoryMetadata {provider: $provider})
            SET meta.revision = coalesce(meta.revision, 0) + CASE WHEN changed > 0 THEN 1 ELSE 0 END
            RETURN changed""",
            rows=rows,
            provider=PROVIDER,
        ).single()
    return int(record["changed"]) if record else 0


def _dedupe_prospective_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate prospective rows that describe the same logical intention.

    When two rows in the same scope have semantically similar text (vector
    similarity >= 0.80) and the same prospective_type, merge them into the
    row with the more complete temporal data (non-empty due_start). This
    prevents duplicate prospectives like "Attend the 1pm meeting" and
    "Attend tomorrow's meeting" from coexisting as separate pending items.
    """
    if len(rows) < 2:
        return rows
    kept: list[dict[str, Any]] = []
    for row in rows:
        merged = False
        for existing in kept:
            if existing["scope_id"] != row["scope_id"]:
                continue
            if existing["prospective_type"] != row["prospective_type"]:
                continue
            sim = _cosine_from_embeddings(existing["embedding"], row["embedding"])
            if sim < 0.80:
                continue
            existing_has_time = bool(existing.get("due_start"))
            row_has_time = bool(row.get("due_start"))
            if row_has_time and not existing_has_time:
                existing["due_start"] = row["due_start"]
                existing["due_end"] = row["due_end"]
                existing["temporal_precision"] = row["temporal_precision"]
                existing["follow_up_until"] = row["follow_up_until"]
            existing.setdefault("extra_event_ids", []).append(row["event_id"])
            merged = True
            break
        if not merged:
            kept.append(row)
    for row in kept:
        extra = row.pop("extra_event_ids", [])
        if extra:
            row["_extra_event_ids"] = extra
    return kept


def _merge_with_existing_prospectives(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Check the graph for existing pending prospectives that semantically
    overlap with the new rows. If a pending prospective in the same scope has
    vector similarity >= 0.75 with a new row, merge the new row into the
    existing prospective instead of creating a duplicate.

    This catches cross-batch duplicates where two different turns produced
    prospectives for the same logical item (e.g., "Attend the 1pm meeting"
    from one turn and "Attend tomorrow's meeting" from another).
    """
    if not rows:
        return rows
    import logging
    logger = logging.getLogger(__name__)
    kept: list[dict[str, Any]] = []
    with session() as neo:
        for row in rows:
            existing = None
            if row.get("prospective_action") == "update":
                subjects = [
                    subject.strip()
                    for subject in row.get("subjects", [])
                    if len(subject.strip()) >= 4
                    and subject.casefold() not in {"user", "owner", "project"}
                ]
                if len(subjects) >= 2:
                    existing = neo.run(
                        """MATCH (p:ProspectiveMemory {
                            provider: $provider, scope_id: $scope_id,
                            evidence_state: "pending"
                        })
                        WHERE p.prospective_id <> $current_pid
                          AND size([subject IN $subjects
                            WHERE toLower(p.text) CONTAINS toLower(subject)]) >= 2
                        RETURN p.prospective_id AS pid,
                               p.prospective_type AS ptype,
                               p.due_start AS dstart, p.due_end AS dend,
                               p.temporal_precision AS tp,
                               p.follow_up_until AS fu, p.text AS ptext,
                               1.0 AS score
                        ORDER BY p.updated_at DESC LIMIT 1""",
                        provider=PROVIDER,
                        scope_id=row["scope_id"],
                        subjects=subjects,
                        current_pid=row["prospective_id"],
                    ).single()
            if existing is None:
                existing = neo.run(
                    """CALL db.index.vector.queryNodes("prospective_memory_embedding", 3, $embedding)
                    YIELD node, score
                    WHERE node:ProspectiveMemory AND node.provider = $provider
                      AND node.scope_id = $scope_id
                      AND node.evidence_state = "pending"
                      AND score >= 0.75
                      AND node.prospective_id <> $current_pid
                    RETURN node.prospective_id AS pid, node.prospective_type AS ptype,
                           node.due_start AS dstart, node.due_end AS dend,
                           node.temporal_precision AS tp, node.follow_up_until AS fu,
                           node.text AS ptext, score
                    ORDER BY score DESC LIMIT 1""",
                    provider=PROVIDER,
                    scope_id=row["scope_id"],
                    embedding=row["embedding"],
                    current_pid=row["prospective_id"],
                ).single()
            if existing and existing.get("pid"):
                logger.debug(
                    "merge_prospectives: merging row=%r into existing pid=%r ptext=%r score=%.4f",
                    row["text"][:60], existing["pid"], existing.get("ptext", "")[:60],
                    existing.get("score", 0),
                )
                row["prospective_id"] = existing["pid"]
                if existing.get("dstart") and not row.get("due_start"):
                    row["due_start"] = existing["dstart"]
                    row["due_end"] = existing.get("dend") or ""
                    row["temporal_precision"] = existing.get("tp") or "unknown"
                    row["follow_up_until"] = existing.get("fu") or ""
                elif row.get("due_start") and not existing.get("dstart"):
                    pass
            kept.append(row)
    return kept


_COMPLETION_SIGNALS = frozenset({
    "passed", "completed", "done", "finished", "fixed", "resolved",
    "shipped", "pushed", "deployed", "launched", "merged", "closed",
    "solved", "handled", "ran", "passed with flying colors",
})


def _has_completion_signal(text: str) -> bool:
    lowered = text.casefold()
    return any(signal in lowered for signal in _COMPLETION_SIGNALS)


def supersede_prospectives(events: list[ValidatedEvent]) -> int:
    """Check if any newly-stored reported events close pending prospectives.

    A reported_past or reported_current event that semantically overlaps a
    pending ProspectiveMemory in the same scope marks it completed. This lets
    the system close a prospective when the owner later reports the work was
    done — even if the model didn't explicitly label it as a completion.

    Two matching strategies are used:
    1. Vector similarity >= 0.75 between the event text and the prospective text.
    2. Subject overlap: if the event shares a subject with a pending prospective
       and the event text contains a completion signal word (passed, done,
       finished, shipped, etc.), the prospective is closed even when vector
       similarity is below the threshold. This catches cases like "it was a
       test and you passed with flying colors" closing an "OSINT investigation"
       prospective — semantically distant text but same subject (Berlecool).
    """
    reported = [
        e for e in events
        if e.modality in {EventModality.REPORTED_PAST, EventModality.REPORTED_CURRENT}
        and e.prospective_action == "none"
    ]
    if not reported:
        return 0
    closed = 0
    import logging
    logger = logging.getLogger(__name__)
    with session() as neo:
        for event in reported:
            event_embedding = get_embedding(event.text)
            matches = neo.run(
                """MATCH (p:ProspectiveMemory {provider: $provider, scope_id: $scope_id, evidence_state: "pending"})
                CALL db.index.vector.queryNodes("prospective_memory_embedding", 12, $embedding)
                YIELD node, score
                WHERE node:ProspectiveMemory AND node.provider = $provider
                  AND node.evidence_state = "pending"
                RETURN p.prospective_id AS pid, p.text AS ptext, score
                ORDER BY score DESC LIMIT 12""",
                provider=PROVIDER,
                scope_id=event.scope_id,
                embedding=event_embedding,
            ).data()

            pid = ""
            if matches and matches[0]["score"] >= 0.75:
                pid = matches[0]["pid"]
            else:
                event_subjects = {
                    s.casefold() for s in event.subjects
                    if s and s.casefold() != "the user"
                }
                logger.debug(
                    "supersede fallback: event=%r subjects=%r matches=%d",
                    event.text[:80], event_subjects, len(matches),
                )
                if event_subjects and _has_completion_signal(event.text):
                    event_subject_tokens: set[str] = set()
                    for subj in event_subjects:
                        event_subject_tokens.update(
                            t for t in re.findall(r"[a-z0-9]{3,}", subj)
                            if t not in {"the", "and", "for", "with"}
                        )
                    for match in matches:
                        prospective_text = match.get("ptext") or ""
                        prospective_embedding = get_embedding(prospective_text)
                        sim = _cosine_from_embeddings(event_embedding, prospective_embedding)
                        logger.debug(
                            "supersede candidate: ptext=%r sim=%.4f score=%.4f",
                            prospective_text[:60], sim, match.get("score", 0),
                        )
                        if sim < 0.35:
                            continue
                        pending_tokens = set(
                            s.casefold() for s in re.findall(
                                r"[A-Za-z][A-Za-z0-9]+", prospective_text
                            )
                            if s.casefold() not in {
                                "the", "a", "an", "to", "for", "of", "and",
                                "or", "in", "on", "at", "is", "was", "be",
                                "with", "by", "that", "this", "it", "as",
                            }
                        )
                        overlap = event_subject_tokens & pending_tokens
                        if overlap:
                            logger.debug("supersede match found: overlap=%r", overlap)
                            pid = match["pid"]
                            break

            if not pid:
                continue
            neo.run(
                """MATCH (p:ProspectiveMemory {prospective_id: $pid, provider: $provider})
                MATCH (e:MemoryEvent {event_id: $event_id, provider: $provider})
                SET p.evidence_state = "completed",
                    p.state_changed_at = $observed_at,
                    p.last_confirmed_at = $observed_at,
                    p.event_ids = CASE
                        WHEN NOT $event_id IN p.event_ids THEN p.event_ids + $event_id
                        ELSE p.event_ids END,
                    p.updated_at = datetime()
                MERGE (p)-[:SUPPORTED_BY]->(e)""",
                pid=pid,
                provider=PROVIDER,
                observed_at=_iso(event.observed_at),
                event_id=event.event_id,
            ).consume()
            closed += 1
        if closed:
            neo.run(
                """MERGE (meta:MemoryMetadata {provider: $provider})
                SET meta.revision = coalesce(meta.revision, 0) + 1""",
                provider=PROVIDER,
            ).consume()
    return closed


def sweep_completed_prospectives() -> int:
    """Cross-batch sweep: check all pending prospectives against all reported
    events in the graph.

    ``supersede_prospectives`` only checks the current batch's reported events
    against pending prospectives. When a completion event arrives in an
    earlier batch than the prospective (e.g., the owner reports "it was a day
    ago" in turn 2, but the prospective is created from a roadmap list in
    turn 5), the completion is never rechecked and the prospective stays
    pending forever.

    This sweep runs after every ingest and catches those ordering gaps by
    checking every pending prospective against every reported_past /
    reported_current event in the same scope, skipping events already
    linked via SUPPORTED_BY (already processed by supersede_prospectives).
    """
    import logging
    logger = logging.getLogger(__name__)

    with session() as neo:
        pending_rows = neo.run(
            """MATCH (p:ProspectiveMemory {provider: $provider, evidence_state: "pending"})
            RETURN p.prospective_id AS pid, p.text AS ptext,
                   p.scope_id AS scope_id, p.embedding AS pembedding
            """,
            provider=PROVIDER,
        ).data()

    if not pending_rows:
        return 0

    closed = 0
    with session() as neo:
        for row in pending_rows:
            pid = row["pid"]
            ptext = row.get("ptext") or ""
            scope_id = row.get("scope_id") or ""
            prospective_embedding = row.get("pembedding")

            # Find reported events in the same scope that are NOT already
            # linked to this prospective (those were handled by supersede).
            event_rows = neo.run(
                """MATCH (e:MemoryEvent {provider: $provider, scope_id: $scope_id})
                WHERE e.modality IN ["reported_past", "reported_current"]
                  AND coalesce(e.prospective_action, "none") = "none"
                  AND NOT (e)<-[:SUPPORTED_BY]-(:ProspectiveMemory {prospective_id: $pid})
                RETURN e.event_id AS event_id, e.text AS text,
                       e.subjects AS subjects, e.observed_at AS observed_at,
                       e.embedding AS embedding
                ORDER BY e.observed_at DESC LIMIT 20""",
                provider=PROVIDER,
                scope_id=scope_id,
                pid=pid,
            ).data()

            if not event_rows:
                continue

            matched_event_id = ""
            matched_observed_at = ""

            for event_row in event_rows:
                event_text = event_row.get("text") or ""
                event_embedding = event_row.get("embedding")
                event_id = event_row.get("event_id") or ""

                # Strategy 1: vector similarity between prospective and event
                if prospective_embedding and event_embedding:
                    sim = _cosine_from_embeddings(prospective_embedding, event_embedding)
                    if sim >= 0.75:
                        matched_event_id = event_id
                        matched_observed_at = event_row.get("observed_at") or ""
                        logger.debug(
                            "sweep vector match: pid=%r event=%r sim=%.4f",
                            pid[:20], event_text[:60], sim,
                        )
                        break

                # Strategy 2: subject overlap + completion signal
                event_subjects = event_row.get("subjects") or []
                if isinstance(event_subjects, list):
                    event_subjects = {
                        s.casefold() for s in event_subjects
                        if s and s.casefold() != "the user"
                    }
                else:
                    event_subjects = set()

                if event_subjects and _has_completion_signal(event_text):
                    event_subject_tokens: set[str] = set()
                    for subj in event_subjects:
                        event_subject_tokens.update(
                            t for t in re.findall(r"[a-z0-9]{3,}", subj)
                            if t not in {"the", "and", "for", "with"}
                        )
                    pending_tokens = set(
                        s.casefold() for s in re.findall(
                            r"[A-Za-z][A-Za-z0-9]+", ptext
                        )
                        if s.casefold() not in {
                            "the", "a", "an", "to", "for", "of", "and",
                            "or", "in", "on", "at", "is", "was", "be",
                            "with", "by", "that", "this", "it", "as",
                        }
                    )
                    overlap = event_subject_tokens & pending_tokens
                    if overlap:
                        matched_event_id = event_id
                        matched_observed_at = event_row.get("observed_at") or ""
                        logger.debug(
                            "sweep subject match: pid=%r event=%r overlap=%r",
                            pid[:20], event_text[:60], overlap,
                        )
                        break

            if not matched_event_id:
                continue

            neo.run(
                """MATCH (p:ProspectiveMemory {prospective_id: $pid, provider: $provider})
                MATCH (e:MemoryEvent {event_id: $event_id, provider: $provider})
                SET p.evidence_state = "completed",
                    p.state_changed_at = $observed_at,
                    p.last_confirmed_at = $observed_at,
                    p.event_ids = CASE
                        WHEN NOT $event_id IN p.event_ids THEN p.event_ids + $event_id
                        ELSE p.event_ids END,
                    p.updated_at = datetime()
                MERGE (p)-[:SUPPORTED_BY]->(e)""",
                pid=pid,
                provider=PROVIDER,
                observed_at=matched_observed_at,
                event_id=matched_event_id,
            ).consume()
            closed += 1

        if closed:
            neo.run(
                """MERGE (meta:MemoryMetadata {provider: $provider})
                SET meta.revision = coalesce(meta.revision, 0) + 1""",
                provider=PROVIDER,
            ).consume()
    return closed


_EPISODE_INACTIVITY_HOURS = 72


def _episode_title(event: ValidatedEvent) -> str:
    subject = next(
        (value for value in event.subjects if value.casefold() != "the user"),
        event.event_type,
    )
    return subject


_EPISODE_GENERIC_SUBJECTS = frozenset({
    "the user", "user", "the owner", "owner", "the assistant", "assistant",
    "the project", "project", "the page", "page", "the site", "site",
    "portfolio", "the portfolio", "the summary", "summary", "test", "result",
    "link", "job",
})


def _episode_subjects(event: ValidatedEvent) -> frozenset[str]:
    """Specific named subjects, excluding generic labels like 'The User'."""
    return frozenset(
        s.casefold() for s in event.subjects
        if s.strip() and s.casefold() not in _EPISODE_GENERIC_SUBJECTS
    )


def _events_share_subject(a: ValidatedEvent, b: ValidatedEvent) -> bool:
    """Two events are related if they share at least one specific named
    subject (not 'The User')."""
    sa, sb = _episode_subjects(a), _episode_subjects(b)
    if not sa or not sb:
        return False
    return bool(sa & sb)


def _group_related_events(events: list[ValidatedEvent]) -> list[list[ValidatedEvent]]:
    """Group events into clusters where each event shares at least one
    specific named subject with at least one other event in the cluster.

    Unrelated events end up in their own singleton cluster. This uses
    union-find so transitive relationships are captured (A shares with B,
    B shares with C -> A,B,C all in one episode).
    """
    if not events:
        return []
    parent = list(range(len(events)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            if _events_share_subject(events[i], events[j]):
                union(i, j)

    clusters: dict[int, list[ValidatedEvent]] = {}
    for i, event in enumerate(events):
        clusters.setdefault(find(i), []).append(event)
    return list(clusters.values())


def _episode_moment(row: dict[str, Any]) -> datetime:
    value = row.get("occurred_end") or row.get("occurred_start") or row.get("observed_at")
    return _parse_datetime(value)


def _validated_event_row(event: ValidatedEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "text": event.text,
        "modality": event.modality.value,
        "occurred_start": _iso(event.occurred_start),
        "occurred_end": _iso(event.occurred_end),
        "observed_at": _iso(event.observed_at),
        "importance": event.importance,
    }


def _within_episode_window(reference: datetime, value: Any) -> bool:
    if value in {None, ""}:
        return False
    return abs(reference - _parse_datetime(value)) <= timedelta(
        hours=_EPISODE_INACTIVITY_HOURS
    )


def assemble_episodes(events: Iterable[ValidatedEvent]) -> int:
    """Build episodes only when at least two temporally-near events share a
    specific named subject.

    A first event remains standalone. A later related event may attach it to an
    existing episode or create a new episode containing both events. This keeps
    atomic evidence searchable without manufacturing a one-event episode for
    every owner turn.
    """
    incoming_events = sorted(
        events, key=lambda e: e.occurred_start or e.observed_at
    )
    if not incoming_events:
        return 0

    clusters = _group_related_events(incoming_events)

    changed = 0
    for cluster in clusters:
        cluster.sort(key=lambda e: e.occurred_start or e.observed_at)
        reference = cluster[0].occurred_start or cluster[0].observed_at
        subject_keys = sorted({
            subject
            for event in cluster
            for subject in _episode_subjects(event)
        })
        if not subject_keys:
            continue
        title_subject = _episode_title(cluster[0])
        title = f"{title_subject} — {cluster[0].event_type}"[:120]
        subject_key = ",".join(subject_keys)
        incoming_ids = [event.event_id for event in cluster]

        with session() as neo:
            episode_candidates = neo.run(
                """MATCH (episode:Episode {provider: $provider, scope_id: $scope_id})
                -[:CONTAINS]->(member:MemoryEvent {provider: $provider})
                WHERE any(subject IN coalesce(member.subjects, [])
                          WHERE toLower(subject) IN $subject_keys)
                RETURN DISTINCT episode.episode_id AS episode_id,
                       episode.last_event_at AS last_event_at
                ORDER BY episode.last_event_at DESC LIMIT 12""",
                provider=PROVIDER,
                scope_id=cluster[0].scope_id,
                subject_keys=subject_keys,
            ).data()

            episode_id = next(
                (
                    row["episode_id"]
                    for row in episode_candidates
                    if _within_episode_window(reference, row.get("last_event_at"))
                ),
                "",
            )
            existing: list[dict[str, Any]] = []
            if episode_id:
                existing = [
                    dict(row)
                    for row in neo.run(
                        """MATCH (episode:Episode {episode_id: $episode_id, provider: $provider})
                        -[:CONTAINS]->(event:MemoryEvent {provider: $provider})
                        RETURN event.event_id AS event_id, event.text AS text,
                               event.modality AS modality,
                               event.occurred_start AS occurred_start,
                               event.occurred_end AS occurred_end,
                               event.observed_at AS observed_at,
                               event.importance AS importance
                        ORDER BY coalesce(event.occurred_start, event.observed_at)""",
                        episode_id=episode_id,
                        provider=PROVIDER,
                    ).data()
                ]
            else:
                standalone = neo.run(
                    """MATCH (event:MemoryEvent {provider: $provider, scope_id: $scope_id})
                    WHERE NOT event.event_id IN $incoming_ids
                      AND NOT (event)<-[:CONTAINS]-(:Episode {provider: $provider})
                      AND any(subject IN coalesce(event.subjects, [])
                              WHERE toLower(subject) IN $subject_keys)
                    RETURN event.event_id AS event_id, event.text AS text,
                           event.modality AS modality,
                           event.occurred_start AS occurred_start,
                           event.occurred_end AS occurred_end,
                           event.observed_at AS observed_at,
                           event.importance AS importance
                    ORDER BY coalesce(event.occurred_start, event.observed_at) DESC
                    LIMIT 12""",
                    provider=PROVIDER,
                    scope_id=cluster[0].scope_id,
                    incoming_ids=incoming_ids,
                    subject_keys=subject_keys,
                ).data()
                existing = [
                    dict(row)
                    for row in standalone
                    if _within_episode_window(reference, _episode_moment(dict(row)))
                ]

        known = {row["event_id"]: row for row in existing}
        for event in cluster:
            known[event.event_id] = _validated_event_row(event)
        ordered = sorted(known.values(), key=_episode_moment)
        if len(ordered) < 2:
            continue
        if not episode_id:
            episode_id = _stable_id(
                "epi", cluster[0].scope_id, subject_key, ordered[0]["event_id"]
            )

        summary, claims = _synthesize_episode(ordered)
        starts = [row["occurred_start"] for row in ordered if row.get("occurred_start")]
        ends = [row["occurred_end"] for row in ordered if row.get("occurred_end")]
        last_event = max(
            (row.get("occurred_end") or row.get("occurred_start") or row.get("observed_at") for row in ordered),
            default="",
        )
        inactivity = (
            _iso(datetime.fromisoformat(last_event) + timedelta(hours=_EPISODE_INACTIVITY_HOURS))
            if last_event
            else ""
        )
        all_event_ids = [row["event_id"] for row in ordered]
        with session() as neo:
            result = neo.run(
                """MERGE (episode:Episode {episode_id: $episode_id, provider: $provider})
                ON CREATE SET episode.created_at = datetime()
                SET episode.title = $title, episode.summary = $summary,
                    episode.provider = $provider,
                    episode.group_key = $group_key,
                    episode.summary_claims = $summary_claims,
                    episode.episode_type = $episode_type,
                    episode.occurred_start = $occurred_start,
                    episode.occurred_end = $occurred_end,
                    episode.assembly_state = "open",
                    episode.last_event_at = $last_event_at,
                    episode.inactivity_deadline = $inactivity_deadline,
                    episode.boundary_confidence = 0.7,
                    episode.importance = $importance,
                    episode.event_ids = $all_event_ids,
                    episode.summary_version = 1,
                    episode.embedding = $embedding,
                    episode.subject_keys = $subject_keys,
                    episode.scope_id = $scope_id,
                    episode.updated_at = datetime()
                WITH episode
                UNWIND $all_event_ids AS event_id
                MATCH (event:MemoryEvent {event_id: event_id, provider: $provider})
                MERGE (episode)-[:CONTAINS]->(event)
                WITH count(event) AS linked
                MERGE (meta:MemoryMetadata {provider: $provider})
                SET meta.revision = coalesce(meta.revision, 0) + CASE WHEN linked > 0 THEN 1 ELSE 0 END
                RETURN linked""",
                episode_id=episode_id,
                title=title,
                group_key=subject_key,
                summary=summary,
                summary_claims=json.dumps(claims, separators=(",", ":")),
                episode_type=cluster[0].event_type,
                occurred_start=min(starts) if starts else "",
                occurred_end=max(ends) if ends else "",
                last_event_at=last_event,
                inactivity_deadline=inactivity,
                importance=max(float(row.get("importance") or 0.5) for row in ordered),
                all_event_ids=all_event_ids,
                embedding=get_embedding(f"{title}\n{summary}"),
                subject_keys=subject_keys,
                scope_id=cluster[0].scope_id,
                provider=PROVIDER,
            ).single()
        if result and result["linked"] > 0:
            changed += 1
    return changed


def migrate_semantic_beliefs() -> dict[str, int]:
    with session() as neo:
        rows = neo.run(
            """MATCH (m:Memory)
            WHERE trim(coalesce(m.evidence, "")) <> ""
              AND size(coalesce(m.source_turn_ids, [])) > 0
            RETURN m.text AS text, m.subject AS subject, m.evidence AS evidence,
                   m.observed_on AS observed_on, m.source_turn_ids AS source_turn_ids,
                   m.memory_type AS memory_type, m.importance AS importance,
                   coalesce(m.lifecycle, "active") AS lifecycle,
                   coalesce(m.operation, "add") AS operation,
                   m.conflict_key AS conflict_key,
                   coalesce(m.extraction_version, 1) AS extraction_version"""
        ).data()
        ineligible = neo.run(
            """MATCH (m:Memory)
            WHERE trim(coalesce(m.evidence, "")) = ""
               OR size(coalesce(m.source_turn_ids, [])) = 0
            RETURN count(m) AS count"""
        ).single()
    created, duplicates, _ids = store_beliefs([dict(row) for row in rows])
    return {
        "eligible": len(rows),
        "created": created,
        "duplicates": duplicates,
        "ineligible": int(ineligible["count"]) if ineligible else 0,
    }


def search_vector(index: str, label: str, id_field: str, text_field: str, embedding: list[float], k: int = 6) -> list[dict[str, Any]]:
    allowed = {
        ("human_belief_embedding", "HumanBelief", "belief_id", "text"),
        ("memory_event_embedding", "MemoryEvent", "event_id", "text"),
        ("episode_embedding", "Episode", "episode_id", "summary"),
        ("prospective_memory_embedding", "ProspectiveMemory", "prospective_id", "text"),
    }
    if (index, label, id_field, text_field) not in allowed:
        raise ValueError("unsupported human-memory vector search")
    with session() as neo:
        rows = neo.run(
            f"""CALL db.index.vector.queryNodes($index, $k, $embedding)
            YIELD node, score
            WHERE node:{label} AND node.provider = $provider
              AND coalesce(node.injectable, true) AND score >= 0.58
            RETURN node{{.*}}, node.{id_field} AS id, node.{text_field} AS text, score
            ORDER BY score DESC""",
            index=index,
            k=k,
            embedding=embedding,
            provider=PROVIDER,
        ).data()
    return [{**dict(row.get("node") or {}), "id": row["id"], "text": row["text"], "score": row["score"]} for row in rows]


def search_keywords(label: str, id_field: str, text_field: str, query: str, k: int = 6) -> list[dict[str, Any]]:
    allowed = {
        ("HumanBelief", "belief_id", "text"),
        ("MemoryEvent", "event_id", "text"),
        ("Episode", "episode_id", "summary"),
        ("ProspectiveMemory", "prospective_id", "text"),
    }
    if (label, id_field, text_field) not in allowed:
        raise ValueError("unsupported human-memory keyword search")
    terms = sorted(
        {
            token
            for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", query.casefold())
            if token not in {"what", "when", "where", "which", "about", "with", "that", "this", "have", "need", "did"}
        }
    )
    if not terms:
        return []
    with session() as neo:
        rows = neo.run(
            f"""MATCH (node:{label})
            WHERE node.provider = $provider AND coalesce(node.injectable, true)
            WITH node, size([term IN $terms WHERE toLower(node.{text_field}) CONTAINS term]) AS matches
            WHERE matches > 0
            RETURN node{{.*}}, node.{id_field} AS id, node.{text_field} AS text,
                   toFloat(matches) / size($terms) AS score
            ORDER BY matches DESC, coalesce(node.importance, 0.5) DESC
            LIMIT $k""",
            terms=terms,
            k=k,
            provider=PROVIDER,
        ).data()
    return [{**dict(row.get("node") or {}), "id": row["id"], "text": row["text"], "score": row["score"]} for row in rows]


def diagnostics() -> dict[str, Any]:
    with session() as neo:
        record = neo.run(
            """OPTIONAL MATCH (b:HumanBelief {provider: $provider})
            WITH count(b) AS beliefs
            OPTIONAL MATCH (e:MemoryEvent {provider: $provider})
            WITH beliefs, count(e) AS events
            OPTIONAL MATCH (p:Episode {provider: $provider})
            WITH beliefs, events, count(p) AS episodes
            OPTIONAL MATCH (f:ProspectiveMemory {provider: $provider})
            RETURN beliefs, events, episodes, count(f) AS prospectives""",
            provider=PROVIDER,
        ).single()
    return dict(record) if record else {"beliefs": 0, "events": 0, "episodes": 0, "prospectives": 0}


def _repair_episode(episode_id: str) -> str:
    with session() as neo:
        rows = neo.run(
            """MATCH (episode:Episode {episode_id: $episode_id, provider: $provider})
            OPTIONAL MATCH (episode)-[:CONTAINS]->(event:MemoryEvent {provider: $provider})
            RETURN event.event_id AS event_id, event.text AS text,
                   event.modality AS modality,
                   event.occurred_start AS occurred_start,
                   event.occurred_end AS occurred_end,
                   event.observed_at AS observed_at,
                   event.importance AS importance
            ORDER BY coalesce(event.occurred_start, event.observed_at)""",
            episode_id=episode_id,
            provider=PROVIDER,
        ).data()
    rows = [dict(row) for row in rows if row.get("event_id")]
    if len(rows) < 2:
        with session() as neo:
            neo.run(
                "MATCH (episode:Episode {episode_id: $episode_id, provider: $provider}) DETACH DELETE episode",
                episode_id=episode_id,
                provider=PROVIDER,
            ).consume()
        return "deleted"
    summary, claims = _synthesize_episode(rows)
    starts = [row["occurred_start"] for row in rows if row.get("occurred_start")]
    ends = [row["occurred_end"] for row in rows if row.get("occurred_end")]
    with session() as neo:
        neo.run(
            """MATCH (episode:Episode {episode_id: $episode_id, provider: $provider})
            SET episode.summary = $summary,
                episode.summary_claims = $summary_claims,
                episode.event_ids = $event_ids,
                episode.occurred_start = $occurred_start,
                episode.occurred_end = $occurred_end,
                episode.importance = $importance,
                episode.embedding = $embedding,
                episode.injectable = true,
                episode.updated_at = datetime()""",
            episode_id=episode_id,
            provider=PROVIDER,
            summary=summary,
            summary_claims=json.dumps(claims, separators=(",", ":")),
            event_ids=[row["event_id"] for row in rows],
            occurred_start=min(starts) if starts else "",
            occurred_end=max(ends) if ends else "",
            importance=max(float(row.get("importance") or 0.5) for row in rows),
            embedding=get_embedding(summary),
        ).consume()
        neo.run(
            """MERGE (meta:MemoryMetadata {provider: $provider})
            SET meta.revision = coalesce(meta.revision, 0) + 1""",
            provider=PROVIDER,
        ).consume()
    return "rebuilt"


def _repair_prospective(prospective_id: str) -> str:
    with session() as neo:
        rows = neo.run(
            """MATCH (p:ProspectiveMemory {prospective_id: $prospective_id, provider: $provider})
            OPTIONAL MATCH (p)-[:SUPPORTED_BY]->(event:MemoryEvent {provider: $provider})
            RETURN event.event_id AS event_id, event.text AS text,
                   event.prospective_action AS action,
                   event.prospective_type AS prospective_type,
                   event.due_start AS due_start, event.due_end AS due_end,
                   event.temporal_precision AS temporal_precision,
                   event.observed_at AS observed_at,
                   event.importance AS importance
            ORDER BY event.observed_at""",
            prospective_id=prospective_id,
            provider=PROVIDER,
        ).data()
    rows = [dict(row) for row in rows if row.get("event_id")]
    if not rows:
        with session() as neo:
            neo.run(
                "MATCH (p:ProspectiveMemory {prospective_id: $prospective_id, provider: $provider}) DETACH DELETE p",
                prospective_id=prospective_id,
                provider=PROVIDER,
            ).consume()
        return "deleted"
    latest = rows[-1]
    observed_at = _parse_datetime(latest.get("observed_at"))
    stale_after = stale_after_for(
        latest.get("prospective_type") or "unknown", observed_at
    )
    due_end = _parse_datetime(latest.get("due_end")) if latest.get("due_end") else None
    due_start = (
        _parse_datetime(latest.get("due_start")) if latest.get("due_start") else None
    )
    occurred_by = due_end or (due_start + timedelta(hours=1) if due_start else None)
    state = {
        "create": "pending",
        "update": "pending",
        "complete": "completed",
        "cancel": "cancelled",
        "supersede": "superseded",
        "dispute": "disputed",
    }.get(latest.get("action"), "disputed")
    with session() as neo:
        neo.run(
            """MATCH (p:ProspectiveMemory {prospective_id: $prospective_id, provider: $provider})
            SET p.text = $text, p.evidence_state = $state,
                p.state_changed_at = $observed_at,
                p.last_confirmed_at = $observed_at,
                p.due_start = $due_start, p.due_end = $due_end,
                p.temporal_precision = $temporal_precision,
                p.prospective_type = $prospective_type,
                p.stale_after = $stale_after,
                p.follow_up_until = $follow_up_until,
                p.importance = $importance,
                p.event_ids = $event_ids, p.embedding = $embedding,
                p.injectable = true,
                p.updated_at = datetime()""",
            prospective_id=prospective_id,
            provider=PROVIDER,
            text=latest["text"],
            state=state,
            observed_at=latest.get("observed_at") or "",
            due_start=latest.get("due_start") or "",
            due_end=latest.get("due_end") or "",
            temporal_precision=latest.get("temporal_precision") or "unknown",
            prospective_type=latest.get("prospective_type") or "unknown",
            stale_after=_iso(stale_after),
            follow_up_until=_iso(occurred_by + timedelta(hours=72)) if occurred_by else "",
            importance=float(latest.get("importance") or 0.5),
            event_ids=[row["event_id"] for row in rows],
            embedding=get_embedding(latest["text"]),
        ).consume()
        neo.run(
            """MERGE (meta:MemoryMetadata {provider: $provider})
            SET meta.revision = coalesce(meta.revision, 0) + 1""",
            provider=PROVIDER,
        ).consume()
    return "rebuilt"


_LINK_MIN_SCORE = 0.55
_LINK_NEIGHBOR_K = 6
_LINK_BATCH_SIZE = 3
_LINK_LABELS = {
    "HumanBelief": ("belief_id", "human_belief_embedding", "text"),
    "MemoryEvent": ("event_id", "memory_event_embedding", "text"),
}


def link_nodes(node_ids: list[str], label: str) -> int:
    """Find vector neighbors for newly stored nodes and create typed relationships.

    Works for HumanBelief and MemoryEvent. Uses the same linking agent as the
    semantic_graph pipeline, adapted for human_memory node labels.
    Processes nodes in small batches so the linking agent prompt stays focused.
    """
    if label not in _LINK_LABELS:
        return 0
    total_created = 0
    for i in range(0, len(node_ids), _LINK_BATCH_SIZE):
        batch = node_ids[i : i + _LINK_BATCH_SIZE]
        total_created += _link_nodes_batch(batch, label)
    return total_created


def _link_nodes_batch(node_ids: list[str], label: str) -> int:
    id_field, index, text_field = _LINK_LABELS[label]
    if not node_ids:
        return 0

    with session() as neo:
        rows = neo.run(
            f"""UNWIND $ids AS nid
            MATCH (n:{label} {{provider: $provider, {id_field}: nid}})
            CALL db.index.vector.queryNodes($index, $k, n.embedding)
            YIELD node, score
            WHERE score >= $min_score AND node:{label} AND node.provider = $provider
              AND node.{id_field} <> nid AND coalesce(node.injectable, true)
            WITH nid, node, score
            ORDER BY nid, score DESC
            RETURN nid AS source_id, collect({{
                id: node.{id_field}, text: node.{text_field}, score: score,
                subject: coalesce(node.subject, ''), subjects: coalesce(node.subjects, [])
            }}) AS neighbors""",
            ids=node_ids,
            index=index,
            k=_LINK_NEIGHBOR_K,
            min_score=_LINK_MIN_SCORE,
            provider=PROVIDER,
        ).data()
        node_rows = neo.run(
            f"""UNWIND $ids AS nid
            MATCH (n:{label} {{provider: $provider, {id_field}: nid}})
            RETURN nid AS source_id, n.{text_field} AS text,
                   coalesce(n.subject, '') AS subject,
                   coalesce(n.subjects, []) AS subjects""",
            ids=node_ids,
            provider=PROVIDER,
        ).data()

    neighbors_by_id = {r["source_id"]: r["neighbors"] for r in rows}
    nodes_by_id = {r["source_id"]: r for r in node_rows}

    batch_nodes = []
    for nid in node_ids:
        neighbors = neighbors_by_id.get(nid, [])
        if not neighbors:
            continue
        node = nodes_by_id.get(nid)
        if not node:
            continue
        neighbor_context = "\n".join(
            f"    [{n['id']}] (score={n['score']:.2f}, subject={n.get('subject') or 'unknown'}): {n['text']}"
            for n in neighbors
        )
        batch_nodes.append({"id": nid, "text": node["text"], "neighbors": neighbor_context})

    if not batch_nodes:
        return 0

    sections = []
    for i, bn in enumerate(batch_nodes, 1):
        sections.append(
            f"--- Node {i} ---\n"
            f"Memory ID: {bn['id']}\n"
            f"Node Text: {bn['text']}\n"
            f"Node Subject: {nodes_by_id[bn['id']].get('subject') or 'unknown'}\n\n"
            f"Candidate neighbors:\n{bn['neighbors']}"
        )
    prompt = "\n\n".join(sections)
    if label == "MemoryEvent":
        prompt = (
            "These are atomic evidence events. Event-to-event relationships are "
            "restricted to CORRECTS (one event corrects a prior event). Do not "
            "create generic similarity links between events — shared subjects do "
            "not justify a relationship. Only link events when one explicitly "
            "corrects, refines, or contradicts the other's occurrence.\n\n"
            + prompt
        )

    try:
        relationships = run_linking_agent(prompt)
    except Exception:
        return 0
    if not relationships:
        return 0

    valid_ids = {bn["id"] for bn in batch_nodes}
    candidate_ids = {n["id"] for bn in batch_nodes for n in neighbors_by_id.get(bn["id"], [])}
    rels: list[dict] = []
    for source_id, targets in relationships.items():
        if source_id not in valid_ids:
            continue
        for target_id, rel_data in targets.items():
            if target_id not in candidate_ids:
                continue
            if isinstance(rel_data, str):
                rel_type, weight = rel_data, 1.0
            elif isinstance(rel_data, dict):
                rel_type = rel_data.get("type", "RELATED_TO")
                weight = rel_data.get("weight", 1.0)
            else:
                continue
            rels.append({"from": source_id, "to": target_id, "type": rel_type, "weight": weight})

    if not rels and label == "HumanBelief":
        rels = _deterministic_links(node_ids, neighbors_by_id, nodes_by_id)

    if not rels:
        return 0

    with session() as neo:
        created = 0
        for rel in rels:
            from_id, to_id = rel["from"], rel["to"]
            rel_type = re.sub(r"[^A-Z_]", "", rel["type"].upper()) or "RELATED_TO"
            if not rel_type:
                continue
            result = neo.run(
                f"""MATCH (a:{label} {{provider: $provider, {id_field}: $from_id}})
                MATCH (b:{label} {{provider: $provider, {id_field}: $to_id}})
                MERGE (a)-[r:{rel_type}]->(b)
                ON CREATE SET r.weight = $weight
                RETURN count(r) AS c""",
                provider=PROVIDER,
                from_id=from_id,
                to_id=to_id,
                weight=rel["weight"],
            ).single()
            if result and result["c"]:
                created += 1
        if created:
            neo.run(
                """MERGE (meta:MemoryMetadata {provider: $provider})
                SET meta.revision = coalesce(meta.revision, 0) + 1""",
                provider=PROVIDER,
            ).consume()
    return created


def _subjects_match(a_subjects: set[str], b_subjects: set[str]) -> bool:
    """Check if two subject sets overlap by exact match, substring containment,
    or shared significant token (3+ chars)."""
    for a in a_subjects:
        for b in b_subjects:
            if a == b or a in b or b in a:
                return True
            a_tokens = {t for t in re.findall(r"[a-z0-9]{3,}", a) if t not in {"the", "and", "for", "with"}}
            b_tokens = {t for t in re.findall(r"[a-z0-9]{3,}", b) if t not in {"the", "and", "for", "with"}}
            if a_tokens & b_tokens:
                return True
    return False


def _deterministic_links(
    node_ids: list[str],
    neighbors_by_id: dict[str, list[dict]],
    nodes_by_id: dict[str, dict],
) -> list[dict]:
    """Fallback when the linking agent returns nothing. Link nodes that share
    an explicit subject (exact or substring) with a vector neighbor."""
    rels: list[dict] = []
    for nid in node_ids:
        node = nodes_by_id.get(nid)
        if not node:
            continue
        node_subjects = set(node.get("subjects") or []) or ({node.get("subject")} if node.get("subject") else set())
        node_subjects = {s.casefold() for s in node_subjects if s and s.casefold() != "the user"}
        if not node_subjects:
            continue
        for neighbor in neighbors_by_id.get(nid, []):
            neighbor_subjects = set(neighbor.get("subjects") or []) or set()
            neighbor_subjects = {s.casefold() for s in neighbor_subjects if s and s.casefold() != "the user"}
            if _subjects_match(node_subjects, neighbor_subjects):
                rels.append({
                    "from": nid,
                    "to": neighbor["id"],
                    "type": "ABOUT_SAME_SUBJECT",
                    "weight": 1.0,
                })
    return rels


_CROSS_LINK_MIN_SCORE = 0.60
_CROSS_LINK_K = 5
_GENERIC_SUBJECTS_LOWER = frozenset({
    "the user", "user", "the owner", "owner", "the assistant", "assistant",
})


def cross_label_link_beliefs_events(
    belief_ids: list[str], event_ids: list[str]
) -> int:
    """Link newly-stored beliefs to newly-stored events that share a specific
    named entity. Uses vector similarity to find candidates and a deterministic
    subject-overlap check to validate the link.

    Only creates links when both nodes share a subject that is NOT a generic
    label ("The User", "owner", etc.). The relationship type is ABOUT_SAME_SUBJECT
    with a neutral weight since a belief and an event about the same entity are
    different kinds of records, not the same kind of fact.
    """
    if not belief_ids or not event_ids:
        return 0
    rels: list[dict] = []
    with session() as neo:
        belief_rows = neo.run(
            """UNWIND $ids AS bid
            MATCH (b:HumanBelief {provider: $provider, belief_id: bid})
            RETURN bid AS id, b.subject AS subject, b.text AS text, b.embedding AS embedding""",
            ids=belief_ids,
            provider=PROVIDER,
        ).data()
        event_rows = neo.run(
            """UNWIND $ids AS eid
            MATCH (e:MemoryEvent {provider: $provider, event_id: eid})
            RETURN eid AS id, e.subjects AS subjects, e.text AS text, e.embedding AS embedding""",
            ids=event_ids,
            provider=PROVIDER,
        ).data()

    if not belief_rows or not event_rows:
        return 0

    for belief in belief_rows:
        b_subjects = {belief.get("subject") or ""}
        b_subjects = {
            s.casefold() for s in b_subjects
            if s and s.casefold() not in _GENERIC_SUBJECTS_LOWER
        }
        if not b_subjects:
            continue
        b_emb = belief.get("embedding")
        if not b_emb:
            continue
        with session() as neo:
            candidates = neo.run(
                """CALL db.index.vector.queryNodes("memory_event_embedding", $k, $embedding)
                YIELD node, score
                WHERE node:MemoryEvent AND node.provider = $provider
                  AND score >= $min_score
                  AND node.event_id IN $event_ids
                RETURN node.event_id AS id, node.subjects AS subjects, node.text AS text, score
                ORDER BY score DESC""",
                embedding=b_emb,
                k=_CROSS_LINK_K,
                min_score=_CROSS_LINK_MIN_SCORE,
                provider=PROVIDER,
                event_ids=event_ids,
            ).data()
        for cand in candidates:
            c_subjects = set(cand.get("subjects") or [])
            c_subjects = {
                s.casefold() for s in c_subjects
                if s and s.casefold() not in _GENERIC_SUBJECTS_LOWER
            }
            if not c_subjects:
                continue
            if _subjects_match(b_subjects, c_subjects):
                rels.append({
                    "from": belief["id"],
                    "to": cand["id"],
                    "type": "ABOUT_SAME_SUBJECT",
                    "weight": 1.0,
                })

    if not rels:
        return 0

    created = 0
    with session() as neo:
        for rel in rels:
            result = neo.run(
                """MATCH (b:HumanBelief {provider: $provider, belief_id: $from_id})
                MATCH (e:MemoryEvent {provider: $provider, event_id: $to_id})
                MERGE (b)-[r:ABOUT_SAME_SUBJECT]->(e)
                ON CREATE SET r.weight = $weight
                RETURN count(r) AS c""",
                provider=PROVIDER,
                from_id=rel["from"],
                to_id=rel["to"],
                weight=rel["weight"],
            ).single()
            if result and result["c"]:
                created += 1
        if created:
            neo.run(
                """MERGE (meta:MemoryMetadata {provider: $provider})
                SET meta.revision = coalesce(meta.revision, 0) + 1""",
                provider=PROVIDER,
            ).consume()
    return created


def forget(target_kind: str, target_id: str) -> tuple[list[str], list[str]]:
    labels = {
        "belief": ("HumanBelief", "belief_id"),
        "event": ("MemoryEvent", "event_id"),
        "episode": ("Episode", "episode_id"),
        "prospective": ("ProspectiveMemory", "prospective_id"),
    }
    deleted: list[str] = []
    rebuilt: list[str] = []
    with session() as neo:
        if target_kind == "source_turn":
            impacted = neo.run(
                """MATCH (event:MemoryEvent {provider: $provider})
                WHERE $target_id IN coalesce(event.source_turn_ids, [])
                OPTIONAL MATCH (episode:Episode {provider: $provider})-[:CONTAINS]->(event)
                OPTIONAL MATCH (prospective:ProspectiveMemory {provider: $provider})-[:SUPPORTED_BY]->(event)
                RETURN collect(DISTINCT episode.episode_id) AS episodes,
                       collect(DISTINCT prospective.prospective_id) AS prospectives""",
                target_id=target_id,
                provider=PROVIDER,
            ).single()
        elif target_kind == "event":
            impacted = neo.run(
                """MATCH (event:MemoryEvent {event_id: $target_id, provider: $provider})
                OPTIONAL MATCH (episode:Episode {provider: $provider})-[:CONTAINS]->(event)
                OPTIONAL MATCH (prospective:ProspectiveMemory {provider: $provider})-[:SUPPORTED_BY]->(event)
                RETURN collect(DISTINCT episode.episode_id) AS episodes,
                       collect(DISTINCT prospective.prospective_id) AS prospectives""",
                target_id=target_id,
                provider=PROVIDER,
            ).single()
        else:
            impacted = None
        impacted_episodes = [
            value for value in (impacted.get("episodes", []) if impacted else []) if value
        ]
        impacted_prospectives = [
            value for value in (impacted.get("prospectives", []) if impacted else []) if value
        ]
        if impacted_episodes or impacted_prospectives:
            neo.run(
                """MATCH (node {provider: $provider})
                WHERE (node:Episode AND node.episode_id IN $episodes)
                   OR (node:ProspectiveMemory AND node.prospective_id IN $prospectives)
                SET node.injectable = false""",
                provider=PROVIDER,
                episodes=impacted_episodes,
                prospectives=impacted_prospectives,
            ).consume()
        if target_kind == "source_turn":
            record = neo.run(
                """MATCH (node)
                WHERE (node:MemoryEvent OR node:HumanBelief)
                  AND node.provider = $provider
                  AND $target_id IN coalesce(node.source_turn_ids, [])
                WITH collect(node) AS doomed
                FOREACH (node IN doomed | DETACH DELETE node)
                RETURN size(doomed) AS deleted""",
                target_id=target_id,
                provider=PROVIDER,
            ).single()
            if record and record["deleted"]:
                deleted.append(target_id)
        elif target_kind in labels:
            label, field = labels[target_kind]
            record = neo.run(
                f"""MATCH (node:{label} {{{field}: $target_id, provider: $provider}})
                DETACH DELETE node RETURN count(*) AS deleted""",
                target_id=target_id,
                provider=PROVIDER,
            ).single()
            if record and record["deleted"]:
                deleted.append(target_id)
        else:
            raise ValueError("unsupported forget target")
        neo.run(
            """MERGE (meta:MemoryMetadata {provider: $provider})
            SET meta.revision = coalesce(meta.revision, 0) + CASE WHEN $changed THEN 1 ELSE 0 END""",
            provider=PROVIDER,
            changed=bool(deleted),
        ).consume()
    if impacted:
        for episode_id in impacted_episodes:
            if episode_id:
                rebuilt.append(f"episode:{episode_id}:{_repair_episode(episode_id)}")
        for prospective_id in impacted_prospectives:
            if prospective_id:
                rebuilt.append(
                    f"prospective:{prospective_id}:{_repair_prospective(prospective_id)}"
                )
    return deleted, rebuilt
