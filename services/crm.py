from __future__ import annotations

from typing import Iterable


PRIORITY_ITEMS = [
    ("low", "Низкий"),
    ("normal", "Обычный"),
    ("high", "Высокий"),
    ("urgent", "Срочный"),
]

LEAD_SOURCE_ITEMS = [
    "Instagram",
    "WhatsApp",
    "Telegram",
    "Avito",
    "Сайт",
    "Рекомендация",
    "Повторный клиент",
    "Звонок",
    "YouTube",
]

PRIORITY_ORDER = {
    "urgent": 0,
    "high": 1,
    "normal": 2,
    "low": 3,
    "": 4,
    None: 4,
}


def priority_label(code: str | None) -> str:
    for item_code, label in PRIORITY_ITEMS:
        if item_code == code:
            return label
    return "Не указан"


def priority_sort_key(code: str | None) -> int:
    return PRIORITY_ORDER.get(code, 99)


def fill_priority_combo(combo, current: str | None = None):
    combo.clear()
    combo.addItem("Не указан", "")
    for code, label in PRIORITY_ITEMS:
        combo.addItem(label, code)
    if current is not None:
        index = combo.findData(current)
        if index >= 0:
            combo.setCurrentIndex(index)


def fill_lead_source_combo(combo, current: str | None = None, items: Iterable[str] | None = None):
    combo.clear()
    combo.setEditable(True)
    combo.addItem("")
    for item in items or LEAD_SOURCE_ITEMS:
        combo.addItem(item)
    if current:
        combo.setEditText(current)
