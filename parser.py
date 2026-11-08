"""Парсер свободного текста расходов: «моющие средства 2350р»."""

from __future__ import annotations

import re
from dataclasses import dataclass

from categories import find_category, normalize

_AMOUNT_RE = re.compile(
    r"(\d+(?:[.,]\d+)*)\s*(р|руб|₽|к)(?=\s|$|[^\w])", re.IGNORECASE
)
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_DEDUCTION_WORD_RE = re.compile(r"\b(минус|вычет)\b", re.IGNORECASE)
_DASHES = str.maketrans({"−": "-", "–": "-", "—": "-"})


def parse_number(raw) -> float | None:
    """Число из строки с точкой/запятой как разделителями.

    «335,50» → 335.5 (запятая — десятичный разделитель),
    «1,246» → 1246.0 (запятая — разделитель тысяч),
    «1,246.00» / «1.246,50» → 1246.0 (оба разделителя).
    """
    t = str(raw).strip().replace("\u00a0", "").replace(" ", "")
    if not t:
        return None
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        int_part, _, frac = t.partition(",")
        if int_part and len(frac) == 3:
            t = t.replace(",", "")
        else:
            t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _amount_match(text: str) -> tuple[float, int, int] | None:
    """Возвращает (сумма, начало, конец) выбранного числа в исходном тексте."""
    m = _AMOUNT_RE.search(text)
    if m:
        value = parse_number(m.group(1))
        if value is None:
            return None
        if m.group(2).lower() == "к":
            value *= 1000
        return value, m.start(), m.end()
    nums = list(_NUMBER_RE.finditer(text))
    if not nums:
        return None
    last = nums[-1]
    value = parse_number(last.group(0))
    if value is None:
        return None
    return value, last.start(), last.end()


def parse_amount(text: str) -> float | None:
    """Ищет сумму: приоритет — число с суффиксом (р/руб/₽/к), иначе последнее число."""
    hit = _amount_match(text)
    return hit[0] if hit else None


def _is_deduction(prefix: str) -> bool:
    """Явный минус или слово «минус»/«вычет» перед суммой."""
    normalized = prefix.translate(_DASHES)
    if re.search(r"(?:^|[\s(])-\s*$", normalized):
        return True
    return bool(_DEDUCTION_WORD_RE.search(normalized))


def _strip_deduction_words(text: str) -> str:
    return " ".join(_DEDUCTION_WORD_RE.sub(" ", text).split())


@dataclass
class ParsedEntry:
    amount: float | None
    subcategory: str
    category: str | None
    matched_synonym: str | None
    is_deduction: bool = False


def _strip_amount(text: str, hit: tuple[float, int, int] | None = None) -> str:
    """Убирает из текста найденную сумму (число с суффиксом или последнее число)."""
    hit = hit if hit is not None else _amount_match(text)
    if hit is None:
        return text.strip()
    _, start, end = hit
    return (text[:start] + text[end:]).strip()


def parse_entry(
    text: str, categories: dict[str, list[str]] | None = None
) -> ParsedEntry:
    """Разбирает сообщение на сумму, подкатегорию и широкую категорию."""
    amount_hit = _amount_match(text)
    amount = amount_hit[0] if amount_hit else None
    is_deduction = bool(amount_hit and _is_deduction(text[:amount_hit[1]]))
    subcategory = _strip_amount(text, amount_hit).strip(" ,-")
    if is_deduction:
        subcategory = _strip_deduction_words(subcategory).strip(" ,-")
    hit = find_category(subcategory, categories)
    category, syn = hit if hit else (None, None)
    if category and normalize(subcategory) == normalize(category):
        subcategory = ""
    return ParsedEntry(
        amount=amount,
        subcategory=subcategory,
        category=category,
        matched_synonym=syn,
        is_deduction=is_deduction,
    )
