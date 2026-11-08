"""Общие фикстуры для тестов."""

from __future__ import annotations

import datetime as dt

import pytest

from sheets import GoogleSheetsGateway


class FakeWorksheet:
    """Минимальный фейк gspread worksheet: таблица in-memory."""

    def __init__(self, data: list[list] | None = None):
        self.data = [list(r) for r in (data or [])]

    def get_all_values(self, value_render_option=None):
        return [list(r) for r in self.data]

    def append_row(self, values, value_input_option=None):
        self.data.append([str(v) for v in values])

    def update(self, values, range_name=None):
        start_row = int(range_name[1:].split(":")[0].split("$")[-1])
        for i, row in enumerate(values):
            while len(self.data) <= start_row - 1 + i:
                self.data.append([])
            self.data[start_row - 1 + i] = [str(v) for v in row]

    def delete_rows(self, start_index, end_index=None):
        del self.data[start_index - 1:(end_index if end_index is not None else start_index)]

    def clear(self):
        self.data = []


class FakeGateway:
    """Записывает вызовы, возвращает предсказуемые данные."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.categories: dict[str, list[str]] = {}
        self.next_id = 1
        self.stats: tuple[float, dict[str, float]] = (0.0, {})
        self.report_data: dict = {"total": 0.0, "count": 0, "by_cat": {}, "top3": []}

    def append_transaction(self, category, subcategory, amount, comment=""):
        self.calls.append(("append", category, subcategory, amount, comment))
        txn_id = self.next_id
        self.next_id += 1
        return txn_id

    def read_categories(self):
        return self.categories

    def add_synonym(self, category, synonym):
        self.calls.append(("add_synonym", category, synonym))
        return True

    def delete_transaction(self, txn_id):
        self.calls.append(("delete", txn_id))
        return True

    def edit_transaction(self, txn_id, amount=None, category=None):
        self.calls.append(("edit", txn_id, amount, category))
        return True

    def monthly_stats(self, year, month):
        self.calls.append(("stats", year, month))
        return self.stats

    def monthly_report_data(self, year, month):
        self.calls.append(("report_data", year, month))
        return self.report_data


@pytest.fixture
def ws_cats():
    return FakeWorksheet([["Категория", "Синонимы"],
                          ["Продукты", "еда, хлеб, молоко"],
                          ["Транспорт", "такси, метро"]])


@pytest.fixture
def ws_trans():
    today = dt.date.today().isoformat()
    return FakeWorksheet([
        ["Дата", "Категория", "Подкатегория", "Сумма", "Комментарий", "ID"],
        [today, "Продукты", "хлеб", "100", "", "1"],
        [today, "Продукты", "молоко", "90", "", "2"],
    ])


@pytest.fixture
def gateway(ws_trans, ws_cats):
    return GoogleSheetsGateway(ws_trans, ws_cats)


def make_update(text: str, user_id: int = 123) -> dict:
    return {"update_id": 1, "message": {"from": {"id": user_id}, "chat": {"id": user_id}, "text": text}}
