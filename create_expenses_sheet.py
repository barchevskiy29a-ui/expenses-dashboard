"""Одноразовая инициализация Google-таблицы расходов.

Запуск: python create_expenses_sheet.py (нужны GOOGLE_SHEET_ID и credentials).
ВНИМАНИЕ: удаляет портфельные листы (Dashboard, Summary, ...).
"""

from __future__ import annotations

import os

import gspread.exceptions
from categories import DEFAULT_CATEGORIES
from formulas import (MONTHLY_CATEGORY_COLUMNS, TRANSACTIONS_HEADERS,
                      TRANSACTIONS_SHEET,
                      avg_month_formula, category_list_formula,
                      current_month_sum_formula, month_category_header_formula,
                      month_category_sum_formula, month_list_formula,
                      month_total_formula, total_sum_formula)
from sheets import (apply_executive_theme, format_header_row,
                    format_table_body, format_table_header, get_gc)

SHEETS_TO_REMOVE = ["Dashboard", "Summary", "Allocation", "Performance",
                    "FeesAndTaxes", "CashFlows", "TWR"]

NEW_SHEETS: dict[str, list[list]] = {
    TRANSACTIONS_SHEET: [TRANSACTIONS_HEADERS],
    "Категории": [["Категория", "Синонимы"]]
    + [[cat, ", ".join(syns)] for cat, syns in DEFAULT_CATEGORIES.items()],
    "По категориям": [["Категория", "Текущий месяц", "Всего", "Среднее в месяц"]],
    "По месяцам": [["Месяц", "ИТОГО"]],
}

_CATEGORY_COLORS = [
    {"red": 0.153, "green": 0.682, "blue": 0.376},
    {"red": 0.118, "green": 0.227, "blue": 0.373},
    {"red": 0.827, "green": 0.557, "blue": 0.224},
    {"red": 0.290, "green": 0.565, "blue": 0.886},
    {"red": 0.906, "green": 0.298, "blue": 0.235},
    {"red": 0.584, "green": 0.647, "blue": 0.650},
]


def build_chart_requests(service, spreadsheet_id: str,
                         sheet_ids: dict[str, int]) -> list[dict]:
    """Requests для 3 диаграмм (pie по категориям + 2 line по месяцам)."""
    by_cat = sheet_ids["По категориям"]
    by_month = sheet_ids["По месяцам"]
    pie = {"addChart": {"chart": {"spec": {
        "title": "Расходы за текущий месяц",
        "pieChart": {
            "domain": {"sourceRange": {"sources": [{
                "sheetId": by_cat, "startRowIndex": 0, "endRowIndex": 60,
                "startColumnIndex": 0, "endColumnIndex": 1}]}},
            "series": {"sourceRange": {"sources": [{
                "sheetId": by_cat, "startRowIndex": 0, "endRowIndex": 60,
                "startColumnIndex": 1, "endColumnIndex": 2}]}},
        }},
        "position": {"overlayPosition": {
            "anchorCell": {"sheetId": by_cat, "rowIndex": 1, "columnIndex": 6},
            "widthPixels": 500, "heightPixels": 320}}}}}
    line_total = {"addChart": {"chart": {"spec": {
        "title": "Все расходы по месяцам",
        "basicChart": {
            "chartType": "LINE", "legendPosition": "BOTTOM_LEGEND",
            "headerCount": 1,
            "axis": [{"position": "BOTTOM_AXIS", "title": "Месяц"},
                     {"position": "LEFT_AXIS", "title": "₽"}],
            "domains": [{"domain": {"sourceRange": {"sources": [{
                "sheetId": by_month, "startRowIndex": 0, "endRowIndex": 200,
                "startColumnIndex": 0, "endColumnIndex": 1}]}}}],
            "series": [{"series": {"sourceRange": {"sources": [{
                "sheetId": by_month, "startRowIndex": 0, "endRowIndex": 200,
                "startColumnIndex": 1, "endColumnIndex": 2}]}},
                "targetAxis": "LEFT_AXIS", "color": _CATEGORY_COLORS[1],
                "lineStyle": {"type": "SOLID"}}],
        }},
        "position": {"overlayPosition": {
            "anchorCell": {"sheetId": by_month, "rowIndex": 0, "columnIndex": 4},
            "widthPixels": 800, "heightPixels": 400}}}}}
    line_cats = {"addChart": {"chart": {"spec": {
        "title": "Расходы по категориям",
        "basicChart": {
            "chartType": "LINE", "legendPosition": "BOTTOM_LEGEND",
            "headerCount": 1,
            "axis": [{"position": "BOTTOM_AXIS", "title": "Месяц"},
                     {"position": "LEFT_AXIS", "title": "₽"}],
            "domains": [{"domain": {"sourceRange": {"sources": [{
                "sheetId": by_month, "startRowIndex": 0, "endRowIndex": 200,
                "startColumnIndex": 0, "endColumnIndex": 1}]}}}],
            "series": [
                {"series": {"sourceRange": {"sources": [{
                    "sheetId": by_month, "startRowIndex": 0, "endRowIndex": 200,
                    "startColumnIndex": c, "endColumnIndex": c + 1}]}},
                 "targetAxis": "LEFT_AXIS",
                 "color": _CATEGORY_COLORS[c % len(_CATEGORY_COLORS)],
                 "lineStyle": {"type": "SOLID"}}
                for c in range(1, MONTHLY_CATEGORY_COLUMNS + 1)
            ],
        }},
        "position": {"overlayPosition": {
            "anchorCell": {"sheetId": by_month, "rowIndex": 21, "columnIndex": 4},
            "widthPixels": 800, "heightPixels": 400}}}}}
    return [pie, line_total, line_cats]


