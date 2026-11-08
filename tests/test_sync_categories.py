# tests/test_sync_categories.py
from sync_categories import _diff, merge_categories


def test_adds_new_category_and_synonyms():
    current = {"Продукты": ["еда"]}
    merged = merge_categories(current)
    assert "Ребёнок" in merged
    assert "детсад" in merged["Ребёнок"]
    assert merged["Продукты"][:1] == ["еда"]
    assert set(merged["Продукты"]) == set(current["Продукты"] + __import__("categories").DEFAULT_CATEGORIES["Продукты"])


def test_adds_tax_category():
    merged = merge_categories({})
    assert "Налоги" in merged
    assert "налог" in merged["Налоги"]


def test_renames_razvlecheniya_and_keeps_synonyms():
    current = {"Развлечения": ["кино", "моё хобби"]}
    merged = merge_categories(current)
    assert "Развлечения" not in merged
    assert "Развлечения / Отдых" in merged
    assert "кино" in merged["Развлечения / Отдых"]
    assert "моё хобби" in merged["Развлечения / Отдых"]
    assert "отдых" in merged["Развлечения / Отдых"]


def test_merges_legacy_into_existing_target():
    current = {"Развлечения": ["кино"], "Развлечения / Отдых": ["концерт"]}
    merged = merge_categories(current)
    assert "Развлечения" not in merged
    syns = merged["Развлечения / Отдых"]
    assert "кино" in syns and "концерт" in syns
    assert len(syns) == len(set(syns))


def test_idempotent():
    first = merge_categories({"Продукты": ["еда"], "Развлечения": ["кино"]})
    second = merge_categories(first)
    assert first == second


def test_user_categories_untouched():
    current = {"Моя категория": ["слово"]}
    merged = merge_categories(current)
    assert merged["Моя категория"] == ["слово"]


def test_user_synonyms_preserved_and_not_duplicated():
    current = {"Продукты": ["еда", "молоко"]}
    merged = merge_categories(current)
    assert merged["Продукты"][:2] == ["еда", "молоко"]
    assert merged["Продукты"].count("молоко") == 1


def test_diff_reports_changes():
    current = {"Развлечения": ["кино"]}
    merged = merge_categories(current)
    changes = _diff(current, merged)
    assert any("Развлечения" in c and "Развлечения / Отдых" in c for c in changes)
    assert any("Ребёнок" in c for c in changes)


def test_diff_empty_when_no_changes():
    current = merge_categories({})
    assert _diff(current, current) == []
