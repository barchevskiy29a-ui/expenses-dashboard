"""Словарь категорий расходов и сопоставление по синонимам."""

from __future__ import annotations

import re

DEFAULT_CATEGORIES: dict[str, list[str]] = {
    "Продукты": ["продукты", "еда", "супермаркет", "магазин", "рынок", "молоко",
                 "хлеб", "мясо", "овощи", "фрукты", "сладости",
                 "пятёрочка", "магнит", "лента", "вкусвилл", "дикси", "ашан",
                 "перекрёсток", "food", "milk", "bread", "supermarket"],
    "Дом и быт": ["моющие средства", "бытовая химия", "порошок", "мебель", "посуда",
                  "ремонт", "инструменты", "техника", "декор", "дом",
                  "furniture", "home"],
    "Транспорт": ["такси", "метро", "проезд", "бензин", "заправка", "парковка",
                  "автосервис", "шины", "транспорт", "taxi", "metro", "gasoline"],
    "Здоровье": ["аптека", "лекарства", "врач", "клиника", "анализы", "стоматолог",
                 "витамины", "массаж", "apteka", "doctor", "clinic", "vitamins"],
    "Одежда": ["одежда", "обувь", "куртка", "джинсы", "кроссовки", "бельё",
               "clothes", "shoes", "jeans"],
    "Ребёнок": ["ребёнок", "ребенок", "дети", "детские товары", "детские", "подгузники",
                "памперсы", "детское питание", "смесь", "игрушки", "детсад",
                "садик", "школа", "детская одежда", "коляска", "развивашки",
                "baby", "kids"],
    "Развлечения / Отдых": ["кино", "концерт", "игры", "хобби", "подписки",
                            "отдых", "отпуск", "путешествия", "поездка",
                            "туризм", "санаторий", "развлечения",
                            "cinema", "games", "movies", "hobby"],
    "Кафе и рестораны": ["кафе", "ресторан", "бар", "кофейня", "кофе", "обед",
                         "ужин", "завтрак", "столовая", "фастфуд", "пицца",
                         "бургер", "шаурма", "суши", "доставка еды", "ленч", "ланч",
                         "cafe", "restaurant", "bar", "coffee", "pizza",
                         "sushi", "burger", "fastfood"],
    "Связь и интернет": ["связь", "телефон", "интернет", "тариф",
                         "internet", "phone", "tariff"],
    "Коммунальные платежи": ["коммуналка", "жкх", "квартплата", "электричество",
                             "свет", "вода", "газ", "отопление",
                             "electricity", "water", "gas", "heating"],
    "Образование": ["курсы", "обучение", "книги", "учебник", "уроки",
                    "courses", "books", "lessons"],
    "Маркетплейсы": ["маркетплейс", "озон", "ozon", "вайлдберриз", "wildberries",
                     "wb", "вб", "алиэкспресс", "али", "aliexpress",
                     "яндекс маркет", "я.маркет", "мегамаркет", "yandex market"],
    "Переводы другим людям": ["перевод", "перевела", "перевел", "сбп", "на карту",
                              "отправила", "отправил", "в долг", "родным", "маме",
                              "папе", "другу", "transfer"],
    "Налоги": ["налог", "налоги", "налоговая", "усн", "патент",
               "пошлина", "страх.взносы", "tax", "taxes"],
    "Спорт и красота": ["спорт", "спортзал", "фитнес", "тренировка", "зал",
                        "бассейн", "йога", "пробежка", "велосипед",
                        "красота", "салон", "маникюр", "педикюр",
                        "парикмахерская", "стрижка", "косметика", "спа",
                        "sport", "fitness", "gym", "beauty"],
    "Прочее": ["другое"],
}


def normalize(text: str) -> str:
    """Нижний регистр, схлопывание пробелов, ё -> е."""
    return " ".join(text.lower().replace("ё", "е").split())


_WORD_RE = re.compile(r"[а-яёa-z]+")
_FUZZY_MIN_LEN = 4  # минимальная длина слова для нечёткого сопоставления


def _levenshtein(a: str, b: str) -> int:
    """Расстояние Левенштейна между строками."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _typo_limit(word_len: int) -> int:
    """Допустимое число опечаток для слова заданной длины."""
    return 1 if word_len <= 6 else 2


def _build_candidates(categories: dict[str, list[str]]) -> list[tuple[str, str, str]]:
    """Строит нормализованный список кандидатов (кэшируемый)."""
    candidates: list[tuple[str, str, str]] = []
    for category, synonyms in categories.items():
        for syn in synonyms:
            if syn:
                candidates.append((normalize(syn), category, syn))
    for category in categories:
        candidates.append((normalize(category), category, category))
    return candidates


def _fuzzy_match(
    text: str, categories: dict[str, list[str]]
) -> tuple[str, str] | None:
    """Нечёткий поиск: недописанное слово (префикс) или опечатка (Левенштейн)."""
    words = [w for w in _WORD_RE.findall(text) if len(w) >= _FUZZY_MIN_LEN]
    if not words:
        return None
    candidates = _build_candidates(categories)
    for word in words:
        for syn_norm, category, matched in candidates:
            if len(syn_norm) >= _FUZZY_MIN_LEN and syn_norm.startswith(word):
                return category, matched
    for word in words:
        limit = _typo_limit(len(word))
        for syn_norm, category, matched in candidates:
            if len(syn_norm) >= _FUZZY_MIN_LEN and _levenshtein(word, syn_norm) <= limit:
                return category, matched
    return None


def find_category(
    text: str,
    categories: dict[str, list[str]] | None = None,
) -> tuple[str, str] | None:
    """Возвращает (категория, найденный синоним) или None."""
    cats = categories if categories is not None else DEFAULT_CATEGORIES
    normalized = normalize(text)
    for category, synonyms in cats.items():
        for syn in synonyms:
            if syn and normalize(syn) in normalized:
                return category, syn
    for category in cats:
        if category and normalize(category) in normalized:
            return category, category
    return _fuzzy_match(normalized, cats)


def canonical_category(
    name: str,
    categories: dict[str, list[str]] | None = None,
) -> str | None:
    """Каноническое имя категории без учёта регистра; None, если нет совпадения."""
    cats = categories if categories is not None else DEFAULT_CATEGORIES
    norm = normalize(name)
    for category in cats:
        if normalize(category) == norm:
            return category
    hit = _fuzzy_match(norm, cats)
    if hit:
        return hit[0]
    return None


def add_synonym(
    categories: dict[str, list[str]], category: str, synonym: str
) -> bool:
    """Добавляет синоним в категорию; False, если уже есть."""
    norm = normalize(synonym)
    existing = categories.setdefault(category, [])
    if any(normalize(s) == norm for s in existing):
        return False
    existing.append(synonym.strip())
    return True
