"""Tree-sitter based extractor for lance sinks."""

from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser, Node
import tree_sitter_python

from lance.schema import PREDICATES, EVIDENCE_FACTS, validate_candidate, validate_discharged
from lance import sinks

parser = Parser(Language(tree_sitter_python.language()))


SINK_PATTERNS = sinks.SINK_PATTERNS

ARG_DANGER_FACTS = frozenset(["fstring", "concat", "format", "percent", "literal", "placeholder"])


def node_text(node: Node | None) -> str:
    if node is None:
        return ""
    t = node.text
    if isinstance(t, (bytes, bytearray)):
        return t.decode("utf-8", errors="replace")
    return str(t)


def get_call_signature(func_node: Node | None) -> tuple | None:
    if func_node is None:
        return None
    if func_node.type == "identifier":
        return (None, node_text(func_node))
    if func_node.type == "attribute":
        obj = func_node.child_by_field_name("object")
        attr = func_node.child_by_field_name("attribute")
        if obj and attr:
            if obj.type == "identifier":
                return (node_text(obj), node_text(attr))
            else:
                return ("*", node_text(attr))
        if attr:
            return ("*", node_text(attr))
    return None


def lookup_sink(sig: tuple | None) -> dict | None:
    if not sig:
        return None
    mod, name = sig
    for pat in SINK_PATTERNS:
        s0, s1 = pat["spec"]
        match_mod = (s0 is None or s0 == "*" or s0 == mod or (mod is None and s0 is None))
        match_name = (s1 == "*" or s1 == name)
        if match_mod and match_name:
            return pat
    return None


def is_request_get_call(call_node: Node) -> bool:
    if call_node.type != "call":
        return False
    func = call_node.child_by_field_name("function")
    if not func or func.type != "attribute":
        return False
    if node_text(func.child_by_field_name("attribute")) != "get":
        return False
    obj = func.child_by_field_name("object")
    if not obj or obj.type != "attribute":
        return False
    oobj = obj.child_by_field_name("object")
    oattr = obj.child_by_field_name("attribute")
    if node_text(oobj) == "request" and node_text(oattr) in ("args", "form", "values"):
        return True
    return False


def collect_assigns(block: Node) -> dict[str, Node]:
    assigns: dict[str, Node] = {}
    for stmt in block.children:
        if stmt.type != "expression_statement":
            continue
        for ch in stmt.children:
            if ch.type == "assignment":
                left = ch.child_by_field_name("left")
                right = ch.child_by_field_name("right")
                if left and left.type == "identifier" and right is not None:
                    var = node_text(left)
                    assigns[var] = right
    return assigns


def analyze_arg(arg: Node, assigns: dict[str, Node], sources: dict) -> dict:
    info: dict[str, Any] = {
        "danger": None,
        "source_class": "unknown",
        "source_name": "",
        "ev": [],
    }
    if arg is None:
        return info
    if arg.type == "identifier":
        v = node_text(arg)
        if v in sources:
            s = sources[v]
            info["source_class"] = s["source_class"]
            info["source_name"] = s["source_name"]
            info["ev"].append("name.host" if s["source_name"] == "host" else "name.request")
            info["danger"] = "source"
            return info
        if v in assigns:
            rhs = assigns[v]
            sub = analyze_arg(rhs, assigns, sources)
            if sub["source_class"] != "unknown":
                info["source_class"] = sub["source_class"]
                info["source_name"] = sub["source_name"]
                for e in sub["ev"]:
                    if e.startswith("name."):
                        info["ev"].append(e)
                if sub["danger"]:
                    info["danger"] = sub["danger"]
            return info
    elif arg.type == "string":
        has_f = False
        interp_v = None
        for c in arg.children:
            if c.type == "interpolation":
                has_f = True
                for ic in c.children:
                    if ic.type == "identifier":
                        interp_v = node_text(ic)
                        break
                break
        if has_f:
            info["danger"] = "fstring"
            info["ev"].append("arg.fstring")
            if interp_v and interp_v in sources:
                s = sources[interp_v]
                info["source_class"] = s["source_class"]
                info["source_name"] = s["source_name"]
                info["ev"].append("name.host" if s["source_name"] == "host" else "name.request")
            elif interp_v:
                info["source_name"] = interp_v
    elif arg.type == "binary_operator":
        op = None
        for c in arg.children:
            if c.type in ("+", "%"):
                op = c.type
                break
        if op == "+":
            info["danger"] = "concat"
            info["ev"].append("arg.concat")
            for c in arg.children:
                if c.type == "identifier":
                    sub = analyze_arg(c, assigns, sources)
                    if sub["source_class"] != "unknown":
                        info["source_class"] = sub["source_class"]
                        info["source_name"] = sub["source_name"]
                        for e in sub["ev"]:
                            if e.startswith("name."):
                                info["ev"].append(e)
                    break
        elif op == "%":
            info["danger"] = "percent"
            info["ev"].append("arg.percent")
            for c in arg.children:
                if c.type == "identifier":
                    sub = analyze_arg(c, assigns, sources)
                    if sub["source_class"] != "unknown":
                        info["source_class"] = sub["source_class"]
                        info["source_name"] = sub["source_name"]
                    break
    elif arg.type == "call":
        f = arg.child_by_field_name("function")
        if f and f.type == "attribute" and node_text(f.child_by_field_name("attribute")) == "format":
            info["danger"] = "format"
            info["ev"].append("arg.format")
            al = arg.child_by_field_name("arguments")
            if al:
                for ch in al.children:
                    if ch.type == "identifier":
                        sub = analyze_arg(ch, assigns, sources)
                        if sub["source_class"] != "unknown":
                            info["source_class"] = sub["source_class"]
                            info["source_name"] = sub["source_name"]
                            for e in sub.get("ev", []):
                                if e.startswith("name."):
                                    info["ev"].append(e)
                        break
    return info


