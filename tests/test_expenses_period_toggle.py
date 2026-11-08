import json
import re
import shutil
import subprocess
from html.parser import HTMLParser

import pytest

DATA = {"categories": [{"category": "Продукты", "total": 700.0}], "months": [{"month": "2026-09", "total": 600.0}], "transactions": [{"date": "2026-09-18", "category": "Продукты", "subcategory": "", "comment": "", "amount": 500.0}, {"date": "2026-08-02", "category": "Продукты", "subcategory": "", "comment": "", "amount": 100.0}], "summary": {"month_total": 500.0, "month_label": "2026-09", "total": 600.0, "average_month": 300.0, "count": 2}}


def _money_only(kpi):
    """Денежные плитки — те, что обязаны оставаться фиксированными.

    Счётчик операций (count) с 2026-10-01 period-driven: он следует за
    выбранным периодом, поэтому сравнивать его наравне с деньгами нельзя.
    """
    return {k: v for k, v in kpi.items() if k not in ("count", "count_label")}


def test_data_json_structure(tmp_path):
    assert set(DATA.keys()) == {"categories", "months", "transactions", "summary"}
    for t in DATA["transactions"]:
        assert set(t.keys()) == {"date", "category", "subcategory", "comment", "amount"}
    assert re.match(r"^\d{4}-\d{2}$", DATA["summary"]["month_label"])


def test_month_total_matches_month_transactions():
    summary = DATA["summary"]
    expected = sum(t["amount"] for t in DATA["transactions"] if t["date"].startswith(summary["month_label"]))
    assert summary["month_total"] == expected


def test_seg_control_markup():
    html = open("mobile-expenses/index.html", encoding="utf-8").read()
    assert "seg-control" in html and 'data-period="month"' in html and 'data-period="all"' in html


def test_period_logic_in_app_js():
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    assert "applyPeriod" in js and "month_label" in js


class _IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == "id":
                self.ids.append(value)


def _dashboard_html():
    return open("mobile-expenses/index.html", encoding="utf-8").read()


def _collect_ids(html):
    collector = _IdCollector()
    collector.feed(html)
    return collector.ids


def test_no_duplicate_ids():
    ids = _collect_ids(_dashboard_html())
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, dupes


def test_month_label_singleton():
    ids = _collect_ids(_dashboard_html())
    assert ids.count("month-label") == 1
    for expected in ("kpi-month-label", "kpi-title", "month-label", "month-total"):
        assert ids.count(expected) == 1, expected


def test_seg_buttons_have_type_button():
    assert 'type="button"' in _dashboard_html()


def test_seg_focus_visible_in_css():
    css = open("mobile-expenses/styles.css", encoding="utf-8").read()
    assert ":focus-visible" in css


def test_dashboard_data_cache_in_app_js():
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    assert "window.__dashboardData" in js


def test_legacy_month_fallback_removed():
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    assert "'текущий месяц'" not in js


def _extract_function(source, name):
    start = re.search(r"function\s+" + name + r"\s*\(", source)
    if not start:
        raise RuntimeError("no function %s in app.js" % name)
    open_brace = source.find("{", start.end())
    if open_brace == -1:
        raise RuntimeError("no body of %s in app.js" % name)
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


@pytest.fixture(scope="module")
def period_pure_result():
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    by_label_src = _extract_function(js, "monthItemsByLabel")
    month_src = _extract_function(js, "monthItems")
    agg_src = _extract_function(js, "aggregateByCategory")
    driver = (
        by_label_src + "\n" + month_src + "\n" + agg_src + "\n"
        + "const data={summary:{month_label:'2026-09'},transactions:["
        + "{date:'2026-09-05',category:'Продукты',amount:500},"
        + "{date:'2026-09-18',category:'Транспорт',amount:200},"
        + "{date:'2026-08-02',category:'Продукты',amount:100}]};"
        + "const month=monthItems(data);"
        + "const agg=aggregateByCategory(month.concat([{category:'Продукты',total:50}]));"
        + "const empty=monthItems({summary:{month_label:'2026-09'},transactions:[]});"
        + "console.log(JSON.stringify({month:month,agg:agg,empty:empty}));"
    )
    proc = subprocess.run(["node", "-e", driver], capture_output=True, text=True, encoding="utf-8", timeout=30)
    proc.check_returncode()
    return json.loads(proc.stdout)


def test_period_switch_month_all_behaviour(period_pure_result):
    month = period_pure_result["month"]
    assert len(month) == 2
    assert sorted(x["category"] for x in month) == ["Продукты", "Транспорт"]
    totals = {x["category"]: x["total"] for x in period_pure_result["agg"]}
    assert totals == {"Продукты": 550, "Транспорт": 200}
    assert period_pure_result["empty"] == []


def test_kpi_toggle_ids_present():
    html = _dashboard_html()
    for expected in ("total-title", "total-label", "count-label"):
        assert f'id="{expected}"' in html, expected


