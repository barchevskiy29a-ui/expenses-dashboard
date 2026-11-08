import datetime as dt

import pytest
from dateutil import tz as _tz

from sheets import GoogleSheetsGateway

_MOSCOW = _tz.gettz("Europe/Moscow")


def _today() -> dt.date:
    """Сегодня по Москве — тот же источник, что в прод-коде (sheets.py).

    Регрессия 07.10.2026: наивный _today() — это UTC на раннере,
    поэтому тест падал ежедневно 21:00–00:00 UTC, когда в Москве уже
    следующие сутки (assert '2026-10-07' == '2026-10-06').
    """
    return dt.datetime.now(_MOSCOW).date()


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


@pytest.fixture
def ws_trans():
    today = _today().isoformat()
    return FakeWorksheet([
        ["Дата", "Категория", "Подкатегория", "Сумма", "Комментарий", "ID"],
        [today, "Продукты", "хлеб", "100", "", "1"],
        [today, "Продукты", "молоко", "90", "", "2"],
    ])


@pytest.fixture
def ws_cats():
    return FakeWorksheet([["Категория", "Синонимы"],
                          ["Продукты", "еда, хлеб, молоко"],
                          ["Дом и быт", "моющие средства, порошок"]])


def test_next_id(ws_trans, ws_cats):
    gw = GoogleSheetsGateway(ws_trans, ws_cats)
    today = _today()
    assert gw.next_txn_id(today.year, today.month) == 3


def test_next_id_empty(ws_cats):
    gw = GoogleSheetsGateway(FakeWorksheet([["Дата", "Категория", "Подкатегория",
                                             "Сумма", "Комментарий", "ID"]]), ws_cats)
    today = _today()
    assert gw.next_txn_id(today.year, today.month) == 1


def test_next_id_ignores_other_month(ws_cats):
    data = [
        ["Дата", "Категория", "Подкатегория", "Сумма", "Комментарий", "ID"],
        ["2020-01-05", "Продукты", "", "100", "", "100"],
        [_today().isoformat(), "Продукты", "хлеб", "100", "", "1"],
    ]
    gw = GoogleSheetsGateway(FakeWorksheet(data), ws_cats)
    today = _today()
    assert gw.next_txn_id(today.year, today.month) == 2
    assert gw.next_txn_id(2020, 1) == 101


def test_next_id_other_month_empty(ws_cats):
    gw = GoogleSheetsGateway(FakeWorksheet([["Дата", "Категория", "Подкатегория",
                                             "Сумма", "Комментарий", "ID"],
                                             ["2020-01-05", "Продукты", "", "100", "", "7"]]), ws_cats)
    assert gw.next_txn_id(2020, 2) == 1


def test_append_transaction(ws_trans, ws_cats):
    gw = GoogleSheetsGateway(ws_trans, ws_cats)
    txn_id = gw.append_transaction("Продукты", "масло", 150.5)
    assert txn_id == 3
    row = ws_trans.data[-1]
    assert row[0] == _today().isoformat()
    assert row[1] == "Продукты"
    assert row[2] == "масло"
    assert row[3] == "150.5"
    assert row[5] == "3"


def test_append_transaction_with_comment(ws_trans, ws_cats):
    gw = GoogleSheetsGateway(ws_trans, ws_cats)
    txn_id = gw.append_transaction("Продукты", "масло", 150.5, comment="u42")
    assert txn_id == 3
    assert ws_trans.data[-1][4] == "u42"
    assert gw.find_txn_by_comment("u42") == 3
    assert gw.find_txn_by_comment("u999") is None


def test_append_transaction_negative_amount(ws_trans, ws_cats):
    gw = GoogleSheetsGateway(ws_trans, ws_cats)
    txn_id = gw.append_transaction(
        "Здоровье", "аптека", -1240, comment="вычет u42"
    )
    row = ws_trans.data[-1]
    assert txn_id == 3
    assert row[3] == "-1240"
    assert row[4] == "вычет u42"
    assert row[5] == "3"


def test_monthly_stats_nets_deduction(ws_cats):
    today = _today().isoformat()
    ws = FakeWorksheet([
        ["Дата", "Категория", "Подкатегория", "Сумма", "Комментарий", "ID"],
        [today, "Здоровье", "аптека", "2000", "", "1"],
        [today, "Здоровье", "возврат", "-1240", "вычет u42", "2"],
    ])
    gw = GoogleSheetsGateway(ws, ws_cats)
    total, by_cat = gw.monthly_stats(_today().year, _today().month)
    assert total == 2000 - 1240
    assert by_cat["Здоровье"] == 2000 - 1240


