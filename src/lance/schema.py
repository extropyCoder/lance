"""Closed vocabulary and validation for lance candidates and model output.

This module is the contract for the extractor and the reviewer.
No tree-sitter, no source parsing, no network, no regex.
"""

SINKS = ("shell-invocation", "sql-concat", "dynamic-exec")
RELATIONS = ("must-satisfy", "can-violate")
SOURCE_CLASSES = ("constant", "parameter", "request", "unknown")
DISCHARGE_REASONS = ("constant_source", "safe_api", "not_an_entry", "guard_dominates")
VERDICTS = ("exploitable", "smell", "insufficient")
REVIEW_STATUSES = ("unreviewed", "accepted", "rejected")
EXPLANATION_STATES = ("refused", "unavailable")

PREDICATES = {
    "shell-invocation": "command is not attacker-controlled",
    "sql-concat": "query is not attacker-controlled",
    "dynamic-exec": "argument is not attacker-controlled",
}

EVIDENCE_FACTS = frozenset(
    [
        "call.shell_true",
        "call.list_form",
        "shell.absent",
        "arg.fstring",
        "arg.concat",
        "arg.format",
        "arg.percent",
        "arg.literal",
        "arg.placeholder",
        "name.host",
        "name.request",
        "name.argv",
        "name.input",
        "name.parameter",
        "name.constant",
        "api.eval",
        "api.exec",
        "api.pickle_loads",
        "api.yaml_load",
        "api.yaml_safe_load",
        "api.os_system",
        "api.os_popen",
        "api.subprocess",
        "api.cursor_execute",
        "reach.route",
        "reach.main",
        "reach.unknown",
    ]
)


def check_vocabulary() -> None:
    """Validate all closed vocabularies at import time."""
    collections = [
        ("SINKS", SINKS),
        ("RELATIONS", RELATIONS),
        ("SOURCE_CLASSES", SOURCE_CLASSES),
        ("DISCHARGE_REASONS", DISCHARGE_REASONS),
        ("VERDICTS", VERDICTS),
        ("REVIEW_STATUSES", REVIEW_STATUSES),
        ("EXPLANATION_STATES", EXPLANATION_STATES),
    ]
    for name, coll in collections:
        if len(coll) == 0:
            raise ValueError(f"{name} must not be empty")
        seen: set[str] = set()
        for item in coll:
            if not isinstance(item, str) or item == "" or item in seen:
                raise ValueError(f"{name} contains duplicate or empty string: {item!r}")
            seen.add(item)
    if set(PREDICATES.keys()) != set(SINKS):
        raise ValueError("PREDICATES keys must exactly match SINKS")
    if any(not f for f in EVIDENCE_FACTS):
        raise ValueError("EVIDENCE_FACTS contains empty string")
    if len(EVIDENCE_FACTS) == 0:
        raise ValueError("EVIDENCE_FACTS must not be empty")


def _check_candidate_id(cid: str) -> None:
    if not (isinstance(cid, str) and cid.startswith("C-") and len(cid) == 5 and cid[2:].isdigit()):
        raise ValueError(f"candidate id must be C- followed by three digits, got {cid!r}")


def _check_discharged_id(did: str) -> None:
    if not (isinstance(did, str) and did.startswith("D-") and len(did) == 5 and did[2:].isdigit()):
        raise ValueError(f"discharged id must be D- followed by three digits, got {did!r}")


def _check_site(site: dict) -> None:
    if not isinstance(site, dict):
        raise ValueError("site must be a dict")
    if not isinstance(site.get("file"), str) or site.get("file") == "":
        raise ValueError("site.file must be non-empty string")
    if not isinstance(site.get("function"), str) or site.get("function") == "":
        raise ValueError("site.function must be non-empty string")
    line = site.get("line")
    if not (isinstance(line, int) and line > 0):
        raise ValueError("site.line must be int > 0")