def test_kpi_toggle_default_texts():
    html = _dashboard_html()
    m_title = re.search(r'id="total-title"[^>]*>(.*?)<', html)
    assert m_title and m_title.group(1) == "Всего расходов"
    m_label = re.search(r'id="total-label"[^>]*>(.*?)<', html)
    assert m_label and m_label.group(1) == "за всё время"
    m_count = re.search(r'id="count-label"[^>]*>(.*?)<', html)
    assert m_count and m_count.group(1) == "записей"


@pytest.fixture(scope="module")
def period_toggle_result():
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    by_label_src = _extract_function(js, "monthItemsByLabel")
    month_src = _extract_function(js, "monthItems")
    agg_src = _extract_function(js, "aggregateByCategory")
    prev_src = _extract_function(js, "prevMonthLabel")
    kpi_src = _extract_function(js, "renderKPI")
    count_src = _extract_function(js, "periodCount")
    apply_src = _extract_function(js, "applyPeriod")
    driver = (
        by_label_src + "\n" + month_src + "\n" + agg_src + "\n" + prev_src + "\n"
        + "const money = n => '₽'+n;\n"
        + "let __bars = null;\n"
        + "function renderCategoryBars(items){__bars = items;}\n"
        + "var state = {selectedCategory:null};\n"
        + "function renderTransactionsForPeriod(){}\n"
        + "const __store = {};\n"
        + "const document = {getElementById:id=>{if(!__store[id])__store[id]={textContent:'',dataset:{},classList:{toggle(){},add(){},remove(){},contains(){return true;}},setAttribute(){},getAttribute(){return null}};return __store[id];},querySelectorAll:()=>[]};\n"
        + "const byId = id => document.getElementById(id);\n"
        + kpi_src + "\n" + count_src + "\n" + apply_src + "\n"
        + "let period = 'month';\n"
        + "const data={summary:{month_label:'2026-09',month_total:500,total:600,count:3},transactions:[{date:'2026-09-05',category:'Продукты',amount:300},{date:'2026-09-18',category:'Транспорт',amount:200},{date:'2026-08-02',category:'Продукты',amount:100}],categories:[{category:'Продукты',total:400},{category:'Транспорт',total:200}]};\n"
        + "renderKPI(data);\n"
        + "applyPeriod(data);\n"
        + "const get = id => (__store[id] ? __store[id].textContent : '');\n"
        + "const month={month_total:get('month-total'),total:get('total'),count:get('count'),month_label:get('month-label'),bars:__bars};\n"
        + "__bars=null;\n"
        + "period='all';\n"
        + "applyPeriod(data);\n"
        + "const all={month_total:get('month-total'),total:get('total'),count:get('count'),month_label:get('month-label'),bars:__bars};\n"
        + "console.log(JSON.stringify({month:month,all:all}));\n"
    )
    proc = subprocess.run(["node", "-e", driver], capture_output=True, text=True, encoding="utf-8", timeout=30)
    proc.check_returncode()
    return json.loads(proc.stdout)


def test_period_toggle_kpi_fixed_values(period_toggle_result):
    m = period_toggle_result["month"]
    a = period_toggle_result["all"]
    assert m["month_total"] == a["month_total"] == "₽500"
    assert m["total"] == a["total"] == "₽600"
    # счётчик операций следует за периодом: 2 траты в сентябре, 3 за всё время
    assert str(m["count"]) == "2"
    assert str(a["count"]) == "3"
    by_cat_m = {x["category"]: x["total"] for x in m["bars"]}
    assert by_cat_m == {"Продукты": 300, "Транспорт": 200}
    by_cat_a = {x["category"]: x["total"] for x in a["bars"]}
    assert by_cat_a == {"Продукты": 400, "Транспорт": 200}
    assert m["month_label"] == "2026-09"
    assert a["month_label"] == "Всё время"


def test_monthly_chart_hscroll_wrapper():
    html = _dashboard_html()
    assert 'class="hscroll"' in html
    assert re.search(r'<div class="hscroll">\s*<div id="monthly-chart"', html)


def test_monthly_chart_hscroll_css():
    css = open("mobile-expenses/styles.css", encoding="utf-8").read()
    assert "min-width:640px" in css


def test_fit_monthly_chart_in_app_js():
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    assert "fitMonthlyChart" in js


def test_fit_monthly_chart_uses_client_width():
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    assert "clientWidth" in js


@pytest.fixture(scope="module")
def deltas_pure_result():
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    prev_src = _extract_function(js, "prevMonthLabel")
    deltas_src = _extract_function(js, "categoryDeltas")
    driver = (
        prev_src + "\n" + deltas_src + "\n"
        + "const tx=["
        + "{date:'2026-09-05',category:'Продукты',amount:560},"
        + "{date:'2026-08-05',category:'Продукты',amount:500},"
        + "{date:'2026-09-06',category:'Транспорт',amount:200},"
        + "{date:'2026-08-06',category:'Транспорт',amount:400},"
        + "{date:'2026-09-07',category:'Кафе',amount:300},"
        + "{date:'2026-08-08',category:'Аптека',amount:100}];"
        + "const rows=categoryDeltas(tx,'2026-09');"
        + "console.log(JSON.stringify({rows:rows,wrap:prevMonthLabel('2026-01')}));"
    )
    proc = subprocess.run(["node", "-e", driver], capture_output=True, text=True, encoding="utf-8", timeout=30)
    proc.check_returncode()
    return json.loads(proc.stdout)