def test_read_categories(ws_trans, ws_cats):
    gw = GoogleSheetsGateway(ws_trans, ws_cats)
    cats = gw.read_categories()
    assert cats["Продукты"] == ["еда", "хлеб", "молоко"]
    assert cats["Дом и быт"] == ["моющие средства", "порошок"]


def test_add_synonym(ws_trans, ws_cats):
    gw = GoogleSheetsGateway(ws_trans, ws_cats)
    assert gw.add_synonym("Продукты", "сыр") is True
    assert gw.add_synonym("Продукты", "сыр") is False
    assert "сыр" in ws_cats.data[1][1]


def test_delete_transaction(ws_trans, ws_cats):
    gw = GoogleSheetsGateway(ws_trans, ws_cats)
    assert gw.delete_transaction(2) is True
    ids = [r[5] for r in ws_trans.data[1:]]
    assert "2" not in ids
    assert gw.delete_transaction(999) is False


def test_delete_first_keeps_header(ws_trans, ws_cats):
    gw = GoogleSheetsGateway(ws_trans, ws_cats)
    assert gw.delete_transaction(1) is True
    assert ws_trans.data[0] == ["Дата", "Категория", "Подкатегория", "Сумма", "Комментарий", "ID"]
    ids = [r[5] for r in ws_trans.data[1:]]
    assert "1" not in ids


def test_delete_other_month_not_found(ws_cats):
    data = [
        ["Дата", "Категория", "Подкатегория", "Сумма", "Комментарий", "ID"],
        ["2020-01-05", "Продукты", "", "100", "", "3"],
        [_today().isoformat(), "Продукты", "хлеб", "100", "", "2"],
    ]
    gw = GoogleSheetsGateway(FakeWorksheet(data), ws_cats)
    assert gw.delete_transaction(3) is False  # ID 3 есть только в другом месяце


def test_edit_other_month_not_found(ws_cats):
    data = [
        ["Дата", "Категория", "Подкатегория", "Сумма", "Комментарий", "ID"],
        ["2020-01-05", "Продукты", "", "100", "", "3"],
        [_today().isoformat(), "Продукты", "хлеб", "100", "", "2"],
    ]
    gw = GoogleSheetsGateway(FakeWorksheet(data), ws_cats)
    assert gw.edit_transaction(3, amount=500.0) is False  # ID 3 — другой месяц
    assert gw.edit_transaction(2, amount=200.0) is True


def test_edit_amount(ws_trans, ws_cats):
    gw = GoogleSheetsGateway(ws_trans, ws_cats)
    assert gw.edit_transaction(1, amount=250.0) is True
    assert ws_trans.data[1][3] == "250.0"


def test_edit_category(ws_trans, ws_cats):
    gw = GoogleSheetsGateway(ws_trans, ws_cats)
    assert gw.edit_transaction(2, category="Развлечения") is True
    assert ws_trans.data[2][1] == "Развлечения"


def test_monthly_stats(ws_trans, ws_cats):
    gw = GoogleSheetsGateway(ws_trans, ws_cats)
    today = _today()
    total, by_cat = gw.monthly_stats(today.year, today.month)
    assert by_cat.get("Продукты", 0) == 190.0
    assert total == 190.0


def test_monthly_stats_text_amount_with_comma(ws_trans, ws_cats):
    ws_trans.data.append([_today().isoformat(), "Продукты", "сыр",
                          "1,246.00", "", "3"])
    gw = GoogleSheetsGateway(ws_trans, ws_cats)
    today = _today()
    total, by_cat = gw.monthly_stats(today.year, today.month)
    assert by_cat["Продукты"] == 190.0 + 1246.0
    assert total == 190.0 + 1246.0


def test_monthly_stats_skips_garbage_amount(ws_trans, ws_cats):
    ws_trans.data.append([_today().isoformat(), "Продукты", "мусор",
                          "не-число", "", "3"])
    gw = GoogleSheetsGateway(ws_trans, ws_cats)
    today = _today()
    total, by_cat = gw.monthly_stats(today.year, today.month)
    assert by_cat.get("Продукты", 0) == 190.0
    assert total == 190.0