def _check_entry(entry: dict) -> None:
    if not isinstance(entry, dict):
        raise ValueError("entry must be a dict")
    if not isinstance(entry.get("function"), str) or entry.get("function") == "":
        raise ValueError("entry.function must be non-empty string")
    ek = entry.get("kind")
    if ek not in ("route", "main", "unknown"):
        raise ValueError(f"entry.kind must be route|main|unknown, got {ek!r}")


def _check_evidence(evidence: list) -> None:
    if not isinstance(evidence, list) or len(evidence) == 0:
        raise ValueError("evidence must be non-empty list")
    for fact in evidence:
        if fact not in EVIDENCE_FACTS:
            raise ValueError(f"unknown evidence fact id: {fact!r}")


def validate_candidate(obj: dict) -> None:
    """Validate a candidate dict against the closed vocabulary."""
    if not isinstance(obj, dict):
        raise ValueError("candidate must be a dict")
    _check_candidate_id(obj.get("id"))
    kind = obj.get("kind")
    if kind not in SINKS:
        raise ValueError(f"kind must be one of {SINKS}, got {kind!r}")
    if obj.get("predicate") != PREDICATES[kind]:
        raise ValueError(f"predicate must be exactly {PREDICATES[kind]!r} for kind {kind}")
    if obj.get("relation") not in RELATIONS:
        raise ValueError(f"relation must be one of {RELATIONS}")
    if obj.get("source_class") not in SOURCE_CLASSES:
        raise ValueError(f"source_class must be one of {SOURCE_CLASSES}")
    src_name = obj.get("source_name")
    if not (isinstance(src_name, str) and src_name != ""):
        raise ValueError("source_name must be non-empty string")
    _check_site(obj.get("site"))
    _check_entry(obj.get("entry"))
    _check_evidence(obj.get("evidence"))
    # require the core keys are present
    for key in ("id", "kind", "predicate", "relation", "source_class", "source_name", "site", "entry", "evidence"):
        if key not in obj:
            raise ValueError(f"missing required key: {key}")


def validate_discharged(obj: dict) -> None:
    """Validate a discharged dict. Must not contain relation/predicate/source_class."""
    if not isinstance(obj, dict):
        raise ValueError("discharged must be a dict")
    _check_discharged_id(obj.get("id"))
    kind = obj.get("kind")
    if kind not in SINKS:
        raise ValueError(f"kind must be one of {SINKS}, got {kind!r}")
    if obj.get("reason") not in DISCHARGE_REASONS:
        raise ValueError(f"reason must be one of {DISCHARGE_REASONS}")
    _check_site(obj.get("site"))
    _check_evidence(obj.get("evidence"))
    for forbidden in ("relation", "predicate", "source_class"):
        if forbidden in obj:
            raise ValueError(f"discharged must not contain {forbidden}")
    for key in ("id", "kind", "reason", "site", "evidence"):
        if key not in obj:
            raise ValueError(f"missing required key: {key}")


def validate_model_output(obj: dict, candidate_id: str) -> None:
    """Validate model output for a candidate. Raises on refused explanations."""
    if not isinstance(obj, dict):
        raise ValueError("model output must be a dict")
    if obj.get("candidate_id") != candidate_id:
        raise ValueError(f"candidate_id must equal {candidate_id!r}")
    if obj.get("verdict") not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    summary = obj.get("summary")
    if not (isinstance(summary, str) and summary != ""):
        raise ValueError("summary must be non-empty string")
    fix = obj.get("fix")
    if not (isinstance(fix, str) and fix != ""):
        raise ValueError("fix must be non-empty string")
    if obj.get("cited_ids") != [candidate_id]:
        raise ValueError(f"cited_ids must be exactly [{candidate_id!r}]")
    text = (summary or "") + (fix or "")
    if explanation_refused(text):
        raise ValueError("explanation refused due to forbidden phrase")


def explanation_refused(text: str) -> bool:
    """Return True if lowercased text contains any forbidden exploit-shaping phrase."""
    if not isinstance(text, str):
        return False
    lowered = text.lower()
    phrases = (
        "payload",
        "proof of concept",
        "proof-of-concept",
        "to exploit",
        "curl ",
    )
    return any(phrase in lowered for phrase in phrases)


check_vocabulary()
