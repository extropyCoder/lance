"""Explain diagnostics, timeout and classification tests (stubs only; no network)."""

import io
import json
import math
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

import lance.explain as explain_mod
from lance.cli import main
from lance.explain import CATEGORIES, explain
from lance.schema import VERDICTS

FIXTURE = Path(__file__).parent.parent / "fixtures" / "bad_shell.py"
MARKER = "SYNTH-CRED-MARKER-9f3a"

VALID_OBJ = {
    "candidate_id": "C-001",
    "verdict": "exploitable",
    "summary": "impact: x",
    "fix": "use safe api",
    "cited_ids": ["C-001"],
}


def _run(tmp_path: Path, name: str = "run") -> Path:
    outdir = tmp_path / name
    assert main(["review", str(FIXTURE), "--out", str(outdir)]) == 0
    return outdir


def _stub(ret: str = "", exc: Exception | None = None):
    calls: list[dict] = []

    def stub(req: dict) -> str:
        calls.append(req)
        if exc is not None:
            raise exc
        return ret

    return stub, calls


def _item(outdir: Path) -> dict:
    return json.loads((outdir / "review.json").read_text())["items"][0]


def _log(outdir: Path) -> dict:
    return json.loads((outdir / "calls" / "C-001.json").read_text())


def _envelope(content: str) -> str:
    return json.dumps({"choices": [{"message": {"content": content}}]})


def _http_error(code: int) -> HTTPError:
    return HTTPError(
        f"http://example.invalid/?k={MARKER}",
        code,
        f"msg {MARKER}",
        {"Authorization": f"Bearer {MARKER}"},  # type: ignore[arg-type]
        io.BytesIO(f"body {MARKER}".encode()),
    )


def _check_diag(item: dict, log: dict, category: str, timeout: float, status=None) -> None:
    d = item["diagnostics"]
    assert d == log["diagnostics"]
    assert d["category"] == category
    assert d["category"] in CATEGORIES
    assert d["timeout_seconds"] == timeout
    assert isinstance(d["elapsed_seconds"], (int, float))
    assert d["elapsed_seconds"] >= 0
    if status is None:
        assert set(d) == {"category", "elapsed_seconds", "timeout_seconds"}
    else:
        assert d["http_status"] == status
        assert set(d) == {"category", "elapsed_seconds", "timeout_seconds", "http_status"}


def test_category_vocabulary_is_closed() -> None:
    assert CATEGORIES == (
        "ok",
        "timeout",
        "http_error",
        "connection_error",
        "response_parse_error",
        "validation_error",
        "unexpected_error",
    )


CASES = [
    ("ok_direct", json.dumps(VALID_OBJ), None, "cited", "ok"),
    ("ok_envelope", _envelope(json.dumps(VALID_OBJ)), None, "cited", "ok"),
    ("timeout_error", "", TimeoutError(MARKER), "unavailable", "timeout"),
    (
        "timeout_urlerror",
        "",
        URLError(TimeoutError(f"timed out {MARKER}")),
        "unavailable",
        "timeout",
    ),
    ("connection_urlerror", "", URLError(f"refused {MARKER}"), "unavailable", "connection_error"),
    ("connection_reset", "", ConnectionResetError(MARKER), "unavailable", "connection_error"),
    ("parse_invalid_outer", "not json", None, "unavailable", "response_parse_error"),
    ("parse_non_object", "[1, 2]", None, "unavailable", "response_parse_error"),
    ("parse_raw_string", '"just a string"', None, "unavailable", "response_parse_error"),
    ("validation_no_object", _envelope("no json here"), None, "refused", "validation_error"),
    (
        "validation_wrong_citation",
        json.dumps({**VALID_OBJ, "candidate_id": "C-999"}),
        None,
        "refused",
        "validation_error",
    ),
    (
        "validation_bad_cited_ids",
        json.dumps({**VALID_OBJ, "cited_ids": ["C-001", "C-002"]}),
        None,
        "refused",
        "validation_error",
    ),
    (
        "validation_phrase",
        json.dumps({**VALID_OBJ, "summary": "a proof of concept"}),
        None,
        "refused",
        "validation_error",
    ),
    ("unexpected", "", RuntimeError(f"boom {MARKER}"), "unavailable", "unexpected_error"),
    ("unexpected_value", "", ValueError(MARKER), "unavailable", "unexpected_error"),
]


