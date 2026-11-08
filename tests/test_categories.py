# tests/test_categories.py
from categories import (DEFAULT_CATEGORIES, add_synonym, canonical_category,
                        find_category, normalize)


def test_normalize_lowercase_and_yo():
    assert normalize("  Моющие Средства ") == "моющие средства"
    assert normalize("бельё") == "белье"


def test_find_category_by_synonym():
    assert find_category("моющие средства 2350р") == ("Дом и быт", "моющие средства")


def test_find_category_case_insensitive():
    assert find_category("OZON заказ") == ("Маркетплейсы", "ozon")


def test_find_category_transfer():
    assert find_category("перевела маме") == ("Переводы другим людям", "перевела")


def test_find_category_yo_matching():
    assert find_category("белье") == ("Одежда", "бельё")


def test_find_category_unknown_returns_none():
    assert find_category("новая штука для кота") is None


def test_find_category_by_exact_category_name():
    assert find_category("дом и быт 200р") == ("Дом и быт", "дом")
    assert find_category("КОММУНАЛЬНЫЕ ПЛАТЕЖИ 5000") == ("Коммунальные платежи", "Коммунальные платежи")
    assert find_category("кафе и рестораны 810") == ("Кафе и рестораны", "кафе")


def test_canonical_category_case_insensitive():
    cats = {"Продукты": ["еда"], "Кафе и рестораны": ["кафе"]}
    assert canonical_category("ПРОДУКТЫ", cats) == "Продукты"
    assert canonical_category("продукты", cats) == "Продукты"
    assert canonical_category("Кафе И Рестораны", cats) == "Кафе и рестораны"


def test_canonical_category_no_match():
    assert canonical_category("Новой нет", {"Продукты": ["еда"]}) is None
    assert canonical_category("Продукты", {}) is None


def test_add_synonym_and_dedupe():
    cats = {"Продукты": ["еда"]}
    assert add_synonym(cats, "Продукты", "молоко") is True
    assert add_synonym(cats, "Продукты", "молоко") is False
    assert add_synonym(cats, "Новая", "слово") is True
    assert cats["Новая"] == ["слово"]


def test_default_categories_has_16():
    assert len(DEFAULT_CATEGORIES) == 16
    assert "Маркетплейсы" in DEFAULT_CATEGORIES
    assert "Переводы другим людям" in DEFAULT_CATEGORIES
    assert "Ребёнок" in DEFAULT_CATEGORIES
    assert "Развлечения / Отдых" in DEFAULT_CATEGORIES
    assert "Налоги" in DEFAULT_CATEGORIES


def test_cafe_restaurant_category():
    assert find_category("обед с семьей") == ("Кафе и рестораны", "обед")
    assert find_category("кафе с коллегами") == ("Кафе и рестораны", "кафе")
    assert find_category("ужин в ресторане") == ("Кафе и рестораны", "ресторан")
    assert find_category("пицца на дом") == ("Дом и быт", "дом")


def test_cafe_not_in_fun_anymore():
    assert "кафе" not in DEFAULT_CATEGORIES["Развлечения / Отдых"]
    assert "ресторан" not in DEFAULT_CATEGORIES["Развлечения / Отдых"]


def test_fuzzy_prefix_word_matches_synonym():
    assert find_category("прод 850") == ("Продукты", "продукты")
    assert find_category("аптек 300") == ("Здоровье", "аптека")


def test_fuzzy_prefix_matches_category_name():
    assert find_category("развлечен 500") == ("Развлечения / Отдых", "развлечения")


def test_fuzzy_prefix_of_multiword_synonym():
    assert find_category("доставк 600") == ("Кафе и рестораны", "доставка еды")


def test_fuzzy_typo_matches_synonym():
    assert find_category("кафа 300") == ("Кафе и рестораны", "кафе")
    assert find_category("продкты 300") == ("Продукты", "продукты")
    assert find_category("озонн заказ") == ("Маркетплейсы", "озон")


def test_fuzzy_short_word_ignored():
    assert find_category("про 100") is None


def test_fuzzy_no_false_positive_on_far_words():
    assert find_category("масло 100") is None
    assert find_category("новая штука для кота") is None


def test_canonical_category_fuzzy():
    cats = {"Продукты": ["еда"], "Развлечения": ["кино"]}
    assert canonical_category("продукт", cats) == "Продукты"
    assert canonical_category("развлечен", cats) == "Развлечения"
    assert canonical_category("кафа", cats) is None


def test_shop_names_synonyms():
    assert find_category("пятерочка 540") == ("Продукты", "пятёрочка")
    assert find_category("магнит 700") == ("Продукты", "магнит")
    assert find_category("лента 350") == ("Продукты", "лента")
    assert find_category("вкусвилл 800") == ("Продукты", "вкусвилл")
    assert find_category("дикси 420") == ("Продукты", "дикси")
    assert find_category("ашан 900") == ("Продукты", "ашан")
    assert find_category("перекресток 250") == ("Продукты", "перекрёсток")


