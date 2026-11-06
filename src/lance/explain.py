"""Explain candidates using local model (one call per candidate)."""

import http.client
import json
import math
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from lance.schema import VERDICTS, validate_model_output

DEFAULT_TIMEOUT = 15.0

CATEGORIES = (
    "ok",
    "timeout",
    "http_error",
    "connection_error",
    "response_parse_error",
    "validation_error",
    "unexpected_error",
)


def valid_timeout(timeout: Any) -> bool:
    """True for a positive, finite int or float (bool excluded)."""
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        return False
    return math.isfinite(timeout) and timeout > 0


def _extract_first_json(text: str) -> dict[str, Any] | None:
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text:
        return None
    # try as-is
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    # find first top-level JSON object
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict):
                        return obj
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
                return None
    # fallback
    try:
        obj = json.loads(text[start:])
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def default_transport(req: dict[str, Any], timeout: float = DEFAULT_TIMEOUT) -> str:
    """HTTP transport for OpenAI-compatible /v1/chat/completions.

    Reads LANCE_API_BASE and LANCE_API_KEY_FILE (overridable by env).
    Raises TimeoutError or other on network failure.
    Never includes key in returned value for logging.
    """
    base = os.environ.get(
        "LANCE_API_BASE", "http://127.0.0.1:8081/v1/chat/completions"
    )
    key_file = os.environ.get(
        "LANCE_API_KEY_FILE", "/home/george/Work/Dev/Qwen3-Coder/.qwen-api-key"
    )
    api_key = ""
    try:
        kf = Path(key_file)
        if kf.is_file():
            api_key = kf.read_text(encoding="utf-8").strip()
    except Exception:
        api_key = ""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = json.dumps(req).encode("utf-8")
    request = Request(base, data=data, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return body
    except HTTPError:
        # HTTPError subclasses URLError; re-raise before the URLError branch so
        # the numeric status survives whatever its reason is.
        raise
    except socket.timeout as e:
        raise TimeoutError("request timed out") from e
    except URLError as e:
        if isinstance(getattr(e, "reason", None), socket.timeout):
            raise TimeoutError("request timed out") from e
        raise


def _classify_transport_error(exc: Exception) -> tuple[str, int | None]:
    """Map a transport exception to (category, http_status) without using its text."""
    if isinstance(exc, HTTPError):
        code = exc.code
        if isinstance(code, int) and not isinstance(code, bool):
            return "http_error", code
        return "http_error", None
    if isinstance(exc, TimeoutError):
        return "timeout", None
    if isinstance(exc, URLError):
        if isinstance(getattr(exc, "reason", None), TimeoutError):
            return "timeout", None
        return "connection_error", None
    if isinstance(exc, (ConnectionError, http.client.HTTPException)):
        return "connection_error", None
    return "unexpected_error", None


def _attempt(
    transport: Callable[[dict[str, Any]], str],
    req_body: dict[str, Any],
    cid: str,
) -> tuple[str, str, dict[str, Any] | None, int | None]:
    """One model call. Returns (category, raw_response, model_output, http_status)."""
    try:
        raw = transport(req_body)
    except Exception as exc:
        category, status = _classify_transport_error(exc)
        return category, "", None, status
    if not isinstance(raw, str):
        return "response_parse_error", "", None, None
    try:
        resp = json.loads(raw)
    except (ValueError, TypeError, RecursionError):
        return "response_parse_error", raw, None, None
    if not isinstance(resp, dict):
        return "response_parse_error", raw, None, None
    try:
        choices = resp.get("choices", []) or []
        model_text = raw
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message", {}) or {}
            if isinstance(message, dict):
                model_text = message.get("content", "") or model_text
        obj = _extract_first_json(model_text)
    except Exception:
        return "unexpected_error", raw, None, None
    if obj is None:
        return "validation_error", raw, None, None
    try:
        validate_model_output(obj, cid)
    except Exception:
        return "validation_error", raw, None, None
    return "ok", raw, obj, None


def explain(
    run_dir: str,
    transport: Callable[[dict[str, Any]], str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> int:
    """Run explain for RUN_DIR.

    Uses provided transport (for tests) or default HTTP with `timeout` seconds
    per call. `timeout` must be a positive finite number; otherwise an error is
    printed and 1 is returned before any file is read or written.
    On timeout/http/conn/unparseable HTTP body/unexpected error:
    explanation="unavailable", no model_output stored, no raise.
    On validate fail: explanation="refused", no model_output stored.
    On success: model_output stored, explanation="cited".
    Every attempt replaces item["diagnostics"] with a closed-vocabulary record
    (category, elapsed_seconds, timeout_seconds, optional http_status) that never
    contains exception text, URLs, headers or bodies; it is also written to the
    call log.
    Human status and reason are left as they are (new items start "unreviewed").
    Discharged never sent (zero calls if only discharged).
    Writes calls/<id>.json with request messages + raw response (no auth/key).
    Does not touch run.json or source file.
    """
    if not valid_timeout(timeout):
        print("error: timeout must be a positive finite number", file=sys.stderr)
        return 1
    rd = Path(run_dir)
    runj = rd / "run.json"
    revj = rd / "review.json"
    if not runj.is_file():
        print(f"error: no run.json in {run_dir}", file=sys.stderr)
        return 1
    if not revj.is_file():
        print(f"error: no review.json in {run_dir}", file=sys.stderr)
        return 1
    try:
        run_data: dict[str, Any] = json.loads(runj.read_text())
        review_data: dict[str, Any] = json.loads(revj.read_text())
    except Exception:
        print(f"error: invalid json in {run_dir}", file=sys.stderr)
        return 1

    candidates: list[dict] = run_data.get("candidates", []) or []
    if not isinstance(candidates, list):
        candidates = []
    items_list: list[dict] = review_data.get("items", []) or []
    if not isinstance(items_list, list):
        items_list = []
    item_map: dict[str, dict[str, Any]] = {
        str(it.get("id")): it for it in items_list if it.get("id")
    }
    source_text: str = ""
    meta = run_data.get("meta", {})
    if isinstance(meta, dict):
        source_text = meta.get("source_text", "") or ""

    calls_dir = rd / "calls"
    calls_dir.mkdir(parents=True, exist_ok=True)

    if transport is None:
        def _t(r: dict[str, Any]) -> str:
            return default_transport(r, timeout=timeout)
        transport = _t

    for c in candidates:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id", ""))
        if not cid.startswith("C-"):
            continue

        # build source_lines: site line + prev + next if exist. never whole file.
        source_lines: list[str] = []
        site = c.get("site", {}) if isinstance(c.get("site"), dict) else {}
        line_no = site.get("line", 0)
        if source_text and isinstance(line_no, int) and line_no > 0:
            all_lines = source_text.splitlines(keepends=False)
            idx = line_no - 1
            if 0 <= idx < len(all_lines):
                if idx > 0:
                    source_lines.append(all_lines[idx - 1])
                source_lines.append(all_lines[idx])
                if idx + 1 < len(all_lines):
                    source_lines.append(all_lines[idx + 1])

        system_text = (
            "you are a reviewer; explain the impact and name a code fix; "
            "do not write exploit steps, payloads, or curl commands; "
            "return only a JSON object with candidate_id, verdict, summary, fix, and cited_ids; "
            "verdict must be exactly one of these strings: "
            + json.dumps(VERDICTS)
            + "; use the exact lowercase string, not a severity label; "
            "cite only the given candidate id."
        )
        user_obj = {"candidate": c, "source_lines": source_lines}
        user_content = json.dumps(user_obj)
        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_content},
        ]
        req_body: dict[str, Any] = {
            "model": "qwen-coder-local",
            "messages": messages,
            "temperature": 0,
        }

        started = time.monotonic()
        category, raw_response, model_output, http_status = _attempt(
            transport, req_body, cid
        )
        elapsed = max(0.0, time.monotonic() - started)
        if category == "ok":
            explanation = "cited"
        elif category == "validation_error":
            explanation = "refused"
        else:
            explanation = "unavailable"
        diagnostics: dict[str, Any] = {
            "category": category,
            "elapsed_seconds": round(elapsed, 3),
            "timeout_seconds": float(timeout),
        }
        if http_status is not None:
            diagnostics["http_status"] = http_status

        # update review item; status stays unreviewed
        if cid not in item_map:
            item_map[cid] = {"id": cid, "status": "unreviewed", "reason": ""}
        it = item_map[cid]
        it["explanation"] = explanation
        it["diagnostics"] = diagnostics
        if model_output is not None:
            it["model_output"] = model_output
        else:
            it.pop("model_output", None)
        # do not touch status or set accepted

        # write call log: messages + raw response; strip auth/key
        log = {
            "request": {"messages": messages},
            "response": raw_response,
            "diagnostics": diagnostics,
        }
        log_path = calls_dir / f"{cid}.json"
        log_path.write_text(json.dumps(log, indent=2) + "\n")

    # write updated review.json (order by candidates)
    new_items: list[dict] = []
    seen: set[str] = set()
    for c in candidates:
        cid = str(c.get("id", ""))
        if cid and cid in item_map:
            new_items.append(item_map[cid])
            seen.add(cid)
    for it in items_list:
        iid = str(it.get("id", ""))
        if iid and iid not in seen:
            new_items.append(item_map.get(iid, it))
    review_data["items"] = new_items
    revj.write_text(json.dumps(review_data, indent=2) + "\n")

    return 0