@pytest.mark.parametrize("name,ret,exc,expl,cat", CASES, ids=[c[0] for c in CASES])
def test_category_classification(tmp_path, capsys, name, ret, exc, expl, cat) -> None:
    outdir = _run(tmp_path)
    stub, calls = _stub(ret, exc)
    assert explain(str(outdir), transport=stub) == 0
    assert len(calls) == 1

    item = _item(outdir)
    assert item["explanation"] == expl
    assert item["status"] == "unreviewed"
    if cat == "ok":
        assert item["model_output"] == VALID_OBJ
    else:
        assert "model_output" not in item
    _check_diag(item, _log(outdir), cat, 15.0)

    captured = capsys.readouterr()
    assert MARKER not in captured.err
    assert MARKER not in captured.out
    if exc is not None:
        # raw response is empty on transport exception paths
        assert _log(outdir)["response"] == ""
        assert MARKER not in (outdir / "calls" / "C-001.json").read_text()
        assert MARKER not in (outdir / "review.json").read_text()


def test_all_seven_categories_covered() -> None:
    covered = {c[4] for c in CASES} | {"http_error"}
    assert covered == set(CATEGORIES)


@pytest.mark.parametrize("code", [401, 404, 500, 503])
def test_http_error_records_numeric_status_only(tmp_path, capsys, code) -> None:
    outdir = _run(tmp_path)
    stub, _ = _stub(exc=_http_error(code))
    assert explain(str(outdir), transport=stub) == 0

    item = _item(outdir)
    assert item["explanation"] == "unavailable"
    assert item["diagnostics"]["category"] == "http_error"
    assert item["diagnostics"]["category"] != "connection_error"
    _check_diag(item, _log(outdir), "http_error", 15.0, status=code)

    for text in (
        (outdir / "review.json").read_text(),
        (outdir / "calls" / "C-001.json").read_text(),
        capsys.readouterr().err,
    ):
        assert MARKER not in text
        assert "Authorization" not in text
        assert "Bearer" not in text


def test_no_http_status_for_non_http_errors(tmp_path) -> None:
    outdir = _run(tmp_path)
    stub, _ = _stub(exc=URLError("x"))
    explain(str(outdir), transport=stub)
    assert "http_status" not in _item(outdir)["diagnostics"]


def test_diagnostics_never_contain_exception_text_in_stderr_or_values(tmp_path, capsys) -> None:
    outdir = _run(tmp_path)
    stub, _ = _stub(exc=URLError(f"http://u/?key={MARKER}"))
    assert explain(str(outdir), transport=stub) == 0
    d = _item(outdir)["diagnostics"]
    assert MARKER not in json.dumps(d)
    assert all(isinstance(v, (str, int, float)) for v in d.values())
    assert capsys.readouterr().err == ""


def test_default_timeout_forwarded_to_default_transport(tmp_path, monkeypatch) -> None:
    outdir = _run(tmp_path)
    seen: list[float] = []

    def fake(req: dict, timeout: float = -1.0) -> str:
        seen.append(timeout)
        return json.dumps(VALID_OBJ)

    monkeypatch.setattr(explain_mod, "default_transport", fake)
    assert explain(str(outdir)) == 0
    assert seen == [15.0]
    assert _item(outdir)["diagnostics"]["timeout_seconds"] == 15.0


def test_explicit_timeout_forwarded_to_urlopen(tmp_path, monkeypatch) -> None:
    outdir = _run(tmp_path)
    keyf = tmp_path / "dummy.key"
    keyf.write_text("dummykey\n")
    monkeypatch.setenv("LANCE_API_KEY_FILE", str(keyf))
    monkeypatch.setenv("LANCE_API_BASE", "http://127.0.0.1:9/v1/chat/completions")
    seen: list[float] = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(VALID_OBJ).encode()

    def fake_urlopen(request, timeout=None):
        seen.append(timeout)
        return Resp()

    monkeypatch.setattr(explain_mod, "urlopen", fake_urlopen)

    assert explain(str(outdir), timeout=120) == 0
    assert seen == [120]
    assert _item(outdir)["diagnostics"]["timeout_seconds"] == 120.0

    seen.clear()
    assert explain(str(outdir)) == 0
    assert seen == [15.0]


