"""Sink patterns for the extractor. Data only."""

SINK_PATTERNS: tuple = (
    {"spec": ("os", "system"), "kind": "shell-invocation", "base_ev": ("api.os_system",), "safe": False},
    {"spec": ("os", "popen"), "kind": "shell-invocation", "base_ev": ("api.os_popen",), "safe": False},
    {"spec": (None, "eval"), "kind": "dynamic-exec", "base_ev": ("api.eval",), "safe": False},
    {"spec": (None, "exec"), "kind": "dynamic-exec", "base_ev": ("api.exec",), "safe": False},
    {"spec": ("pickle", "loads"), "kind": "dynamic-exec", "base_ev": ("api.pickle_loads",), "safe": False},
    {"spec": ("yaml", "load"), "kind": "dynamic-exec", "base_ev": ("api.yaml_load",), "safe": False},
    {"spec": ("yaml", "safe_load"), "kind": "dynamic-exec", "base_ev": ("api.yaml_safe_load",), "safe": True},
    {"spec": ("*", "execute"), "kind": "sql-concat", "base_ev": ("api.cursor_execute",), "safe": False},
    {"spec": ("*", "executemany"), "kind": "sql-concat", "base_ev": ("api.cursor_execute",), "safe": False},
    {"spec": ("subprocess", "run"), "kind": "shell-invocation", "base_ev": ("api.subprocess",), "safe": False},
    {"spec": ("subprocess", "*"), "kind": "shell-invocation", "base_ev": ("api.subprocess",), "safe": False},
)
