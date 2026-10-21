"""Tests for lance CLI review queue."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

from lance.cli import main


def test_review_bad_shell(tmp_path: Path) -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "bad_shell.py"
    before = hashlib.sha256(fixture.read_bytes()).hexdigest()

    outdir = tmp_path / "r1"
    ret = main(["review", str(fixture), "--out", str(outdir)])
    assert ret == 0

    after = hashlib.sha256(fixture.read_bytes()).hexdigest()
    assert before == after, "fixture must be unchanged"

    runj = outdir / "run.json"
    assert runj.is_file()
    data = json.loads(runj.read_text())
    assert len(data.get("candidates", [])) == 1
    assert data["meta"]["model"] == "not called"
    assert data["meta"]["lance_version"] == "0.1.0"
    assert data["meta"]["files"][0]["path"] == "bad_shell.py"
    assert data["meta"]["files"][0]["sha256"] == before

    revj = outdir / "review.json"
    rdata = json.loads(revj.read_text())
    assert len(rdata.get("items", [])) == 1
    item = rdata["items"][0]
    assert item["id"] == "C-001"
    assert item["status"] == "unreviewed"
    assert item["reason"] == ""

    assert (outdir / "review.md").is_file()


def test_review_clean_subprocess(tmp_path: Path) -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "clean_subprocess.py"
    outdir = tmp_path / "r2"
    ret = main(["review", str(fixture), "--out", str(outdir)])
    assert ret == 0

    data = json.loads((outdir / "run.json").read_text())
    assert data.get("candidates", []) == []
    disch = data.get("discharged", [])
    assert len(disch) == 1
    assert disch[0].get("reason") == "safe_api"

    rdata = json.loads((outdir / "review.json").read_text())
    assert rdata.get("items", []) == []


def test_review_directory_exits_nonzero(tmp_path: Path) -> None:
    d = tmp_path / "somedir"
    d.mkdir()
    ret = main(["review", str(d)])
    assert ret != 0


def test_accept_then_reject(tmp_path: Path) -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "bad_shell.py"
    outdir = tmp_path / "r3"
    ret = main(["review", str(fixture), "--out", str(outdir)])
    assert ret == 0

    run_bytes = (outdir / "run.json").read_bytes()

    # accept
    ret = main(["accept", str(outdir), "C-001"])
    assert ret == 0
    rdata = json.loads((outdir / "review.json").read_text())
    assert rdata["items"][0]["status"] == "accepted"
    assert rdata["items"][0]["reason"] == ""
    assert (outdir / "run.json").read_bytes() == run_bytes

    # reject
    ret = main(["reject", str(outdir), "C-001", "--reason", "test reason"])
    assert ret == 0
    rdata = json.loads((outdir / "review.json").read_text())
    assert rdata["items"][0]["status"] == "rejected"
    assert rdata["items"][0]["reason"] == "test reason"
    assert (outdir / "run.json").read_bytes() == run_bytes

    # accept already accepted is no-op
    # first make accepted
    (outdir / "review.json").write_text(
        json.dumps({"items": [{"id": "C-001", "status": "accepted", "reason": ""}]}, indent=2) + "\n"
    )
    ret = main(["accept", str(outdir), "C-001"])
    assert ret == 0
    # still accepted
    rdata = json.loads((outdir / "review.json").read_text())
    assert rdata["items"][0]["status"] == "accepted"


def test_reject_without_reason_exits_nonzero_and_no_change(tmp_path: Path) -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "bad_shell.py"
    outdir = tmp_path / "r4"
    main(["review", str(fixture), "--out", str(outdir)])
    before = (outdir / "review.json").read_bytes()

    # without --reason: argparse will SystemExit
    with pytest.raises(SystemExit) as excinfo:
        main(["reject", str(outdir), "C-001"])
    assert excinfo.value.code != 0

    # status unchanged
    after = (outdir / "review.json").read_bytes()
    assert before == after
    rdata = json.loads(after.decode())
    assert rdata["items"][0]["status"] == "unreviewed"


def test_no_network_imports_static() -> None:
    cli_py = Path(__file__).parent.parent / "src" / "lance" / "cli.py"
    src = cli_py.read_text()
    assert "urllib" not in src
    assert "requests" not in src
    assert "http.client" not in src
    assert "socket" not in src


def test_reject_unknown_id_no_create(tmp_path: Path) -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "bad_shell.py"
    outdir = tmp_path / "r5"
    main(["review", str(fixture), "--out", str(outdir)])
    before_items = json.loads((outdir / "review.json").read_text())["items"]

    ret = main(["reject", str(outdir), "C-999", "--reason", "no"])
    assert ret != 0
    after = json.loads((outdir / "review.json").read_text())["items"]
    assert after == before_items  # no new item created


def test_accept_reject_d_id_nonzero(tmp_path: Path) -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "bad_shell.py"
    outdir = tmp_path / "r6"
    main(["review", str(fixture), "--out", str(outdir)])

    ret = main(["accept", str(outdir), "D-001"])
    assert ret != 0

    ret = main(["reject", str(outdir), "D-001", "--reason", "x"])
    assert ret != 0


# explain tests (use stubs; never touch real key file or port 8081)

import os
from lance.explain import explain, default_transport


def _make_stub(ret_val: str = "", exc: Exception | None = None):
    calls: list[dict] = []

    def stub(req: dict) -> str:
        calls.append(req)
        if exc is not None:
            raise exc
        return ret_val

    return stub, calls


def test_explain_stub_cited_stores_model_output_and_log_no_auth(tmp_path: Path) -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "bad_shell.py"
    outdir = tmp_path / "re1"
    main(["review", str(fixture), "--out", str(outdir)])

    valid = json.dumps(
        {
            "candidate_id": "C-001",
            "verdict": "exploitable",
            "summary": "impact: x",
            "fix": "use safe api",
            "cited_ids": ["C-001"],
        }
    )
    stub, calls = _make_stub(valid)

    ret = explain(str(outdir), transport=stub)
    assert ret == 0
    assert len(calls) == 1

    rdata = json.loads((outdir / "review.json").read_text())
    item = rdata["items"][0]
    assert item["id"] == "C-001"
    assert item["status"] == "unreviewed"
    assert item["explanation"] == "cited"
    assert "model_output" in item
    assert item["model_output"]["candidate_id"] == "C-001"
    assert item["model_output"]["summary"] == "impact: x"

    clog = outdir / "calls" / "C-001.json"
    assert clog.is_file()
    clog_text = clog.read_text()
    assert "Authorization" not in clog_text
    assert "you are a reviewer" in clog_text  # request messages present, no auth/key


def test_explain_stub_refused_does_not_store_and_no_raise(tmp_path: Path) -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "bad_shell.py"
    outdir = tmp_path / "re2"
    main(["review", str(fixture), "--out", str(outdir)])

    refused_text = (
        '{"candidate_id":"C-001","verdict":"exploitable",'
        '"summary":"proof of concept","fix":"no","cited_ids":["C-001"]}'
    )
    stub, calls = _make_stub(refused_text)

    ret = explain(str(outdir), transport=stub)
    assert ret == 0
    assert len(calls) == 1

    rdata = json.loads((outdir / "review.json").read_text())
    item = rdata["items"][0]
    assert item["explanation"] == "refused"
    assert "model_output" not in item
    # summary not stored
    assert "summary" not in item
    assert item["status"] == "unreviewed"


def test_explain_stub_timeout_unavailable_no_raise(tmp_path: Path) -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "bad_shell.py"
    outdir = tmp_path / "re3"
    main(["review", str(fixture), "--out", str(outdir)])

    stub, calls = _make_stub(exc=TimeoutError("boom"))

    ret = explain(str(outdir), transport=stub)
    assert ret == 0
    assert len(calls) == 1

    rdata = json.loads((outdir / "review.json").read_text())
    item = rdata["items"][0]
    assert item["explanation"] == "unavailable"
    assert "model_output" not in item
    assert item["status"] == "unreviewed"


def test_explain_only_discharged_zero_calls(tmp_path: Path) -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "clean_subprocess.py"
    outdir = tmp_path / "re4"
    main(["review", str(fixture), "--out", str(outdir)])

    data = json.loads((outdir / "run.json").read_text())
    assert data.get("candidates", []) == []
    assert len(data.get("discharged", [])) > 0
    rdata = json.loads((outdir / "review.json").read_text())
    assert rdata.get("items", []) == []

    stub, calls = _make_stub("unused")

    ret = explain(str(outdir), transport=stub)
    assert ret == 0
    assert len(calls) == 0  # never sent


def test_explain_default_http_unavailable_no_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "bad_shell.py"
    outdir = tmp_path / "re5"
    main(["review", str(fixture), "--out", str(outdir)])

    keyf = tmp_path / "test.key"
    keyf.write_text("dummykey\n")  # one line, not real key file

    monkeypatch.setenv("LANCE_API_BASE", "http://127.0.0.1:9/v1/chat/completions")
    monkeypatch.setenv("LANCE_API_KEY_FILE", str(keyf))

    # use default transport via explain with short timeout; conn refused -> unavailable fast
    ret = explain(str(outdir), timeout=1.0)
    assert ret == 0

    rdata = json.loads((outdir / "review.json").read_text())
    item = rdata["items"][0]
    assert item["explanation"] == "unavailable"
    assert "model_output" not in item
    assert item["status"] == "unreviewed"

    clog = outdir / "calls" / "C-001.json"
    assert clog.is_file()
    # no auth in log
    assert "Authorization" not in clog.read_text()


def test_explain_regression_second_explain_clears_previous_model_output(tmp_path: Path) -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "bad_shell.py"
    outdir = tmp_path / "re6"
    main(["review", str(fixture), "--out", str(outdir)])

    # First stub returns a valid object. model_output is present and explanation is cited.
    valid = json.dumps(
        {
            "candidate_id": "C-001",
            "verdict": "exploitable",
            "summary": "impact: x",
            "fix": "use safe api",
            "cited_ids": ["C-001"],
        }
    )
    stub1, calls1 = _make_stub(valid)

    ret = explain(str(outdir), transport=stub1)
    assert ret == 0

    rdata = json.loads((outdir / "review.json").read_text())
    item = rdata["items"][0]
    assert item["id"] == "C-001"
    assert item["status"] == "unreviewed"
    assert item["explanation"] == "cited"
    assert "model_output" in item
    assert item["model_output"]["candidate_id"] == "C-001"

    # Second stub for the same run returns a body containing "proof of concept".
    # explanation is refused and model_output is absent.
    refused_body = (
        '{"candidate_id":"C-001","verdict":"exploitable",'
        '"summary":"proof of concept","fix":"no","cited_ids":["C-001"]}'
    )
    stub2, calls2 = _make_stub(refused_body)

    ret = explain(str(outdir), transport=stub2)
    assert ret == 0

    rdata = json.loads((outdir / "review.json").read_text())
    item = rdata["items"][0]
    assert item["explanation"] == "refused"
    assert "model_output" not in item
    assert item["status"] == "unreviewed"

    # capture review item after the refusal stub (for reporting)
    (Path("/tmp") / "review_item_after_refusal.json").write_text(
        json.dumps(item, indent=2) + "\n"
    )

    # Third stub raises TimeoutError. explanation is unavailable and model_output is absent.
    stub3, calls3 = _make_stub(exc=TimeoutError("boom"))

    ret = explain(str(outdir), transport=stub3)
    assert ret == 0

    rdata = json.loads((outdir / "review.json").read_text())
    item = rdata["items"][0]
    assert item["explanation"] == "unavailable"
    assert "model_output" not in item
    assert item["status"] == "unreviewed"