def test_cli_timeout_flag_and_default_reach_urlopen(tmp_path, monkeypatch) -> None:
    outdir = _run(tmp_path)
    keyf = tmp_path / "dummy.key"
    keyf.write_text("dummykey\n")
    monkeypatch.setenv("LANCE_API_KEY_FILE", str(keyf))
    monkeypatch.setenv("LANCE_API_BASE", "http://127.0.0.1:9/v1/chat/completions")
    seen: list[float] = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(VALID_OBJ).encode()

    monkeypatch.setattr(
        explain_mod, "urlopen", lambda r, timeout=None: (seen.append(timeout), Resp())[1]
    )
    assert main(["explain", str(outdir), "--timeout", "120"]) == 0
    assert seen == [120.0]
    assert main(["explain", str(outdir)]) == 0
    assert seen == [120.0, 15.0]


def test_default_transport_httperror_with_timeout_reason_keeps_status(tmp_path, monkeypatch, capsys) -> None:
    outdir = _run(tmp_path)
    keyf = tmp_path / "dummy.key"
    keyf.write_text(f"{MARKER}\n")
    monkeypatch.setenv("LANCE_API_KEY_FILE", str(keyf))
    monkeypatch.setenv("LANCE_API_BASE", f"http://127.0.0.1:9/v1/chat/completions?k={MARKER}")

    def fake_urlopen(request, timeout=None):
        raise HTTPError(
            f"http://example.invalid/?k={MARKER}",
            401,
            TimeoutError(f"synthetic {MARKER}"),  # type: ignore[arg-type]
            {"Authorization": f"Bearer {MARKER}"},  # type: ignore[arg-type]
            io.BytesIO(f"body {MARKER}".encode()),
        )

    monkeypatch.setattr(explain_mod, "urlopen", fake_urlopen)
    assert explain(str(outdir)) == 0

    item = _item(outdir)
    assert item["explanation"] == "unavailable"
    _check_diag(item, _log(outdir), "http_error", 15.0, status=401)
    captured = capsys.readouterr()
    for text in (
        (outdir / "review.json").read_text(),
        (outdir / "calls" / "C-001.json").read_text(),
        captured.err,
        captured.out,
    ):
        assert MARKER not in text
        assert "Bearer" not in text


def test_urlopen_timeout_is_classified_as_timeout(tmp_path, monkeypatch) -> None:
    import socket

    outdir = _run(tmp_path)
    monkeypatch.setenv("LANCE_API_KEY_FILE", str(tmp_path / "absent.key"))

    def fake_urlopen(request, timeout=None):
        raise socket.timeout("timed out")

    monkeypatch.setattr(explain_mod, "urlopen", fake_urlopen)
    assert explain(str(outdir), timeout=2.5) == 0
    _check_diag(_item(outdir), _log(outdir), "timeout", 2.5)


@pytest.mark.parametrize("bad", ["0", "-1", "-0.5", "nan", "NaN", "inf", "-inf", "1e999", "abc", ""])
def test_cli_invalid_timeout_rejected_before_any_work(tmp_path, monkeypatch, capsys, bad) -> None:
    outdir = _run(tmp_path)
    before = {p.name: p.read_bytes() for p in outdir.iterdir() if p.is_file()}
    called: list[object] = []
    monkeypatch.setattr(explain_mod, "urlopen", lambda *a, **k: called.append(1))
    monkeypatch.setattr(explain_mod, "default_transport", lambda *a, **k: called.append(1))

    with pytest.raises(SystemExit) as ei:
        main(["explain", str(outdir), "--timeout", bad])
    assert ei.value.code == 2
    assert called == []
    assert not (outdir / "calls").exists()
    after = {p.name: p.read_bytes() for p in outdir.iterdir() if p.is_file()}
    assert before == after
    assert "timeout" in capsys.readouterr().err


