"""Кнопки +/− масштабируют линейный график расходов по месяцам.

Механика: ширина #monthly-chart = max(ширина родителя, точек×80×зум, 640)
внутри .hscroll. Кнопки меняют множитель шагом ×1.25 в пределах [0.5, 3],
пересчитывают ширину и делают chart.resize(). Выбор не сохраняется между
открытиями (решение владельца).
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

APP_JS = Path("mobile-expenses/app.js")


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


def _run_js(*functions, body=""):
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = APP_JS.read_text(encoding="utf-8")
    driver = "\n".join(_extract_function(js, name) for name in functions) + "\n" + body
    proc = subprocess.run(
        ["node", "-e", driver], capture_output=True, text=True, encoding="utf-8", timeout=30
    )
    if proc.returncode != 0:
        raise AssertionError("node driver failed:\n%s" % proc.stderr)
    return json.loads(proc.stdout)


def test_zoom_buttons_markup():
    """Кнопки +/− в шапке карточки «Динамика», доступные и типизированные."""
    html = open("mobile-expenses/index.html", encoding="utf-8").read()
    assert 'id="chart-zoom-out"' in html
    assert 'id="chart-zoom-in"' in html
    assert 'aria-label="Уменьшить график"' in html
    assert 'aria-label="Увеличить график"' in html
    m = re.search(r'<button[^>]*id="chart-zoom-in"[^>]*>', html)
    assert m and 'type="button"' in m.group(0)


def test_zoom_buttons_do_not_break_hscroll_wrapper():
    """Разметка .hscroll > #monthly-chart обязана сохраниться."""
    html = open("mobile-expenses/index.html", encoding="utf-8").read()
    assert re.search(r'<div class="hscroll">\s*<div id="monthly-chart"', html)


def test_zoom_css_group():
    css = open("mobile-expenses/styles.css", encoding="utf-8").read()
    assert ".chart-zoom" in css


def test_hscroll_visible_bottom_scrollbar():
    """У линейного графика видимый горизонтальный скроллбар снизу.

    Раньше полоса была системной тонкой (на мобильных практически невидимой).
    Проверяем стилизацию для WebKit и Firefox; сам механизм overflow-x:auto
    не трогаем.
    """
    css = open("mobile-expenses/styles.css", encoding="utf-8").read()
    assert "overflow-x:auto" in css
    assert ".hscroll::-webkit-scrollbar" in css
    assert "height:10px" in css.replace(" ", "")
    assert ".hscroll::-webkit-scrollbar-thumb" in css
    assert "scrollbar-width" in css
    assert "scrollbar-color" in css


import pytest


def _zoom_consts():
    """Константы клампа живут вне функций — драйверу node их нужно передать явно."""
    js = APP_JS.read_text(encoding="utf-8")
    parts = []
    for name in ("MONTHLY_ZOOM_MIN", "MONTHLY_ZOOM_MAX", "MONTHLY_ZOOM_STEP"):
        m = re.search(name + r"\s*=\s*([0-9.]+)", js)
        if not m:
            raise RuntimeError("no const %s in app.js" % name)
        parts.append("const %s = %s;" % (name, m.group(1)))
    return "\n".join(parts) + "\n"


def _zoom_result():
    consts = _zoom_consts()
    return _run_js(
        "monthlyChartBase",
        "monthlyChartWidth",
        "setMonthlyZoom",
        body=(
            consts
            + "let monthlyZoomFactor = 1;\n"
            + "const out={};\n"
            + "out.base=monthlyChartWidth(360, 12, 1);\n"
            + "out.in1=setMonthlyZoom(1); out.w_in1=monthlyChartWidth(360, 12, monthlyZoomFactor);\n"
            + "out.in2=setMonthlyZoom(1); out.in3=setMonthlyZoom(1); out.in4=setMonthlyZoom(1);\n"
            + "out.in5=setMonthlyZoom(1); out.in6=setMonthlyZoom(1);\n"
            + "out.w_max=monthlyChartWidth(360, 12, monthlyZoomFactor);\n"
            + "monthlyZoomFactor = 1;\n"
            + "out.out1=setMonthlyZoom(-1); out.w_out1=monthlyChartWidth(360, 12, monthlyZoomFactor);\n"
            + "out.out2=setMonthlyZoom(-1); out.out3=setMonthlyZoom(-1);\n"
            + "out.out4=setMonthlyZoom(-1); out.out5=setMonthlyZoom(-1);\n"
            + "out.w_min=monthlyChartWidth(360, 12, monthlyZoomFactor);\n"
            + "out.w_min_wide=monthlyChartWidth(360, 20, monthlyZoomFactor);\n"
            + "out.parent_floor=monthlyChartWidth(1200, 2, 0.5);\n"
            + "out.hard_floor=monthlyChartWidth(100, 2, 0.5);\n"
            + "out.few=[0.5,1,1.25,2,3].map(function(z){return monthlyChartWidth(360, 3, z);});\n"
            + "out.few_pc=[0.5,1,1.25,2,3].map(function(z){return monthlyChartWidth(1100, 3, z);});\n"
            + "console.log(JSON.stringify(out));"
        ),
    )


@pytest.fixture(scope="module")
def zoom_result():
    return _zoom_result()


def test_zoom_step_up(zoom_result):
    assert zoom_result["in1"] == pytest.approx(1.25)
    assert zoom_result["w_in1"] == 12 * 80 * 1.25


def test_zoom_clamped_at_max(zoom_result):
    assert zoom_result["in6"] == pytest.approx(3.0)
    assert zoom_result["w_max"] == 12 * 80 * 3.0


def test_zoom_step_down(zoom_result):
    assert zoom_result["out1"] == pytest.approx(0.8)
    assert zoom_result["w_out1"] == pytest.approx(12 * 80 * 0.8)


def test_zoom_clamped_at_min(zoom_result):
    # Флор 320, а не ширина родителя: уменьшение должно быть видно всегда.
    assert zoom_result["out5"] == pytest.approx(0.5)
    assert zoom_result["w_min"] == 480
    assert zoom_result["w_min_wide"] == 20 * 80 * 0.5


def test_zoom_actually_changes_width_on_few_points(zoom_result):
    """Регрессия 06.10.2026: при 3 точках ширина стояла на месте при любом
    зуме (флор max(родитель, 640) съедал эффект) — кнопки казались мёртвыми
    и на мобилке, и на ПК. Теперь ширина обязана отличаться на каждом шаге."""
    assert zoom_result["few"] == [320, 640, 800, 1280, 1920]
    assert zoom_result["few_pc"] == [550, 1100, 1375, 2200, 3300]


def test_parent_width_floor_preserved(zoom_result):
    """Базовая ширина как раньше (max с clientWidth), зум масштабирует её целиком."""
    assert zoom_result["parent_floor"] == 600
    assert zoom_result["hard_floor"] == 320


def test_zoom_handler_wires_buttons():
    """Обработчики кликов вызывают пересчёт ширины и resize графика."""
    js = APP_JS.read_text(encoding="utf-8")
    body = _extract_function(js, "applyMonthlyZoom")
    assert "fitMonthlyChart()" in body
    assert "chart.resize()" in body
    assert "chart-zoom-in" in js