def test_deltas_pct_values(deltas_pure_result):
    by_cat = {r["category"]: r for r in deltas_pure_result["rows"]}
    assert by_cat["Продукты"]["pct"] == 12
    assert by_cat["Транспорт"]["pct"] == -50
    assert by_cat["Кафе"]["pct"] is None
    assert by_cat["Аптека"]["prev"] == 100


def test_deltas_sorted_by_curr_desc(deltas_pure_result):
    currs = [r["curr"] for r in deltas_pure_result["rows"]]
    assert currs == sorted(currs, reverse=True)
    assert deltas_pure_result["rows"][0]["category"] == "Продукты"


def test_prev_month_label_year_wrap(deltas_pure_result):
    assert deltas_pure_result["wrap"] == "2025-12"


def test_deltas_ids_present():
    html = _dashboard_html()
    assert 'id="category-deltas"' in html
    assert 'id="deltas-label"' in html


def test_render_deltas_in_app_js():
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    assert "renderDeltas" in js


def test_render_deltas_escapes_category():
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    assert "escapeHtml(r.category)" in js


def test_prev_tile_ids_present():
    html = _dashboard_html()
    assert 'id="prev-total"' in html
    assert 'id="prev-month-label"' in html


def test_prev_period_markup():
    html = _dashboard_html()
    assert 'data-period="prev"' in html


def test_prev_button_between_month_all():
    html = _dashboard_html()
    m = re.search(r'<div class="seg-control".*?</div>', html, re.S)
    assert m, "seg-control not found"
    seg = m.group(0)
    i_month = seg.find('data-period="month"')
    i_prev = seg.find('data-period="prev"')
    i_all = seg.find('data-period="all"')
    assert i_month != -1 and i_prev != -1 and i_all != -1
    assert i_month < i_prev < i_all


def test_month_items_by_label_in_app_js():
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    assert "monthItemsByLabel" in js


def test_is_prev_in_app_js():
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    assert "isPrev" in js


def test_prev_tile_cursor_css():
    css = open("mobile-expenses/styles.css", encoding="utf-8").read()
    assert ".card[data-period]{cursor:pointer}" in css


def test_period_handler_uses_data_period_selector():
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    assert "querySelectorAll('[data-period]')" in js


@pytest.fixture(scope="module")
def prev_toggle_result():
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    by_label_src = _extract_function(js, "monthItemsByLabel")
    month_src = _extract_function(js, "monthItems")
    agg_src = _extract_function(js, "aggregateByCategory")
    prev_src = _extract_function(js, "prevMonthLabel")
    kpi_src = _extract_function(js, "renderKPI")
    count_src = _extract_function(js, "periodCount")
    apply_src = _extract_function(js, "applyPeriod")
    driver = (
        by_label_src + "\n" + month_src + "\n" + agg_src + "\n" + prev_src + "\n"
        + "const money = n => '₽'+n;\n"
        + "let __bars = null;\n"
        + "function renderCategoryBars(items){__bars = items;}\n"
        + "var state = {selectedCategory:null};\n"
        + "function renderTransactionsForPeriod(){}\n"
        + "const __store = {};\n"
        + "function __el(){return {textContent:'',dataset:{},classList:{toggle(){},add(){},remove(){},contains(){return true;}},setAttribute(){},getAttribute(){return null},addEventListener(){}};}\n"
        + "const document = {getElementById:id=>{if(!__store[id])__store[id]=__el();return __store[id];},querySelectorAll:()=>[]};\n"
        + "const byId = id => document.getElementById(id);\n"
        + kpi_src + "\n" + count_src + "\n" + apply_src + "\n"
        + "let period = 'month';\n"
        + "const data={summary:{month_label:'2026-09',month_total:500,total:600,count:3},transactions:[{date:'2026-09-05',category:'Продукты',amount:300},{date:'2026-09-18',category:'Транспорт',amount:200},{date:'2026-08-02',category:'Продукты',amount:100}],categories:[{category:'Продукты',total:400},{category:'Транспорт',total:200}]};\n"
        + "renderKPI(data);\n"
        + "applyPeriod(data);\n"
        + "const get = id => (__store[id] ? __store[id].textContent : '');\n"
        + "const month={month_total:get('month-total'),total:get('total'),count:get('count'),month_label:get('month-label'),bars:__bars};\n"
        + "__bars=null;\n"
        + "period='all';\n"
        + "applyPeriod(data);\n"
        + "const all={month_total:get('month-total'),total:get('total'),count:get('count'),month_label:get('month-label'),bars:__bars};\n"
        + "__bars=null;\n"
        + "period='prev';\n"
        + "applyPeriod(data);\n"
        + "const prev={month_total:get('month-total'),total:get('total'),count:get('count'),month_label:get('month-label'),bars:__bars};\n"
        + "console.log(JSON.stringify({month:month,all:all,prev:prev}));\n"
    )
    proc = subprocess.run(["node", "-e", driver], capture_output=True, text=True, encoding="utf-8", timeout=30)
    proc.check_returncode()
    return json.loads(proc.stdout)


