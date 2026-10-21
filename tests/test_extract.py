"""Tests for extract pinned to fixtures/expected.json.

Six fixture tests are the exit. Main entry test skipped as hard
without modifying extract_path signature or adding files under fixtures/.
"""

import hashlib
import json
import tempfile
from pathlib import Path

from lance.extract import extract_path
from lance.schema import validate_candidate, validate_discharged, EVIDENCE_FACTS

FIXTURES = Path(__file__).parent.parent / "fixtures"

PINNED_HASHES = {
    "bad_shell.py": "897c824635c4b6f85a3b27e23b2921dd94fb84f48966bcad30ef90f30db7bc19",
    "bad_sql.py": "27aebc275a0351d2a1db1596bf7230e02c7ebc0651f368a6130cfc1e3ebf052d",
    "bad_eval.py": "71d05e835589df3ffd9db4284eb14e97edc59facd948ab74cf38ea0ed79c8c0f",
    "clean_subprocess.py": "fedbb2ad7e04b278c66e1149e1c351c1d3884d6e97df3032d371b7a38f3eaca0",
    "clean_sql.py": "c800fe5475677032f72bca8cae52c7342c78ebd62dbc8878ca151b5ab829247b",
    "clean_yaml.py": "62260c47a5534600709b7e7b3e84cc9dd9b794b0e89c1ee769f69052a7dfebdc",
    "helper_shell.py": "dcd2a500b0f76d500daf7a92492b75c8fee3f94db93f5b0c436c2f3166503f15",
    "expected.json": "3d3c95a3bd9359c00070607d633a3357a158e254ce5b56c7486c9801ed81cefe",
}


def _assert_not_modified() -> None:
    for name, expected_h in PINNED_HASHES.items():
        p = FIXTURES / name
        actual_h = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual_h == expected_h, f"{name} was modified (hash mismatch)"


REQUIRED_FACTS = {
    "bad_shell.py": ["api.os_system", "arg.fstring", "reach.route"],
    "bad_sql.py": ["api.cursor_execute", "arg.concat"],
    "bad_eval.py": ["api.eval"],
    "clean_subprocess.py": ["call.list_form", "shell.absent", "api.subprocess"],
    "clean_sql.py": ["api.cursor_execute", "arg.placeholder"],
    "clean_yaml.py": ["api.yaml_safe_load"],
    "helper_shell.py": ["api.os_system", "arg.fstring", "reach.route"],
}


def test_extract_fixtures() -> None:
    _assert_not_modified()

    with open(FIXTURES / "expected.json") as f:
        expected = json.load(f)

    for fname, exp in expected["files"].items():
        actual = extract_path(FIXTURES / fname)

        for c in actual["candidates"]:
            validate_candidate(c)
        for d in actual["discharged"]:
            validate_discharged(d)

        all_evs = []
        for item in actual.get("candidates", []) + actual.get("discharged", []):
            all_evs.extend(item.get("evidence", []))
        for fact in all_evs:
            assert fact in EVIDENCE_FACTS, f"unknown evidence fact: {fact}"

        for fact in REQUIRED_FACTS.get(fname, []):
            found = any(
                fact in item.get("evidence", [])
                for item in actual.get("candidates", []) + actual.get("discharged", [])
            )
            assert found, f"missing required fact {fact} for {fname}"

        def project_cand(c: dict) -> dict:
            return {
                "id": c["id"],
                "kind": c["kind"],
                "predicate": c["predicate"],
                "relation": c["relation"],
                "source_class": c["source_class"],
                "source_name": c["source_name"],
                "function": c["site"]["function"],
                "entry_kind": c["entry"]["kind"],
            }

        def project_disch(d: dict) -> dict:
            return {
                "id": d["id"],
                "kind": d["kind"],
                "reason": d["reason"],
                "function": d["site"]["function"],
            }

        act_cands = [project_cand(c) for c in actual["candidates"]]
        act_disch = [project_disch(d) for d in actual["discharged"]]
        exp_cands = exp.get("candidates", [])
        exp_disch = exp.get("discharged", [])

        assert act_cands == exp_cands
        assert act_disch == exp_disch

        if fname == "helper_shell.py":
            assert len(actual["candidates"]) == 1
            c = actual["candidates"][0]
            assert c["site"]["function"] == "helper"
            assert c.get("entry", {}).get("function") == "ping"
            assert c.get("entry", {}).get("kind") == "route"
            assert "reach.route" in c.get("evidence", [])
            assert "api.os_system" in c.get("evidence", [])
            assert "arg.fstring" in c.get("evidence", [])

        if exp_cands:
            assert actual["discharged"] == [], f"bad file {fname} should have empty discharged"
        if exp_disch and not exp_cands:
            assert actual["candidates"] == [], f"clean file {fname} should have empty candidates"


