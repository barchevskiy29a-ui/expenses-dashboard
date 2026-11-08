from parser import ParsedEntry, parse_amount, parse_entry


def test_amount_with_ruble_suffix():
    assert parse_amount("моющие средства 2350р") == 2350.0


def test_amount_with_rub_word():
    assert parse_amount("продукты 850 руб") == 850.0


def test_amount_with_thousands_k():
    assert parse_amount("кафе 1.5к") == 1500.0


def test_amount_with_symbol():
    assert parse_amount("такси 300 ₽") == 300.0


def test_amount_last_number_when_no_suffix():
    assert parse_amount("такси до аэропорта 1200") == 1200.0


def test_amount_ignores_numbers_in_words():
    assert parse_amount("купил 2 бутылки масла 500") == 500.0


def test_amount_missing():
    assert parse_amount("продукты") is None


def test_amount_comma_decimal():
    assert parse_amount("продукты 335,50р") == 335.5


def test_amount_comma_thousands():
    assert parse_amount("транспорт 1,246р") == 1246.0


def test_amount_both_separators_comma_first():
    assert parse_amount("продукты 1,246.00р") == 1246.0


def test_amount_both_separators_dot_first():
    assert parse_amount("продукты 1.246,50р") == 1246.5


def test_amount_comma_thousands_no_suffix():
    assert parse_amount("обед 1,246") == 1246.0


def test_amount_dot_is_decimal():
    assert parse_amount("такси 1.246") == 1.246


def test_amount_ruble_symbol_not_at_end():
    assert parse_amount("поездка 300 ₽ и чаевые 200") == 300.0


def test_parse_entry_known_category():
    e = parse_entry("моющие средства 2350р")
    assert e == ParsedEntry(amount=2350.0, subcategory="моющие средства",
                            category="Дом и быт", matched_synonym="моющие средства")


def test_parse_entry_unknown_category():
    e = parse_entry("новая штука для кота 100")
    assert e.amount == 100.0
    assert e.category is None


def test_parse_entry_no_amount():
    e = parse_entry("покупка без суммы")
    assert e.amount is None


def test_parse_entry_ruble_symbol_stripped():
    e = parse_entry("такси 300 ₽")
    assert e.amount == 300.0
    assert e.subcategory == "такси"


def test_parse_entry_amount_at_start():
    e = parse_entry("2070 р обед с семьей")
    assert e.amount == 2070.0
    assert e.category == "Кафе и рестораны"
    assert e.subcategory == "обед с семьей"


def test_parse_entry_amount_at_end():
    e = parse_entry("обед с семьей 335р")
    assert e.amount == 335.0
    assert e.category == "Кафе и рестораны"
    assert e.subcategory == "обед с семьей"


def test_parse_entry_amount_in_middle():
    e = parse_entry("обед в кафе 500 р с коллегами")
    assert e.amount == 500.0
    assert e.category == "Кафе и рестораны"


def test_parse_entry_cafe_restaurant():
    e = parse_entry("кафе 1.5к")
    assert e.amount == 1500.0
    assert e.category == "Кафе и рестораны"
    assert e.matched_synonym == "кафе"


def test_parse_entry_exact_category_name_empty_subcategory():
    e = parse_entry("кафе и рестораны 810")
    assert e.amount == 810.0
    assert e.category == "Кафе и рестораны"
    assert e.subcategory == ""


def test_parse_entry_category_name_case_insensitive():
    e = parse_entry("ДОМ И БЫТ 200р")
    assert e.amount == 200.0
    assert e.category == "Дом и быт"
    assert e.subcategory == ""


def test_parse_entry_category_name_keeps_other_subcategory():
    e = parse_entry("дом и быт порошок 200р")
    assert e.category == "Дом и быт"
    assert e.subcategory == "дом и быт порошок"


def test_parse_entry_sport_and_beauty():
    """Новая категория «Спорт и красота» распознаётся по синонимам и имени."""
    e = parse_entry("спортзал 1500")
    assert e.amount == 1500.0
    assert e.category == "Спорт и красота"
    assert e.matched_synonym == "спорт"
    e = parse_entry("маникюр 2500р")
    assert e.amount == 2500.0
    assert e.category == "Спорт и красота"
    e = parse_entry("Спорт и красота 3000")
    assert e.amount == 3000.0
    assert e.category == "Спорт и красота"
    assert e.subcategory == ""


def test_parse_entry_deduction_minus_spaced():
    e = parse_entry("аптека - 1240")
    assert e.amount == 1240.0
    assert e.category == "Здоровье"
    assert e.subcategory == "аптека"
    assert e.is_deduction is True


def test_parse_entry_deduction_minus_attached():
    e = parse_entry("аптека -1240")
    assert e.amount == 1240.0
    assert e.category == "Здоровье"
    assert e.is_deduction is True


def test_parse_entry_deduction_unicode_minus():
    e = parse_entry("аптека −1240")
    assert e.amount == 1240.0
    assert e.category == "Здоровье"
    assert e.is_deduction is True


def test_parse_entry_deduction_word_minus():
    e = parse_entry("аптека минус 1240")
    assert e.amount == 1240.0
    assert e.category == "Здоровье"
    assert e.subcategory == "аптека"
    assert e.is_deduction is True


def test_parse_entry_deduction_word_vychit():
    e = parse_entry("аптека вычет 1240")
    assert e.amount == 1240.0
    assert e.category == "Здоровье"
    assert e.subcategory == "аптека"
    assert e.is_deduction is True


def test_parse_entry_deduction_with_currency_suffix():
    e = parse_entry("аптека -1240р")
    assert e.amount == 1240.0
    assert e.category == "Здоровье"
    assert e.subcategory == "аптека"
    assert e.is_deduction is True


def test_parse_entry_normal_expense_is_not_deduction():
    e = parse_entry("аптека 1240")
    assert e.amount == 1240.0
    assert e.category == "Здоровье"
    assert e.is_deduction is False


def test_parse_entry_debt_repayment_is_not_deduction():
    """«возврат долга» — трата, а не вычет: без минуса не угадываем."""
    e = parse_entry("возврат долга 5000")
    assert e.amount == 5000.0
    assert e.is_deduction is False


def test_parse_amount_stays_positive_for_deduction_text():
    """parse_amount не меняет контракт: знак вычета ставит бот."""
    assert parse_amount("аптека - 1240") == 1240.0
