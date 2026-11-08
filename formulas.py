"""Генерация Google Sheets формул агрегации расходов (лист «Транзакции»)."""

from __future__ import annotations

from categories import DEFAULT_CATEGORIES

TRANSACTIONS_SHEET = "Транзакции"
TRANSACTIONS_HEADERS = ["Дата", "Категория", "Подкатегория", "Сумма",
                        "Комментарий", "ID"]

# Единственный источник правды — DEFAULT_CATEGORIES. Раньше здесь стояло
# число 14 при фактических 15 категориях: лист «По месяцам» получал колонки
# C:P, и последняя категория («Прочее») в месячные итоги не попадала.
CATEGORY_COUNT = len(DEFAULT_CATEGORIES)
MONTHLY_CATEGORY_COLUMNS = len(DEFAULT_CATEGORIES)


def category_list_formula(row: int = 2) -> str:
    """Категория для строки row листа «По категориям» (ячейка A2, A3, ...).

    Скалярная формула (без расширения массива вниз): INDEX берёт одну
    категорию из отсортированного уникального списка. IFERROR — пусто,
    если категорий меньше, чем строк.
    """
    return (
        f"=IFERROR(INDEX(SORT(UNIQUE(FILTER('{TRANSACTIONS_SHEET}'!$B$2:$B, "
        f"'{TRANSACTIONS_SHEET}'!$B$2:$B<>\"\"))), {row - 1}), \"\")"
    )


def month_list_formula(row: int = 2) -> str:
    """Месяц (YYYY-MM) для строки row листа «По месяцам» (ячейка A2, A3, ...)."""
    return (
        f"=IFERROR(INDEX(SORT(UNIQUE(FILTER(TEXT('{TRANSACTIONS_SHEET}'!$A$2:$A,"
        f"\"YYYY-MM\"), '{TRANSACTIONS_SHEET}'!$A$2:$A<>\"\"))), {row - 1}), \"\")"
    )


def month_total_formula(row: int = 2) -> str:
    """Итоговая сумма месяца строки row (ячейка B2, B3, ... листа «По месяцам»)."""
    return (
        f"=IF($A{row}=\"\",\"\",SUMIFS('{TRANSACTIONS_SHEET}'!$D$2:$D, "
        f"'{TRANSACTIONS_SHEET}'!$A$2:$A, \">=\"&DATE(LEFT($A{row},4),"
        f"RIGHT($A{row},2),1), '{TRANSACTIONS_SHEET}'!$A$2:$A, "
        f'"<"&EDATE(DATE(LEFT($A{row},4),RIGHT($A{row},2),1),1)))'
    )


def month_category_header_formula(col: int) -> str:
    """Категория в шапке (ячейка C1, D1, ... листа «По месяцам»)."""
    return (
        f"=IFERROR(INDEX(SORT(UNIQUE(FILTER('{TRANSACTIONS_SHEET}'!$B$2:$B, "
        f"'{TRANSACTIONS_SHEET}'!$B$2:$B<>\"\"))), COLUMN()-2), \"\")"
    )


def month_category_sum_formula(row: int, col: int) -> str:
    """Сумма месяца row по категории из шапки колонки col (C2, D2, ...)."""
    col_letter = chr(64 + col)
    return (
        f'=IF(OR($A{row}="",{col_letter}$1=""),"",'
        f"SUMIFS('{TRANSACTIONS_SHEET}'!$D$2:$D, "
        f"'{TRANSACTIONS_SHEET}'!$B$2:$B, {col_letter}$1, "
        f"'{TRANSACTIONS_SHEET}'!$A$2:$A, \">=\"&DATE(LEFT($A{row},4),"
        f"RIGHT($A{row},2),1), '{TRANSACTIONS_SHEET}'!$A$2:$A, "
        f'"<"&EDATE(DATE(LEFT($A{row},4),RIGHT($A{row},2),1),1)))'
    )


def current_month_sum_formula(category_cell: str = "A2") -> str:
    """Сумма по категории за текущий месяц."""
    return (
        f"=SUMIFS('{TRANSACTIONS_SHEET}'!$D$2:$D, "
        f"'{TRANSACTIONS_SHEET}'!$B$2:$B, {category_cell}, "
        f"'{TRANSACTIONS_SHEET}'!$A$2:$A, \">=\"&DATE(YEAR(TODAY()),MONTH(TODAY()),1), "
        f"'{TRANSACTIONS_SHEET}'!$A$2:$A, "
        '"<"&EDATE(DATE(YEAR(TODAY()),MONTH(TODAY()),1),1))'
    )


def total_sum_formula(category_cell: str = "A2") -> str:
    """Сумма по категории за всё время."""
    return (
        f"=SUMIFS('{TRANSACTIONS_SHEET}'!$D$2:$D, "
        f"'{TRANSACTIONS_SHEET}'!$B$2:$B, {category_cell})"
    )


def avg_month_formula(category_cell: str = "A2", total_cell: str = "C2") -> str:
    """Средняя сумма в месяц по категории (C{r} — итог строки)."""
    return (
        f"=IFERROR({total_cell}/COUNTUNIQUE(FILTER(TEXT('{TRANSACTIONS_SHEET}'"
        f"!$A$2:$A,\"YYYY-MM\"),'{TRANSACTIONS_SHEET}'!$A$2:$A<>\"\","
        f"'{TRANSACTIONS_SHEET}'!$B$2:$B={category_cell})),0)"
    )