def test_prev_toggle_kpi_fixed(prev_toggle_result):
    m = prev_toggle_result["month"]
    a = prev_toggle_result["all"]
    p = prev_toggle_result["prev"]
    assert m["month_total"] == a["month_total"] == p["month_total"] == "₽500"
    assert m["total"] == a["total"] == p["total"] == "₽600"
    assert str(m["count"]) == "2"
    assert str(a["count"]) == "3"
    assert str(p["count"]) == "1"
    by_cat_m = {x["category"]: x["total"] for x in m["bars"]}
    assert by_cat_m == {"Продукты": 300, "Транспорт": 200}
    by_cat_a = {x["category"]: x["total"] for x in a["bars"]}
    assert by_cat_a == {"Продукты": 400, "Транспорт": 200}
    by_cat_p = {x["category"]: x["total"] for x in p["bars"]}
    assert by_cat_p == {"Продукты": 100}
    assert m["month_label"] == "2026-09"
    assert a["month_label"] == "Всё время"
    assert p["month_label"] == "2026-08"


@pytest.fixture(scope="module")
def click_gating_result():
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    by_label_src = _extract_function(js, "monthItemsByLabel")
    month_src = _extract_function(js, "monthItems")
    agg_src = _extract_function(js, "aggregateByCategory")
    prev_src = _extract_function(js, "prevMonthLabel")
    avg_src = _extract_function(js, "avgItems")
    kpi_src = _extract_function(js, "renderKPI")
    count_src = _extract_function(js, "periodCount")
    apply_src = _extract_function(js, "applyPeriod")
    driver = (
        by_label_src + "\n" + month_src + "\n" + agg_src + "\n" + prev_src + "\n" + avg_src + "\n"
        + "const money = n => '₽'+n;\n"
        + "let __bars = null;\n"
        + "function renderCategoryBars(items){__bars = items;}\n"
        + "var state = {selectedCategory:null};\n"
        + "function renderTransactionsForPeriod(){}\n"
        + "function makeEl(classes, periodVal, tag){const cls=new Set(classes);const attrs={};const handlers={};return {tagName:tag,dataset:{period:periodVal},classList:{toggle:(n,on)=>{if(on)cls.add(n);else cls.delete(n);},add:n=>cls.add(n),remove:n=>cls.delete(n),contains:n=>cls.has(n)},setAttribute:(k,v)=>{attrs[k]=String(v);},getAttribute:k=>(k in attrs?attrs[k]:null),addEventListener:(ev,fn)=>{handlers[ev]=fn;},_cls:cls,_attrs:attrs,_handlers:handlers};}\n"
        + "const segMonth=makeEl(['seg-btn'],'month','BUTTON');\n"
        + "const segPrev=makeEl(['seg-btn'],'prev','BUTTON');\n"
        + "const segAll=makeEl(['seg-btn'],'all','BUTTON');\n"
        + "const tileMonth=makeEl(['card','kpi-card'],'month','ARTICLE');\n"
        + "const tilePrev=makeEl(['card','kpi-card'],'prev','ARTICLE');\n"
        + "const tileTotal=makeEl(['card','kpi-card'],'all','ARTICLE');\n"
        + "const tileAvg=makeEl(['card','kpi-card'],'avg','ARTICLE');\n"
        + "const plainNote=makeEl(['note'],'month','DIV');\n"
        + "const __nodes=[segMonth,segPrev,segAll,tileMonth,tilePrev,tileTotal,tileAvg,plainNote];\n"
        + "const __store={};\n"
        + "const document={getElementById:id=>{if(!__store[id])__store[id]=makeEl([],null,'STRONG');return __store[id];},querySelectorAll:sel=>__nodes};\n"
        + "const byId=id=>document.getElementById(id);\n"
        + kpi_src + "\n" + count_src + "\n" + apply_src + "\n"
        + "let period='month';\n"
        + "const window={};\n"
        + "const data={summary:{month_label:'2026-09',month_total:500,total:600,count:3},transactions:[{date:'2026-09-05',category:'Продукты',amount:300},{date:'2026-09-18',category:'Транспорт',amount:200},{date:'2026-08-02',category:'Продукты',amount:100}],categories:[{category:'Продукты',total:400},{category:'Транспорт',total:200}]};\n"
        + "window.__dashboardData=data;\n"
        + "renderKPI(data);\n"
        + "document.querySelectorAll('[data-period]').forEach(b=>b.addEventListener('click',()=>{period=b.dataset.period;applyPeriod(window.__dashboardData);}));\n"
        + "const __calls=[];\n"
        + "const __realApply=applyPeriod;\n"
        + "applyPeriod=function(d){__calls.push(period);return __realApply(d);};\n"
        + "function snap(){return {nodes:__nodes.length,period:period,bars:__bars,month_label:(__store['month-label']?__store['month-label'].textContent:''),kpi:{month_total:(__store['month-total']?__store['month-total'].textContent:''),total:(__store['total']?__store['total'].textContent:''),count:(__store['count']?__store['count'].textContent:'')},segMonthActive:segMonth._cls.has('active'),segPrevActive:segPrev._cls.has('active'),segAllActive:segAll._cls.has('active'),tileMonthActive:tileMonth._cls.has('active'),tilePrevActive:tilePrev._cls.has('active'),tileTotalActive:tileTotal._cls.has('active'),tileAvgActive:tileAvg._cls.has('active'),plainActive:plainNote._cls.has('active'),segMonthAria:('aria-selected' in segMonth._attrs?segMonth._attrs['aria-selected']:null),segPrevAria:('aria-selected' in segPrev._attrs?segPrev._attrs['aria-selected']:null),segAllAria:('aria-selected' in segAll._attrs?segAll._attrs['aria-selected']:null),tileMonthAria:('aria-selected' in tileMonth._attrs?tileMonth._attrs['aria-selected']:null),tilePrevAria:('aria-selected' in tilePrev._attrs?tilePrev._attrs['aria-selected']:null),tileTotalAria:('aria-selected' in tileTotal._attrs?tileTotal._attrs['aria-selected']:null),tileAvgAria:('aria-selected' in tileAvg._attrs?tileAvg._attrs['aria-selected']:null),plainAria:('aria-selected' in plainNote._attrs?plainNote._attrs['aria-selected']:null),calls:__calls.slice()};}\n"
        + "segMonth._handlers.click();\n"
        + "const afterMonth=snap();\n"
        + "tilePrev._handlers.click();\n"
        + "const afterPrev=snap();\n"
        + "segAll._handlers.click();\n"
        + "const afterAll=snap();\n"
        + "tileAvg._handlers.click();\n"
        + "const afterAvg=snap();\n"
        + "console.log(JSON.stringify({afterMonth:afterMonth,afterPrev:afterPrev,afterAll:afterAll,afterAvg:afterAvg}));\n"
    )
    proc = subprocess.run(["node", "-e", driver], capture_output=True, text=True, encoding="utf-8", timeout=30)
    proc.check_returncode()
    return json.loads(proc.stdout)


