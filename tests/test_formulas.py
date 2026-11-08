# tests/test_formulas.py
from formulas import (TRANSACTIONS_HEADERS, TRANSACTIONS_SHEET,
                      avg_month_formula, category_list_formula,
                      current_month_sum_formula, month_category_header_formula,
                      month_category_sum_formula, month_list_formula,
                      month_total_formula, total_sum_formula)


def test_transactions_headers():
    assert TRANSACTIONS_HEADERS == ["Дата", "Категория", "Подкатегория",
                                    "Сумма", "Комментарий", "ID"]


def test_sheet_name_quoted_in_formulas():
    assert "'Транзакции'" in category_list_formula()
    assert "'Транзакции'" in month_list_formula()


def test_category_list_is_scalar_index():
    f = category_list_formula(2)
    assert f.startswith("=IFERROR(INDEX(SORT(UNIQUE(FILTER(")
    assert "'Транзакции'!$B$2:$B" in f
    assert ", 1), \"\")" in f
    assert "QUERY" not in f
    assert "ARRAYFORMULA" not in f


def test_category_list_row_number():
    assert ", 3), \"\")" in category_list_formula(4)


def test_current_month_formula():
    f = current_month_sum_formula()
    assert "SUMIFS" in f
    assert "EDATE" in f
    assert "A2" in f


def test_total_formula():
    f = total_sum_formula()
    assert "SUMIFS" in f
    assert f.endswith(")")


def test_avg_formula():
    f = avg_month_formula()
    assert "COUNTUNIQUE" in f
    assert "FILTER" in f
    assert "'Транзакции'!$A$2:$A<>\"\"" in f
    assert "C2/" in f


def test_avg_formula_with_row_cells():
    f = avg_month_formula("A3", "C3")
    assert "C3/" in f
    assert "=A3" in f


def test_category_count_matches_default_categories():
    """Константы листа «По месяцам» не должны разъезжаться со списком категорий.

    Регрессия 04.10.2026: в formulas.py стояло MONTHLY_CATEGORY_COLUMNS = 14
    при 15 категориях в DEFAULT_CATEGORIES — последняя («Прочее») не попадала
    в месячные итоги. Теперь обе константы считаются из списка.
    """
    from categories import DEFAULT_CATEGORIES

    import formulas

    assert formulas.CATEGORY_COUNT == len(DEFAULT_CATEGORIES)
    assert formulas.MONTHLY_CATEGORY_COLUMNS == len(DEFAULT_CATEGORIES)


def test_month_list_formula():
    f = month_list_formula(2)
    assert f.startswith("=IFERROR(INDEX(SORT(UNIQUE(FILTER(TEXT(")
    assert "YYYY-MM" in f
    assert ", 1), \"\")" in f


def test_month_total_formula():
    f = month_total_formula(2)
    assert f.startswith("=IF($A2=\"\",\"\",SUMIFS(")
    assert "EDATE" in f
    assert "LEFT($A2,4)" in f


def test_month_category_header_formula():
    f = month_category_header_formula(3)
    assert f.startswith("=IFERROR(INDEX(SORT(UNIQUE(FILTER(")
    assert "COLUMN()-2" in f


def test_month_category_sum_formula():
    f = month_category_sum_formula(2, 3)
    assert f.startswith("=IF(OR($A2=\"\",C$1=\"\"),\"\",SUMIFS(")
    assert "C$1" in f
