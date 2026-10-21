"""CLI for lance review queue (no model calls)."""

import argparse
import hashlib
import importlib.metadata
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lance.extract import extract_path
from lance.schema import REVIEW_STATUSES, validate_candidate, validate_discharged
from lance import __version__


def _get_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except Exception:
        return "unavailable"


def _render_review_md(run: dict[str, Any], review: dict[str, Any]) -> str:
    lines: list[str] = ["# Lance Review", ""]
    items = {it["id"]: it for it in review.get("items", [])}
    for c in run.get("candidates", []):
        cid = c["id"]
        it = items.get(cid, {"status": "unreviewed", "reason": ""})
        lines.append(f"## {cid} {c.get('kind', '')}")
        site = c.get("site", {})
        lines.append(
            f"- site: {site.get('file', '')}:{site.get('line', '')} in {site.get('function', '')}()"
        )
        lines.append(f"- status: {it.get('status', 'unreviewed')}")
        if it.get("reason"):
            lines.append(f"- reason: {it['reason']}")
        lines.append("")
    for d in run.get("discharged", []):
        lines.append(f"## {d.get('id', '')} {d.get('kind', '')} (discharged)")
        lines.append(f"- reason: {d.get('reason', '')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def review(path: str, out: str | None, json_file: str | None) -> int:
    p = Path(path)
    if p.is_dir():
        print("error: PATH must be a file, not a directory", file=sys.stderr)
        return 1
    if not p.is_file():
        print(f"error: {path} is not a file", file=sys.stderr)
        return 1

    src_bytes = p.read_bytes()
    sha = hashlib.sha256(src_bytes).hexdigest()

    try:
        result = extract_path(p)
    except Exception as e:
        print(f"error: extract failed: {e}", file=sys.stderr)
        return 1

    cands: list[dict] = result.get("candidates", [])
    disch: list[dict] = result.get("discharged", [])

    try:
        for c in cands:
            validate_candidate(c)
        for d in disch:
            validate_discharged(d)
    except Exception as e:
        print(f"error: validation failed: {e}", file=sys.stderr)
        return 1

    meta: dict[str, Any] = {
        "model": "not called",
        "lance_version": __version__,
        "tree_sitter": _get_version("tree-sitter"),
        "tree_sitter_python": _get_version("tree-sitter-python"),
        "files": [{"path": p.name, "sha256": sha}],
    }

    run_data: dict[str, Any] = {
        "candidates": cands,
        "discharged": disch,
        "meta": meta,
    }

    if out:
        run_dir = Path(out)
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = Path("runs") / ts

    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "run.json").write_text(json.dumps(run_data, indent=2) + "\n")

    review_items: list[dict] = [
        {"id": c["id"], "status": "unreviewed", "reason": ""}
        for c in cands
    ]
    review_data: dict[str, Any] = {"items": review_items}
    (run_dir / "review.json").write_text(json.dumps(review_data, indent=2) + "\n")

    md = _render_review_md(run_data, review_data)
    (run_dir / "review.md").write_text(md)

    if json_file:
        Path(json_file).write_text(json.dumps(run_data, indent=2) + "\n")

    return 0


def _load_review(run_dir: str) -> tuple[Path, dict[str, Any]]:
    rd = Path(run_dir)
    rj = rd / "review.json"
    if not rj.is_file():
        print(f"error: no review.json in {run_dir}", file=sys.stderr)
        return rd, {}
    try:
        data = json.loads(rj.read_text())
        if not isinstance(data, dict):
            data = {}
        items = data.get("items", [])
        if not isinstance(items, list):
            items = []
        return rd, {"items": items}
    except Exception:
        print(f"error: invalid review.json in {run_dir}", file=sys.stderr)
        return rd, {}


def accept(run_dir: str, cid: str) -> int:
    if not (isinstance(cid, str) and cid.startswith("C-")):
        return 1
    rd, data = _load_review(run_dir)
    if not data:
        return 1
    items: list[dict] = data["items"]
    found = False
    changed = False
    for item in items:
        if item.get("id") == cid:
            found = True
            if item.get("status") == "accepted":
                return 0  # no-op success, do not rewrite
            item["status"] = "accepted"
            changed = True
            break
    if not found:
        return 1
    if changed:
        (rd / "review.json").write_text(json.dumps({"items": items}, indent=2) + "\n")
    return 0


def reject(run_dir: str, cid: str, reason: str | None) -> int:
    if not reason or not str(reason).strip():
        return 1
    if not (isinstance(cid, str) and cid.startswith("C-")):
        return 1
    rd, data = _load_review(run_dir)
    if not data:
        return 1
    items: list[dict] = data["items"]
    found = False
    for item in items:
        if item.get("id") == cid:
            found = True
            item["status"] = "rejected"
            item["reason"] = str(reason)
            break
    if not found:
        return 1
    (rd / "review.json").write_text(json.dumps({"items": items}, indent=2) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lance")
    sub = parser.add_subparsers(dest="cmd", required=True)

    rev = sub.add_parser("review", help="review a python file")
    rev.add_argument("path", help="path to python file")
    rev.add_argument("--out", help="write run to this dir instead of runs/<ts>")
    rev.add_argument("--json", dest="json_file", help="also write copy of run.json to FILE")

    acc = sub.add_parser("accept", help="accept a candidate")
    acc.add_argument("run_dir")
    acc.add_argument("id")

    rej = sub.add_parser("reject", help="reject a candidate")
    rej.add_argument("run_dir")
    rej.add_argument("id")
    rej.add_argument("--reason", required=True)

    args = parser.parse_args(argv)

    if args.cmd == "review":
        return review(args.path, args.out, args.json_file)
    elif args.cmd == "accept":
        return accept(args.run_dir, args.id)
    elif args.cmd == "reject":
        return reject(args.run_dir, args.id, args.reason)
    return 1


if __name__ == "__main__":
    sys.exit(main())