def is_true_value(val_node: Node | None) -> bool:
    if val_node is None:
        return False
    if val_node.type == "true":
        return True
    txt = node_text(val_node).strip().lower()
    return txt in ("true", "1")


def unique_ev(evs: list[str]) -> list[str]:
    seen: set[str] = set()
    res: list[str] = []
    for e in evs:
        if e and e not in seen:
            seen.add(e)
            res.append(e)
    return res


def get_entry_for_func(func_node: Node) -> dict:
    parent = getattr(func_node, "parent", None)
    func_name = node_text(func_node.child_by_field_name("name"))
    entry = {"function": func_name, "kind": "unknown"}
    if parent and parent.type == "decorated_definition":
        for ch in parent.children:
            if ch.type == "decorator":
                for dch in ch.children:
                    if dch.type == "call":
                        f = dch.child_by_field_name("function")
                        if f and f.type == "attribute":
                            dec_attr = node_text(f.child_by_field_name("attribute"))
                            if dec_attr in ("route", "get", "post", "put", "delete", "patch"):
                                entry["kind"] = "route"
                                break
                        elif f and f.type == "identifier":
                            dec_name = node_text(f)
                            if dec_name in ("route", "get", "post", "put", "delete", "patch"):
                                entry["kind"] = "route"
                                break
    return entry