# Main entry test skipped: extract_path takes Path only, no in-memory
# without temp files or changing public API. Six fixture tests are exit.


def test_extract_request_sql_concat_regression() -> None:
    """In-memory regression for request-derived arg reaching sql sink.

    Writes the crashing snippet to a temp .py (never under fixtures/),
    runs extract_path, asserts the candidate properties, that no
    'arg.source' evidence is synthesized (which is not in EVIDENCE_FACTS),
    and that all evidence facts are valid.
    """
    snippet = '''from flask import Flask, request
app = Flask(__name__)

@app.route("/search")
def search():
    q = request.args.get("q")
    cursor.execute(q)
'''
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
            tmp.write(snippet)
            tmp_path = Path(tmp.name)
        actual = extract_path(tmp_path)
        assert len(actual["candidates"]) == 1, "expected exactly one candidate"
        c = actual["candidates"][0]
        assert c["kind"] == "sql-concat"
        assert c["source_class"] == "request"
        assert c["source_name"] == "q"
        assert c.get("entry", {}).get("kind") == "route"
        # no exception was raised (would have during validate if arg.source)
        all_evs: list[str] = []
        for item in actual.get("candidates", []) + actual.get("discharged", []):
            all_evs.extend(item.get("evidence", []))
        for fact in all_evs:
            assert fact in EVIDENCE_FACTS, f"unknown evidence fact: {fact}"
        assert "arg.source" not in all_evs
        assert "arg.source" not in c.get("evidence", [])
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def test_extract_unused_not_an_entry() -> None:
    """Unused function with unsafe sink (has other entry in file): discharged not_an_entry, no candidate."""
    snippet = '''from flask import Flask, request
import os
app = Flask(__name__)

@app.route("/x")
def route_func():
    pass

def unused():
    host = request.args.get("host")
    os.system(f"ping {host}")
'''
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
            tmp.write(snippet)
            tmp_path = Path(tmp.name)
        actual = extract_path(tmp_path)
        assert len(actual["candidates"]) == 0
        assert len(actual["discharged"]) == 1
        d = actual["discharged"][0]
        assert d["reason"] == "not_an_entry"
        assert d["site"]["function"] == "unused"
        assert "api.os_system" in d.get("evidence", [])
        assert "arg.fstring" in d.get("evidence", [])
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def test_extract_unused_no_route_not_an_entry() -> None:
    """Unused function with unsafe sink (no route, no if-main in file): discharged not_an_entry, no candidate."""
    snippet = """def unused():
    host = request.args.get("host")
    os.system(f"ping {host}")
"""
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
            tmp.write(snippet)
            tmp_path = Path(tmp.name)
        actual = extract_path(tmp_path)
        assert len(actual["candidates"]) == 0
        assert len(actual["discharged"]) == 1
        d = actual["discharged"][0]
        assert d["reason"] == "not_an_entry"
        assert d["site"]["function"] == "unused"
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def test_extract_two_hop_unknown_reach() -> None:
    """Two-hop from route: helper gets unknown entry + reach.unknown, no reach.route."""
    snippet = '''from flask import Flask, request
import os
app = Flask(__name__)

@app.route("/ping")
def ping():
    wrapper()

def wrapper():
    helper()

def helper():
    host = request.args.get("host")
    os.system(f"ping {host}")
'''
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
            tmp.write(snippet)
            tmp_path = Path(tmp.name)
        actual = extract_path(tmp_path)
        assert len(actual["candidates"]) == 1
        c = actual["candidates"][0]
        assert c["site"]["function"] == "helper"
        assert c["entry"]["kind"] == "unknown"
        assert c["entry"]["function"] == "helper"
        assert "reach.unknown" in c.get("evidence", [])
        assert "reach.route" not in c.get("evidence", [])
        assert "api.os_system" in c.get("evidence", [])
        assert "arg.fstring" in c.get("evidence", [])
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def test_extract_main_entry() -> None:
    """if __name__ == "__main__": ping() : candidate with entry main, entry.function=ping, reach.main not route."""
    snippet = '''import os
from flask import request

def ping():
    host = request.args.get("host")
    os.system(f"ping {host}")

if __name__ == "__main__":
    ping()
'''
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
            tmp.write(snippet)
            tmp_path = Path(tmp.name)
        actual = extract_path(tmp_path)
        assert len(actual["candidates"]) == 1
        c = actual["candidates"][0]
        assert c["site"]["function"] == "ping"
        assert c["entry"]["kind"] == "main"
        assert c["entry"]["function"] == "ping"
        assert "reach.main" in c.get("evidence", [])
        assert "reach.route" not in c.get("evidence", [])
        assert "api.os_system" in c.get("evidence", [])
        assert "arg.fstring" in c.get("evidence", [])
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
