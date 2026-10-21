# lance — Wittgenstein semifinal plan

A local Python secure-code-review agent. The model is not allowed to invent structure. It may only speak about a tree-sitter precondition graph, cite its IDs, and propose a fix. A human accepts or rejects. Nothing is remediated automatically.

This repository is the submission. It already exists at `~/Work/Dev/lance` (`git@github.com:extropyCoder/lance.git`). Do not create another repo.

Deadline: semifinal submission **31 October 2026**. Today is 20 October. Eleven days, one language, three sink kinds.

`silver-telegram` (Masaq) is prior art you own, cited in the proposal. It is not the submission, and its modules are not imported.

## Decision

Build the catalog item **Secure Code Review Agent (Python)**, using the Masaq lesson rather than the Masaq engine.

The lesson, from `silver-telegram/docs/architecture/prep-structures.md` and `silver-telegram/docs/architecture/DESIGN-attack-precondition-graph.md`:

- Prep is model-free and writes JSON.
- Every checker emits the same envelope: kind, predicate, site, relation, plus a `discharged` list of things already refuted.
- Guards (the code checks this) are a different relation from assumptions (the code relies on this and never checks it).
- Markdown is a view. JSON is the boundary.
- Nothing is auto-promoted. The human review queue is the authority.

`silver-telegram` is read-only. Do not edit, commit, format, or hook it. If a pattern is worth keeping, copy that file into this repo and adapt it here. No symlinks, no imports across the two trees, no shared venv.

Do not copy Solidity checkers, Slither, Solodit, contest profiles, x402, the Submitted stage, `attack_tree.py`'s full backward walk, or `skills/methodology/poc-generation`.

Do not generate exploits, replays, or attack scripts. The product explains a broken assumption and names a fix. If the model emits exploit steps, the validator rejects that output and the demo shows the rejection.

## Coordination

The coordinator does not write product code. Two subagents do the work, on different models, so the reviewer does not share the builder's blind spots.

| Role | Model | May edit |
|---|---|---|
| Coordinator | `xai/grok-4.7` | `PLAN.md` only, unless a subagent is blocked |
| Builder | `openai/gpt-5.3-codex-spark#high` | This repo, never `silver-telegram` |
| Reviewer | `openai/gpt-6.1-sol#high` | Nothing. Read, run tests, report. |

Fallback builder if Codex Spark fails: `xai/grok-build-0.1`. That fallback is in effect. On 20 October 2026 the OpenAI provider rejected `openai/gpt-5.3-codex-spark` with: not supported when using Codex with a ChatGPT account. Do not then use a Grok model as the reviewer. If a review is shallow, rerun the reviewer on `openai/gpt-6-astra#high`. Do not use `openai/gpt-6-luna` for either role.

These models are development tools. The submitted agent still calls local Qwen3-Coder. Do not name GPT or Grok as the submission's base model.

First build slice is schema and fixtures only. No tree-sitter walk, no CLI, no model client, until that slice has passed review.

## Why this scores

| Weight | How lance hits it |
|---|---|
| Technical quality 35% | Deterministic extractor with a pinned schema, tests on labeled fixtures, model output rejected unless it cites real IDs. |
| Real-world impact 30% | A reviewer runs one command on a file or a small tree and gets a queue, not a chat transcript. Catalog item they already named. |
| Innovation 20% | The language is the product. Guards vs assumptions, discharged as the skeptic, model confined to the graph. Wittgenstein, not a linter wrapper. |
| Documentation 15% | Proposal states the manifesto mapping, the model lineage, and the three-month roadmap in one place. Demo is one screen recording. |

## Hard constraints

- Open-source base model, local inference, no cloud API.
- Use the server you already have: `Qwen3-Coder-30B-A3B-Instruct-Q4_K_M` via `~/Work/Dev/Qwen3-Coder/start-qwen.sh`, alias `qwen-coder-local`, OpenAI-compatible API on `127.0.0.1:8081`. Cite the model card, the GGUF filename, and the SHA-256 in `MODEL-SHA256.txt`. Lineage is Qwen3-Coder (Apache-2.0 weights). Active parameters are 3B; say that. Do not claim the 18GB file is tiny. Do not read or commit `.qwen-api-key`.
- CPU inference (`--gpu-layers 0`) will be slow. The mechanical report is the demo backbone. Record **one** model explanation, not a batch.
- Human in the loop. The CLI never writes `accepted` by itself.
- Semi-autonomous. The agent recommends. It does not edit the target tree.
- Register for the tournament before writing code if that is not already done. The page still shows a form, and it also says registration closed 15 September 2026. Confirm the form accepts the team before spending the week.

