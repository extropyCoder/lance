What a reviewer does with it

A reviewer runs `python3 -m lance.cli review FILE --out DIR` to let the extractor emit run.json (candidates plus discharged) and review.json (initially all unreviewed). They may then run `python3 -m lance.cli explain DIR`. If the local server is up, that call cites a fix or records a refusal. If it is down, the command still runs, writes a call log, records explanation "unavailable", leaves the item unreviewed, and exits 0. Finally they run `python3 -m lance.cli reject DIR C-001 --reason "..."` (or the accept equivalent) to record a human decision. The tool recommends. It does not edit the source and it does not mark a finding accepted by itself.

The language

Guards are checks the code makes. Assumptions are conditions the code relies on and never checks. A candidate is an assumption the extractor could not discharge. A discharged item was refuted by the machine and is not sent to the model.

The real extractor output for fixtures/bad_shell.py is:

```json
{
  "id": "C-001",
  "kind": "shell-invocation",
  "predicate": "command is not attacker-controlled",
  "relation": "can-violate",
  "source_class": "request",
  "source_name": "host",
  "site": {"file": "bad_shell.py", "function": "ping", "line": 10},
  "entry": {"function": "ping", "kind": "route"},
  "evidence": ["api.os_system", "arg.fstring", "name.host", "reach.route"]
}
```

fixtures/clean_subprocess.py produces no candidate and one discharged item, id D-001, kind shell-invocation, reason safe_api, because subprocess.run is a list and shell=True is absent.

Model lineage

The base model is Qwen3-Coder-30B-A3B-Instruct, quantized Q4_K_M, file Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf, sha256 fadc3e5f8d42bf7e894a785b05082e47daee4df26680389817e2093056f088ad. Weights are Apache-2.0. Active parameters are 3B. The file is about 18GB. Inference is local llama.cpp, OpenAI-compatible API at 127.0.0.1:8081, alias qwen-coder-local. Nothing in a review leaves the machine. The mechanical review does not call the model at all.

Human gate

I ran:

PYTHONPATH=.deps:src python3 -m lance.cli review fixtures/bad_shell.py --out /tmp/lance-proposal-demo

PYTHONPATH=.deps:src python3 -m lance.cli reject /tmp/lance-proposal-demo C-001 --reason "test fixture, not production"

The resulting review.json (then deleted the directory):

```json
{
  "items": [
    {
      "id": "C-001",
      "status": "rejected",
      "reason": "test fixture, not production"
    }
  ]
}
```

The pasted JSON is exactly the file the reject command wrote. Status is rejected. The command did not edit fixtures/bad_shell.py.

What you measured

`python3 -m pytest tests -q` with PYTHONPATH including src reported 20 passed on this machine.

| fixture            | expected (one line)                                      | result |
|--------------------|----------------------------------------------------------|--------|
| bad_shell          | produces C-001 shell-invocation (request fstring to os.system, reach.route) | pass |
| bad_sql            | produces C-001 sql-concat (request param)                | pass |
| bad_eval           | produces C-001 dynamic-exec (request to eval)            | pass |
| clean_subprocess   | no candidate, D-001 shell-invocation (safe_api)          | pass |
| clean_sql          | no candidate, D-001 sql-concat (safe_api)                | pass |
| clean_yaml         | no candidate, D-001 dynamic-exec (safe_api)              | pass |
| helper_shell       | produces C-001 shell-invocation (reached from route)     | pass |

The extractor tests pin those expectations.

What this will not do

No proof of concept, no exploit script, no automatic patch, no cloud API. If the model returns exploit-shaped text, explain records explanation refused and leaves the item unreviewed. A timeout records unavailable and also leaves it unreviewed.

Finals roadmap

Same schema. First cross-file calls, still Python. Then one new predicate family: an unchecked return of a fallible call. Only after that, consider C as a second grammar emitting the same JSON. Solidity stays out unless a judge asks. Reinforcement learning stays out.

Limitations

Reachability is one hop inside one file, and a method on a class is not treated as an entry.
