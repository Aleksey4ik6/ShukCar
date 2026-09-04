# ShukCar/ui/address_search_dialog.py
from __future__ import annotations

from typing import Optional, Dict, Any, List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QPushButton, QLabel, QMessageBox
)
from services.dadata_client import DaDataClient


class AddressSearchDialog(QDialog):
    """
    Модальный диалог поиска адреса (по кнопке "Найти").
    Если подсказок нет — показываем понятную причину (нет токена/requests/HTTP ошибка/сеть).
    """
    def __init__(self, parent=None, initial_query: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Поиск адреса")
        self.resize(700, 420)

        self._ed_query = QLineEdit(self)
        self._ed_query.setPlaceholderText("Введите адрес (например: Москва, Тверская 1)")
        if initial_query:
            self._ed_query.setText(initial_query)

        self._btn_find = QPushButton("Найти", self)
        self._btn_choose = QPushButton("Выбрать", self)
        self._btn_cancel = QPushButton("Отмена", self)
        self._status = QLabel("", self)
        self._status.setObjectName("SearchStatus")
        self._btn_cancel.setProperty("accent", "secondary")
        self._btn_choose.setProperty("accent", "secondary")

        self._list = QListWidget(self)
        self._list.setAlternatingRowColors(True)

        top = QVBoxLayout(self)
        hl = QHBoxLayout()
        hl.addWidget(self._ed_query)
        hl.addWidget(self._btn_find)
        top.addLayout(hl)
        top.addWidget(self._list)
        hl2 = QHBoxLayout()
        hl2.addWidget(self._status)
        hl2.addStretch(1)
        hl2.addWidget(self._btn_cancel)
        hl2.addWidget(self._btn_choose)
        top.addLayout(hl2)

        self._client = DaDataClient()
        self._value_map: Dict[str, Dict[str, Any]] = {}
        self._selected: Optional[Dict[str, Any]] = None

        # Сигналы
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_choose.clicked.connect(self._accept_current)
        self._btn_find.clicked.connect(self._do_search)
        self._list.itemDoubleClicked.connect(lambda _i: self._accept_current())

    def result_address(self) -> Optional[Dict[str, Any]]:
        return self._selected

    def _do_search(self):
        query = (self._ed_query.text() or "").strip()
        if not query:
            QMessageBox.information(self, "Поиск адреса", "Введите строку запроса.")
            return

        self._status.setText("Поиск…")
        self._list.clear()
        self._value_map.clear()

        suggestions: List[Dict[str, Any]] = self._client.suggest(query, count=15)
        if not suggestions:
            # Если пусто — покажем причину, если она известна
            if self._client.last_error:
                self._status.setText(f"Ошибка: {self._client.last_error}")
                QMessageBox.warning(self, "Подсказки адреса", self._client.last_error)
            else:
                self._status.setText("Ничего не найдено.")
            return

        for s in suggestions:
            title = s.get("value") or s.get("source") or ""
            if not title:
                continue
            self._value_map[title] = s
            self._list.addItem(title)

        self._status.setText(f"Найдено: {len(suggestions)}")

    def _accept_current(self):
        it = self._list.currentItem()
        if not it:
            # Ничего не выбрано — используем как свободный ввод
            src = (self._ed_query.text() or "").strip() or None
            self._selected = {"source": src}
            self.accept()
            return
        title = it.text()
        self._selected = self._value_map.get(title) or {"source": title}
        self.accept()
