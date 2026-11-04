# Lance demo: terminal recording outline (~3 min)

An outline for a screen recording, not an executable script. Run each command by hand, in order, in one terminal session. Branch: `dev`. Fixtures are curated, so this shows the workflow. It does not measure detection accuracy.

Target length is about 3:10 of on-screen time. Server startup and inference waits are cut and don't count toward that.

## Preflight (off camera)

- Entry status: the semifinal deadline listed earlier (October 31) has passed. Confirm entry status with the organizers before relying on this recording for a submission.
- **Terminal A (CLI, recorded).** Keep `DEMO_ROOT` and the exports in this one session. If you open a new shell, restart from step 1.

  ```bash
  cd ~/Work/Dev/lance
  export PYTHONPATH="$PWD/.deps:$PWD/src"
  export LANCE_API_BASE=http://127.0.0.1:8081/v1/chat/completions
  export LANCE_API_KEY_FILE=$HOME/Work/Dev/Qwen3-Coder/.qwen-api-key
  mkdir -p /tmp/opencode
  DEMO_ROOT="$(mktemp -d /tmp/opencode/lance-demo.XXXXXX)"
  ```

  If `.deps` is missing, do the README installation off camera first. Don't install during the recording.
- Define a helper so on-screen commands stay short. It prints candidates, discharged items, the queue and `meta.model`, and leaves out `source_text`:

  ```bash
  proj() { python3 -c 'import json,sys; d=sys.argv[1]; r=json.load(open(d+"/run.json")); print(json.dumps({"candidates":r["candidates"],"discharged":r["discharged"],"queue":json.load(open(d+"/review.json"))["items"],"meta.model":r["meta"]["model"]},indent=2))' "$1"; }
  ```
- Never `cat` the key file or print the environment (`env`, `printenv`, `export -p`). Clear the screen before recording.
- **Terminal B (server, recorded only at the Segment 3 start).** Check it off camera. Start the recording with the Qwen server you own stopped, if you can. If you started it in Terminal B earlier, stop it there with Ctrl-C. Don't kill a listener you don't recognize. If something is already running and you leave it, review needs no inference. Skip the server start in Segment 3 and use the "already running" narration below.
- Logs, run directories and any recordings stay under `/tmp/opencode`. Don't add any of it to git, and don't commit or push.

## 1. Review the bad fixture (0:00–0:50)

```bash
python3 -m lance.cli review fixtures/bad_shell.py --out "$DEMO_ROOT/bad"
proj "$DEMO_ROOT/bad"
```

Optional, off camera: record hashes now so Segment 4 can show nothing else changed.

```bash
sha256sum fixtures/bad_shell.py "$DEMO_ROOT/bad/run.json" > "$DEMO_ROOT/bad.sha256"
```

Point at, in this order:
- `C-001`, kind `shell-invocation`, relation `can-violate`
- site `bad_shell.py` line 10 in `ping`
- entry kind `route`, source class `request`, source name `host`
- evidence `api.os_system`, `arg.fstring`, `name.host`, `reach.route`
- `meta.model` is `"not called"`

> "This is a mechanical pass over one Python file. It finds a request value flowing into a shell call. That's a candidate, a hypothesis for a person to check. It isn't proof of exploitability. No model was involved: `meta.model` says `not called`."

If the server happens to be running, add: "Review never needs inference, and `meta.model` shows it didn't call one."

## 2. Review the clean fixture (0:50–1:30)

```bash
python3 -m lance.cli review fixtures/clean_subprocess.py --out "$DEMO_ROOT/clean"
proj "$DEMO_ROOT/clean"
```

Point at:
- `candidates` is `[]`
- discharged `D-001`, reason `safe_api`, evidence `api.subprocess`, `call.list_form`, `shell.absent`
- `queue` is `[]`
- `meta.model` is `"not called"`