## Non-goals

- Solidity, Rust, Move, Cairo, or C in the semifinal.
- A call graph, a taint engine, or the Attack Precondition Graph as designed. Those are the finals roadmap.
- Multi-agent swarms, reinforcement learning, fine-tuning.
- Live probing of applications, generated PoCs, dependency confusion, or anything that attacks a running target.
- Importing or editing Masaq. Reimplement the envelope here. Copy a file only when this repo needs that text, then change the copy. The grant, if you win, should cover this repo only.
- A second repository. All code, fixtures, proposal, and demo notes live here.

## Layout

```text
lance/
  README.md                 # how to run, model lineage, what it refuses to do
  PLAN.md                   # this file
  PROPOSAL.md               # the submission narrative
  pyproject.toml            # package + dev deps
  src/lance/
    __init__.py
    schema.py               # vocabulary constants, load-time validation
    extract.py              # tree-sitter walk, candidate + discharged emission
    sinks.py                # the three sink tables
    reach.py                # entry-point and intra-function source class
    review.py               # human queue read/write
    explain.py              # one local model call, schema-checked
    cli.py                  # lance review PATH
  fixtures/                 # labeled, tiny, committed
  tests/
  demo/
    script.md               # the recording checklist
```

Python 3.14 is already on this machine. Pin `tree-sitter` and `tree-sitter-python` in this project, not the Masaq venv.

License suggestion: Apache-2.0, so the open-source story matches the base model. Your choice. State it in the README.

## The language

One JSON document per run. No markdown crosses a stage boundary. A markdown review view may be rendered from the JSON.

### Vocabulary (closed)

Sink kinds:

- `shell-invocation` — `os.system`, `os.popen`, `subprocess.*` with `shell=True`, or a string passed where a list is the safe form.
- `sql-concat` — `cursor.execute` / `executemany` whose SQL argument is an f-string, `%` format, `.format`, or `+` concatenation.
- `dynamic-exec` — `eval`, `exec`, `pickle.loads`, `yaml.load` without `SafeLoader`, `marshal.loads`.

Relations, taken from the APG note and renamed only where a defender needs the word:

- `must-satisfy` — a guard is on the path. The question is whether the guard covers this sink.
- `can-violate` — the sink relies on an assumption the code does not check.

Source classes, intra-function only:

- `constant`
- `parameter`
- `request` — names that resolve to Flask/FastAPI `request`, Django `request`, `input()`, `sys.argv`
- `unknown`

Discharge reasons, also closed:

- `constant_source`
- `safe_api` — list-form subprocess without `shell=True`, parameterized `execute` with a placeholder, `yaml.safe_load`
- `not_an_entry` — sink is in a function that is not an entry and is not called from one in this file
- `guard_dominates` — only if you can show it by tree structure in this file. If you cannot, do not invent this reason.

Reachability for the semifinal is **one file**. An entry is:

- a function called from `if __name__ == "__main__"`
- a function decorated `@app.route`, `@router.get/post/...`, `@app.get/post/...`
- the body of that `if __name__` block itself

No cross-file resolution. If the only call is in another file, the candidate stays, relation unchanged, reachability `unknown`. Unknown is not discharged.

### Candidate envelope

```json
{
  "id": "C-001",
  "kind": "shell-invocation",
  "predicate": "command is not attacker-controlled",
  "relation": "can-violate",
  "source_class": "request",
  "source_name": "host",
  "site": {"file": "app.py", "function": "ping", "line": 14},
  "entry": {"function": "ping", "kind": "route"},
  "evidence": ["call.shell_true", "arg.fstring", "name.host"]
}
```

`evidence` is a list of extractor fact IDs, not prose. The model may quote these. It may not add new ones.

### Discharged envelope

```json
{
  "id": "D-001",
  "kind": "shell-invocation",
  "reason": "safe_api",
  "site": {"file": "app.py", "function": "ping", "line": 22},
  "evidence": ["call.list_form", "shell.absent"]
}
```