def test_click_gating_highlight_tiles_and_segs(click_gating_result):
    m = click_gating_result["afterMonth"]
    p = click_gating_result["afterPrev"]
    a = click_gating_result["afterAll"]
    v = click_gating_result["afterAvg"]
    assert m["nodes"] == 8
    assert m["period"] == "month"
    assert m["segMonthActive"] is True
    assert m["tileMonthActive"] is True
    assert m["segPrevActive"] is False
    assert m["segAllActive"] is False
    assert m["tilePrevActive"] is False
    assert m["tileTotalActive"] is False
    assert m["tileAvgActive"] is False
    assert m["plainActive"] is False
    assert m["segMonthAria"] == "true"
    assert m["tileMonthAria"] == "true"
    assert m["plainAria"] == "true"
    assert m["segAllAria"] == "false"
    assert m["calls"] == ["month"]
    assert m["month_label"] == "2026-09"
    by_cat = {x["category"]: x["total"] for x in m["bars"]}
    assert by_cat == {"Продукты": 300, "Транспорт": 200}
    assert p["period"] == "prev"
    assert p["segPrevActive"] is True
    assert p["tilePrevActive"] is True
    assert p["segMonthActive"] is False
    assert p["segAllActive"] is False
    assert p["tileMonthActive"] is False
    assert p["tileTotalActive"] is False
    assert p["plainActive"] is False
    assert p["tilePrevAria"] == "true"
    assert p["segPrevAria"] == "true"
    assert p["plainAria"] == "false"
    assert p["month_label"] == "2026-08"
    by_cat_p = {x["category"]: x["total"] for x in p["bars"]}
    assert by_cat_p == {"Продукты": 100}
    assert _money_only(p["kpi"]) == _money_only(m["kpi"])
    assert str(p["kpi"]["count"]) == "1" and str(m["kpi"]["count"]) == "2"
    assert p["calls"] == ["month", "prev"]
    assert a["period"] == "all"
    assert a["segAllActive"] is True
    assert a["tileTotalActive"] is True
    assert a["segMonthActive"] is False
    assert a["tileMonthActive"] is False
    assert a["tilePrevActive"] is False
    assert a["plainActive"] is False
    assert a["segAllAria"] == "true"
    assert a["tileTotalAria"] == "true"
    assert _money_only(a["kpi"]) == _money_only(m["kpi"])
    assert str(a["kpi"]["count"]) == "3" and str(m["kpi"]["count"]) == "2"
    assert a["month_label"] == "Всё время"
    by_cat_a = {x["category"]: x["total"] for x in a["bars"]}
    assert by_cat_a == {"Продукты": 400, "Транспорт": 200}
    assert a["calls"] == ["month", "prev", "all"]
    assert v["period"] == "avg"
    assert v["tileAvgActive"] is True
    assert v["segMonthActive"] is False
    assert v["segPrevActive"] is False
    assert v["segAllActive"] is False
    assert v["tileMonthActive"] is False
    assert v["plainActive"] is False
    assert v["tileAvgAria"] == "true"
    assert v["segMonthAria"] == "false"
    assert _money_only(v["kpi"]) == _money_only(m["kpi"])
    # в этой фикстуре months отсутствует, поэтому среднее = все записи (fallback как в avgItems)
    assert str(v["kpi"]["count"]) == "3" and str(m["kpi"]["count"]) == "2"
    assert v["month_label"] == "Среднее в месяц"


