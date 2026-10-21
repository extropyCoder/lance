lance

Mechanical extractor for attacker-controlled data reaching Python sinks. Produces candidates for optional model explanation; discharged items are machine-refuted and skipped. A person decides on every candidate.

Python 3.11 or newer. Dependencies: tree-sitter, tree-sitter-python.

Without venv (ensurepip missing here): `pip3 install --target .deps tree-sitter tree-sitter-python pytest` then `PYTHONPATH=.deps:src python3 -m lance.cli review fixtures/bad_shell.py --out /tmp/lance-demo`. A normal `pip install -e .` works where venv is available.

The mechanical review works with the model server stopped; meta.model is the string "not called".

Start local server: `bash ~/Work/Dev/Qwen3-Coder/start-qwen.sh` (serves qwen-coder-local at http://127.0.0.1:8081/v1; key file beside script read at runtime, never printed). Then `python3 -m lance.cli explain /tmp/lance-demo`.

A candidate is still open. A discharged item was refuted by the extractor (clean_subprocess.py is the safe_api example). reject and accept change only review.json.

Refusal rule: model output containing "payload", "proof of concept", "to exploit", or "curl " is refused and the item left unreviewed; timeouts also leave the item unreviewed.
