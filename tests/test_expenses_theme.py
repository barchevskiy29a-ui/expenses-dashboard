"""Логика тёмной/светлой темы PWA: разрешение предпочтений и переключение.

Чистые функции из app.js прогоняются через node (без DOM): тестируем
решение темы (явный выбор пользователя > системная prefers-color-scheme)
и переключение.
"""

from __future__ import annotations

import shutil
import subprocess

APP_JS = "mobile-expenses/app.js"


def _extract_function(source, name):
    import re as _re

    start = _re.search(r"function\s+" + name + r"\s*\(", source)
    assert start, "no function %s in app.js" % name
    open_brace = source.find("{", start.end())
    depth, i, quote = 0, open_brace, None
    while i < len(source):
        ch = source[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start.start():i + 1]
        i += 1
    raise AssertionError("unbalanced braces in %s" % name)


def _run(expr):
    assert shutil.which("node"), "нужен node"
    js = open(APP_JS, encoding="utf-8").read()
    parts = [
        _extract_function(js, "resolveTheme"),
        _extract_function(js, "nextTheme"),
    ]
    script = "\n".join(parts) + "\nconsole.log(JSON.stringify(" + expr + "));\n"
    proc = subprocess.run(["node", "-e", script], capture_output=True,
                          text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    import json as _json

    return _json.loads(proc.stdout)


def test_explicit_preference_wins_over_system():
    assert _run("[resolveTheme('dark', false), resolveTheme('light', true)]") \
        == ["dark", "light"]


def test_missing_preference_falls_back_to_system():
    assert _run("[resolveTheme('', true), resolveTheme(null, false), "
                "resolveTheme(undefined, true)]") == ["dark", "light", "dark"]


def test_invalid_preference_treated_as_missing():
    assert _run("[resolveTheme('blue', true), resolveTheme('ДARK', false)]") \
        == ["dark", "light"]


def test_next_theme_toggles():
    assert _run("[nextTheme('light'), nextTheme('dark')]") \
        == ["dark", "light"]
