# ShukCar/ui/clients_view.py
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QLabel, QFrame
)
from PyQt6.QtCore import Qt
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from datetime import date

from db import SessionLocal
from models import Client
from .clients_form import ClientForm
from services.crm import priority_label


class ClientsView(QWidget):
    """
    Стабильный список клиентов:
      - QTableWidget
      - Панель "Выбранный клиент": ФИО / Телефон / E-mail / Адрес
      - Кнопки: Добавить / Изменить / Удалить / Обновить
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        # Панель выбранного клиента
        self.lbl_name = QLabel("—")
        self.lbl_phone = QLabel("—")
        self.lbl_email = QLabel("—")
        self.lbl_manager = QLabel("—")
        self.lbl_source = QLabel("—")
        self.lbl_priority = QLabel("—")
        self.lbl_addr = QLabel("—")
        for l in (self.lbl_name, self.lbl_phone, self.lbl_email, self.lbl_manager, self.lbl_source, self.lbl_priority, self.lbl_addr):
            l.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        header = QHBoxLayout()
        head_box = QFrame(self)
        head_box.setFrameShape(QFrame.Shape.StyledPanel)
        head_box.setProperty("card", True)
        hb = QVBoxLayout(head_box)
        hb.setContentsMargins(8, 8, 8, 8)
        title = QLabel("Выбранный клиент:")
        title.setObjectName("SectionTitle")
        hb.addWidget(title)
        hb.addWidget(self._row("ФИО:", self.lbl_name))
        hb.addWidget(self._row("Телефон:", self.lbl_phone))
        hb.addWidget(self._row("E-mail:", self.lbl_email))
        hb.addWidget(self._row("Менеджер:", self.lbl_manager))
        hb.addWidget(self._row("Источник:", self.lbl_source))
        hb.addWidget(self._row("Приоритет:", self.lbl_priority))
        hb.addWidget(self._row("Адрес:", self.lbl_addr))
        header.addWidget(head_box)

        # Таблица
        self.table = QTableWidget(0, 8, self)
        self.table.setHorizontalHeaderLabels([
            "ID",
            "ФИО",
            "Телефон",
            "Источник",
            "Приоритет",
            "Менеджер",
            "E-mail",
            "Адрес регистрации",
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.currentCellChanged.connect(self._on_current_changed)

        # Кнопки
        btn_add = QPushButton("Добавить")
        btn_edit = QPushButton("Изменить")
        btn_del = QPushButton("Удалить")
        btn_refresh = QPushButton("Обновить")
        btn_edit.setProperty("accent", "secondary")
        btn_del.setProperty("accent", "danger-secondary")
        btn_refresh.setProperty("accent", "secondary")

        btns = QHBoxLayout()
        btns.addWidget(btn_add)
        btns.addWidget(btn_edit)
        btns.addWidget(btn_del)
        btns.addStretch(1)
        btns.addWidget(btn_refresh)

        root = QVBoxLayout(self)
        root.addLayout(header)
        root.addLayout(btns)
        root.addWidget(self.table)

        btn_add.clicked.connect(self.on_add)
        btn_edit.clicked.connect(self.on_edit)
        btn_del.clicked.connect(self.on_delete)
        btn_refresh.clicked.connect(self.load_clients)

        self.load_clients()

    # --- helpers ---
    def _row(self, title: str, value_label: QLabel) -> QWidget:
        w = QWidget(self)
        ly = QHBoxLayout(w)
        ly.setContentsMargins(0, 0, 0, 0)
        tit = QLabel(title)
        tit.setObjectName("InlineMutedLabel")
        ly.addWidget(tit)
        ly.addWidget(value_label, 1)
        return w

    # ----------------------------
    # БАЗОВЫЕ ОПЕРАЦИИ
    # ----------------------------
    def load_clients(self):
        try:
            with SessionLocal() as s:
                rows = (
                    s.query(Client)
                    .options(joinedload(Client.responsible_user))
                    .order_by(Client.id.desc())
                    .all()
                )
        except SQLAlchemyError as e:
            self._show_error("Ошибка загрузки клиентов", str(e))
            rows = []

        self.table.setRowCount(0)
        for cl in rows:
            self._add_table_row(cl)

        self.table.resizeColumnsToContents()
        if self.table.rowCount() > 0:
            self.table.setCurrentCell(0, 0)  # подсветим первого
        else:
            self._set_selected(None)

    def _add_table_row(self, cl: Client):
        r = self.table.rowCount()
        self.table.insertRow(r)

        def _it(val):
            t = "" if val is None else str(val)
            item = QTableWidgetItem(t)
            item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
            return item

        self.table.setItem(r, 0, _it(cl.id))
        self.table.setItem(r, 1, _it(cl.full_name))
        self.table.setItem(r, 2, _it(cl.phone))
        self.table.setItem(r, 3, _it(cl.lead_source))
        self.table.setItem(r, 4, _it(priority_label(getattr(cl, "priority", None))))
        self.table.setItem(r, 5, _it(getattr(getattr(cl, "responsible_user", None), "full_name", None) or getattr(getattr(cl, "responsible_user", None), "login", None)))
        self.table.setItem(r, 6, _it(cl.email))
        self.table.setItem(r, 7, _it(cl.registration_address))

    def _current_client_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        try:
            return int(item.text())
        except Exception:
            return None

    def _on_current_changed(self, *_):
        cid = self._current_client_id()
        if not cid:
            self._set_selected(None)
            return
        try:
            from db import SessionLocal
            from models import Client
            with SessionLocal() as s:
                cl = (
                    s.query(Client)
                    .options(joinedload(Client.responsible_user))
                    .filter(Client.id == cid)
                    .first()
                )
            self._set_selected(cl)
        except Exception:
            self._set_selected(None)

    def _set_selected(self, cl: Client | None):
        if not cl:
            self.lbl_name.setText("—")
            self.lbl_phone.setText("—")
            self.lbl_email.setText("—")
            self.lbl_manager.setText("—")
            self.lbl_source.setText("—")
            self.lbl_priority.setText("—")
            self.lbl_addr.setText("—")
        else:
            self.lbl_name.setText(cl.full_name or "—")
            self.lbl_phone.setText(cl.phone or "—")
            self.lbl_email.setText(cl.email or "—")
            manager = getattr(cl, "responsible_user", None)
            self.lbl_manager.setText((manager.full_name or manager.login) if manager else "—")
            self.lbl_source.setText(cl.lead_source or "—")
            self.lbl_priority.setText(priority_label(getattr(cl, "priority", None)))
            self.lbl_addr.setText(cl.registration_address or "—")

    # ----------------------------
    # КНОПКИ
    # ----------------------------
    def on_add(self):
        dlg = ClientForm(self)
        if dlg.exec():
            data = dlg.get_data()
            try:
                self._save_client(None, data)
                self.load_clients()
            except SQLAlchemyError as e:
                self._show_error("Ошибка сохранения клиента", str(e))

    def on_edit(self):
        client_id = self._current_client_id()
        if not client_id:
            QMessageBox.information(self, "Клиенты", "Выберите клиента в таблице.")
            return

        try:
            with SessionLocal() as s:
                cl = s.get(Client, client_id)
                if not cl:
                    QMessageBox.warning(self, "Клиенты", f"Клиент ID={client_id} не найден.")
                    return
                dlg = ClientForm(self, client=cl)
                if dlg.exec():
                    data = dlg.get_data()
                    self._save_client(client_id, data)
                    self.load_clients()
        except SQLAlchemyError as e:
            self._show_error("Ошибка изменения клиента", str(e))

    def on_delete(self):
        client_id = self._current_client_id()
        if not client_id:
            QMessageBox.information(self, "Клиенты", "Выберите клиента в таблице.")
            return

        if QMessageBox.question(self, "Удалить клиента", f"Удалить клиента ID={client_id}?") != QMessageBox.StandardButton.Yes:
            return

        try:
            with SessionLocal() as s:
                cl = s.get(Client, client_id)
                if not cl:
                    QMessageBox.warning(self, "Клиенты", f"Клиент ID={client_id} не найден.")
                    return
                s.delete(cl)
                s.commit()
            self.load_clients()
        except SQLAlchemyError as e:
            self._show_error("Ошибка удаления клиента", str(e))

    # ----------------------------
    # СЕРВИС
    # ----------------------------
    def _save_client(self, client_id: int | None, data: dict):
        def to_date(s: str | None):
            if not s: return None
            try: return date.fromisoformat(s)
            except Exception: return None

        with SessionLocal() as s:
            if client_id:
                cl = s.get(Client, client_id)
                if not cl:
                    raise SQLAlchemyError(f"Клиент ID={client_id} не найден.")
            else:
                cl = Client()

            cl.full_name = data.get("full_name") or ""
            cl.phone = data.get("phone")
            cl.email = data.get("email")
            cl.passport_no = data.get("passport_no")
            cl.registration_address = data.get("registration_address")
            cl.snils = data.get("snils")
            cl.inn = data.get("inn")
            cl.date_of_birth = to_date(data.get("date_of_birth"))
            cl.passport_issuer = data.get("passport_issuer")
            cl.passport_issue_date = to_date(data.get("passport_issue_date"))
            cl.passport_division_code = data.get("passport_division_code")
            cl.responsible_user_id = data.get("responsible_user_id")
            cl.lead_source = data.get("lead_source")
            cl.priority = data.get("priority") or "normal"

            # нормализованные адресные поля (если есть)
            for key in ("country","region","city","street","house","block","flat",
                        "postal_code","fias_id","kladr_id","geo_lat","geo_lon"):
                if key in data:
                    setattr(cl, key, data.get(key))

            if not client_id:
                s.add(cl)
            s.commit()

    def _show_error(self, title: str, text: str):
        QMessageBox.critical(self, title, text if text else "Неизвестная ошибка")
