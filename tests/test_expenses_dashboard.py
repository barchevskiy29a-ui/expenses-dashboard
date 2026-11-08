"""Честность цифр дашборда расходов: всё пересчитывается скриптом.

Инварианты data.json: ISO-даты, каноничные категории, равенство итогов,
среднее за календарные месяцы истории (решение владельца).
"""

import datetime as dt

from scripts.export_expenses_dashboard import build_dashboard_output


def _tx(date, category, amount, subcategory="", comment=""):
    return {
        "date": date, "category": category, "subcategory": subcategory,
        "comment": comment, "amount": amount,
    }


def _now():
    return dt.datetime(2026, 10, 7, 12, 0,
                       tzinfo=dt.timezone(dt.timedelta(hours=3)))


def _output():
    return build_dashboard_output([
        _tx("2026-08-02", "Продукты", 100.0),
        _tx("2026-09-18", "продукты", 500.0),
        _tx("2026-10-01", "Кафе и рестораны", 335.5),
    ], _now())


def test_all_dates_are_iso():
    import re

    for t in _output()["transactions"]:
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", t["date"]), t["date"]


def test_categories_are_canonical():
    cats = [c["category"] for c in _output()["categories"]]
    assert "продукты" not in cats, "регистр плодил бы отдельный сектор"
    assert "Продукты" in cats


def test_totals_match_transactions():
    out = _output()
    expected = sum(t["amount"] for t in out["transactions"])
    assert out["summary"]["total"] == expected
    assert sum(c["total"] for c in out["categories"]) == expected
    assert sum(m["total"] for m in out["months"]) == expected


def test_month_total_is_recomputed():
    out = _output()
    label = out["summary"]["month_label"]
    expected = sum(t["amount"] for t in out["transactions"]
                   if t["date"].startswith(label))
    assert out["summary"]["month_total"] == expected


def test_deduction_nets_totals():
    out = build_dashboard_output([
        _tx("2026-10-01", "Здоровье", 1000.0),
        _tx("2026-10-02", "Здоровье", -400.0,
            subcategory="аптека", comment="вычет u42"),
        _tx("2026-10-03", "Продукты", 500.0),
    ], _now())
    assert out["summary"]["month_total"] == 1000 - 400 + 500
    assert out["summary"]["total"] == 1000 - 400 + 500
    categories = {c["category"]: c["total"] for c in out["categories"]}
    assert categories["Здоровье"] == 1000 - 400
    deductions = [t for t in out["transactions"] if t["amount"] < 0]
    assert len(deductions) == 1
    assert deductions[0]["amount"] == -400


def test_average_over_calendar_months():
    """Среднее = всего / календарные месяцы истории (08, 09, 10 = 3)."""
    out = _output()
    assert out["summary"]["average_month"] == out["summary"]["total"] / 3


def test_month_label_is_current():
    assert _output()["summary"]["month_label"] == "2026-10"


def test_custom_category_survives_export():
    """Кастомная категория не склеивается с дефолтной нечётким матчингом."""
    out = build_dashboard_output([
        _tx("2026-10-01", "Такси работа", 100.0),
        _tx("2026-10-02", "Кофе с собой", 200.0),
    ], _now())
    cats = [c["category"] for c in out["categories"]]
    assert "Такси работа" in cats, cats
    assert "Кофе с собой" in cats, cats


def test_case_only_is_canonicalized():
    """Регистр правится, смысл — нет: «продукты» → «Продукты»."""
    out = build_dashboard_output([_tx("2026-10-01", "продукты", 100.0)], _now())
    assert [c["category"] for c in out["categories"]] == ["Продукты"]


def test_future_dates_do_not_break_average():
    """Будущие даты не дают отрицательный спан и не раздувают total."""
    out = build_dashboard_output([
        _tx("2026-10-01", "Продукты", 100.0),
        _tx("2026-12-15", "Продукты", 900.0),
    ], _now())
    assert out["summary"]["average_month"] == 100.0
    assert out["summary"]["total"] == 100.0


