"""Цвета категорий на столбчатой диаграмме не должны зависеть от режима.

Симптом (04.10.2026): при переключении «за месяц» / «всё время» цвета
менялись местами. Причина: в series[].data передавались только
{name, value}, поэтому ECharts красил по индексу, а порядок
категорий в двух режимах разный:

  месяц:     Дом и быт, Кафе и рестораны, Продукты, Транспорт, ...
  всё время: Дом и быт, Продукты, Кафе и рестораны, Коммунальные, ...

Исправление: цвет задаётся по имени категории из фиксированной палитры,
порядок элементов на это не влияет.

Круговая диаграмма удалена 14.10.2026 по решению владельца: осталась только
кликабельная столбчатая, покрупнее.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

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


@pytest.fixture(scope="module")
def colors_result():
    return _run_js(
        "categoryPalette",
        "categoryColor",
        "buildCategoryData",
        body=(
            "const month=[{category:'Дом и быт',total:100},{category:'Продукты',total:50},"
            "{category:'Транспорт',total:25}];"
            "const all=[{category:'Дом и быт',total:900},{category:'Продукты',total:800},"
            "{category:'Транспорт',total:700},{category:'Новая категория',total:5}];"
            "const a=buildCategoryData(month); const b=buildCategoryData(all);"
            "const pick=(rows,name)=>{const r=rows.find(x=>x.name===name);return r?r.itemStyle.color:null;};"
            "const probe=[categoryColor('Новая категория'),categoryColor('Новая категория'),"
            "categoryColor('') ,categoryColor(null),categoryColor(undefined)];"
            "console.log(JSON.stringify({"
            "month:a, all:b,"
            "same_product_month:pick(a,'Продукты'), same_product_all:pick(b,'Продукты'),"
            "same_home_month:pick(a,'Дом и быт'), same_home_all:pick(b,'Дом и быт'),"
            "unknown:pick(b,'Новая категория'), probe:probe,"
            "palette_size:Object.keys(categoryPalette()).length}));"
        ),
    )


def test_pie_data_carries_explicit_color(colors_result):
    """Каждый столбец обязан получить явный itemStyle.color."""
    for row in colors_result["month"] + colors_result["all"]:
        assert row["itemStyle"]["color"], row
        assert re.fullmatch(r"#[0-9a-fA-F]{6}|hsl\([^)]+\)", row["itemStyle"]["color"]), row


def test_color_is_stable_across_period_modes(colors_result):
    """Одна и та же категория — один цвет в обоих режимах."""
    assert colors_result["same_product_month"] == colors_result["same_product_all"]
    assert colors_result["same_home_month"] == colors_result["same_home_all"]


def test_different_categories_get_different_colors(colors_result):
    month = colors_result["month"]
    colors = [row["itemStyle"]["color"] for row in month]
    assert len(set(colors)) == len(colors), "категории слились в один цвет"


def test_palette_covers_every_default_category():
    """Палитра обязана покрывать все категории проекта, иначе часть уйдёт в fallback."""
    from categories import DEFAULT_CATEGORIES

    js = APP_JS.read_text(encoding="utf-8")
    for name in DEFAULT_CATEGORIES:
        assert f"'{name}'" in js or f'"{name}"' in js, f"нет цвета для категории {name!r}"

    palette = _run_js(
        "categoryPalette", "categoryColor", body="console.log(JSON.stringify(categoryPalette()));"
    )
    assert set(palette) == set(DEFAULT_CATEGORIES)


def test_palette_colors_are_unique():
    palette = _run_js(
        "categoryPalette", "categoryColor", body="console.log(JSON.stringify(categoryPalette()));"
    )
    assert len(set(palette.values())) == len(palette), "в палитре есть повторяющиеся цвета"


def test_unknown_category_color_is_deterministic(colors_result):
    """Категория вне палитры получает стабильный цвет, а не случайный."""
    assert colors_result["unknown"] == colors_result["probe"][0]
    assert colors_result["probe"][0] == colors_result["probe"][1]


def test_empty_category_name_does_not_throw(colors_result):
    for color in colors_result["probe"][2:]:
        assert color


def test_render_chart_uses_pie_data_helper():
    """renderCategoryBars обязан брать цвета из buildCategoryData, а не из палитры ECharts."""
    js = APP_JS.read_text(encoding="utf-8")
    assert "function renderCategoryChart" not in js, "круговая диаграмма удалена"
    body = _extract_function(js, "renderCategoryBars")
    assert "buildBarData(items)" in body
    assert "itemStyle:{color" not in body, "цвет столбца задаётся только через buildCategoryData"


def test_no_pie_markup():
    """Круговой диаграммы нет в разметке — только столбцы."""
    html = open("mobile-expenses/index.html", encoding="utf-8").read()
    assert 'id="category-bars"' in html
    assert "category-chart" not in html
    assert '"pie"' not in APP_JS.read_text(encoding="utf-8"), "тип pie остался в коде"


@pytest.fixture(scope="module")
def bars_result():
    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    js = APP_JS.read_text(encoding="utf-8")
    parts = [_extract_function(js, name) for name in (
        "chartBase", "categoryPalette", "categoryColor", "buildCategoryData",
        "buildBarData", "selectedOpacity", "periodName", "updateBarsHint",
        "onCategoryBarClick", "renderCategoryBars",
    )]
    driver = (
        "\n".join(parts) + "\n"
        + "const money = n => '₽'+n;\n"
        + "var state = {charts:[], selectedCategory:null, headItems:[]};\n"
        + "var period = 'month';\n"
        + "const __els = {};\n"
        + "function __el(id){ if(!__els[id]) __els[id] = {style:{}, textContent:''}; return __els[id]; }\n"
        + "const byId = id => __el(id);\n"
        + "const __plots = [];\n"
        + "const echarts = {init: el => { const c = {el:el, opts:[], resized:0, "
        + "setOption(o){this.opts.push(o);}, resize(){this.resized++;}, on(){}}; __plots.push(c); return c; }};\n"
        + "var window = {echarts: echarts};\n"
        + "const month=[{category:'Продукты',total:500},{category:'Транспорт',total:200}];\n"
        + "const all=[{category:'Продукты',total:800},{category:'Транспорт',total:700},"
        + "{category:'Дом и быт',total:900}];\n"
        + "const many=[]; for(let i=0;i<10;i++) many.push({category:'Кат'+i,total:1000-10*i});\n"
        + "renderCategoryBars(month);\n"
        + "const bars1=__plots[0].opts[0], h2=__els['category-bars'].style.height;\n"
        + "renderCategoryBars(all);\n"
        + "const bars2=__plots[0].opts[1];\n"
        + "renderCategoryBars(many);\n"
        + "const h10=__els['category-bars'].style.height;\n"
        + "console.log(JSON.stringify({bars1:bars1.series, h2:h2,"
        + "bars2:bars2.series, h10:h10}));"
    )
    proc = subprocess.run(
        ["node", "-e", driver], capture_output=True, text=True, encoding="utf-8", timeout=30
    )
    if proc.returncode != 0:
        raise AssertionError("node driver failed:\n%s" % proc.stderr)
    return json.loads(proc.stdout)


def test_bars_mirror_pie_data_sorted_desc(bars_result):
    """Столбцы отсортированы по убыванию суммы."""
    bar = bars_result["bars2"][0]
    assert bar["type"] == "bar"
    assert [x["name"] for x in bar["data"]] == ["Дом и быт", "Продукты", "Транспорт"]
    assert [x["value"] for x in bar["data"]] == [900, 800, 700]


def test_bars_use_palette_colors(bars_result):
    expected = {"Дом и быт": "#2fb344", "Продукты": "#206bc4", "Транспорт": "#8b5cf6"}
    bar_colors = {x["name"]: x["itemStyle"]["color"] for x in bars_result["bars2"][0]["data"]}
    assert bar_colors == expected


def test_bars_update_with_period_switch(bars_result):
    """При смене периода столбцы перерисовываются."""
    assert [x["name"] for x in bars_result["bars1"][0]["data"]] == ["Продукты", "Транспорт"]
    assert [x["name"] for x in bars_result["bars2"][0]["data"]] == ["Дом и быт", "Продукты", "Транспорт"]


def test_bars_height_scales_with_categories(bars_result):
    assert bars_result["h2"] == "260px"
    assert bars_result["h10"] == "480px"
