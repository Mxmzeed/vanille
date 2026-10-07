from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import redis.asyncio as aioredis

from human_memory import storage
from human_memory.extraction import (
    render_batch,
    run_unified_memory_agent,
    validate_event_candidates,
)
from human_memory.retrieval import retrieve as retrieve_human_memory
from memory.agents import run_verifier_agent
from memory.contracts import (
    ComponentOutcome,
    ComponentStatus,
    ForgetResult,
    IntakeResult,
    IntakeStatus,
    MemoryContext,
    RetrievalRequest,
    TurnBatch,
)
from memory.pipeline import (
    _user_turns,
    score_extraction_worthiness,
    verification_reasons,
)
from memory.validation import validate_candidates
from sage.settings import load_settings


class HumanMemoryProvider:
    def __init__(self) -> None:
        self.timezone_name = load_settings().owner_timezone
        self._migration: dict[str, int] = {}

    async def start(self) -> None:
        await asyncio.to_thread(storage.setup_schema)
        self._migration = await asyncio.to_thread(storage.migrate_semantic_beliefs)

    async def healthcheck(self) -> None:
        await asyncio.to_thread(storage.diagnostics)

    async def close(self) -> None:
        return None

    async def ingest(
        self, batch: TurnBatch, *, conversation: TurnBatch | None = None
    ) -> IntakeResult:
        del conversation  # The intake contract is deliberately the bounded exchange.
        transcript = render_batch(batch)
        owner_turns = [turn for turn in batch.turns if turn.role == "user"]
        if not owner_turns:
            return IntakeResult(IntakeStatus.GATED, "no_owner_turn")
        if not score_extraction_worthiness(transcript):
            return IntakeResult(IntakeStatus.GATED, "deterministic_filler")
        components: dict[str, ComponentOutcome] = {}

        try:
            beliefs, proposed_events = await asyncio.to_thread(
                run_unified_memory_agent, transcript
            )
            if verification_reasons(beliefs, transcript):
                beliefs = await asyncio.to_thread(
                    run_verifier_agent, transcript, beliefs
                )
            observed_on = (
                owner_turns[-1]
                .observed_at.astimezone(ZoneInfo(self.timezone_name))
                .date()
            )
            facts, rejected_beliefs = validate_candidates(
                beliefs, _user_turns(transcript), observed_on
            )
            belief_created, belief_duplicates, belief_ids = await asyncio.to_thread(
                storage.store_beliefs, facts
            )
            if belief_ids:
                await asyncio.to_thread(storage.link_nodes, belief_ids, "HumanBelief")
            components["semantic"] = ComponentOutcome(
                ComponentStatus.SUCCEEDED,
                "stored" if facts else "no_candidates",
                extracted=len(beliefs),
                stored=belief_created,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "semantic extraction failed: %s: %s", type(exc).__name__, exc
            )
            components["semantic"] = ComponentOutcome(
                ComponentStatus.RETRYABLE_ERROR, type(exc).__name__
            )
            return IntakeResult(
                IntakeStatus.RETRYABLE_ERROR,
                "semantic_extraction_error",
                components=components,
            )

        try:
            events, rejected_events = validate_event_candidates(
                proposed_events, batch, self.timezone_name
            )
            event_created, event_duplicates, event_ids = await asyncio.to_thread(
                storage.store_events, events
            )
            if event_ids:
                await asyncio.to_thread(storage.link_nodes, event_ids, "MemoryEvent")
            if belief_ids and event_ids:
                await asyncio.to_thread(
                    storage.cross_label_link_beliefs_events, belief_ids, event_ids
                )
            components["event"] = ComponentOutcome(
                ComponentStatus.SUCCEEDED,
                "stored" if events else "no_candidates",
                extracted=len(proposed_events),
                stored=event_created,
            )
        except Exception as exc:
            components["event"] = ComponentOutcome(
                ComponentStatus.RETRYABLE_ERROR, type(exc).__name__
            )
            return IntakeResult(
                IntakeStatus.RETRYABLE_ERROR,
                "event_extraction_error",
                extracted=len(beliefs),
                stored=belief_created,
                duplicates=belief_duplicates,
                components=components,
            )

        intentions = [event for event in events if event.prospective_action != "none"]
        try:
            prospective_count = await asyncio.to_thread(
                storage.derive_prospectives, intentions
            )
            components["prospective"] = ComponentOutcome(
                (
                    ComponentStatus.SUCCEEDED
                    if intentions
                    else ComponentStatus.NOT_APPLICABLE
                ),
                "stored" if intentions else "no_intentions",
                extracted=len(intentions),
                stored=prospective_count,
            )
        except Exception as exc:
            components["prospective"] = ComponentOutcome(
                ComponentStatus.RETRYABLE_ERROR, type(exc).__name__
            )
            return IntakeResult(
                IntakeStatus.RETRYABLE_ERROR,
                "prospective_derivation_error",
                extracted=len(beliefs) + len(proposed_events),
                stored=belief_created + event_created,
                duplicates=belief_duplicates + event_duplicates,
                components=components,
            )

        try:
            superseded = await asyncio.to_thread(storage.supersede_prospectives, events)
            if superseded:
                components["prospective"] = ComponentOutcome(
                    ComponentStatus.SUCCEEDED,
                    "superseded",
                    extracted=len(intentions),
                    stored=prospective_count + superseded,
                )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "supersede_prospectives failed: %s", type(exc).__name__
            )

        try:
            swept = await asyncio.to_thread(storage.sweep_completed_prospectives)
            if swept:
                components["prospective"] = ComponentOutcome(
                    ComponentStatus.SUCCEEDED,
                    "swept_completed",
                    extracted=len(intentions),
                    stored=prospective_count + swept,
                )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "sweep_completed_prospectives failed: %s", type(exc).__name__
            )

        try:
            episode_count = await asyncio.to_thread(storage.assemble_episodes, events)
            components["episode"] = ComponentOutcome(
                ComponentStatus.SUCCEEDED,
                "assembled" if episode_count else "no_episode_candidates",
                extracted=len(events),
                stored=episode_count,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("episode assembly failed: %s", exc)
            components["episode"] = ComponentOutcome(
                ComponentStatus.RETRYABLE_ERROR, type(exc).__name__
            )
            return IntakeResult(
                IntakeStatus.RETRYABLE_ERROR,
                "episode_assembly_error",
                extracted=len(beliefs) + len(proposed_events),
                stored=belief_created + event_created + prospective_count,
                duplicates=belief_duplicates + event_duplicates,
                components=components,
            )

        total_stored = (
            belief_created + event_created + prospective_count + episode_count
        )
        total_duplicates = belief_duplicates + event_duplicates
        total_rejected = len(rejected_beliefs) + len(rejected_events)
        if total_stored or total_duplicates:
            status, reason = IntakeStatus.STORED, "stored"
        elif total_rejected:
            status, reason = IntakeStatus.REJECTED, "all_candidates_rejected"
        else:
            status, reason = IntakeStatus.EMPTY, "no_candidates"
        return IntakeResult(
            status,
            reason,
            extracted=len(beliefs) + len(proposed_events),
            stored=total_stored,
            duplicates=total_duplicates,
            components=components,
        )

    async def retrieve(
        self, request: RetrievalRequest | str, *, tier: str = "fast"
    ) -> MemoryContext:
        if isinstance(request, str):
            now = datetime.now(timezone.utc)
            request = RetrievalRequest(
                query=request,
                tier=tier,
                now_utc=now,
                owner_local_time=now.astimezone(ZoneInfo(self.timezone_name)),
                graph_revision=await self.graph_revision(),
                normalized_query=" ".join(request.casefold().split()),
            )
        return await retrieve_human_memory(request)

    async def graph_revision(self) -> int:
        return await asyncio.to_thread(storage.graph_revision)

    def temporal_bucket(self, now_utc) -> str:
        return now_utc.strftime("%Y-%m-%dT%H:%M")

    async def forget(
        self, target_kind: str, target_id: str, *, request_context: Any
    ) -> ForgetResult:
        if not getattr(request_context, "is_owner", False):
            raise PermissionError("memory deletion requires owner authorization")
        deleted, rebuilt = await asyncio.to_thread(
            storage.forget, target_kind, target_id
        )
        prospective_ids = {target_id} if target_kind == "prospective" else set()
        prospective_ids.update(
            item.split(":", 2)[1] for item in rebuilt if item.startswith("prospective:")
        )
        if prospective_ids:
            redis = aioredis.from_url(load_settings().redis_url, decode_responses=True)
            try:
                async for key in redis.scan_iter(match="sage:memory:surfacing:*"):
                    await redis.hdel(key, *prospective_ids)
            finally:
                await redis.aclose()
        return ForgetResult(tuple(deleted), tuple(rebuilt))

    async def diagnostics(self) -> Mapping[str, Any]:
        counts = await asyncio.to_thread(storage.diagnostics)
        return {
            "module_id": "human_memory",
            "graph_revision": await self.graph_revision(),
            "migration": self._migration,
            "labels": [
                "HumanBelief",
                "MemoryEvent",
                "Episode",
                "ProspectiveMemory",
            ],
            **counts,
        }
