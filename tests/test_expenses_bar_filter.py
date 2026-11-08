"""Кликабельная столбчатая диаграмма фильтрует операции (14.10.2026).

Решение владельца: круговая диаграмма удалена, остался только кликабельный
столбчатый график. Клик по столбцу показывает в «Операциях» только эту
категорию за выбранный период; повторный клик снимает фильтр; смена периода
сбрасывает выбор.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

APP_JS = Path("mobile-expenses/app.js")
INDEX_HTML = Path("mobile-expenses/index.html")


def _extract_function(source, name):
    start = re.search(r"function\s+" + name + r"\s*\(", source)
    if not start:
        raise RuntimeError("no function %s in app.js" % name)
    open_brace = source.find("{", start.end())
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


def _run_driver(extra_body, data, period="month", selected=None, want_html=False):
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = APP_JS.read_text(encoding="utf-8")
    money = re.search(r"const money = .*?;", js).group(0)
    escape = [line for line in js.splitlines()
              if line.startswith("function escapeHtml")][0]
    parts = [money, escape]
    for name in ("displayNote", "prevMonthLabel", "periodMonthPrefix",
                 "periodName", "renderTransactions", "renderTransactionsForPeriod",
                 "onCategoryBarClick"):
        parts.append(_extract_function(js, name))
    driver = (
        "\n".join(parts) + "\n"
        + f"const DATA = {json.dumps(data, ensure_ascii=False)};\n"
        + f"var SEL = {json.dumps(selected)};\n"
        + "var state = {data: DATA, selectedCategory: SEL, headItems: []};\n"
        + f"var period = {period!r};\n"
        + "const __store = {};\n"
        + "function __el(id){ if(!__store[id]) __store[id]={value:'',textContent:'',innerHTML:''}; return __store[id]; }\n"
        + "const document = {getElementById: id => __el(id)};\n"
        + "const byId = id => document.getElementById(id);\n"
        + "function renderCategoryBars(items){ __rebars.push((items||[]).length); }\n"
        + "var __rebars = [];\n"
        + extra_body + "\n"
        + "console.log(JSON.stringify({rows:(__store['transactions-body'].innerHTML.match(/<tr>/g)||[]).length,"
        + "html:__store['transactions-body'].innerHTML,"
        + "count:__store['transaction-count'].textContent,"
        + "title:__store['operations-title'].textContent,"
        + "selected:state.selectedCategory,rebars:__rebars.length}));\n"
    )
    proc = subprocess.run(["node", "-e", driver], capture_output=True,
                          text=True, encoding="utf-8", timeout=30)
    if proc.returncode != 0:
        raise AssertionError("node driver failed:\n%s" % proc.stderr)
    return json.loads(proc.stdout)


def _fixture():
    return {
        "summary": {"month_label": "2026-10"},
        "transactions": [
            {"date": "2026-10-05", "category": "Продукты", "subcategory": "", "comment": "", "amount": 100.0},
            {"date": "2026-10-06", "category": "Продукты", "subcategory": "", "comment": "", "amount": 200.0},
            {"date": "2026-10-07", "category": "Транспорт", "subcategory": "", "comment": "", "amount": 500.0},
            {"date": "2026-09-05", "category": "Продукты", "subcategory": "", "comment": "", "amount": 300.0},
        ],
    }


def test_click_filters_operations_to_category():
    out = _run_driver("onCategoryBarClick({name:'Продукты'});", _fixture())
    assert out["selected"] == "Продукты"
    assert out["rows"] == 2, out
    assert out["title"] == "Операции · Продукты"
    assert out["rebars"] == 1, "клик обязан перерисовать бары (подсветка)"


def test_second_click_clears_filter():
    out = _run_driver(
        "onCategoryBarClick({name:'Продукты'});onCategoryBarClick({name:'Продукты'});",
        _fixture(),
    )
    assert out["selected"] is None
    assert out["rows"] == 3, out
    assert out["title"] == "Операции"


def test_prev_period_shows_only_prev_month():
    out = _run_driver("renderTransactionsForPeriod();", _fixture(), period="prev")
    assert out["rows"] == 1, out
    assert "2026-09" in out["count"], out


def test_all_period_shows_everything():
    out = _run_driver("renderTransactionsForPeriod();", _fixture(), period="all")
    assert out["rows"] == 4, out


def test_click_empty_category_shows_nothing_found():
    out = _run_driver(
        "onCategoryBarClick({name:'Транспорт'});", _fixture(), period="prev",
        want_html=True,
    )
    assert out["rows"] == 1, out
    assert "Ничего не найдено" in out["html"], out


def test_search_combines_with_category_filter():
    out = _run_driver(
        "__store['search'] || (__store['search']={value:'',textContent:'',innerHTML:''});"
        "__store['search'].value='500';"
        "onCategoryBarClick({name:'Транспорт'});",
        _fixture(),
    )
    assert out["rows"] == 1, out


def test_operations_section_above_deltas():
    html = INDEX_HTML.read_text(encoding="utf-8")
    tx_pos = html.find('id="transactions"')
    deltas_pos = html.find('id="deltas-card"')
    assert tx_pos != -1 and deltas_pos != -1
    assert tx_pos < deltas_pos, "операции должны быть выше динамики категорий"


def test_operations_title_is_dynamic():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="operations-title"' in html
    assert "Операции за текущий месяц" not in html


def test_bars_hint_present():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="bars-hint"' in html


def test_operations_right_after_bars_dynamics_after_operations():
    """Порядок на телефоне: бары → операции → динамика → дельты.

    Решение владельца: журнал операций должен быть виден сразу после
    столбчатой диаграммы, а не после графика динамики.
    """
    html = INDEX_HTML.read_text(encoding="utf-8")
    bars = html.find('id="category-bars"')
    ops = html.find('id="transactions"')
    monthly = html.find('id="monthly-chart"')
    deltas = html.find('id="deltas-card"')
    assert -1 not in (bars, ops, monthly, deltas)
    assert bars < ops < monthly < deltas, "порядок: бары → операции → динамика → дельты"


def _run_live_bars_driver(extra_body, data):
    """Прогоняет настоящий renderCategoryBars с моком ECharts.

    Ловит регрессию накопления обработчиков: ECharts .on() не отменяет
    предыдущие подписки, поэтому повторный render без off() вешал бы N
    обработчиков — один клик тогглил бы выбор чётное число раз (видимо ничего).
    """
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = APP_JS.read_text(encoding="utf-8")
    money = re.search(r"const money = .*?;", js).group(0)
    escape = [line for line in js.splitlines()
              if line.startswith("function escapeHtml")][0]
    parts = [money, escape]
    for name in ("displayNote", "prevMonthLabel", "periodMonthPrefix",
                 "periodName", "renderTransactions", "renderTransactionsForPeriod",
                 "chartBase", "categoryPalette", "categoryColor",
                 "buildCategoryData", "buildBarData", "selectedOpacity",
                 "updateBarsHint", "onCategoryBarClick", "renderCategoryBars"):
        parts.append(_extract_function(js, name))
    driver = (
        "\n".join(parts) + "\n"
        + f"const DATA = {json.dumps(data, ensure_ascii=False)};\n"
        + "var state = {data: DATA, selectedCategory: null, headItems: [], charts: []};\n"
        + "var period = 'month';\n"
        + "const __store = {};\n"
        + "function __el(id){ if(!__store[id]) __store[id]={value:'',textContent:'',innerHTML:'',style:{}}; return __store[id]; }\n"
        + "const document = {getElementById: id => __el(id)};\n"
        + "const byId = id => document.getElementById(id);\n"
        + "var __chart = null;\n"
        + "const echarts = {init: el => { __chart = {el:el, opts:[], handlers:{}, "
        + "setOption(o){this.opts.push(o);}, resize(){}, "
        + "on(ev,fn){(this.handlers[ev]=this.handlers[ev]||[]).push(fn);}, "
        + "off(ev){delete this.handlers[ev];}, "
        + "fire(ev,arg){(this.handlers[ev]||[]).forEach(fn=>fn(arg));}}; return __chart; }};\n"
        + "var window = {echarts: echarts};\n"
        + extra_body + "\n"
        + "console.log(JSON.stringify({rows:(__store['transactions-body'].innerHTML.match(/<tr>/g)||[]).length,"
        + "selected:state.selectedCategory}));\n"
    )
    proc = subprocess.run(["node", "-e", driver], capture_output=True,
                          text=True, encoding="utf-8", timeout=30)
    if proc.returncode != 0:
        raise AssertionError("node driver failed:\n%s" % proc.stderr)
    return json.loads(proc.stdout)


def test_click_handler_fires_once_after_rerenders():
    """Два render подряд (смена периода + клик) — клик тогглит ровно один раз."""
    out = _run_live_bars_driver(
        "renderCategoryBars([{category:'Продукты',total:500},{category:'Транспорт',total:200}]);"
        "renderCategoryBars([{category:'Продукты',total:500},{category:'Транспорт',total:200}]);"
        "__chart.fire('click',{name:'Продукты'});",
        _fixture(),
    )
    assert out["selected"] == "Продукты", out
    assert out["rows"] == 2, out