> "The same route calls subprocess with a list, so there's no shell string interpolation. The extractor discharges it and nothing goes to the queue. That's about this call form only. It doesn't say every subprocess call or argument is safe. Again, no model."

## 3. Explain with the local model (1:30–2:30, startup and inference cut)

**Server start (CUT, off the main timeline).** In Terminal B, run this manually and wait until it's ready. Don't run it from the CLI terminal. Skip it if the server is already up.

```bash
bash ~/Work/Dev/Qwen3-Coder/start-qwen.sh
```

Back in Terminal A:

```bash
python3 -m lance.cli explain "$DEMO_ROOT/bad"
cat "$DEMO_ROOT/bad/review.json"
```

Cut the inference wait if it's long. Say that you cut it. The default timeout is 15 seconds per call.

> "Explain sends the model exactly one call per candidate. The call carries the candidate plus at most the previous, current and next source lines, never the whole file, at temperature 0. The output is checked for schema, a citation of only this candidate id, and a short phrase denylist. A cited label means the output passed those checks. It doesn't mean the model was right. Status stays `unreviewed`."

Show `review.json` only. Don't open `calls/C-001.json` on camera, because it holds the raw response. Don't show raw model logs. Narrate what's actually on screen, whichever of the three outcomes it is:

- **Cited.** The item has `"explanation": "cited"` and a `model_output` with verdict, summary, fix and `cited_ids: ["C-001"]`. Say: "It passed the checks. Whether it's correct is for the reviewer."
- **Refused.** The item has `"explanation": "refused"` and no `model_output`. Say: "The output failed validation or the phrase denylist, so it's withheld and nothing is shown." Don't try to display the withheld text.
- **Unavailable.** The item has `"explanation": "unavailable"` and no `model_output`. Say: "The model was unreachable or timed out. We record that and move on, and the mechanical result still stands." This can happen even with the server running. A malformed HTTP body also lands here, so just show what `review.json` says.

Note: `meta.model` in `run.json` stays `"not called"` on purpose. `run.json` is the immutable review snapshot. The explain outcome lives in `review.json` and `calls/C-001.json`. Don't use `meta.model` as the latest call status.

**Failure branch (honest):**
- If it's unavailable or refused, don't paste in a stub or fake a good transcript. Keep the real result on screen.
- Optionally, off the main timeline, re-run explain on the same run before the human decision. Check the server is ready first. Re-running calls again for every candidate and overwrites `calls/C-001.json`, because the log filename is the same, so it isn't an append-only log. Whatever the second run produces is what counts.
- If it's still unavailable, say so and go on to Segment 4. The human decision doesn't depend on the model.
- If the CLI prints an error instead, show it as-is. Don't hide it.

## 4. Human decision (2:30–3:00)

```bash
python3 -m lance.cli reject "$DEMO_ROOT/bad" C-001 --reason "test fixture, not production"
cat "$DEMO_ROOT/bad/review.json"
```

Optional check that the source and snapshot are unchanged:

```bash
sha256sum -c "$DEMO_ROOT/bad.sha256"
```

Point at `"status": "rejected"` and the reason. That's a human disposition, not a model refusal.

> "A person decides. I'm rejecting this one because it's a test fixture. That's a demo disposition, not a claim that `bad_shell.py` is safe. Reject and accept change only `review.json`. The source file and `run.json` are untouched."

Don't show `review.md` here. It's the initial view written at review time and isn't refreshed by accept or reject.

## 5. Close (3:00–3:10)

> "Lance gives a person bounded evidence and leaves the decision with them. These are curated fixtures showing the workflow. They aren't a measurement of real-world detection accuracy. It looks at one file, top-level and one-hop flows, so it isn't a full precondition graph or general taint analysis. The model's phrase check isn't a universal content filter, and none of this guarantees security."

## After recording

- Leave `$DEMO_ROOT` in `/tmp/opencode` for review. Delete it by hand later if you want.
- Don't `cat` the key file, and don't commit or push any run output or recording.