Discharged items never enter the model prompt. They appear in the human view so the reviewer can see what the skeptic killed. That is the false-positive story.

### Model output

One call per surviving candidate, not one call for the file. Input is that candidate plus the cited source lines and nothing else.

```json
{
  "candidate_id": "C-001",
  "verdict": "exploitable",
  "summary": "one sentence a reviewer can paste",
  "fix": "the code change, not an attack",
  "cited_ids": ["C-001"]
}
```

`verdict` is `exploitable` | `smell` | `insufficient`. Reject the call if `cited_ids` is not exactly `[candidate_id]`, if the JSON does not parse, or if the text matches a small denylist of exploit-shaping phrases (`payload`, `proof of concept`, `to exploit`, `curl ...`). On rejection, keep the mechanical candidate and record `explanation: refused`. The review can still be demoed.

Temperature 0. Log the full request and response under `runs/<timestamp>/` and gitignore that directory.

### Human queue

`review.json` next to the run, or a path the user passes. Status values: `unreviewed`, `accepted`, `rejected`. Default `unreviewed`. The CLI has `lance accept C-001` and `lance reject C-001 --reason "..."`. It does not edit the target source.

## Fixtures

Six files, committed, each under 40 lines. Labels live in `fixtures/expected.json`, which the tests compare against extractor IDs and discharge reasons, not against model prose.

| File | Expect |
|---|---|
| `bad_shell.py` | route builds an f-string into `os.system` → one `can-violate` candidate |
| `bad_sql.py` | route concatenates into `cursor.execute` → one candidate |
| `bad_eval.py` | `eval` of a query parameter → one candidate |
| `clean_subprocess.py` | list-form `subprocess.run` → discharged `safe_api` |
| `clean_sql.py` | `execute("... %s", (param,))` → discharged `safe_api` |
| `clean_yaml.py` | `yaml.safe_load` → discharged `safe_api` |

Add a seventh only if a real miss shows up: a helper in the same file called by a route, so same-file call reachability is tested. Do not add it on day one.

Model eval is separate and small. Three recorded calls, scored by hand: did it cite the ID, did it refuse to write an exploit, did the fix match the sink kind. Do not build an LLM-as-judge.

## CLI

```text
lance review PATH [--json out.json]
lance explain RUN_DIR          # requires the local server
lance accept RUN_DIR C-001
lance reject RUN_DIR C-001 --reason "test fixture, not production"
```

`review` must succeed with the server stopped. That is the robustness claim.

## Day by day

Dates are the work, not a promise that each day is eight hours. Stop at the end of day 7 if the extractor and the queue are solid and the model call is ugly. A working mechanical agent with a refused or slow explanation beats a chat demo.

### 20 Oct — freeze the contract

- Confirm tournament registration.
- Stay in this repo. Replace the README stub with model lineage and the refusal rule.
- Write `schema.py` and `fixtures/expected.json` before any tree-sitter code.
- Decide the six fixture files and commit them unlabeled-in-code, labeled-in-JSON.

Exit: a stranger can read the schema and know what the program will refuse to output.

### 21–22 Oct — extractor

- Walk tree-sitter-python. Calls, decorators, f-strings, binary `+`, `if __name__`.
- Implement the three sink tables as data, not branches piled into one function. Same rule you already enforce in Masaq: vocabulary is a table.
- Emit candidates and discharged. Tests fail if an expected ID is missing or a clean fixture produces a candidate.
- No model, no CLI polish.

Exit: `pytest` green on the six fixtures. This is the submission if everything else slips.

### 23 Oct — same-file reachability

- Mark entries.
- If a sink's function is called directly from an entry in the same file, copy that entry onto the candidate.
- If it is not, and it is not itself an entry, discharge `not_an_entry` only when the function is never called in this file. If it is called from a non-entry, leave reachability `unknown`. Do not guess.
- One test for the helper case if you add the seventh fixture. Otherwise skip.

Exit: no cross-file code exists. If you feel the need for an import graph, write it in the finals section of the proposal and stop.

### 24 Oct — CLI and review queue

- `lance review` writes `run.json` (candidates, discharged, meta with model name "not called") and `review.md` rendered from it.
- Accept/reject updates status only.
- Meta records tree-sitter grammar version, lance version, and file hashes.

Exit: you can demo with the server off.

### 25 Oct — local model call