def build_category_formulas() -> list[list]:
    """Данные листа «По категориям»: категории + формулы по каждой строке.

    Все формулы скалярные (без расширения массива вниз), чтобы они не
    перекрывали соседние строки с формулами.
    """
    rows = []
    for r in range(2, 52):
        rows.append([
            category_list_formula(r),
            current_month_sum_formula(f"A{r}"),
            total_sum_formula(f"A{r}"),
            avg_month_formula(f"A{r}", f"C{r}"),
        ])
    return rows


def write_category_formulas(ws) -> None:
    """Запись формул листа «По категориям» (raw=False — как формулы, не текст)."""
    ws.update(build_category_formulas(), range_name="A2:D51", raw=False)


def build_monthly_formulas() -> tuple[list[list], list[list], list[list], list[list]]:
    """Формулы листа «По месяцам»: месяцы, итоги, шапка и суммы по категориям."""
    months = [[month_list_formula(r)] for r in range(2, 52)]
    totals = [[month_total_formula(r)] for r in range(2, 52)]
    end_col = 3 + MONTHLY_CATEGORY_COLUMNS
    headers = [[month_category_header_formula(c) for c in range(3, end_col)]]
    cats = [[month_category_sum_formula(r, c) for c in range(3, end_col)]
            for r in range(2, 52)]
    return months, totals, headers, cats


def write_monthly_formulas(ws) -> None:
    """Запись формул листа «По месяцам» (raw=False — как формулы, не текст)."""
    months, totals, headers, cats = build_monthly_formulas()
    ws.update(months, range_name="A2:A51", raw=False)
    ws.update(totals, range_name="B2:B51", raw=False)
    end_letter = chr(64 + 2 + MONTHLY_CATEGORY_COLUMNS)
    ws.update(headers, range_name=f"C1:{end_letter}1", raw=False)
    ws.update(cats, range_name=f"C2:{end_letter}51", raw=False)


def set_spreadsheet_locale(service, spreadsheet_id: str) -> None:
    """Локаль таблицы en_US: запятые в формулах валидны в любой локали Sheets."""
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"updateSpreadsheetProperties": {
            "properties": {"locale": "en_US"}, "fields": "locale"}}]}).execute()


def main() -> None:
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise SystemExit("GOOGLE_SHEET_ID не задан")
    gc = get_gc()
    sh = gc.open_by_key(sheet_id)

    for title in SHEETS_TO_REMOVE:
        try:
            ws = sh.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            continue
        sh.del_worksheet(ws)
        print(f"  ✓ Удалён лист: {title}")

    sheet_ids: dict[str, int] = {}
    for title, rows in NEW_SHEETS.items():
        ws = sh.worksheet(title) if _exists(sh, title) else sh.add_worksheet(title, rows=200, cols=30)
        ws.clear()
        ws.update(values=rows, range_name="A1")
        sheet_ids[title] = ws.id
        print(f"  ✓ Лист готов: {title}")

    # Формулы «По категориям»
    write_category_formulas(sh.worksheet("По категориям"))

    # Формулы «По месяцам»
    write_monthly_formulas(sh.worksheet("По месяцам"))

    # Формат дат и сумм на листе «Транзакции» (локаль таблицы en_US)
    ws = sh.worksheet(TRANSACTIONS_SHEET)
    ws.format("A2:A200", {"numberFormat": {"type": "DATE", "pattern": "DD.MM.YYYY"}})
    ws.format("D2:D200", {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"}})

    # Форматирование
    requests: list[dict] = []
    for title in ("Транзакции", "По категориям", "По месяцам", "Категории"):
        ws = sh.worksheet(title)
        requests.extend(apply_executive_theme(ws))
        requests.extend(format_table_header(ws, 1, 0, 6))
        requests.extend(format_table_body(ws, 2, 200, 0, 6))
        requests.extend(format_header_row(ws))
    sh.batch_update({"requests": requests})

    # Диаграммы: удалить старые, добавить новые
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from sheets import get_creds
    service = build("sheets", "v4", credentials=get_creds(), cache_discovery=False)
    set_spreadsheet_locale(service, sheet_id)
    spreadsheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    delete_reqs = []
    for sheet in spreadsheet.get("sheets", []):
        for chart in sheet.get("charts", []):
            delete_reqs.append({"deleteEmbeddedObject": {"objectId": chart["chartId"]}})
    if delete_reqs:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id, body={"requests": delete_reqs}).execute()
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": build_chart_requests(service, sheet_id, sheet_ids)},
    ).execute()
    print("  ✓ Диаграммы созданы")
    print(f"Готово: https://docs.google.com/spreadsheets/d/{sheet_id}")


def _exists(sh, title: str) -> bool:
    try:
        sh.worksheet(title)
        return True
    except gspread.exceptions.WorksheetNotFound:
        return False


if __name__ == "__main__":
    main()