def test_cli_invalid_timeout_on_missing_dir_does_not_create_it(tmp_path) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(SystemExit) as ei:
        main(["explain", str(missing), "--timeout", "0"])
    assert ei.value.code == 2
    assert not missing.exists()


@pytest.mark.parametrize("bad", [0, -1, 0.0, math.nan, math.inf, -math.inf, "5", None, True])
def test_programmatic_invalid_timeout_returns_error_and_mutates_nothing(tmp_path, capsys, bad) -> None:
    outdir = _run(tmp_path)
    before = {p.name: p.read_bytes() for p in outdir.iterdir() if p.is_file()}
    stub, calls = _stub(json.dumps(VALID_OBJ))
    assert explain(str(outdir), transport=stub, timeout=bad) == 1
    assert calls == []
    assert not (outdir / "calls").exists()
    after = {p.name: p.read_bytes() for p in outdir.iterdir() if p.is_file()}
    assert before == after
    assert "timeout must be a positive finite number" in capsys.readouterr().err


def test_repeated_failure_then_success_clears_stale_diagnostics(tmp_path) -> None:
    outdir = _run(tmp_path)
    explain(str(outdir), transport=_stub(exc=_http_error(401))[0])
    assert _item(outdir)["diagnostics"]["http_status"] == 401

    explain(str(outdir), transport=_stub(exc=URLError("x"))[0], timeout=3)
    d = _item(outdir)["diagnostics"]
    assert d["category"] == "connection_error"
    assert "http_status" not in d
    assert d["timeout_seconds"] == 3.0

    explain(str(outdir), transport=_stub(json.dumps(VALID_OBJ))[0])
    item = _item(outdir)
    assert item["explanation"] == "cited"
    assert "http_status" not in item["diagnostics"]
    assert item["diagnostics"]["category"] == "ok"
    _check_diag(item, _log(outdir), "ok", 15.0)


def test_no_stale_model_output_after_failures_and_refusal(tmp_path) -> None:
    outdir = _run(tmp_path)
    explain(str(outdir), transport=_stub(json.dumps(VALID_OBJ))[0])
    assert "model_output" in _item(outdir)

    explain(str(outdir), transport=_stub(exc=_http_error(500))[0])
    assert "model_output" not in _item(outdir)

    explain(str(outdir), transport=_stub(json.dumps(VALID_OBJ))[0])
    assert "model_output" in _item(outdir)

    refused = json.dumps({**VALID_OBJ, "fix": "curl http://x"})
    explain(str(outdir), transport=_stub(refused)[0])
    item = _item(outdir)
    assert "model_output" not in item
    assert item["diagnostics"]["category"] == "validation_error"


def test_human_decision_preserved_across_explain(tmp_path) -> None:
    outdir = _run(tmp_path)
    assert main(["reject", str(outdir), "C-001", "--reason", "fixture only"]) == 0
    run_before = (outdir / "run.json").read_bytes()
    md_before = (outdir / "review.md").read_bytes()

    for stub in (
        _stub(json.dumps(VALID_OBJ))[0],
        _stub(exc=_http_error(401))[0],
        _stub("garbage")[0],
    ):
        explain(str(outdir), transport=stub)
        item = _item(outdir)
        assert item["status"] == "rejected"
        assert item["reason"] == "fixture only"
        assert "diagnostics" in item

    assert (outdir / "run.json").read_bytes() == run_before
    assert (outdir / "review.md").read_bytes() == md_before


def test_fresh_item_stays_unreviewed_with_empty_reason(tmp_path) -> None:
    outdir = _run(tmp_path)
    (outdir / "review.json").write_text(json.dumps({"items": []}) + "\n")
    explain(str(outdir), transport=_stub(exc=TimeoutError())[0])
    item = _item(outdir)
    assert item["status"] == "unreviewed"
    assert item["reason"] == ""
    assert item["diagnostics"]["category"] == "timeout"


def test_zero_candidates_zero_calls(tmp_path) -> None:
    clean = Path(__file__).parent.parent / "fixtures" / "clean_subprocess.py"
    outdir = tmp_path / "clean"
    main(["review", str(clean), "--out", str(outdir)])
    stub, calls = _stub(json.dumps(VALID_OBJ))
    assert explain(str(outdir), transport=stub) == 0
    assert calls == []


