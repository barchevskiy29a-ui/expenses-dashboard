# tests/test_create_expenses_sheet.py
from create_expenses_sheet import (NEW_SHEETS, SHEETS_TO_REMOVE,
                                   build_category_formulas,
                                   build_chart_requests,
                                   set_spreadsheet_locale,
                                   write_category_formulas,
                                   write_monthly_formulas)


class FakeWorksheet:
    """Записывает вызовы update: (values, range_name, raw)."""

    def __init__(self):
        self.calls: list[tuple[list, str, bool]] = []

    def update(self, values, range_name=None, raw=True):
        self.calls.append((values, range_name, raw))


class FakeSheetsService:
    """Записывает batchUpdate-запросы."""

    def __init__(self):
        self.bodies: list[dict] = []

    def spreadsheets(self):
        return self

    def batchUpdate(self, spreadsheetId, body):
        self.bodies.append(body)
        return self

    def execute(self):
        return None


def test_removes_portfolio_sheets():
    assert "Dashboard" in SHEETS_TO_REMOVE
    assert "Summary" in SHEETS_TO_REMOVE
    assert "Allocation" in SHEETS_TO_REMOVE
    assert "Performance" in SHEETS_TO_REMOVE
    assert "FeesAndTaxes" in SHEETS_TO_REMOVE
    assert "CashFlows" in SHEETS_TO_REMOVE
    assert "TWR" in SHEETS_TO_REMOVE


def test_new_sheets_contain_transactions():
    assert "Транзакции" in NEW_SHEETS
    headers = NEW_SHEETS["Транзакции"][0]
    assert headers[:6] == ["Дата", "Категория", "Подкатегория",
                           "Сумма", "Комментарий", "ID"]


def test_categories_sheet_has_16_rows():
    rows = NEW_SHEETS["Категории"]
    assert rows[0] == ["Категория", "Синонимы"]
    assert len(rows) - 1 == 16


def test_chart_requests_created():
    reqs = build_chart_requests(None, "fake_id", {"Транзакции": 1, "Категории": 2,
                                                  "По категориям": 3, "По месяцам": 4})
    assert len(reqs) == 3  # pie + 2 line charts
    assert all("addChart" in r for r in reqs)


def test_category_formulas_fit_range():
    rows = build_category_formulas()
    assert len(rows) == 50  # A2:D51 вмещает 50 строк
    assert rows[0][0].startswith("=IFERROR(INDEX(SORT(UNIQUE(FILTER(")
    assert all(row[1].startswith("=SUMIFS") for row in rows)
    assert all(len(row) == 4 for row in rows)


def test_category_formulas_written_as_formulas():
    ws = FakeWorksheet()
    write_category_formulas(ws)
    values, range_name, raw = ws.calls[0]
    assert range_name == "A2:D51"
    assert raw is False  # иначе Google запишет «=…» текстом


def test_monthly_formulas_written_as_formulas():
    ws = FakeWorksheet()
    write_monthly_formulas(ws)
    assert [(r, raw) for _, r, raw in ws.calls] == [
        ("A2:A51", False), ("B2:B51", False), ("C1:R1", False), ("C2:R51", False)]
    assert len(ws.calls[0][0]) == 50  # A2:A51 — месяцы
    assert len(ws.calls[2][0][0]) == 16  # C1:R1 — шапка категорий


def test_locale_set_to_en_us():
    service = FakeSheetsService()
    set_spreadsheet_locale(service, "fake_id")
    req = service.bodies[0]["requests"][0]
    assert req["updateSpreadsheetProperties"]["properties"]["locale"] == "en_US"
    assert req["updateSpreadsheetProperties"]["fields"] == "locale"
