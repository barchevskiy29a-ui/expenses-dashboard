"""Описание операции не должно показывать техническую метку идемпотентности.

Если источник данных пишет в «Комментарий» служебную метку вида u{id},
дашборд не должен показывать её как описание траты. Метка вырезается только
на витрине (displayNote в app.js), данные и поиск не тронуты.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

APP_JS = Path("mobile-expenses/app.js")
DATA_JSON = Path("mobile-expenses/data.json")


def _extract_function(source, name):
    start = re.search(r"function\s+" + name + r"\s*\(", source)
    if not start:
        raise RuntimeError("no function %s in app.js" % name)
    open_brace = source.find("{", start.end())
    if open_brace == -1:
        raise RuntimeError("no body of function %s" % name)
    depth = 0
    i = open_brace
    quote = None
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
    raise RuntimeError("unbalanced braces in %s" % name)


def _run_js(body):
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = APP_JS.read_text(encoding="utf-8")
    driver = _extract_function(js, "displayNote") + "\n" + body
    proc = subprocess.run(
        ["node", "-e", driver], capture_output=True, text=True, encoding="utf-8", timeout=30
    )
    if proc.returncode != 0:
        raise AssertionError("node driver failed:\n%s" % proc.stderr)
    return json.loads(proc.stdout)


def test_marker_only_comment_renders_empty():
    out = _run_js(
        "console.log(JSON.stringify({"
        "a: displayNote({subcategory:'', comment:'u000000001'}),"
        "b: displayNote({subcategory:'', comment:'u1'}),"
        "c: displayNote({}),"
        "}));"
    )
    assert out["a"] == ""
    assert out["c"] == ""


def test_marker_does_not_swallow_short_ids():
    """Короткие u+цифры (не формат метки) — обычный текст, не вырезать."""
    out = _run_js(
        "console.log(JSON.stringify({b: displayNote({subcategory:'', comment:'u1'})}));"
    )
    assert out["b"] == "u1"


def test_subcategory_wins_over_comment():
    out = _run_js(
        "console.log(JSON.stringify({"
        "a: displayNote({subcategory:'кафе', comment:'u000000002'}),"
        "}));"
    )
    assert out["a"] == "кафе"


def test_marker_with_text_keeps_text():
    out = _run_js(
        "console.log(JSON.stringify({"
        "a: displayNote({subcategory:'', comment:'u000000002 обед'}),"
        "}));"
    )
    assert out["a"] == "обед"


def test_render_transactions_uses_display_note():
    js = APP_JS.read_text(encoding="utf-8")
    body = _extract_function(js, "renderTransactions")
    assert "displayNote(x)" in body


def test_demo_data_has_no_user_markers():
    """Демо-данные не должны содержать пользовательских меток или ID."""
    data = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    for row in data["transactions"]:
        for field in ("comment", "subcategory"):
            value = row.get(field) or ""
            assert not re.search(r"\bu\d{6,}\b", value), (field, value)