def test_shop_names_typo_prefix():
    assert find_category("пятерочк 540") == ("Продукты", "пятёрочка")
    assert find_category("пятерочко 540") == ("Продукты", "пятёрочка")


def test_marketplaces_ru_en():
    assert find_category("озон 1200") == ("Маркетплейсы", "озон")
    assert find_category("ozon 1200") == ("Маркетплейсы", "ozon")
    assert find_category("wildberries 700") == ("Маркетплейсы", "wildberries")
    assert find_category("aliexpress 300") == ("Маркетплейсы", "aliexpress")
    assert find_category("yandex market 450") == ("Маркетплейсы", "yandex market")
    assert find_category("вб 900") == ("Маркетплейсы", "вб")


def test_transport_ru_en():
    assert find_category("taxi 300") == ("Транспорт", "taxi")
    assert find_category("metro 60") == ("Транспорт", "metro")


def test_cafe_ru_en():
    assert find_category("cafe 250") == ("Кафе и рестораны", "cafe")
    assert find_category("restaurant 1000") == ("Кафе и рестораны", "restaurant")
    assert find_category("pizza 400") == ("Кафе и рестораны", "pizza")
    assert find_category("sushi 800") == ("Кафе и рестораны", "sushi")
    assert find_category("coffee 150") == ("Кафе и рестораны", "coffee")


def test_health_ru_en():
    assert find_category("apteka 500") == ("Здоровье", "apteka")
    assert find_category("doctor 2000") == ("Здоровье", "doctor")


def test_communication_ru_en():
    assert find_category("internet 600") == ("Связь и интернет", "internet")
    assert find_category("phone 400") == ("Связь и интернет", "phone")


def test_utilities_ru_en():
    assert find_category("electricity 800") == ("Коммунальные платежи", "electricity")
    assert find_category("water 300") == ("Коммунальные платежи", "water")
    assert find_category("gas 200") == ("Коммунальные платежи", "gas")


def test_education_ru_en():
    assert find_category("courses 5000") == ("Образование", "courses")
    assert find_category("books 700") == ("Образование", "books")


def test_clothes_ru_en():
    assert find_category("clothes 3000") == ("Одежда", "clothes")
    assert find_category("shoes 2500") == ("Одежда", "shoes")


def test_fun_ru_en():
    assert find_category("cinema 500") == ("Развлечения / Отдых", "cinema")
    assert find_category("games 1000") == ("Развлечения / Отдых", "games")


def test_child_category():
    assert find_category("детсад 500") == ("Ребёнок", "детсад")
    assert find_category("подгузники 700") == ("Ребёнок", "подгузники")
    assert find_category("игрушки 300") == ("Ребёнок", "игрушки")
    assert find_category("школа 1000") == ("Ребёнок", "школа")
    assert find_category("baby 800") == ("Ребёнок", "baby")
    assert find_category("kids 400") == ("Ребёнок", "kids")


def test_fun_leisure_category():
    assert find_category("отдых 1000") == ("Развлечения / Отдых", "отдых")
    assert find_category("отпуск 2000") == ("Развлечения / Отдых", "отпуск")
    assert find_category("путешествия 3000") == ("Развлечения / Отдых", "путешествия")
    assert find_category("туризм 1500") == ("Развлечения / Отдых", "туризм")


def test_transfers_ru_en():
    assert find_category("transfer 1500") == ("Переводы другим людям", "transfer")


def test_food_ru_en():
    assert find_category("food 800") == ("Продукты", "food")
    assert find_category("milk 100") == ("Продукты", "milk")
    assert find_category("bread 50") == ("Продукты", "bread")


def test_home_synonym():
    assert find_category("дом 5000") == ("Дом и быт", "дом")
    assert find_category("дом 370") == ("Дом и быт", "дом")
    assert find_category("ДОМ 200") == ("Дом и быт", "дом")


def test_drugoe_synonym():
    assert find_category("другое") == ("Прочее", "другое")
    assert find_category("2520 другое") == ("Прочее", "другое")


def test_lanch_synonyms():
    assert find_category("ленч 810") == ("Кафе и рестораны", "ленч")
    assert find_category("810 ланч") == ("Кафе и рестораны", "ланч")
    assert find_category("ЛАНЧ 500") == ("Кафе и рестораны", "ланч")


def test_tax_category():
    assert find_category("налог 500") == ("Налоги", "налог")
    assert find_category("налоги 300") == ("Налоги", "налог")
    assert find_category("усн 1000") == ("Налоги", "усн")
    assert find_category("патент 200") == ("Налоги", "патент")
    assert find_category("налоговая 400") == ("Налоги", "налог")
    assert find_category("tax 200") == ("Налоги", "tax")
    assert find_category("taxes 150") == ("Налоги", "tax")