- Client talks to `http://127.0.0.1:8081/v1`, key read from the existing key file at runtime, never printed, never committed.
- System prompt: you are a reviewer; you explain impact and a fix; you do not write exploit steps; you return only the JSON schema; you cite only the given ID.
- Validator as specified above.
- Timeout. On timeout, the candidate remains `unreviewed` and `explanation: unavailable`.

Exit: one saved call log for `bad_shell.py`, and one deliberate refusal test using a stub response that contains "proof of concept".

### 26 Oct — proposal and README

`PROPOSAL.md` sections, in this order:

1. What a reviewer does with it, in one paragraph.
2. The language: guards, assumptions, discharged. One JSON excerpt from a real fixture run.
3. Model lineage, where it runs, what leaves the machine (nothing).
4. Human gate, with a screenshot or pasted `review.json` showing a rejection.
5. What you measured: fixture table, pass/fail, not a percentage theater.
6. What you will not do: no PoC, no auto-patch, no cloud.
7. Finals roadmap, three months: same schema, cross-file calls, then one more sink family. Not a new product. Not Solidity unless you explicitly park that as optional and after the Python path is boring.

README: install, start the model server, run the demo, interpret discharged vs candidate.

### 27 Oct — demo script

`demo/script.md` is a three-minute recording outline:

1. Server stopped. `lance review fixtures/bad_shell.py`. Show the candidate and the cited line.
2. `lance review fixtures/clean_subprocess.py`. Show discharged `safe_api` and that the model was not called.
3. Start the local server. `lance explain` on the one bad candidate. Show the citation check.
4. `lance reject` with a reason. Show the queue.
5. Say the sentence: the model cannot see a world it was not given.

Record on 28 Oct if the 27th is still fixing the prompt. Do not re-tune the extractor to make the model sound smarter.

### 28–29 Oct — buffer

Allowed fixes only:

- a tree-sitter node type you got wrong (f-string, keyword `shell`)
- a discharge false positive on a fixture
- the model returning prose around the JSON, which the parser should already tolerate by extracting one JSON object

Not allowed: a fourth sink, a second language, a web UI, a swarm, a fine-tune.

### 30 Oct — freeze

- Tag `semifinal-2026-10-30`.
- Fresh venv, `pytest`, one cold `lance review` on all fixtures.
- Confirm no secrets, no `.qwen-api-key`, no `runs/` logs with anything you do not want to publish. Commit one redacted call log if you want the validator visible.
- Read the proposal aloud once. Cut any sentence that says "autonomous".

### 31 Oct — submit

- Push the tag.
- Submit whatever the tournament form asks for: repo URL, proposal, demo link.
- Stop. Do not refactor on submission day.

## Finals roadmap (write it, do not build it)

If this places in the top three, the three months are:

1. Cross-file calls, still Python, same envelope. Unknown becomes resolved or stays unknown with a reason.
2. The assumption branch from the APG note: one new predicate family (unchecked return of a fallible call), extractor plus discharged, no redesign.
3. Only then consider C, as a second grammar emitting the same JSON. Solidity stays out unless a judge asks. The contest is not a bug-bounty leaderboard.

Reinforcement learning stays out. A learned ranker is not the bottleneck. The bottleneck is the language.

## Risks

| Risk | Response |
|---|---|
| Registration actually closed 15 September | Confirm on 20 Oct before day-two work. If closed, keep the repo anyway; do not pretend. |
| tree-sitter-python node types differ from what you remember from Solidity | Spike one call node on 21 Oct morning. Adjust the table, not the schema. |
| Qwen on CPU takes minutes | Demo the mechanical path. Record a single explain, even if you cut the wait in the video and show the saved log. |
| Model writes an exploit anyway | Validator rejects it. That rejection is a feature in the recording, not a failure. |
| Temptation to edit or import Masaq | Masaq is read-only. Copy the specific file into this repo if you need it. Different license surface, secrets nearby, and the judges will not run it. |
| Scope creep into "real taint" | Same-file or it is unknown. Write the urge into the roadmap. |

## Done means

A reviewer who has never seen Masaq can clone `lance`, run it on the fixtures with the model server off, and get the labeled candidates and discharges. With the server on, one candidate gets a cited fix or a recorded refusal. A human rejection is in the queue. The proposal maps that to the manifesto without claiming autonomy.