def test_money_shows_kopeks():
    """Суммы с копейками (решение владельца): 335.5 → «335,50 ₽»."""
    import re
    import shutil
    import subprocess

    assert shutil.which("node"), "нужен node"
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    match = re.search(r"const money = .*?;", js)
    assert match, "функция money не найдена"
    script = match.group(0) + "\nconsole.log(money(335.5));\nconsole.log(money(1000));"
    proc = subprocess.run(["node", "-e", script], capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    lines = proc.stdout.decode("utf-8").strip().splitlines()
    assert "335,50" in lines[0], lines
    normalized = lines[1].replace("\u00a0", " ").replace("\u202f", " ")
    assert normalized.endswith("1 000,00 ₽"), lines


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


def _render_transactions(items, month_label):
    """Прогоняет renderTransactions из app.js через node с DOM-заглушкой."""
    import json as _json
    import shutil
    import subprocess

    assert shutil.which("node"), "нужен node"
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    money = None
    import re as _re

    money = _re.search(r"const money = .*?;", js).group(0)
    escape = [line for line in js.splitlines()
              if line.startswith("function escapeHtml")][0]
    driver = (
        escape + "\n"
        + _extract_function(js, "displayNote") + "\n"
        + money + "\n"
        + _extract_function(js, "renderTransactions") + "\n"
        + "const __store = {};\n"
        + "const document = {getElementById:id=>{if(!__store[id])"
        + "__store[id]={value:'',textContent:'',innerHTML:''};return __store[id];}};\n"
        + "const byId = id => document.getElementById(id);\n"
        + f"const items = {_json.dumps(items, ensure_ascii=False)};\n"
        + f"renderTransactions(items, {month_label!r});\n"
        + "console.log(JSON.stringify({count:__store['transaction-count'].textContent,"
        + "rows:(__store['transactions-body'].innerHTML.match(/<tr>/g)||[]).length}));\n"
    )
    proc = subprocess.run(["node", "-e", driver], capture_output=True,
                          text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    return _json.loads(proc.stdout)


def test_list_uses_summary_month_not_browser():
    """Список строится от month_label, а не от часового пояса браузера.

    Все записи заведомо вне реального текущего месяца: со старым кодом
    (new Date()) список был бы пуст.
    """
    items = [
        {"date": "2020-01-05", "category": "Продукты", "subcategory": "хлеб",
         "comment": "", "amount": 100.0},
        {"date": "2020-01-06", "category": "Транспорт", "subcategory": "",
         "comment": "", "amount": 50.0},
    ]
    result = _render_transactions(items, "2020-01")
    assert result["rows"] == 2, result


def test_non_iso_date_excluded_from_month():
    """Не-ISO дата не попадает в фильтр месяца (и не ломает его молча)."""
    items = [
        {"date": "2020-01-05", "category": "Продукты", "subcategory": "",
         "comment": "", "amount": 100.0},
        {"date": "05.01.2020", "category": "Продукты", "subcategory": "",
         "comment": "", "amount": 999.0},
    ]
    result = _render_transactions(items, "2020-01")
    assert result["rows"] == 1, result
    assert "из 1" in result["count"], result


def test_export_has_machine_readable_timestamp():
    """updated_at_iso с offset — возраст данных считается скриптом."""
    import datetime as _dt

    out = _output()
    assert "updated_at_iso" in out
    parsed = _dt.datetime.fromisoformat(out["updated_at_iso"])
    assert parsed.utcoffset() is not None, "offset обязателен"
    assert parsed.strftime("%Y-%m-%d %H:%M") == "2026-10-07 12:00"


def test_data_age_text_marks_stale():
    """Возраст данных: свежим — часы, старше 24 ч — stale."""
    import shutil
    import subprocess

    assert shutil.which("node"), "нужен node"
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    start = js.find("function dataAgeText")
    assert start != -1, "dataAgeText не найдена"
    script = js[start:js.find("\n}\n", start) + 3]
    script += (
        "\nconst now = Date.parse('2026-10-08T12:00:00+03:00');\n"
        "console.log(JSON.stringify(["
        "dataAgeText('2026-10-08T10:00:00+03:00', now),"
        "dataAgeText('2026-10-07T10:00:00+03:00', now),"
        "]));\n"
    )
    proc = subprocess.run(["node", "-e", script], capture_output=True,
                          text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    import json as _json

    fresh, stale = _json.loads(proc.stdout)
    assert fresh["stale"] is False and "2" in fresh["text"], fresh
    assert stale["stale"] is True, stale


def test_fetch_retries_before_failing():
    """Загрузка повторяется, а не падает с первой ошибки сети."""
    import shutil
    import subprocess

    assert shutil.which("node"), "нужен node"
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    assert "fetchWithRetry" in js
    start = js.find("async function fetchWithRetry")
    assert start != -1
    script = js[start:js.find("\n}\n", start) + 3]
    script += (
        "\nlet calls = 0;\n"
        "const flaky = () => (++calls < 3\n"
        "  ? Promise.reject(new Error('down'))\n"
        "  : Promise.resolve('data'));\n"
        "fetchWithRetry(flaky, 'u', {}, 3, 1).then(\n"
        "  v => console.log(JSON.stringify({value: v, calls})));\n"
    )
    proc = subprocess.run(["node", "-e", script], capture_output=True,
                          text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    import json as _json

    result = _json.loads(proc.stdout)
    assert result == {"value": "data", "calls": 3}, result


def test_sw_serves_cached_data_offline():
    """data.json: сеть пишет в кэш, офлайн отдаёт копию."""
    js = open("mobile-expenses/sw.js", encoding="utf-8").read()
    assert "data.json" in js
    assert "caches.match" in js
    assert ".put(" in js
    assert "response.ok" in js, "ошибочные ответы кэшировать нельзя"
    assert "pathname" in js, "ключ обязан быть без query (?ts=...)"


def _run_driver(extract_names, driver_tail):
    import shutil
    import subprocess

    assert shutil.which("node"), "нужен node"
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    parts = []
    for name in extract_names:
        if name == "money":
            import re as _re

            parts.append(_re.search(r"const money = .*?;", js).group(0))
        else:
            parts.append(_extract_function(js, name))
    script = "\n".join(parts) + "\n" + driver_tail
    proc = subprocess.run(["node", "-e", script], capture_output=True,
                          text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    import json as _json

    return _json.loads(proc.stdout)


def test_prev_total_matches_export_recompute():
    """prev-total клиента равен пересчёту по транзакциям за прошлый месяц."""
    import json as _json

    items = [
        {"date": "2026-09-05", "category": "Продукты", "amount": 300.0},
        {"date": "2026-09-18", "category": "Транспорт", "amount": 200.0},
        {"date": "2026-10-01", "category": "Продукты", "amount": 500.0},
    ]
    result = _run_driver(
        ["monthItemsByLabel", "prevMonthLabel"],
        f"const items = {_json.dumps(items)};\n"
        "const prev = prevMonthLabel('2026-10');\n"
        "const total = monthItemsByLabel({transactions: items}, prev)"
        ".reduce((a, t) => a + t.total, 0);\n"
        "console.log(JSON.stringify({prev, total}));\n",
    )
    assert result == {"prev": "2026-09", "total": 500.0}, result


def test_avg_times_months_equals_total():
    """Режим «среднее» согласован: avg * n месяцев == итог."""
    import json as _json

    data = _output()
    result = _run_driver(
        ["avgItems"],
        f"const data = {_json.dumps({'months': data['months'], 'categories': data['categories'], 'summary': data['summary']})};\n"
        "const avg = avgItems(data);\n"
        "const n = data.months.length;\n"
        "const restored = avg.reduce((a, x) => a + x.total, 0) * n;\n"
        "const total = data.categories.reduce((a, x) => a + x.total, 0);\n"
        "console.log(JSON.stringify({restored, total}));\n",
    )
    assert abs(result["restored"] - result["total"]) < 1e-6, result


def test_avg_mode_counts_empty_months():
    """Пропуск месяца (авг+окт без сен) делит на 3, а не на 2."""
    import json as _json

    data = {
        "months": [{"month": "2026-08", "total": 300.0},
                   {"month": "2026-10", "total": 300.0}],
        "categories": [{"category": "Продукты", "total": 600.0}],
        "summary": {"months_span": 3},
    }
    result = _run_driver(
        ["avgItems"],
        f"const data = {_json.dumps(data)};\n"
        "const avg = avgItems(data);\n"
        "console.log(JSON.stringify(avg));\n",
    )
    assert result == [{"category": "Продукты", "total": 200.0}], result


def test_status_falls_back_to_legacy_timestamp():
    """Старый data.json без updated_at_iso: возраст считается по updated_at."""
    import json as _json
    import shutil
    import subprocess

    assert shutil.which("node"), "нужен node"
    js = open("mobile-expenses/app.js", encoding="utf-8").read()
    start = js.find("function parseLegacyUpdatedAt")
    assert start != -1, "parseLegacyUpdatedAt не найдена"
    script = js[start:js.find("\n}\n", start) + 3]
    script += (
        "\nconst now = Date.parse('2026-10-08T12:00:00+03:00');\n"
        "console.log(JSON.stringify([\n"
        "  parseLegacyUpdatedAt('2026-10-08 10:00 МСК'),\n"
        "  parseLegacyUpdatedAt('мусор'),\n"
        "]));\n"
    )
    proc = subprocess.run(["node", "-e", script], capture_output=True,
                          text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    iso, garbage = _json.loads(proc.stdout)
    assert iso == "2026-10-08T10:00:00+03:00", iso
    assert garbage == "", garbage


def test_september_home_category_reconciliation():
    """Сверка 14.10.2026: сентябрь «Дом и быт» = 95 309 ровно.

    Метод, которым цифра подтверждена против Google Sheets: сумма amount
    по транзакциям сентября с каноничной категорией, без утечек через границу
    месяца и без дублей. Тест фиксирует метод на фикстуре с границей 30.09/01.10
    и регистровым вариантом категории.
    """
    out = build_dashboard_output([
        _tx("2026-09-01", "Дом и быт", 1000.0),
        _tx("2026-09-15", "дом и быт", 500.50),
        _tx("2026-09-30", "Дом и быт", 322.0),
        _tx("2026-09-30", "Продукты", 715.09),
        _tx("2026-10-01", "Дом и быт", 133.0),
        _tx("2026-10-01", "Продукты", 613.0),
    ], _now())
    by_cat_month = {}
    for t in out["transactions"]:
        by_cat_month.setdefault((t["date"][:7], t["category"]), 0.0)
        by_cat_month[(t["date"][:7], t["category"])] += t["amount"]
    assert by_cat_month[("2026-09", "Дом и быт")] == 1000.0 + 500.50 + 322.0
    assert by_cat_month[("2026-10", "Дом и быт")] == 133.0
    assert by_cat_month[("2026-09", "Продукты")] == 715.09
    months = {m["month"]: m["total"] for m in out["months"]}
    assert months["2026-09"] == 1000.0 + 500.50 + 322.0 + 715.09
    assert months["2026-10"] == 133.0 + 613.0
