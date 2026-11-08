"""Синхронизация листа «Категории» Google-таблицы с DEFAULT_CATEGORIES.

Аддитивная операция: переименовывает legacy-категорию «Развлечения» в
«Развлечения / Отдых», дополняет синонимы из DEFAULT_CATEGORIES и добавляет
отсутствующие категории. Пользовательские категории и синонимы сохраняются.
Запуск: python sync_categories.py (нужны GOOGLE_SHEET_ID и credentials).
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from categories import DEFAULT_CATEGORIES
from sheets import get_gc

load_dotenv()

RENAME_MAP = {"Развлечения": "Развлечения / Отдых"}


def merge_categories(current: dict[str, list[str]]) -> dict[str, list[str]]:
    """Возвращает обновлённый словарь категорий без потери пользовательских.

    Правила:
    - категории из DEFAULT_CATEGORIES дополняются недостающими синонимами;
    - legacy-имя «Развлечения» переименовывается в «Развлечения / Отдых»,
      его синонимы переносятся (если целевая категория уже есть — сливаются);
    - категории, которых нет в DEFAULT_CATEGORIES, сохраняются как есть.
    """
    result: dict[str, list[str]] = {}
    legacy_syns = list(current.get("Развлечения", [])) if "Развлечения" in RENAME_MAP else []

    for cat, syns in current.items():
        if cat == "Развлечения" and cat in RENAME_MAP:
            continue
        result[cat] = list(syns)

    for cat, default_syns in DEFAULT_CATEGORIES.items():
        merged = list(result.get(cat, []))
        if cat == RENAME_MAP.get("Развлечения"):
            merged = merged + [s for s in legacy_syns if s not in merged]
        result[cat] = merged + [s for s in default_syns if s not in merged]

    return result


def _diff(current: dict[str, list[str]], merged: dict[str, list[str]]) -> list[str]:
    """Человекочитаемый список изменений для вывода в консоль."""
    changes: list[str] = []
    for cat, syns in merged.items():
        if cat not in current:
            changes.append(f"+ категория «{cat}»")
            continue
        added = [s for s in syns if s not in current[cat]]
        if added:
            changes.append(f"«{cat}»: +{len(added)} синонимов")
    for cat in current:
        if cat not in merged and cat in RENAME_MAP:
            changes.append(f"«{cat}» -> «{RENAME_MAP[cat]}»")
    return changes


def main() -> None:
    """Обновляет лист «Категории» таблицы GOOGLE_SHEET_ID."""
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise SystemExit("GOOGLE_SHEET_ID не задан")
    ws = get_gc().open_by_key(sheet_id).worksheet("Категории")
    rows = ws.get_all_values()

    current: dict[str, list[str]] = {}
    for row in rows[1:]:
        if len(row) >= 1 and row[0].strip():
            syns = [s.strip() for s in row[1].split(",") if s.strip()] if len(row) > 1 else []
            current[row[0].strip()] = syns

    merged = merge_categories(current)
    changes = _diff(current, merged)
    if not changes:
        print("Категории уже актуальны, изменений нет.")
        return

    values = [["Категория", "Синонимы"]]
    values += [[cat, ", ".join(syns)] for cat, syns in merged.items()]
    ws.update(values, range_name=f"A1:B{len(values)}")

    print(f"Обновлено {len(values) - 1} категорий:")
    for change in changes:
        print(f"  {change}")


if __name__ == "__main__":
    main()
