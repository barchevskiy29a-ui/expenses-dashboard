"""Плитка «Операций» следует за выбранным периодом.

Инцидент 2026-10-01: плитка «Операций» всегда показывала summary.count —
это количество записей за всё время (239). Переключение плиток/кнопок меняло
pie и подсветку, но счётчик оставался тотальным, из-за чего «Операций»
противоречил остальному экрану.

Контракт:
- month → число записей текущего месяца;
- prev  → число записей прошлого месяца;
- all   → число записей за всё время (summary.count);
- avg   → среднее число записей в месяц, подпись «записей/мес»;
- денежные плитки (месяц/прошлый/всего/среднее) остаются ФИКСИРОВАННЫМИ;
- писателем count/count-label владеет только applyPeriod.
"""

import json
import shutil
import subprocess

import pytest

_ROOT_MARKER = "mobile-expenses/app.js"


def _extract_function(js: str, name: str) -> str:
    start = js.index(f"function {name}(")
    depth = 0
    for i in range(start, len(js)):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                return js[start:i + 1]
    raise AssertionError(f"function {name} not closed")


_FIXTURE = (
    "const data={summary:{month_label:'2026-09',month_total:500,total:600,count:3,average_month:300},"
    "months:[{month:'2026-08',total:100},{month:'2026-09',total:500}],"
    "transactions:[{date:'2026-09-05',category:'Продукты',amount:300},"
    "{date:'2026-09-18',category:'Транспорт',amount:200},"
    "{date:'2026-08-02',category:'Продукты',amount:100}],"
    "categories:[{category:'Продукты',total:400},{category:'Транспорт',total:200}]};"
)


