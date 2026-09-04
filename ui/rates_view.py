# ShukCar/ui/rates_view.py
from PyQt6 import QtWidgets
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QLabel, QSpinBox, QCheckBox
)
from PyQt6.QtCore import QTimer, Qt
from decimal import Decimal
from typing import Callable, Dict, List

from db import SessionLocal
from models import ExchangeRate
from rates_updater import fetch_cbr_rates, upsert_rates, RatesProviderError

TARGET_CODES: List[str] = ["USD", "EUR", "CNY", "KRW", "JPY"]

class RatesView(QWidget):
    """
    Онлайн-курсы валют (USD, EUR, CNY, KRW, JPY) к RUB.
    Источник: ЦБ РФ (cbr-xml-daily).
    """
    def __init__(self, parent=None, on_back: Callable[[], None] | None = None):
        super().__init__(parent)
        self.on_back = on_back

        self.timer = QTimer(self)
        self.timer.setInterval(60 * 1000)  # авто-обновление раз в 1 минуту
        self.timer.timeout.connect(self._update_online_silent)

        v = QVBoxLayout(self)

        # Верхняя панель
        top = QHBoxLayout()
        btn_back = QPushButton("← Назад")
        if self.on_back:
            btn_back.clicked.connect(self.on_back)
        else:
            btn_back.setEnabled(False)
        top.addWidget(btn_back)

        self.btn_refresh_now = QPushButton("Обновить сейчас")
        self.btn_refresh_now.clicked.connect(self._update_online_now)
        top.addWidget(self.btn_refresh_now)

        self.chk_auto = QCheckBox("Авто-обновление")
        self.chk_auto.setChecked(True)
        self.chk_auto.stateChanged.connect(self._toggle_auto)
        top.addWidget(self.chk_auto)

        top.addWidget(QLabel("Интервал:"))
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 60)
        self.spin_interval.setValue(1)
        self.spin_interval.setSuffix(" мин")
        self.spin_interval.valueChanged.connect(self._interval_changed)
        top.addWidget(self.spin_interval)

        top.addStretch(1)

        self.lbl_updated = QLabel("—")
        self.lbl_updated.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.lbl_updated)

        v.addLayout(top)

        # Таблица: только нужные валюты
        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels(["Валюта", "Курс к RUB"])
        self.tbl.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.tbl)

        # Первичная загрузка (молча, с авто-таймером)
        self._toggle_auto()  # запустит таймер и тихое обновление
        self._fill_from_db() # показать что уже есть

    # ===== вспомогательные =====
    def _fill_from_db(self):
        self.tbl.setRowCount(0)
        with SessionLocal() as db:
            rows: Dict[str, ExchangeRate] = {
                r.code.upper(): r for r in db.query(ExchangeRate).all()
            }
        for code in TARGET_CODES:
            row = self.tbl.rowCount()
            self.tbl.insertRow(row)
            self.tbl.setItem(row, 0, QTableWidgetItem(code))
            if code in rows:
                r = rows[code]
                self.tbl.setItem(row, 1, QTableWidgetItem(f"{Decimal(str(r.rate_to_rub)):.6f}"))
            else:
                self.tbl.setItem(row, 1, QTableWidgetItem("—"))

        # обновим подпись "обновлено" по RUB (если есть)
        rub_updated = rows.get("RUB").updated_at if rows.get("RUB") else None
        any_updated = None
        if rows:
            # возьмём максимум по времени
            any_updated = max((r.updated_at for r in rows.values() if r.updated_at), default=None)
        stamp = rub_updated or any_updated
        self.lbl_updated.setText(f"Обновлено: {stamp.strftime('%d.%m.%Y %H:%M')}" if stamp else "Обновлено: —")

    def _interval_changed(self):
        self.timer.setInterval(self.spin_interval.value() * 60 * 1000)
        if self.chk_auto.isChecked():
            self.timer.start()

    def _toggle_auto(self):
        if self.chk_auto.isChecked():
            self.timer.start()
            self._update_online_silent()
        else:
            self.timer.stop()

    # ===== онлайн обновления =====
    def _update_online_now(self):
        try:
            rates = fetch_cbr_rates()  # все валюты
            # оставим только нужные + RUB
            filtered = {"RUB": rates.get("RUB", Decimal("1"))}
            for c in TARGET_CODES:
                if c in rates:
                    filtered[c] = rates[c]
            with SessionLocal() as db:
                upsert_rates(db, filtered)
            self._fill_from_db()
            QtWidgets.QMessageBox.information(self, "Готово", "Курсы обновлены.")
        except RatesProviderError as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка обновления", str(e))

    def _update_online_silent(self):
        try:
            rates = fetch_cbr_rates()
            filtered = {"RUB": rates.get("RUB", Decimal("1"))}
            for c in TARGET_CODES:
                if c in rates:
                    filtered[c] = rates[c]
            with SessionLocal() as db:
                upsert_rates(db, filtered)
            self._fill_from_db()
        except RatesProviderError:
            pass
