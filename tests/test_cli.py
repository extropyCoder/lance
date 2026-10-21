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
