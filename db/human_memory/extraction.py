from __future__ import annotations

import hashlib
import json
import re
from typing import Iterable

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from human_memory.models import (
    BeliefCandidate,
    EventCandidate,
    EventModality,
    EventOutput,
    EvidenceSpan,
    UnifiedMemoryOutput,
    ValidatedEvent,
)
from human_memory.temporal import resolve_temporal_expression
from memory.agents import _prep_model
from memory.contracts import TurnBatch
from memory.validation import has_unresolved_reference


EVENT_EXTRACTION_VERSION = 4
_THIRD_PARTY_PROSPECTIVE_PRONOUN = re.compile(
    r"^(?:[A-Z][\w'-]+)\s+(?:told|said|texted|messaged|emailed|wrote|stated|mentioned)"
    r".*?\b(?:he|she|they)\b|"
    r"\b(?:he|she|they)\s+(?:has|have|needs?|must|will|plans?|intends?)\b",
    re.IGNORECASE,
)
_THIRD_PARTY_PROSPECTIVE_NAMED = re.compile(
    r"(?:^|\s)([A-Z][\w'-]+)\s+(?:needs?|must|will\s+submit|will\s+send|plans?\s+(?:to|on|for)|intends?|has\s+to|have\s+to)\b"
)
_INQUIRY_PROSPECTIVE = re.compile(
    r"^\s*(?:do|does|did|is|are|was|were|can|could|would|will|have|has|what|"
    r"whats|where|whens|why|how|who|whom|which|u|you|yo|hey|sup)\b",
    re.IGNORECASE,
)
_IMMEDIATE_REQUEST = re.compile(
    r"\b(?:just\s+(?:check|tell|run|do|send|redeploy|fix|look)|"
    r"check\s+\S+\s+and\s+tell\s+me|"
    r"can\s+u\s+(?:redeploy|fix|check|run|do|send)|"
    r"run\s+(?:this|that|it)\s+for\s+me|"
    r"do\s+(?:this|that|it)\s+(?:now|right\s+now|for\s+me))\b",
    re.IGNORECASE,
)
_TRANSIENT_OPERATIONAL_EVENT_TYPES = frozenset({
    "command", "instruction", "query", "request", "status_check",
})
_OPEN_SLOT_INTENTION = re.compile(
    r"\b(?:add|adding|choose|choosing|select|selecting)\s+"
    r"(?:more\s+items?|something|an?\s+(?:new\s+)?(?:item|technology|tool))\b",
    re.IGNORECASE,
)
_MVP_TARGET = re.compile(r"\b(?:achieve|reach)\s+(?:an?\s+)?mvp\b", re.IGNORECASE)
_SECURITY_AUDIT_TARGET = re.compile(r"\bsecurity\s+audit\b", re.IGNORECASE)
_EXPLICIT_COMPLETION = re.compile(
    r"\b(?:i|we)\s+(?:finished|completed)\b|"
    r"\b(?:task|errand|return|work)\s+(?:is|was)\s+(?:done|finished|complete|completed)\b|"
    r"\b(?:is|was|are|were)\s+(?:now\s+)?(?:done|finished|complete|completed)\b",
    re.IGNORECASE,
)
_EXPLICIT_CANCELLATION = re.compile(
    r"\b(?:cancelled|canceled|called\s+off)\b",
    re.IGNORECASE,
)
_GENERIC_SUBJECTS = frozenset({
    "summary", "the owner", "owner", "assistant", "the user", "user",
    "the summary", "the assistant", "the page", "the site", "the project",
    "page", "site", "link", "job", "good", "test", "result",
})
_CONTENT_TOKENS = re.compile(r"[a-z0-9]{3,}")
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "was", "not", "that", "said", "owner",
    "had", "has", "have", "been", "from", "into", "its", "but", "are",
    "was", "were", "they", "them", "this", "their", "there", "then",
    "about", "after", "also", "just", "only", "than", "too", "very",
    "sent", "noted", "asked", "confirmed", "pointed", "reported", "stated",
})