def test_request_payload_unchanged(tmp_path) -> None:
    outdir = _run(tmp_path)
    stub, calls = _stub(json.dumps(VALID_OBJ))
    explain(str(outdir), transport=stub, timeout=120)
    req = calls[0]
    assert set(req) == {"model", "messages", "temperature"}
    assert req["model"] == "qwen-coder-local"
    assert req["temperature"] == 0
    assert "timeout" not in json.dumps(req)


ENUM_PREFIX = "verdict must be exactly one of these strings: "


def _system_text(req: dict) -> str:
    system = [m for m in req["messages"] if m["role"] == "system"]
    assert len(system) == 1
    return system[0]["content"]


def test_system_instruction_lists_exactly_the_allowed_verdicts(tmp_path) -> None:
    outdir = _run(tmp_path)
    stub, calls = _stub(json.dumps(VALID_OBJ))
    assert explain(str(outdir), transport=stub) == 0
    assert len(calls) == 1
    text = _system_text(calls[0])

    assert VERDICTS == ("exploitable", "smell", "insufficient")
    assert ENUM_PREFIX + json.dumps(VERDICTS) in text
    start = text.index(ENUM_PREFIX) + len(ENUM_PREFIX)
    listed, _ = json.JSONDecoder().raw_decode(text[start:])
    assert tuple(listed) == VERDICTS
    assert "exact lowercase string" in text
    assert "not a severity label" in text

    # existing constraints are retained
    assert "you are a reviewer" in text
    assert "explain the impact and name a code fix" in text
    assert "do not write exploit steps" in text
    assert "return only a JSON object with candidate_id, verdict, summary, fix, and cited_ids" in text
    assert "cite only the given candidate id" in text


@pytest.mark.parametrize("verdict", VERDICTS)
def test_each_allowed_verdict_is_cited_and_validated(tmp_path, verdict) -> None:
    outdir = _run(tmp_path)
    obj = {**VALID_OBJ, "verdict": verdict}
    stub, calls = _stub(json.dumps(obj))
    assert explain(str(outdir), transport=stub) == 0
    assert len(calls) == 1
    assert ENUM_PREFIX + json.dumps(VERDICTS) in _system_text(calls[0])

    item = _item(outdir)
    assert item["explanation"] == "cited"
    assert item["model_output"] == obj
    assert item["status"] == "unreviewed"
    assert item["reason"] == ""
    _check_diag(item, _log(outdir), "ok", 15.0)


def test_severity_label_verdict_still_refused(tmp_path) -> None:
    outdir = _run(tmp_path)
    obj = {**VALID_OBJ, "verdict": "high"}
    assert set(obj) == set(VALID_OBJ)
    assert obj["candidate_id"] == "C-001"
    assert obj["cited_ids"] == ["C-001"]
    stub, calls = _stub(_envelope(json.dumps(obj)))
    assert explain(str(outdir), transport=stub) == 0
    assert len(calls) == 1

    item = _item(outdir)
    assert item["explanation"] == "refused"
    assert "model_output" not in item
    assert item["status"] == "unreviewed"
    assert item["reason"] == ""
    _check_diag(item, _log(outdir), "validation_error", 15.0)

    logged = _log(outdir)["request"]["messages"]
    assert logged == calls[0]["messages"]
    assert ENUM_PREFIX + json.dumps(VERDICTS) in logged[0]["content"]


def test_request_shape_user_message_and_no_discharged_data(tmp_path) -> None:
    outdir = _run(tmp_path)
    run = json.loads((outdir / "run.json").read_text())
    stub, calls = _stub(json.dumps(VALID_OBJ))
    assert explain(str(outdir), transport=stub) == 0

    req = calls[0]
    assert set(req) == {"model", "messages", "temperature"}
    assert req["model"] == "qwen-coder-local"
    assert req["temperature"] == 0
    assert [m["role"] for m in req["messages"]] == ["system", "user"]
    user = json.loads(req["messages"][1]["content"])
    assert set(user) == {"candidate", "source_lines"}
    assert user["candidate"] == run["candidates"][0]
    assert 1 <= len(user["source_lines"]) <= 3
    assert "discharged" not in req["messages"][1]["content"]
