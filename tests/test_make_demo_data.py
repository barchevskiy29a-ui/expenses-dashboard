"""Демо-данные обязаны использовать только категории из DEFAULT_CATEGORIES.

Категория — единственный источник истины для словаря. Если генератор или
готовый data.json содержит категорию вне словаря, агрегации по словарю
потеряют эти транзакции.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import make_demo_data  # noqa: E402
from categories import DEFAULT_CATEGORIES  # noqa: E402

DATA_JSON = ROOT / "mobile-expenses" / "data.json"


def test_generator_uses_only_default_categories():
    rows = make_demo_data.build_demo_transactions(
        end=dt.date(2026, 11, 8), months=6, seed=42
    )
    assert rows, "генератор не вернул транзакции"
    unknown = sorted(
        {r["category"] for r in rows if r["category"] not in DEFAULT_CATEGORIES}
    )
    assert not unknown, f"генератор использует категории вне словаря: {unknown}"


def test_committed_demo_data_uses_only_default_categories():
    data = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    unknown = sorted(
        {
            t["category"]
            for t in data["transactions"]
            if t["category"] not in DEFAULT_CATEGORIES
        }
    )
    assert not unknown, f"data.json содержит категории вне словаря: {unknown}"