def extract_path(path: Path) -> dict:
    src_bytes = path.read_bytes()
    tree = parser.parse(src_bytes)
    root = tree.root_node

    candidates: list[dict] = []
    discharged: list[dict] = []

    func_nodes: list[Node] = []

    def collect_funcs(n: Node) -> None:
        if n.type == "function_definition":
            func_nodes.append(n)
        for c in n.children:
            collect_funcs(c)

    collect_funcs(root)

    for func_node in func_nodes:
        func_name = node_text(func_node.child_by_field_name("name"))
        entry = get_entry_for_func(func_node)
        body = func_node.child_by_field_name("body")
        if body is None:
            continue
        assigns = collect_assigns(body)
        call_nodes: list[Node] = []

        def collect_calls(n: Node) -> None:
            if n.type == "call":
                call_nodes.append(n)
            for c in n.children:
                collect_calls(c)

        collect_calls(body)

        sources: dict[str, dict] = {}
        for var, rhs in assigns.items():
            if rhs is not None and rhs.type == "call" and is_request_get_call(rhs):
                sources[var] = {"source_class": "request", "source_name": var}

        for call_node in call_nodes:
            func_f = call_node.child_by_field_name("function")
            sig = get_call_signature(func_f)
            pat = lookup_sink(sig)
            if pat is None:
                continue
            kind = pat["kind"]
            base_ev = list(pat.get("base_ev", ()))
            safe = pat.get("safe", False)

            arglist = call_node.child_by_field_name("arguments")
            arg_nodes: list[Node] = []
            keywords: dict[str, Node] = {}
            if arglist:
                for ch in arglist.children:
                    if ch.type == "keyword_argument":
                        kn = ch.child_by_field_name("name")
                        kv = ch.child_by_field_name("value")
                        if kn:
                            keywords[node_text(kn)] = kv
                    elif ch.is_named and ch.type not in ("(", ")", ","):
                        arg_nodes.append(ch)

            is_cand = False
            reason = None
            extra_ev: list[str] = []
            source_class = "unknown"
            source_name = ""

            if kind == "shell-invocation" and sig and sig[0] == "subprocess":
                has_list = len(arg_nodes) > 0 and arg_nodes[0].type == "list"
                has_shell_kw = "shell" in keywords
                shell_true = has_shell_kw and is_true_value(keywords.get("shell"))
                if has_list and not has_shell_kw:
                    extra_ev.extend(["call.list_form", "shell.absent"])
                    is_cand = False
                    reason = "safe_api"
                elif shell_true:
                    extra_ev.append("call.shell_true")
                    is_cand = True
                elif has_list:
                    extra_ev.append("call.list_form")
                    is_cand = False
                    reason = "safe_api"
                else:
                    is_cand = True
                if is_cand:
                    for a in arg_nodes:
                        inf = analyze_arg(a, assigns, sources)
                        if inf["source_class"] != "unknown":
                            source_class = inf["source_class"]
                            source_name = inf["source_name"]
                            for e in inf["ev"]:
                                if e not in extra_ev:
                                    extra_ev.append(e)
                            break
            else:
                if kind == "shell-invocation":
                    if len(arg_nodes) > 0:
                        a0 = arg_nodes[0]
                        inf = analyze_arg(a0, assigns, sources)
                        if inf["danger"] or inf["source_class"] != "unknown":
                            is_cand = True
                            extra_ev.extend(inf["ev"])
                            source_class = inf["source_class"]
                            source_name = inf["source_name"]
                elif kind == "sql-concat":
                    if len(arg_nodes) >= 2:
                        a1 = arg_nodes[1]
                        if a1.type in ("list", "tuple"):
                            extra_ev.append("arg.placeholder")
                            is_cand = False
                            reason = "safe_api"
                    if len(arg_nodes) >= 1 and reason is None:
                        a0 = arg_nodes[0]
                        inf = analyze_arg(a0, assigns, sources)
                        if inf["danger"] in ("concat", "fstring", "format", "percent") or inf["source_class"] != "unknown":
                            is_cand = True
                            if inf["danger"] in ARG_DANGER_FACTS:
                                extra_ev.append(f"arg.{inf['danger']}")
                            for e in inf["ev"]:
                                if e not in extra_ev:
                                    extra_ev.append(e)
                            if inf["source_class"] != "unknown":
                                source_class = inf["source_class"]
                                source_name = inf["source_name"]
                elif kind == "dynamic-exec":
                    if safe:
                        is_cand = False
                        reason = "safe_api"
                    else:
                        if len(arg_nodes) > 0:
                            a0 = arg_nodes[0]
                            inf = analyze_arg(a0, assigns, sources)
                            if inf["source_class"] != "unknown" or inf["danger"]:
                                is_cand = True
                                if inf["danger"] in ARG_DANGER_FACTS:
                                    extra_ev.append(f"arg.{inf['danger']}")
                                for e in inf["ev"]:
                                    if e not in extra_ev:
                                        extra_ev.append(e)
                                source_class = inf["source_class"]
                                source_name = inf["source_name"]
                            elif sig and sig[0] == "yaml" and not safe:
                                is_cand = True
                                source_class = "unknown"
                                source_name = "?"

            if is_cand and entry.get("kind") == "route":
                if "reach.route" not in extra_ev:
                    extra_ev.append("reach.route")

            site = {
                "file": path.name,
                "function": func_name,
                "line": call_node.start_point.row + 1,
            }
            ev_list = unique_ev(base_ev + extra_ev)

            if is_cand:
                if source_class == "unknown" and not source_name:
                    source_name = "?"
                cand_obj: dict = {
                    "id": "",
                    "kind": kind,
                    "predicate": PREDICATES[kind],
                    "relation": "can-violate",
                    "source_class": source_class,
                    "source_name": source_name,
                    "site": site,
                    "entry": {"function": entry["function"], "kind": entry["kind"]},
                    "evidence": ev_list,
                }
                candidates.append(cand_obj)
            elif reason is not None:
                dis_obj: dict = {
                    "id": "",
                    "kind": kind,
                    "reason": reason,
                    "site": site,
                    "evidence": ev_list,
                }
                discharged.append(dis_obj)

    candidates.sort(key=lambda c: c["site"]["line"])
    discharged.sort(key=lambda d: d["site"]["line"])

    for i, c in enumerate(candidates, 1):
        c["id"] = f"C-{i:03d}"
    for i, d in enumerate(discharged, 1):
        d["id"] = f"D-{i:03d}"

    for c in candidates:
        validate_candidate(c)
    for d in discharged:
        validate_discharged(d)

    return {"candidates": candidates, "discharged": discharged}
