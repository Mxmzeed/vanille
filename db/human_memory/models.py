from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class EventModality(str, Enum):
    REPORTED_PAST = "reported_past"
    REPORTED_CURRENT = "reported_current"
    INTENDED = "intended"
    EXPECTED = "expected"
    RUNTIME_OBSERVED = "runtime_observed"


class TemporalPrecision(str, Enum):
    INSTANT = "instant"
    DAY = "day"
    RANGE = "range"
    RELATIVE_RESOLVED = "relative_resolved"
    UNKNOWN = "unknown"


class EventCandidate(BaseModel):
    text: str
    event_type: str = "experience"
    modality: Literal[
        "reported_past",
        "reported_current",
        "intended",
        "expected",
    ]
    evidence: str
    source_turn_id: str
    subjects: list[str] = Field(default_factory=list)
    importance: float = 0.5
    temporal_expression: str = ""
    prospective_type: str = ""
    prospective_action: Literal[
        "none", "create", "update", "complete", "cancel", "supersede", "dispute"
    ] = "none"
    prospective_key: str = ""
    prospective_text: str = ""
    corrects_event_id: str = ""


class EventOutput(BaseModel):
    events: list[EventCandidate]


from memory.agents import MemoryCandidate as BeliefCandidate


class UnifiedMemoryOutput(BaseModel):
    beliefs: list[BeliefCandidate] = Field(default_factory=list)
    events: list[EventCandidate] = Field(default_factory=list)


@dataclass(frozen=True)
class EvidenceSpan:
    turn_id: str
    start: int
    end: int


@dataclass(frozen=True)
class TemporalResolution:
    start: datetime | None
    end: datetime | None
    precision: TemporalPrecision
    confidence: float


@dataclass(frozen=True)
class ValidatedEvent:
    event_id: str
    idempotency_key: str
    text: str
    event_type: str
    modality: EventModality
    observed_at: datetime
    occurred_start: datetime | None
    occurred_end: datetime | None
    temporal_precision: TemporalPrecision
    temporal_expression: str
    temporal_confidence: float
    evidence: str
    evidence_span: EvidenceSpan
    source: str
    scope_id: str
    subjects: tuple[str, ...]
    importance: float
    extraction_version: int
    prospective_type: str
    prospective_action: str
    prospective_key: str
    prospective_text: str
    due_start: datetime | None
    due_end: datetime | None
    corrects_event_id: str