_TODO_LIST_HEADERS = re.compile(
    r"\b(?:what\s+we\s+need\s+to\s+do|to[-\s]?do(?:\s*list)?|action\s+items?"
    r"|agenda|roadmap|tasks?\s*:|goals?\s*:|milestones?\s*:"
    r"|what\s+(?:i|we)\s+(?:need|have|want)\s+to\s+do"
    r"|what('?s|s)\s+(?:left|next)|plan\s+of\s+action)\b",
    re.IGNORECASE,
)

UNIFIED_MEMORY_PROMPT = """
You are a memory extraction agent for an AI assistant. You receive one bounded
owner exchange: at most the preceding Assistant reply, the current User turn,
and the following Assistant reply. Extract two kinds of long-term memory from
the current User turn only: durable beliefs and atomic events.

Assistant text is context only and can never be evidence. Quoted text, role-play,
speculation, jokes, obviously false facts, and things the assistant inferred are
not evidence. Only explicit User-authored statements can establish facts or
events.

Use Assistant text only to resolve references in the current User turn. Do not
re-extract claims from earlier context, and do not treat the following Assistant
reply as evidence that requested work succeeded.

=== BELIEFS ===

Beliefs are durable facts that will still be accurate in a year. Extract one
belief per self-contained claim.

Fields:
- text: one complete, self-contained fact containing one claim.
- subject: the explicit entity described by the fact.
- evidence: an exact verbatim excerpt from a User-authored turn.
- durability: stable, time_qualified, or transient.
- source_turn_id: the stable ID printed on the supporting User turn.
- memory_type: a concise open-ended category.
- rationale: why the fact is durable and important enough to retain.
- importance: 0.0 to 1.0.
- operation: add, update, or dispute.
- routing_confidence: 0.0 to 1.0.

DO STORE as beliefs:
- User identity & preferences: "The User prefers pnpm over npm."
- Project definitions & architecture: "The Lilian Project is a distributed ledger system."
- Established facts: "The User lives in Berlin."
- Relationships: "The Lilian Project uses Rust for its consensus layer."
- Durable ongoing role assignments explicitly stated as roles: "Berle is the
  project's security lead."

DO NOT STORE as beliefs:
- One-off task assignments such as "Berle will run the audit" or "Concept will
  choose the processor." These are event/prospective state, not durable roles.
- Pending work items or task lists. Any belief that describes work that needs
  to be done is transient, not durable — it becomes false once the work is
  done. This includes ANY phrasing of pending work: "The project requires a
  security audit", "The project team needs to make the admin dashboard
  functional", "Before launch, the project needs to select a payment
  processor", "The app needs testing", "We need to create pricing plans".
  These belong in events and prospectives, not beliefs. If the belief would
  become false when a task is completed, it is NOT a belief — it is a task.
  Only store as a belief if the statement describes a permanent structural
  or architectural fact (e.g., "The project uses pnpm"), not a to-do item.
- Milestones or goals that are the target of a roadmap. When a User writes a
  list of things to do ("what we need to do:") and the final bullet is a
  milestone ("mvp achieved"), that milestone is a GOAL they are working toward,
  NOT a completed fact. Do not read it as past tense. "mvp achieved" in a
  to-do list means "achieve MVP" (future), not "MVP has been achieved" (past).
  The surrounding list structure ("what we need to do:") tells you the tense.
  Never extract a milestone as a reported_past belief or event when it appears
  in a to-do or roadmap list — it is an intended future outcome.
- Current actions, relative time, session behavior, mutable state.
- Recent activity bounded to the past few days/weeks/months, a school term or
  year, or something "starting soon." These are events, not durable beliefs.
- Pleasantries, greetings, filler.

Logic Filter: "If the user looks at this memory in a year, will it still be
accurate?" If no, it's not a belief. If the answer is "only until the task is
done," it's not a belief.

=== EVENTS ===

Events are atomic, evidence-backed occurrences. Return one event per
supported occurrence, decision, attempt, result, change, intention, expected
occurrence, need, or commitment. A turn may contain multiple events.

Lists contain independently updateable items. When the owner names two or more
supplies, groceries, tasks, or commitments that could be completed separately,
return one intended event and one prospective key per item. Do not merge
"nitrile gloves and specimen labels" or "milk and bread" into one event.

When a single owner turn mentions both a completion AND a new intention, extract
them as SEPARATE events. "well it was a day ago, just thinking bout my 1pm
meeting tmrw" = one reported_past event (the thing that happened a day ago) +
one expected event (the meeting). Do not merge them.

Likewise, preserve attempt history. When one action failed or left the problem
unchanged and a later action succeeded, return separate attempt and result
events. "We tightened the belt, but the vibration stayed; replacing the bearing
fixed it" is two events, not one combined repair summary.

When the owner references something being done ("it was a day ago", "I pushed
it", "it's live", "it's done") but doesn't name what "it" is, look at the
assistant's preceding turn for context. If the assistant just said "I pushed the
Caitlinn page redesign live," and the owner replies "well it was a day ago,"
extract a reported_past event with subject "Caitlinn page redesign" — the
assistant turn tells you what "it" refers to. The evidence is the owner's words
("well it was a day ago"), but the subject comes from resolving the reference
using the full conversation.

Reject transient in-conversation exchanges that won't matter later: greetings
("hey"), status checks ("u still got caitlinn page in yo projects?"), quick
questions ("whats the site link"), nudges ("u nvr sent the summary"), pleasantries
("yeah i always aim for solid, thanks"). These are conversation filler, not events.

Also reject quick operational requests that the assistant is expected to finish
inside the current exchange: checking a git log, opening a project, finding a
logo, retrying a command, reporting status, or "check again." A request is a
long-term event only when it establishes a durable decision or a cross-session
commitment; forward-looking work that remains pending must be represented as an
intended/expected event with prospective state.

A transient request can contain a durable decision. If the owner says "find the
logos, and actually I prefer Motion over GSAP," ignore the logo-finding request
but extract the preference as a belief and the replacement as a decision-change
event. Use prospective_action=update for a pending choice that is being replaced
and phrase the prospective text as the new current choice.

Every stored text must be self-contained. Never use an unnamed placeholder such
as "the project", "the app", "the site", "the page", "it", or "that thing".
Resolve it to a concrete name from the bounded exchange; if the bounded exchange
does not identify the referent, return no candidate for that claim. Do not store
"receive money" without an amount, source, or named compensation context. An
action also needs a concrete target: reject bare "achieve MVP" or "security
audit" when no product/system is named, and reject open slots such as "add a new
technology" until the owner chooses the actual item.

Event fields:
- text: a self-contained event description in natural prose that preserves the
  meaningful context — the actor, the object, the outcome, and any distinguishing
  detail. Write it the way a person would describe the moment to someone who
  wasn't there: specific, concrete, grounded in what was said. Do NOT start with
  "The owner asked for..." or "The user intended to..." — that lab-report style
  strips the life out of it. Write "OSINT investigation requested for the
  username Berlecool" or "Caitlinn page redesign requested with awwards-tier
  design skills, to be pushed for redeploy when finished." A reader who never
  sees the source turn should understand what happened and why it mattered.
- event_type: open-ended short category.
- modality: reported_past, reported_current, intended, or expected.
- evidence: an exact verbatim excerpt from the owner User turn.
- source_turn_id: the stable ID printed on that User turn.
- subjects: explicit people, projects, places, or artifacts.
- importance: 0 to 1.
- temporal_expression: exact time wording, or empty.
- prospective_type: meeting, work, task, need, grocery, commitment, deadline, or
  another short type when the owner has a forward-looking commitment. Empty for
  a pure inquiry, status question, passing remark, or immediate request.
- prospective_action: create/update for a pending item the owner commits to as a
  forward-looking plan — something that may still be pending next time you ask.
  complete/cancel/supersede/dispute only when the owner explicitly states that
  outcome. none for inquiries, casual remarks, third-party plans, or quick tasks
  the assistant finishes in the current conversation.
- prospective_key: stable concise identity for the same item across updates,
  excluding mutable state and dates. Empty when prospective_action is none.
- prospective_text: concise description of the pending commitment in observer
  voice — "Buy milk" not "I need to buy milk." Empty when prospective_action
  is none.
- corrects_event_id: only an explicitly supplied event ID, otherwise empty.

Never turn elapsed time into confirmed completion. "I had a meeting at 9" is
reported_past; "I have a meeting at 9" is expected and pending. A question is
never an intention. A third party's intention is never the owner's prospective.
An immediate operational instruction is transient and is not a memory event.
When the owner explicitly says an errand, return, task, or commitment is done,
finished, complete, or cancelled, keep the reported event and set
prospective_action to complete or cancel with a stable key for that item. This
is an evidence-backed state transition even if no earlier pending item appears
inside the bounded exchange.

Never turn a roadmap milestone into a past completion. When a User writes a
to-do list ("what we need to do:") and includes a milestone as the final bullet
("mvp achieved"), that milestone is an intended future outcome, not a reported
past event. The list header ("what we need to do") defines the tense. Extract
it as "intended" with the milestone as the goal, or do not extract it at all.
Never assign modality "reported_past" to a milestone that appears in a to-do or
roadmap list.

Do not let temporal expressions leak from surrounding context onto a task that
doesn't share the time. If the owner says "I have a meeting tomorrow" and then
lists tasks to discuss IN that meeting, the tasks themselves don't happen at
the meeting time — they're undated intentions.

=== SHARED RULES ===

- Entity resolution: when a pronoun or generic phrase refers to a named entity
  mentioned elsewhere in the conversation, replace it with the proper name.
- Contradiction: if the User states something and later reverses it, extract
  only the final/current state.
- Authority: only User-authored statements can establish facts or events.
  Assistant turns are context only.
- Never equate aliases, handles, or people unless the User explicitly states
  the equivalence.
- Do not conflate separate statements. If the User says "I'll let Concept
  figure that out" about one topic and "We probably need to hash out the
  pricing tiers" in the next sentence, those are two different facts about two
  different responsible parties. Do not merge them into a single belief that
  assigns both responsibilities to the same entity.
- Do not embellish or add inferential descriptions. If the User says "it just
  happens automatically," record that it happens automatically — do not add
  "tracks conversation context" or any other functional description the User
  did not state. The text must be a faithful restatement, not an interpretation
  of what the thing does.
- Capture every distinct monetary amount. If the User mentions multiple dollar
  figures ("five hundred USD. So seven hundred dollars."), extract each amount
  as a separate fact or include all amounts in one fact. Do not silently drop a
  stated amount.
- Return empty arrays when nothing is supported.

OUTPUT:
Return exactly one JSON object with a "beliefs" array and an "events" array.
"""