def test_applyperiod_does_not_touch_heavy_renders():
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    src = _extract_function(js, "applyPeriod")
    for heavy in ("renderMonthlyChart", "renderDeltas", "initCharts", "loadData"):
        assert heavy not in src, heavy
    assert "renderTransactionsForPeriod()" in src, (
        "applyPeriod делегирует обновление списка операций — иначе клик по периоду "
        "не обновит операции"
    )


def test_applyperiod_does_not_write_money_tiles():
    """applyPeriod не пишет денежные плитки — только счётчик операций.

    С 2026-10-01 единственный period-driven элемент — count/count-label
    (следует за периодом). Деньги остаются фиксированными, их пишет
    renderKPI единожды. См. tests/test_expenses_count_period.py.
    """
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    src = _extract_function(js, "applyPeriod")
    for token in ("month-total", "kpi-title", "prev-total", "kpi-month-label",
                  "total-title", "total-label", "prev-month-label"):
        assert token not in src, token


def test_render_kpi_in_app_js():
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    assert "function renderKPI" in js
    render_src = _extract_function(js, "render")
    assert "renderKPI" in render_src
    assert "applyPeriod" in render_src


def test_month_tile_markup():
    html = _dashboard_html()
    assert re.search(r'<article[^>]*data-period="month"[^>]*>.*?id="month-total"', html, re.S), "month tile missing data-period=month"
    m = re.search(r'<article[^>]*class="([^"]*)"[^>]*data-period="month"', html)
    if m is None:
        m = re.search(r'<article[^>]*data-period="month"[^>]*class="([^"]*)"', html)
    assert m and "active" in m.group(1).split(), "month tile must have active by default"


def test_kpi_active_outline_css():
    css = open("mobile-expenses/styles.css", encoding="utf-8").read()
    assert ".kpi-card.active{outline:2px solid var(--blue);outline-offset:-2px}" in css


def test_month_items_single_pass():
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    src = _extract_function(js, "monthItemsByLabel")
    assert src.count(".filter(") == 1


def test_avg_tile_has_data_period_avg():
    html = _dashboard_html()
    assert re.search(r'<article[^>]*data-period="avg"[^>]*>.*?Среднее в месяц', html, re.S), "avg tile missing data-period=avg"


def test_total_tile_has_data_period_all():
    html = _dashboard_html()
    assert re.search(r'<article[^>]*data-period="all"[^>]*>.*?id="total-title"', html, re.S), "total tile missing data-period=all"


def test_avg_items_in_app_js():
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    assert "avgItems" in js


_AVG_FIXTURE_JS = (
    "const data={summary:{month_label:'2026-09',month_total:700,total:1000,count:3,average_month:500},"
    "months:[{month:'2026-08',total:300},{month:'2026-09',total:700}],"
    "transactions:[{date:'2026-09-05',category:'Продукты',amount:500},"
    "{date:'2026-09-18',category:'Транспорт',amount:200},"
    "{date:'2026-08-02',category:'Продукты',amount:300}],"
    "categories:[{category:'Продукты',total:500},{category:'Транспорт',total:200}]};"
)


@pytest.fixture(scope="module")
def avg_toggle_result():
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    by_label_src = _extract_function(js, "monthItemsByLabel")
    month_src = _extract_function(js, "monthItems")
    agg_src = _extract_function(js, "aggregateByCategory")
    prev_src = _extract_function(js, "prevMonthLabel")
    avg_src = _extract_function(js, "avgItems")
    kpi_src = _extract_function(js, "renderKPI")
    count_src = _extract_function(js, "periodCount")
    apply_src = _extract_function(js, "applyPeriod")
    driver = (
        by_label_src + "\n" + month_src + "\n" + agg_src + "\n" + prev_src + "\n" + avg_src + "\n"
        + "const money = n => '₽'+n;\n"
        + "let __bars = null;\n"
        + "function renderCategoryBars(items){__bars = items;}\n"
        + "var state = {selectedCategory:null};\n"
        + "function renderTransactionsForPeriod(){}\n"
        + "const __store = {};\n"
        + "function __el(){return {textContent:'',dataset:{},classList:{toggle(){},add(){},remove(){},contains(){return true;}},setAttribute(){},getAttribute(){return null},addEventListener(){}};}\n"
        + "const document = {getElementById:id=>{if(!__store[id])__store[id]=__el();return __store[id];},querySelectorAll:()=>[]};\n"
        + "const byId = id => document.getElementById(id);\n"
        + kpi_src + "\n" + count_src + "\n" + apply_src + "\n"
        + "let period = 'month';\n"
        + _AVG_FIXTURE_JS + "\n"
        + "renderKPI(data);\n"
        + "applyPeriod(data);\n"
        + "const get = id => (__store[id] ? __store[id].textContent : '');\n"
        + "const before = {month_total:get('month-total'),total:get('total'),count:get('count')};\n"
        + "period = 'avg';\n"
        + "applyPeriod(data);\n"
        + "const after = {month_total:get('month-total'),total:get('total'),count:get('count')};\n"
        + "console.log(JSON.stringify({before:before,after:after,bars:__bars,month_label:get('month-label')}));\n"
    )
    proc = subprocess.run(["node", "-e", driver], capture_output=True, text=True, encoding="utf-8", timeout=30)
    proc.check_returncode()
    return json.loads(proc.stdout)


