lance

Mechanical extractor for attacker-controlled data reaching Python sinks. Produces candidates for optional model explanation; discharged items are machine-refuted and skipped. A person decides on every candidate.

Python 3.11 or newer. Dependencies: tree-sitter, tree-sitter-python.

Without venv (ensurepip missing here): `pip3 install --target .deps tree-sitter tree-sitter-python pytest` then `PYTHONPATH=.deps:src python3 -m lance.cli review fixtures/bad_shell.py --out /tmp/lance-demo`. A normal `pip install -e .` works where venv is available.

The mechanical review works with the model server stopped; meta.model is the string "not called".

Start local server: `bash ~/Work/Dev/Qwen3-Coder/start-qwen.sh` (serves qwen-coder-local at http://127.0.0.1:8081/v1; key file beside script read at runtime, never printed). Then `python3 -m lance.cli explain /tmp/lance-demo`.

Each model call waits 15 seconds by default. To wait longer, pass a positive finite number of seconds: `python3 -m lance.cli explain /tmp/lance-demo --timeout 120`. The default is unchanged, and `--timeout` has no environment variable form.

Every explain attempt records a `diagnostics` object on the item in `review.json` (also in `calls/<id>.json`): `category`, `elapsed_seconds`, `timeout_seconds`, and `http_status` only for HTTP errors. It is replaced on each attempt. `category` is one of:

- `ok`: the output passed the checks (`explanation` is `cited`).
- `timeout`: the call hit the timeout (`unavailable`).
- `http_error`: the server answered with an HTTP error; `http_status` has the numeric code, for example 401 for an auth failure (`unavailable`).
- `connection_error`: the connection failed or was dropped (`unavailable`).
- `response_parse_error`: the HTTP body was not a JSON object (`unavailable`).
- `validation_error`: no valid model JSON object, wrong citation, schema failure or phrase denylist hit (`refused`).
- `unexpected_error`: any other failure; no details are recorded (`unavailable`).

Diagnostics hold no exception text, URLs, headers or error bodies. `calls/<id>.json` still holds the raw model response, which is not redacted.

A candidate is still open. A discharged item was refuted by the extractor (clean_subprocess.py is the safe_api example). reject and accept change only review.json.

Refusal rule: model output containing "payload", "proof of concept", "to exploit", or "curl " is refused and the item left unreviewed; timeouts also leave the item unreviewed.