def _unified_memory_agent():
    schema = json.dumps(UnifiedMemoryOutput.model_json_schema(), separators=(",", ":"))
    prompt = UNIFIED_MEMORY_PROMPT + "\nReturn exactly one JSON object matching: " + schema
    model = _prep_model("memory").with_structured_output(UnifiedMemoryOutput, method="json_mode")
    return ChatPromptTemplate.from_messages(
        [SystemMessage(prompt), MessagesPlaceholder("messages")]
    ) | model


def run_unified_memory_agent(transcript: str) -> tuple[list[BeliefCandidate], list[EventCandidate]]:
    result = _unified_memory_agent().invoke(
        {"messages": [{"role": "user", "content": transcript}]}
    )
    if isinstance(result, UnifiedMemoryOutput):
        return result.beliefs, result.events
    if isinstance(result, dict):
        parsed = UnifiedMemoryOutput.model_validate(result)
        return parsed.beliefs, parsed.events
    raise TypeError("unified memory agent returned an invalid structured result")


def canonical_signature(text: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", text.casefold())
    return " ".join(tokens)


def _signature_words(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", text.casefold()))


_DUPLICATE_JACCARD = 0.55


def stable_event_identity(
    *, source_turn_id: str, span: EvidenceSpan, modality: str, text: str
) -> tuple[str, str]:
    """Build the evidence-span and canonical-proposition identity required by
    the episodic contract.

    Canonicalization ignores punctuation and casing, while retaining enough of
    the proposition to keep two distinct events supported by one evidence span
    from collapsing into the same node.
    """
    material = "\x1f".join(
        (
            source_turn_id,
            str(span.start),
            str(span.end),
            modality,
            canonical_signature(text),
        )
    ).encode("utf-8")
    key = hashlib.sha256(material).hexdigest()
    return "evt_" + key[:20], key


def _candidate_turn(candidate: EventCandidate, batch: TurnBatch):
    return next(
        (
            turn
            for turn in batch.turns
            if turn.role == "user" and turn.turn_id == candidate.source_turn_id
        ),
        None,
    )


def _locate_evidence(source: str, evidence: str) -> tuple[int, int] | None:
    """Locate evidence exactly, tolerating whitespace insertion/removal only.

    Speech transcripts sometimes omit a space after punctuation while a model
    reproduces the same characters with conventional spacing. The returned
    offsets always select the original source text, so provenance remains
    verbatim and no punctuation or wording differences are accepted.
    """
    direct = source.find(evidence)
    if direct >= 0:
        return direct, direct + len(evidence)
    compact_evidence = "".join(char for char in evidence if not char.isspace())
    if not compact_evidence:
        return None
    compact_source: list[str] = []
    source_indexes: list[int] = []
    for index, char in enumerate(source):
        if char.isspace():
            continue
        compact_source.append(char)
        source_indexes.append(index)
    compact_start = "".join(compact_source).find(compact_evidence)
    if compact_start < 0:
        return None
    compact_end = compact_start + len(compact_evidence) - 1
    return source_indexes[compact_start], source_indexes[compact_end] + 1


def _is_in_todo_list_context(evidence: str, turn_text: str) -> bool:
    """Check whether the evidence appears after a to-do list header in the turn.

    If the turn contains a to-do list header ("what we need to do:", "agenda:",
    "roadmap:", etc.) and the evidence text appears after that header, the
    evidence is part of a to-do list. Any event extracted from it must be
    intended/expected (future), never reported_past/reported_current.
    """
    header_match = _TODO_LIST_HEADERS.search(turn_text)
    if header_match is None:
        return False
    evidence_pos = turn_text.find(evidence)
    if evidence_pos == -1:
        return False
    return evidence_pos >= header_match.start()


def _is_too_vague(text: str, subjects: list[str]) -> bool:
    """Reject events that are too generic to be useful on their own.

    An event is too vague when ALL its subjects are generic labels (summary,
    the owner, assistant, etc.) AND the text contains fewer than 2 significant
    content tokens OR none of the content tokens are 4+ characters long.
    """
    normalized_subjects = [s.casefold().strip() for s in subjects if s.strip()]
    has_specific_subject = any(
        s not in _GENERIC_SUBJECTS for s in normalized_subjects
    )
    if has_specific_subject:
        return False
    content_tokens = [
        t for t in _CONTENT_TOKENS.findall(text.casefold())
        if t not in _STOPWORDS and t not in _GENERIC_SUBJECTS
    ]
    unique = set(content_tokens)
    if len(unique) < 2:
        return True
    return not any(len(t) >= 4 for t in unique)


def _has_missing_action_target(text: str, subjects: list[str]) -> bool:
    """Reject plans whose action is named but whose object remains unknown."""
    if _OPEN_SLOT_INTENTION.search(text):
        return True
    normalized = {
        subject.casefold().strip() for subject in subjects if subject.strip()
    }
    if _MVP_TARGET.search(text):
        return not bool(normalized - {"mvp", "project mvp", "project", "user", "owner"})
    if _SECURITY_AUDIT_TARGET.search(text):
        return not bool(normalized - {
            "security audit", "audit", "project", "user", "owner",
        })
    return False


def _prospective_identity(candidate: EventCandidate, text: str) -> str:
    supplied = candidate.prospective_key.strip()
    if supplied:
        return supplied
    material = " ".join(candidate.subjects).strip() or text
    return "-".join(re.findall(r"[a-z0-9]+", material.casefold()))[:120]


def _is_third_party_intention(evidence: str, text: str) -> bool:
    combined = f"{evidence} {text}"
    if _THIRD_PARTY_PROSPECTIVE_PRONOUN.search(combined):
        return True
    named = _THIRD_PARTY_PROSPECTIVE_NAMED.search(combined)
    if not named:
        return False
    return named.group(1).casefold() not in {"i", "owner", "user", "we"}


def validate_event_candidates(
    candidates: Iterable[EventCandidate],
    batch: TurnBatch,
    timezone_name: str,
) -> tuple[list[ValidatedEvent], list[tuple[EventCandidate, str]]]:
    accepted: list[ValidatedEvent] = []
    rejected: list[tuple[EventCandidate, str]] = []
    seen: set[str] = set()
    seen_signatures: dict[str, str] = {}
    seen_word_sets: list[tuple[str, frozenset[str], str]] = []
    for candidate in candidates:
        turn = _candidate_turn(candidate, batch)
        evidence = candidate.evidence.strip()
        text = candidate.text.strip()
        prospective_action = candidate.prospective_action
        prospective_type = candidate.prospective_type.strip()
        prospective_key = candidate.prospective_key.strip()
        prospective_text = candidate.prospective_text.strip()
        third_party_intention = _is_third_party_intention(evidence, text)
        if prospective_action == "none" and _EXPLICIT_CANCELLATION.search(evidence):
            prospective_action = "cancel"
        elif prospective_action == "none" and _EXPLICIT_COMPLETION.search(evidence):
            prospective_action = "complete"
        if prospective_action != "none":
            prospective_type = prospective_type or candidate.event_type.strip() or "task"
            prospective_key = prospective_key or _prospective_identity(candidate, text)
            prospective_text = prospective_text or text
        evidence_span = _locate_evidence(turn.text, evidence) if turn and evidence else None
        reason = ""
        if turn is None:
            reason = "unauthorized_source_turn"
        elif not evidence or not text:
            reason = "malformed"
        elif evidence_span is None:
            reason = "evidence_not_in_owner_turn"
        elif not 0 <= candidate.importance <= 1:
            reason = "malformed_importance"
        elif (
            candidate.modality in {"intended", "expected"}
            and prospective_action == "none"
            and not third_party_intention
        ):
            reason = "missing_prospective_action"
        elif prospective_action != "none" and not prospective_key:
            reason = "missing_prospective_key"
        elif (
            candidate.event_type.strip().casefold() in _TRANSIENT_OPERATIONAL_EVENT_TYPES
            and prospective_action == "none"
        ):
            reason = "transient_operational_request"
        elif has_unresolved_reference(text) or (
            prospective_action != "none"
            and has_unresolved_reference(prospective_text)
        ):
            reason = "unresolved_reference"
        elif _has_missing_action_target(text, candidate.subjects) or (
            prospective_action != "none"
            and _has_missing_action_target(prospective_text, candidate.subjects)
        ):
            reason = "missing_action_target"
        elif _is_too_vague(text, candidate.subjects):
            reason = "too_vague"
        elif (
            candidate.modality in {"reported_past", "reported_current"}
            and _TODO_LIST_HEADERS.search(turn.text)
            and _is_in_todo_list_context(evidence, turn.text)
        ):
            reason = "milestone_in_todo_list"
        if reason:
            rejected.append((candidate, reason))
            continue

        start, end = evidence_span
        evidence = turn.text[start:end]
        span = EvidenceSpan(turn.turn_id, start, end)
        event_id, key = stable_event_identity(
            source_turn_id=turn.turn_id,
            span=span,
            modality=candidate.modality,
            text=text,
        )
        if key in seen:
            continue
        sig = canonical_signature(text)
        sig_key = f"{turn.turn_id}\x1f{sig}"
        if sig_key in seen_signatures:
            rejected.append((candidate, "near_duplicate_event"))
            continue
        words = _signature_words(text)
        near_dup = False
        candidate_prospective_key = prospective_key.casefold()
        for _prev_id, prev_words, prev_prospective_key in seen_word_sets:
            if (
                candidate_prospective_key
                and prev_prospective_key
                and candidate_prospective_key != prev_prospective_key
            ):
                continue
            if not words or not prev_words:
                continue
            union = words | prev_words
            if len(union) == 0:
                continue
            jaccard = len(words & prev_words) / len(union)
            if jaccard >= _DUPLICATE_JACCARD:
                near_dup = True
                break
        if near_dup:
            rejected.append((candidate, "near_duplicate_event"))
            continue
        seen.add(key)
        seen_signatures[sig_key] = event_id
        seen_word_sets.append((event_id, words, candidate_prospective_key))
        modality = EventModality(candidate.modality)
        if prospective_action != "none" and third_party_intention:
            prospective_action = "none"
            prospective_type = ""
            prospective_key = ""
            prospective_text = ""
        if prospective_action != "none" and _INQUIRY_PROSPECTIVE.search(evidence):
            prospective_action = "none"
            prospective_type = ""
            prospective_key = ""
            prospective_text = ""
        if prospective_action != "none" and _IMMEDIATE_REQUEST.search(evidence):
            prospective_action = "none"
            prospective_type = ""
            prospective_key = ""
            prospective_text = ""
        temporal = resolve_temporal_expression(
            candidate.temporal_expression,
            turn.observed_at,
            timezone_name,
            future_facing=modality in {EventModality.INTENDED, EventModality.EXPECTED},
        )
        is_future = modality in {EventModality.INTENDED, EventModality.EXPECTED}
        creates_prospective = prospective_action != "none"
        accepted.append(
            ValidatedEvent(
                event_id=event_id,
                idempotency_key=key,
                text=text,
                event_type=candidate.event_type.strip() or "experience",
                modality=modality,
                observed_at=turn.observed_at,
                occurred_start=None if is_future else temporal.start,
                occurred_end=None if is_future else temporal.end,
                temporal_precision=temporal.precision,
                temporal_expression=candidate.temporal_expression.strip(),
                temporal_confidence=temporal.confidence,
                evidence=evidence,
                evidence_span=span,
                source=turn.source,
                scope_id=turn.scope_id,
                subjects=tuple(dict.fromkeys(s.strip() for s in candidate.subjects if s.strip())),
                importance=candidate.importance,
                extraction_version=EVENT_EXTRACTION_VERSION,
                prospective_type=prospective_type,
                prospective_action=prospective_action,
                prospective_key=prospective_key,
                prospective_text=prospective_text,
                due_start=temporal.start if is_future and creates_prospective else None,
                due_end=temporal.end if is_future and creates_prospective else None,
                corrects_event_id=candidate.corrects_event_id.strip(),
            )
        )
    return accepted, rejected


def render_batch(batch: TurnBatch) -> str:
    return "\n".join(
        f"{'User' if turn.role == 'user' else 'Assistant'}: "
        f"[source_turn_id={turn.turn_id}] {turn.text}"
        for turn in batch.turns
    )