def test_avg_click_pie_is_per_category_over_months(avg_toggle_result):
    by_cat = {x["category"]: x["total"] for x in avg_toggle_result["bars"]}
    assert by_cat == {"Продукты": 250, "Транспорт": 100}


def test_avg_click_label_and_kpi_untouched(avg_toggle_result):
    assert avg_toggle_result["month_label"] == "Среднее в месяц"
    assert avg_toggle_result["before"]["month_total"] == "₽700"
    # деньги не меняются; count — period-driven, поэтому сравниваем только деньги
    assert _money_only(avg_toggle_result["after"]) == _money_only(avg_toggle_result["before"])
    assert str(avg_toggle_result["after"]["count"]) == "2"
    assert str(avg_toggle_result["before"]["count"]) == "2"


@pytest.fixture(scope="module")
def avg_total_click_result():
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    html = open("mobile-expenses/index.html", encoding="utf-8").read()
    has_avg = bool(re.search(r'<article[^>]*data-period="avg"', html))
    has_total = bool(re.search(r'<article[^>]*data-period="all"', html))
    by_label_src = _extract_function(js, "monthItemsByLabel")
    month_src = _extract_function(js, "monthItems")
    agg_src = _extract_function(js, "aggregateByCategory")
    prev_src = _extract_function(js, "prevMonthLabel")
    avg_src = _extract_function(js, "avgItems")
    kpi_src = _extract_function(js, "renderKPI")
    count_src = _extract_function(js, "periodCount")
    apply_src = _extract_function(js, "applyPeriod")
    driver = (
        by_label_src + "\n" + month_src + "\n" + agg_src + "\n" + prev_src + "\n" + avg_src + "\n"
        + "const money = n => '₽'+n;\n"
        + "let __bars = null;\n"
        + "function renderCategoryBars(items){__bars = items;}\n"
        + "var state = {selectedCategory:null};\n"
        + "function renderTransactionsForPeriod(){}\n"
        + "function makeEl(classes, periodVal, tag){const cls=new Set(classes);const attrs={};const handlers={};return {tagName:tag,dataset:{period:periodVal},classList:{toggle:(n,on)=>{if(on)cls.add(n);else cls.delete(n);},add:n=>cls.add(n),remove:n=>cls.delete(n),contains:n=>cls.has(n)},setAttribute:(k,v)=>{attrs[k]=String(v);},getAttribute:k=>(k in attrs?attrs[k]:null),addEventListener:(ev,fn)=>{handlers[ev]=fn;},_cls:cls,_attrs:attrs,_handlers:handlers};}\n"
        + "function __idEl(){return {textContent:'',dataset:{},classList:{toggle(){},add(){},remove(){},contains(){return true;}},setAttribute(){},getAttribute(){return null},addEventListener(){}};}\n"
        + "const HAS_AVG = " + ("true" if has_avg else "false") + ";\n"
        + "const HAS_TOTAL = " + ("true" if has_total else "false") + ";\n"
        + "if(!HAS_AVG) throw new Error('no avg tile node');\n"
        + "if(!HAS_TOTAL) throw new Error('no total tile node');\n"
        + "const segMonth=makeEl(['seg-btn'],'month','BUTTON');\n"
        + "const segAll=makeEl(['seg-btn'],'all','BUTTON');\n"
        + "const tileAvg=makeEl(['card','kpi-card'],'avg','ARTICLE');\n"
        + "const tileTotal=makeEl(['card','kpi-card'],'all','ARTICLE');\n"
        + "const __nodes=[segMonth,segAll,tileAvg,tileTotal];\n"
        + "const __store={};\n"
        + "const document={getElementById:id=>{if(!__store[id])__store[id]=__idEl();return __store[id];},querySelectorAll:sel=>__nodes};\n"
        + "const byId=id=>document.getElementById(id);\n"
        + kpi_src + "\n" + count_src + "\n" + apply_src + "\n"
        + "let period='month';\n"
        + "const window={};\n"
        + _AVG_FIXTURE_JS + "\n"
        + "window.__dashboardData=data;\n"
        + "renderKPI(data);\n"
        + "document.querySelectorAll('[data-period]').forEach(b=>b.addEventListener('click',()=>{period=b.dataset.period;applyPeriod(window.__dashboardData);}));\n"
        + "const get=id=>(__store[id]?__store[id].textContent:'');\n"
        + "function snap(){return {period:period,bars:__bars,month_label:get('month-label'),kpi:{month_total:get('month-total'),total:get('total'),count:get('count'),kpi_title:get('kpi-title'),total_title:get('total-title'),total_label:get('total-label'),count_label:get('count-label')},tileAvgActive:tileAvg._cls.has('active'),tileTotalActive:tileTotal._cls.has('active'),segMonthActive:segMonth._cls.has('active'),segAllActive:segAll._cls.has('active'),segMonthAria:('aria-selected' in segMonth._attrs?segMonth._attrs['aria-selected']:null),segAllAria:('aria-selected' in segAll._attrs?segAll._attrs['aria-selected']:null),tileAvgAria:('aria-selected' in tileAvg._attrs?tileAvg._attrs['aria-selected']:null),tileTotalAria:('aria-selected' in tileTotal._attrs?tileTotal._attrs['aria-selected']:null)};}\n"
        + "segAll._handlers.click();\n"
        + "const afterSegAll=snap();\n"
        + "__bars=null;\n"
        + "tileTotal._handlers.click();\n"
        + "const afterTotal=snap();\n"
        + "__bars=null;\n"
        + "tileAvg._handlers.click();\n"
        + "const afterAvg=snap();\n"
        + "console.log(JSON.stringify({afterSegAll:afterSegAll,afterTotal:afterTotal,afterAvg:afterAvg}));\n"
    )
    proc = subprocess.run(["node", "-e", driver], capture_output=True, text=True, encoding="utf-8", timeout=30)
    proc.check_returncode()
    return json.loads(proc.stdout)


