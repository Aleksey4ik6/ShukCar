# ShukCar/ui/rates_realtime_view.py
from PyQt6 import QtWidgets
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QSpinBox, QCheckBox, QComboBox, QMessageBox
)
from PyQt6.QtCore import QTimer, Qt
from decimal import Decimal
from typing import List, Dict

from rates_updater import fetch_cbr_rates, upsert_rates, RatesProviderError
from db import SessionLocal
from models import WatchedCurrency, ExchangeRate

DEFAULT_CODES: List[str] = ["USD", "EUR", "CNY", "KRW", "JPY"]

class RatesRealtimeView(QWidget):
    """
    Реальные курсы к RUB: список настраиваемый.
    По умолчанию: USD, EUR, CNY, KRW, JPY.
    Можно добавлять любые валюты, присутствующие у ЦБ.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        self._all_codes_from_cbr: List[str] = []   # справочник кодов ЦБ
        self._last_rates: Dict[str, Decimal] = {}  # свежие курсы {CODE: Decimal}
        self._watch_list: List[str] = []           # коды, которые показываем (из БД)

        v = QVBoxLayout(self)

        # Верхняя панель (без кнопок Назад/Домой)
        top = QHBoxLayout()
        self.btn_refresh = QPushButton("Обновить сейчас")
        self.btn_refresh.clicked.connect(self.refresh_now)
        top.addWidget(self.btn_refresh)

        self.chk_auto = QCheckBox("Авто-обновление")
        self.chk_auto.setChecked(True)
        self.chk_auto.stateChanged.connect(self._toggle_auto)
        top.addWidget(self.chk_auto)

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(10, 600)  # 10 сек — 10 мин
        self.spin_interval.setValue(60)
        self.spin_interval.setSuffix(" сек")
        self.spin_interval.valueChanged.connect(self._interval_changed)
        top.addWidget(self.spin_interval)

        top.addStretch(1)
        self.lbl_updated = QLabel("—")
        self.lbl_updated.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.lbl_updated)
        v.addLayout(top)

        # Панель управления списком наблюдения
        ctl = QHBoxLayout()
        ctl.addWidget(QLabel("Добавить валюту:"))
        self.cb_all_codes = QComboBox()
        ctl.addWidget(self.cb_all_codes)
        self.btn_add_code = QPushButton("Добавить")
        self.btn_add_code.setProperty("accent", "secondary")
        self.btn_add_code.clicked.connect(self.on_add_code)
        ctl.addWidget(self.btn_add_code)

        self.btn_remove_selected = QPushButton("Удалить выбранные")
        self.btn_remove_selected.setProperty("accent", "danger-secondary")
        self.btn_remove_selected.clicked.connect(self.on_remove_selected)
        ctl.addWidget(self.btn_remove_selected)
        ctl.addStretch(1)
        v.addLayout(ctl)

        # Таблица
        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels(["Валюта", "Курс к RUB"])
        self.tbl.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.tbl)

        # Таймер автообновления
        self.timer = QTimer(self)
        self.timer.setInterval(self.spin_interval.value() * 1000)
        self.timer.timeout.connect(self._refresh_silent)

        # Первичная инициализация
        self._load_watch_list()
        self._load_all_codes_from_db_or_default()
        self._fill_all_codes_combo()
        self._toggle_auto()
        self._refresh_silent()  # первая тихая загрузка

    # ===== DB helpers =====
    def _load_watch_list(self):
        with SessionLocal() as db:
            codes = [w.code.upper() for w in db.query(WatchedCurrency).order_by(WatchedCurrency.code).all()]
            if not codes:
                for c in DEFAULT_CODES:
                    db.add(WatchedCurrency(code=c))
                db.commit()
                codes = DEFAULT_CODES.copy()
        self._watch_list = codes

    def _save_watch_code(self, code: str):
        code = code.upper()
        with SessionLocal() as db:
            if not db.query(WatchedCurrency).filter(WatchedCurrency.code == code).first():
                db.add(WatchedCurrency(code=code))
                db.commit()
        if code not in self._watch_list:
            self._watch_list.append(code)

    def _remove_watch_codes(self, codes: List[str]):
        codes = [c.upper() for c in codes]
        with SessionLocal() as db:
            for c in codes:
                row = db.query(WatchedCurrency).filter(WatchedCurrency.code == c).first()
                if row:
                    db.delete(row)
            db.commit()
        self._watch_list = [c for c in self._watch_list if c not in codes]

    # ===== Справочник всех кодов =====
    def _load_all_codes_from_db_or_default(self):
        with SessionLocal() as db:
            rows = db.query(ExchangeRate).all()
            codes = sorted({r.code.upper() for r in rows if r.code})
        self._all_codes_from_cbr = codes if codes else ["RUB"] + DEFAULT_CODES

    def _fill_all_codes_combo(self):
        self.cb_all_codes.clear()
        for c in self._all_codes_from_cbr:
            if c == "RUB":
                continue
            if c not in self._watch_list:
                self.cb_all_codes.addItem(c)

    # ===== UI handlers =====
    def on_add_code(self):
        code = (self.cb_all_codes.currentText() or "").upper()
        if not code:
            return
        if code not in self._all_codes_from_cbr:
            QMessageBox.warning(self, "Нет в списке", f"Код {code} отсутствует в справочнике ЦБ.")
            return
        self._save_watch_code(code)
        self._fill_all_codes_combo()
        self._render_table(self._last_rates)

    def on_remove_selected(self):
        rows = self.tbl.selectionModel().selectedRows()
        if not rows:
            return
        codes = []
        for idx in rows:
            code = self.tbl.item(idx.row(), 0).text()
            codes.append(code)
        codes = [c for c in codes if c != "RUB"]
        if not codes:
            return
        self._remove_watch_codes(codes)
        self._fill_all_codes_combo()
        self._render_table(self._last_rates)

    # ===== Обновления =====
    def refresh_now(self):
        try:
            rates = fetch_cbr_rates()
            self._apply_rates(rates)
            QtWidgets.QMessageBox.information(self, "Готово", "Курсы обновлены.")
        except RatesProviderError as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка обновления", str(e))

    def _refresh_silent(self):
        try:
            rates = fetch_cbr_rates()
            self._apply_rates(rates)
        except RatesProviderError:
            pass

    def _apply_rates(self, rates: Dict[str, Decimal]):
        self._last_rates = rates
        with SessionLocal() as db:
            upsert_rates(db, rates)
        self._render_table(rates)
        from datetime import datetime
        self.lbl_updated.setText(f"Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
        self._all_codes_from_cbr = sorted(rates.keys())
        self._fill_all_codes_combo()

    def _render_table(self, rates: Dict[str, Decimal]):
        show_codes = ["RUB"] + [c for c in self._watch_list if c != "RUB"]
        self.tbl.setRowCount(0)
        for code in show_codes:
            row = self.tbl.rowCount()
            self.tbl.insertRow(row)
            self.tbl.setItem(row, 0, QTableWidgetItem(code))
            val = rates.get(code)
            self.tbl.setItem(row, 1, QTableWidgetItem(f"{val:.6f}" if val is not None else "—"))

    # ===== Таймер =====
    def _toggle_auto(self):
        if self.chk_auto.isChecked():
            self.timer.start()
        else:
            self.timer.stop()

    def _interval_changed(self):
        self.timer.setInterval(self.spin_interval.value() * 1000)
        if self.chk_auto.isChecked():
            self.timer.start()
