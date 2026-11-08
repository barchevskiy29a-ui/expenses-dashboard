"""Generate synthetic demo data for the expenses dashboard.

The file is deterministic for a given seed. It never uses real user data:
amounts are random, comments are empty, subcategories are empty.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from categories import DEFAULT_CATEGORIES  # noqa: E402

MOSCOW = dt.timezone(dt.timedelta(hours=3))


def _calendar_months(first: str, last: str) -> int:
    y1, m1 = int(first[:4]), int(first[5:7])
    y2, m2 = int(last[:4]), int(last[5:7])
    return (y2 - y1) * 12 + (m2 - m1) + 1


def build_demo_transactions(
    end: dt.date, months: int, seed: int
) -> list[dict]:
    rng = random.Random(seed)
    categories = list(DEFAULT_CATEGORIES)
    start = (end - dt.timedelta(days=months * 30)).replace(day=1)
    rows: list[dict] = []
    day = start
    while day <= end:
        # 0..5 ordinary transactions a day keeps the chart lively but not noisy.
        for _ in range(rng.randint(0, 5)):
            rows.append(
                {
                    "date": day.isoformat(),
                    "category": rng.choice(categories),
                    "subcategory": "",
                    "comment": "",
                    "amount": round(rng.uniform(120, 4200), 2),
                }
            )
        # A few recurring monthly expenses.
        if day.day == 1:
            rows.append(
                {
                    "date": day.isoformat(),
                    "category": "Дом и быт",
                    "subcategory": "",
                    "comment": "",
                    "amount": round(rng.uniform(25000, 45000), 2),
                }
            )
        if day.day == 5:
            rows.append(
                {
                    "date": day.isoformat(),
                    "category": "Связь и интернет",
                    "subcategory": "",
                    "comment": "",
                    "amount": round(rng.uniform(600, 1400), 2),
                }
            )
        day += dt.timedelta(days=1)
    return rows


def build_output(rows: list[dict], now: dt.datetime) -> dict:
    month_key = now.strftime("%Y-%m")
    clean = [row for row in rows if row["date"][:7] <= month_key]

    category_totals: dict[str, float] = {}
    month_totals: dict[str, float] = {}
    for row in clean:
        category_totals[row["category"]] = (
            category_totals.get(row["category"], 0.0) + row["amount"]
        )
        key = row["date"][:7]
        month_totals[key] = month_totals.get(key, 0.0) + row["amount"]

    total = sum(category_totals.values())
    current_total = sum(
        row["amount"] for row in clean if row["date"].startswith(month_key)
    )
    first_month = min(month_totals) if month_totals else month_key
    span = _calendar_months(first_month, month_key)
    return {
        "updated_at": now.strftime("%Y-%m-%d %H:%M МСК"),
        "updated_at_iso": now.isoformat(),
        "summary": {
            "month_total": current_total,
            "month_label": month_key,
            "total": total,
            "average_month": total / span if span else 0.0,
            "months_span": span,
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--end",
        type=dt.date.fromisoformat,
        default=dt.date.today(),
        help="Last day of the demo period (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "mobile-expenses" / "data.json",
    )
    args = parser.parse_args()

    now = dt.datetime.now(MOSCOW)
    rows = build_demo_transactions(args.end, args.months, args.seed)
    output = build_output(rows, now)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"wrote {args.out}: {len(rows)} transactions, "
        f"{output['summary']['months_span']} months"
    )


if __name__ == "__main__":
    main()