def test_total_tile_click_matches_seg_all(avg_total_click_result):
    r = avg_total_click_result
    assert r["afterTotal"]["period"] == "all"
    assert r["afterTotal"]["kpi"] == r["afterSegAll"]["kpi"]
    assert r["afterTotal"]["tileTotalActive"] is True
    assert r["afterTotal"]["segAllActive"] is True
    assert r["afterTotal"]["tileTotalAria"] == "true"
    assert r["afterTotal"]["segAllAria"] == "true"
    assert r["afterTotal"]["month_label"] == "Всё время"
    by_cat = {x["category"]: x["total"] for x in r["afterTotal"]["bars"]}
    assert by_cat == {"Продукты": 500, "Транспорт": 200}


def test_avg_tile_click_reaches_apply(avg_total_click_result):
    r = avg_total_click_result
    assert r["afterAvg"]["period"] == "avg"
    by_cat = {x["category"]: x["total"] for x in r["afterAvg"]["bars"]}
    assert by_cat == {"Продукты": 250, "Транспорт": 100}
    assert r["afterAvg"]["month_label"] == "Среднее в месяц"
    assert r["afterAvg"]["tileAvgActive"] is True
    assert r["afterAvg"]["tileAvgAria"] == "true"
    assert _money_only(r["afterAvg"]["kpi"]) == _money_only(r["afterSegAll"]["kpi"])
    # в режиме avg счётчик = среднее в месяц: 3 записи / 2 месяца = 2
    assert r["afterAvg"]["kpi"]["count"] == "2"
    assert r["afterAvg"]["kpi"]["count_label"] == "записей/мес"
    assert r["afterSegAll"]["kpi"]["count"] == "3"


def test_avg_click_clears_stale_seg_highlight(avg_total_click_result):
    r = avg_total_click_result
    assert r["afterAvg"]["segMonthActive"] is False
    assert r["afterAvg"]["segAllActive"] is False
    assert r["afterAvg"]["segMonthAria"] == "false"
    assert r["afterAvg"]["segAllAria"] == "false"


def test_avg_empty_months_uses_totals():
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    avg_src = _extract_function(js, "avgItems")
    driver = (
        avg_src + "\n"
        + "const data={months:[],categories:[{category:'Продукты',total:500},{category:'Транспорт',total:200}]};\n"
        + "console.log(JSON.stringify({bars:(" + "avgItems" + "(data))}));\n"
    )
    proc = subprocess.run(["node", "-e", driver], capture_output=True, text=True, encoding="utf-8", timeout=30)
    proc.check_returncode()
    pie = json.loads(proc.stdout)["bars"]
    by_cat = {x["category"]: x["total"] for x in pie}
    assert by_cat == {"Продукты": 500, "Транспорт": 200}


def test_noindex_meta_in_head():
    """Личный дашборд закрыт от индексации: noindex и запреты — в <head>."""
    html = open("mobile-expenses/index.html", encoding="utf-8").read()
    head = html.split("</head>")[0]
    assert '<meta name="robots"' in head
    for directive in ("noindex", "nofollow", "noarchive", "nosnippet", "noimageindex"):
        assert directive in head, directive


def test_robots_txt_disallows_all():
    """robots.txt запрещает обход всем ботам (просьба; noindex — запрет)."""
    robots = open("mobile-expenses/robots.txt", encoding="utf-8").read()
    assert "User-agent: *" in robots
    assert "Disallow: /" in robots
