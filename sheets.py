"""Обёртки gspread: запись транзакций, словарь категорий, Executive Blue."""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import time
from datetime import date, timedelta
from dateutil import tz

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, GSpreadException, WorksheetNotFound  # noqa: F401

from parser import parse_number

logger = logging.getLogger(__name__)

_EXCEL_EPOCH = date(1899, 12, 30)
_MOSCOW = tz.gettz("Europe/Moscow")

_RETRYABLE_STATUS = (429, 500, 503)
_MAX_RETRIES = 3
_MAX_RETRY_WAIT = 5  # секунд; окно функции — 30с (см. vercel.json), суммарный backoff 1+2+4с


def _parse_cell_date(raw: str) -> date | None:
    """Парсит дату из ячейки: serial-число Excel, ДД.ММ.ГГГГ или ГГГГ-ММ-ДД."""
    s = raw.strip()
    if not s:
        return None
    try:
        return _EXCEL_EPOCH + timedelta(days=int(float(s)))
    except (ValueError, OverflowError):
        pass
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def _with_retry(fn, *args, **kwargs):
    """Вызывает fn с повторными попытками при 429/500/503."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except APIError as exc:
            status = getattr(exc, "response", None)
            code = getattr(status, "status_code", None) if status else None
            if code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                delay = min(2 ** attempt, _MAX_RETRY_WAIT)
                logger.warning("Google API %s, retry %s/%s in %ss", code, attempt + 1, _MAX_RETRIES, delay)
                time.sleep(delay)
                continue
            raise
        except GSpreadException:
            if attempt < _MAX_RETRIES:
                time.sleep(1)
                continue
            raise


def _sanitize_cell(value: str) -> str:
    """Экранирует формулы Google Sheets (защита от инъекций)."""
    v = str(value).strip()
    if v and v[0] in "=+-@":
        return "'" + v
    return v


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# Executive Blue палитра
DARK_BLUE = {"red": 0.118, "green": 0.227, "blue": 0.373}
LIGHT_BLUE = {"red": 0.290, "green": 0.565, "blue": 0.886}
OFF_WHITE = {"red": 0.973, "green": 0.976, "blue": 0.980}
DARK_GRAY = {"red": 0.173, "green": 0.243, "blue": 0.314}


def get_creds() -> Credentials:
    """Credentials: файл GOOGLE_CREDENTIALS_PATH или GOOGLE_CREDENTIALS_JSON."""
    path = os.getenv("GOOGLE_CREDENTIALS_PATH", "google_credentials.json")
    if os.path.exists(path):
        return Credentials.from_service_account_file(path, scopes=SCOPES)
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        raise ValueError("Нет Google credentials: GOOGLE_CREDENTIALS_PATH или GOOGLE_CREDENTIALS_JSON")
    return Credentials.from_service_account_info(json.loads(creds_json), scopes=SCOPES)


def get_gc() -> gspread.Client:
    return gspread.authorize(get_creds())


class GoogleSheetsGateway:
    """Операции над листами «Транзакции» и «Категории»."""

    def __init__(self, transactions_ws, categories_ws):
        self.transactions_ws = transactions_ws
        self.categories_ws = categories_ws
        self._cats_cache: dict[str, list[str]] | None = None
        self._cats_cache_ttl = 10  # сброс кэша каждые N вызовов
        self._cats_calls = 0

    def _invalidate_cats_cache(self) -> None:
        self._cats_cache = None

    def _get_all_values_retry(self, ws, **kwargs):
        return _with_retry(ws.get_all_values, **kwargs)

    # --- Транзакции ---

    def next_txn_id(self, year: int, month: int) -> int:
        """Возвращает следующий ID в пределах месяца — нумерация начинается заново каждый месяц."""
        rows = self._get_all_values_retry(self.transactions_ws)
        max_id = 0
        for row in rows[1:]:
            if len(row) < 6:
                continue
            cell_date = _parse_cell_date(str(row[0]))
            if cell_date is None or cell_date.year != year or cell_date.month != month:
                continue
            if row[5].strip().isdigit():
                max_id = max(max_id, int(row[5]))
        return max_id + 1

    def append_transaction(
        self, category: str, subcategory: str, amount: float,
        comment: str = "",
    ) -> int:
        today = _dt.datetime.now(_MOSCOW).date()
        txn_id = self.next_txn_id(today.year, today.month)
        _with_retry(
            self.transactions_ws.append_row,
            [today.isoformat(), _sanitize_cell(category), _sanitize_cell(subcategory),
             str(amount), _sanitize_cell(comment), str(txn_id)],
            value_input_option="USER_ENTERED",
        )
        return txn_id

    def _find_row_by_id(
        self, txn_id: int, year: int, month: int
    ) -> tuple[int, list[str]] | None:
        """Возвращает (индекс, данные строки) записи с ID в указанном месяце, или None."""
        rows = self._get_all_values_retry(self.transactions_ws)
        for i, row in enumerate(rows[1:], start=1):
            if len(row) < 6 or row[5].strip() != str(txn_id):
                continue
            cell_date = _parse_cell_date(str(row[0]))
            if cell_date is not None and cell_date.year == year and cell_date.month == month:
                return i, row
        return None

    def delete_transaction(self, txn_id: int) -> bool:
        today = _dt.datetime.now(_MOSCOW).date()
        found = self._find_row_by_id(txn_id, today.year, today.month)
        if found is None:
            return False
        row, _ = found
        _with_retry(self.transactions_ws.delete_rows, row + 1)
        return True

    def find_txn_by_comment(self, comment: str) -> int | None:
        """Возвращает ID транзакции с заданным комментарием (update_id), или None."""
        for row in self._get_all_values_retry(self.transactions_ws)[1:]:
            if len(row) >= 6 and row[4].strip() == comment and row[5].strip().isdigit():
                return int(row[5])
        return None

    def edit_transaction(
        self, txn_id: int,
        amount: float | None = None,
        category: str | None = None,
    ) -> bool:
        today = _dt.datetime.now(_MOSCOW).date()
        found = self._find_row_by_id(txn_id, today.year, today.month)
        if found is None:
            return False
        row, current = found
        if amount is not None:
            current[3] = str(amount)
        if category is not None:
            current[1] = _sanitize_cell(category)
        _with_retry(self.transactions_ws.update, [current], range_name=f"A{row + 1}")
        return True

    # --- Словарь категорий ---

    def read_categories(self) -> dict[str, list[str]]:
        self._cats_calls += 1
        if self._cats_cache is not None and self._cats_calls < self._cats_cache_ttl:
            return self._cats_cache
        rows = self._get_all_values_retry(self.categories_ws)
        result: dict[str, list[str]] = {}
        for row in rows[1:]:
            if len(row) >= 1 and row[0].strip():
                synonyms = [s.strip() for s in row[1].split(",") if s.strip()] if len(row) > 1 else []
                result[row[0].strip()] = synonyms
        self._cats_cache = result
        self._cats_calls = 0
        return result

    def add_synonym(self, category: str, synonym: str) -> bool:
        rows = self._get_all_values_retry(self.categories_ws)
        for i, row in enumerate(rows[1:], start=1):
            if len(row) >= 1 and row[0].strip() == category:
                synonyms = [s.strip() for s in row[1].split(",") if s.strip()] if len(row) > 1 else []
                if synonym in synonyms:
                    return False
                synonyms.append(synonym)
                _with_retry(
                    self.categories_ws.update,
                    [[row[0], ", ".join(synonyms)]],
                    range_name=f"A{i + 1}",
                )
                self._invalidate_cats_cache()
                return True
        _with_retry(
            self.categories_ws.append_row,
            [category, synonym],
            value_input_option="USER_ENTERED",
        )
        self._invalidate_cats_cache()
        return True

    # --- Статистика (для /stats) ---

    def monthly_stats(self, year: int, month: int) -> tuple[float, dict[str, float]]:
        total = 0.0
        by_cat: dict[str, float] = {}
        for row in self._get_all_values_retry(self.transactions_ws, value_render_option="UNFORMATTED_VALUE")[1:]:
            if len(row) < 4:
                continue
            cell_date = _parse_cell_date(str(row[0]))
            if cell_date is None or cell_date.year != year or cell_date.month != month:
                continue
            amount = parse_number(row[3])
            if amount is None:
                continue
            total += amount
            by_cat[row[1]] = by_cat.get(row[1], 0.0) + amount
        return total, by_cat

    def monthly_report_data(self, year: int, month: int) -> dict:
        """Данные для ежемесячного отчёта: total, by_cat, count, top3."""
        total = 0.0
        by_cat: dict[str, float] = {}
        count = 0
        deductions_total = 0.0
        deductions_count = 0
        transactions: list[tuple[float, str, str, str]] = []
        for row in self._get_all_values_retry(self.transactions_ws, value_render_option="UNFORMATTED_VALUE")[1:]:
            if len(row) < 4:
                continue
            cell_date = _parse_cell_date(str(row[0]))
            if cell_date is None or cell_date.year != year or cell_date.month != month:
                continue
            amount = parse_number(row[3])
            if amount is None:
                continue
            total += amount
            by_cat[row[1]] = by_cat.get(row[1], 0.0) + amount
            count += 1
            if amount < 0:
                deductions_total += amount
                deductions_count += 1
            date_str = cell_date.isoformat()
            category = row[1]
            subcategory = row[2] if len(row) > 2 else ""
            transactions.append((amount, date_str, category, subcategory))
        positive = [item for item in transactions if item[0] > 0]
        positive.sort(key=lambda x: -x[0])
        top3 = [(d, c, s, a) for a, d, c, s in positive[:3]]
        return {
            "total": total,
            "by_cat": by_cat,
            "count": count,
            "top3": top3,
            "deductions_total": deductions_total,
            "deductions_count": deductions_count,
        }


# --- Executive Blue formatting requests (batchUpdate) ---

def apply_executive_theme(ws) -> list[dict]:
    return [
        {"updateSheetProperties": {
            "properties": {"sheetId": ws.id,
                           "gridProperties": {"hideGridlines": True}},
            "fields": "gridProperties.hideGridlines"}},
        {"repeatCell": {
            "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1000,
                      "startColumnIndex": 0, "endColumnIndex": 26},
            "cell": {"userEnteredFormat": {
                "backgroundColor": OFF_WHITE,
                "textFormat": {"fontFamily": "Roboto", "fontSize": 10,
                               "foregroundColor": DARK_GRAY}}},
            "fields": "userEnteredFormat(backgroundColor,textFormat)"}},
    ]


def format_table_header(ws, row: int, start_col: int, end_col: int) -> list[dict]:
    return [{"repeatCell": {
        "range": {"sheetId": ws.id, "startRowIndex": row - 1, "endRowIndex": row,
                  "startColumnIndex": start_col, "endColumnIndex": end_col},
        "cell": {"userEnteredFormat": {
            "backgroundColor": DARK_BLUE,
            "textFormat": {"fontFamily": "Montserrat", "fontSize": 11, "bold": True,
                           "foregroundColor": OFF_WHITE}}},
        "fields": "userEnteredFormat(backgroundColor,textFormat)"}}]


def format_table_body(ws, start_row: int, end_row: int,
                      start_col: int, end_col: int) -> list[dict]:
    return [{"repeatCell": {
        "range": {"sheetId": ws.id, "startRowIndex": start_row - 1,
                  "endRowIndex": end_row, "startColumnIndex": start_col,
                  "endColumnIndex": end_col},
        "cell": {"userEnteredFormat": {
            "textFormat": {"fontFamily": "Roboto", "fontSize": 10,
                           "foregroundColor": DARK_GRAY}}},
        "fields": "userEnteredFormat(textFormat)"}}]


def format_header_row(ws) -> list[dict]:
    """Закрепить строку заголовка."""
    return [{"updateSheetProperties": {
        "properties": {"sheetId": ws.id,
                       "gridProperties": {"frozenRowCount": 1}},
        "fields": "gridProperties.frozenRowCount"}}]