@pytest.fixture(scope="module")
def count_period():
    """Прогоняет renderKPI+applyPeriod по всем четырём периодам под node."""
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = open(_ROOT_MARKER, encoding="utf-8").read()
    parts = [
        _extract_function(js, "monthItemsByLabel"),
        _extract_function(js, "monthItems"),
        _extract_function(js, "aggregateByCategory"),
        _extract_function(js, "prevMonthLabel"),
        _extract_function(js, "avgItems"),
        _extract_function(js, "periodCount"),
        "const money = n => 'R'+n;",
        "let __bars = null;",
        "function renderCategoryBars(items){__bars = items;}",
        "var state = {selectedCategory:null};",
        "var __txcalls = [];",
        "function renderTransactionsForPeriod(){__txcalls.push(1);}",
        "const __store = {};",
        "function __el(){return {textContent:'',dataset:{},classList:{toggle(){},add(){},remove(){},"
        "contains(){return true;}},setAttribute(){},getAttribute(){return null},addEventListener(){}};}",
        "const document = {getElementById:id=>{if(!__store[id])__store[id]=__el();return __store[id];},"
        "querySelectorAll:()=>[]};",
        "const byId = id => document.getElementById(id);",
        _extract_function(js, "renderKPI"),
        _extract_function(js, "applyPeriod"),
        "let period = 'month';",
        _FIXTURE,
        "renderKPI(data);",
        "applyPeriod(data);",
        "const get = id => (__store[id] ? __store[id].textContent : '');",
        "function snap(){return {period:period, count:get('count'), count_label:get('count-label'),"
        " month_total:get('month-total'), prev_total:get('prev-total'), total:get('total'),"
        " average:get('average')};}",
        "const out={};",
        "out.initial = snap();",
        "for (const p of ['month','prev','all','avg']) { period = p; applyPeriod(data); out[p] = snap(); }",
        "console.log(JSON.stringify(out));",
    ]
    proc = subprocess.run(["node", "-e", "\n".join(parts)], capture_output=True, text=True,
                          encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_count_follows_period(count_period):
    assert count_period["month"]["count"] == "2"
    assert count_period["prev"]["count"] == "1"
    assert count_period["all"]["count"] == "3"


def test_count_avg_is_average_per_month(count_period):
    """3 записи на 2 активных месяца = 2 в среднем (округление)."""
    assert count_period["avg"]["count"] == "2"


def test_count_label_switches_for_avg(count_period):
    for key in ("month", "prev", "all"):
        assert count_period[key]["count_label"] == "записей", key
    assert count_period["avg"]["count_label"] == "записей/мес"


def test_money_tiles_stay_fixed_across_periods(count_period):
    money = {
        key: (count_period[key]["month_total"], count_period[key]["prev_total"],
              count_period[key]["total"], count_period[key]["average"])
        for key in ("month", "prev", "all", "avg")
    }
    values = list(money.values())
    for value in values[1:]:
        assert value == values[0], money


def test_initial_render_count_is_month(count_period):
    """Первый кадр (до клика) показывает счётчик текущего месяца."""
    assert count_period["initial"]["count"] == "2"
    assert count_period["initial"]["count_label"] == "записей"


def test_render_kpi_is_not_count_writer():
    """Единственный писатель count — applyPeriod, чтобы не было двух источников."""
    js = open(_ROOT_MARKER, encoding="utf-8").read()
    render_src = _extract_function(js, "renderKPI")
    for token in ("'count'", '"count"', "count-label"):
        assert token not in render_src, \
            f"renderKPI не должен писать {token}: единственный писатель — applyPeriod"


def test_applyperiod_writes_count_and_label():
    js = open(_ROOT_MARKER, encoding="utf-8").read()
    apply_src = _extract_function(js, "applyPeriod")
    assert "periodCount" in apply_src
    assert "count-label" in apply_src


def test_period_count_all_without_summary_count():
    """Нет summary.count → 0, без исключений."""
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = open(_ROOT_MARKER, encoding="utf-8").read()
    parts = [
        _extract_function(js, "monthItemsByLabel"),
        _extract_function(js, "prevMonthLabel"),
        _extract_function(js, "periodCount"),
        "let period = 'all';",
        "console.log(JSON.stringify(periodCount({summary:{},transactions:[],months:[]})));",
    ]
    proc = subprocess.run(["node", "-e", "\n".join(parts)], capture_output=True, text=True,
                          encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["value"] == 0
    assert result["label"] == "записей"


def _period_count(source_data, period):
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = open(_ROOT_MARKER, encoding="utf-8").read()
    parts = [
        _extract_function(js, "monthItemsByLabel"),
        _extract_function(js, "prevMonthLabel"),
        _extract_function(js, "periodCount"),
        f"let period = {period!r};",
        f"const data = {source_data};",
        "console.log(JSON.stringify(periodCount(data)));",
    ]
    proc = subprocess.run(["node", "-e", "\n".join(parts)], capture_output=True, text=True,
                          encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_prev_count_crosses_year_boundary():
    """В январе prev = декабрь прошлого года, а не текущий месяц."""
    data = ("{summary:{month_label:'2026-01',count:3},"
            "transactions:[{date:'2026-01-10',amount:100},"
            "{date:'2025-12-05',amount:200},{date:'2025-12-09',amount:300}]}")
    assert _period_count(data, "prev")["value"] == 2
    assert _period_count(data, "month")["value"] == 1


def test_month_and_prev_with_zero_transactions():
    """Начало месяца: трат ещё нет — 0, без исключений."""
    data = "{summary:{month_label:'2026-10',count:0},transactions:[{date:'2026-09-30',amount:100}]}"
    assert _period_count(data, "month")["value"] == 0
    assert _period_count(data, "prev")["value"] == 1


def test_avg_falls_back_to_all_when_months_empty():
    """Пустой months → среднее = все записи (та же конвенция, что в avgItems)."""
    data = "{summary:{month_label:'2026-10',count:7},transactions:[],months:[]}"
    result = _period_count(data, "avg")
    assert result["value"] == 7
    assert result["label"] == "записей/мес"


def test_summary_count_matches_transactions_length():
    """periodCount берёт all/avg из summary.count и month/prev из transactions.

    Экспортёр обязан держать summary.count == len(transactions), иначе счётчик
    для «всё время» разойдётся со счётчиком по месяцам.
    """
    data = json.load(open("mobile-expenses/data.json", encoding="utf-8"))
    assert data["summary"]["count"] == len(data["transactions"])