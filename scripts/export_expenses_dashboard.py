"""Экспорт таблицы расходов в JSON для мобильного статического сайта."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from dateutil import tz
from dotenv import load_dotenv

from parser import parse_number
from sheets import _parse_cell_date, get_gc
from categories import normalize

load_dotenv()
_MOSCOW = tz.gettz("Europe/Moscow")


def _calendar_months(first: str, last: str) -> int:
    """Число календарных месяцев от first до last включительно (YYYY-MM)."""
    y1, m1 = int(first[:4]), int(first[5:7])
    y2, m2 = int(last[:4]), int(last[5:7])
    return (y2 - y1) * 12 + (m2 - m1) + 1


def _canonical_exact(name: str, categories: dict[str, list[str]]) -> str | None:
    """Только точное совпадение (регистр/ё/пробелы): без нечёткого матчинга.

    Нечёткий матчинг живёт на уровне парсинга бота, а не экспорта истории:
    иначе «Такси работа» молча склеилась бы с «Транспорт», а «Кофе с собой»
    — с «Кафе и рестораны», и отдельный сектор кастомной категории исчез бы.
    """
    from categories import DEFAULT_CATEGORIES

    cats = categories if categories is not None else DEFAULT_CATEGORIES
    norm = normalize(name)
    for category in cats:
        if normalize(category) == norm:
            return category
    return None


def build_dashboard_output(transactions: list[dict], now: dt.datetime) -> dict:
    """Строит data.json из нормализованных транзакций (чистая функция).

    Входной список не мутируется. Будущие даты (позже текущего месяца)
    отбрасываются: иначе они раздували бы total, не попадая в спан.
    Среднее считается за календарные месяцы истории, а не за месяцы
    с данными.
    """
    month_key = now.strftime("%Y-%m")
    clean: list[dict] = []
    for item in transactions:
        if item["date"][:7] > month_key:
            continue
        row = dict(item)
        canonical = _canonical_exact(row["category"] or "Прочее", None)
        row["category"] = canonical or row["category"] or "Прочее"
        clean.append(row)

    category_totals: dict[str, float] = {}
    month_totals: dict[str, float] = {}
    for item in clean:
        category = item["category"] or "Прочее"
        category_totals[category] = category_totals.get(category, 0.0) + item["amount"]
        key = item["date"][:7]
        month_totals[key] = month_totals.get(key, 0.0) + item["amount"]

    total = sum(category_totals.values())
    current_total = sum(item["amount"] for item in clean if item["date"].startswith(month_key))
    first_month = min(month_totals) if month_totals else month_key
    months_span = _calendar_months(first_month, month_key)
    return {
        "updated_at": now.strftime("%Y-%m-%d %H:%M МСК"),
        "updated_at_iso": now.isoformat(),
        "summary": {
            "month_total": current_total,
            "month_label": month_key,
            "total": total,
            "average_month": total / months_span if months_span else 0.0,
            "months_span": months_span,
            "count": len(clean),
        },
        "categories": [
            {"category": key, "total": value}
            for key, value in sorted(category_totals.items(), key=lambda item: -item[1])
        ],
        "months": [
            {"month": key, "total": value}
            for key, value in sorted(month_totals.items())
        ],
        "transactions": sorted(clean, key=lambda item: item["date"], reverse=True),
    }


def main() -> None:
    """Читает лист «Транзакции» и сохраняет mobile-expenses/data.json."""
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise SystemExit("GOOGLE_SHEET_ID не задан")

    workbook = get_gc().open_by_key(sheet_id)
    rows = workbook.worksheet("Транзакции").get_all_values(
        value_render_option="UNFORMATTED_VALUE"
    )[1:]
    now = dt.datetime.now(_MOSCOW)
    transactions: list[dict] = []

    for row in rows:
        if len(row) < 4:
            continue
        date_value = _parse_cell_date(str(row[0]))
        amount = parse_number(row[3])
        if date_value is None or amount is None:
            continue
        transactions.append({
            "date": date_value.isoformat(),
            "category": str(row[1]).strip(),
            "subcategory": str(row[2]).strip() if len(row) > 2 else "",
            "comment": str(row[4]).strip() if len(row) > 4 else "",
            "amount": amount,
        })

    output = build_dashboard_output(transactions, now)
    target = Path(__file__).parents[1] / "mobile-expenses" / "data.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
