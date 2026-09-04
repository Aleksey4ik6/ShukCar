from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from db import SessionLocal
from models import Car, Client, Deal, DealStage, DealStatus, User
from services.crm import fill_lead_source_combo, fill_priority_combo
from services.deal_sync import build_deal_title


PKG_ROOT = Path(__file__).resolve().parents[1]
ICON_PATH = PKG_ROOT / "img" / "logo_shukcar.jpg"


def _make_optional_date_edit() -> QDateEdit:
    edit = QDateEdit()
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("dd.MM.yyyy")
    edit.setMinimumDate(QDate(2000, 1, 1))
    edit.setDate(QDate(2000, 1, 1))
    edit.setSpecialValueText("Не указано")
    return edit


def _optional_qdate_to_date(edit: QDateEdit) -> Optional[dt.date]:
    value = edit.date()
    if not value or not value.isValid() or value == edit.minimumDate():
        return None
    return dt.date(value.year(), value.month(), value.day())


class DealFormDialog(QDialog):
    def __init__(self, parent=None, deal_id: Optional[int] = None):
        super().__init__(parent)
        self.deal_id = deal_id
        self.session = SessionLocal()

        self.setWindowTitle("Сделка")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(860, 720)
        self.setMinimumSize(760, 620)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(12)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self.scroll, 1)

        self.content = QWidget(self.scroll)
        self.scroll.setWidget(self.content)

        root = QVBoxLayout(self.content)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(12)

        self.card_link = QFrame(self.content)
        self.card_link.setProperty("card", True)
        link_form = QFormLayout(self.card_link)
        link_form.setContentsMargins(16, 16, 16, 16)
        link_form.setSpacing(10)

        self.ed_title = QLineEdit(self.card_link)
        self.ed_title.setPlaceholderText("Название сделки")

        self.cb_client = QComboBox(self.card_link)
        self.cb_client.setEditable(True)
        self.cb_client.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        self.cb_car = QComboBox(self.card_link)
        self.cb_car.setEditable(True)
        self.cb_car.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        link_hint = QLabel(
            "Рабочий сценарий: сначала создаёте клиента, потом карточку авто с этим клиентом. "
            "В сделке вы уже управляете только статусом, этапом и архивом.",
            self.card_link,
        )
        link_hint.setObjectName("InlineMutedLabel")
        link_hint.setWordWrap(True)

        link_form.addRow("Название:", self.ed_title)
        link_form.addRow("Клиент:", self.cb_client)
        link_form.addRow("Авто клиента:", self.cb_car)
        link_form.addRow("", link_hint)
        root.addWidget(self.card_link)

        self.card_workflow = QFrame(self.content)
        self.card_workflow.setProperty("card", True)
        workflow_form = QFormLayout(self.card_workflow)
        workflow_form.setContentsMargins(16, 16, 16, 16)
        workflow_form.setSpacing(10)

        self.cb_responsible = QComboBox(self.card_workflow)
        self.cb_status = QComboBox(self.card_workflow)
        self.cb_status.setEditable(True)
        self.cb_stage = QComboBox(self.card_workflow)
        self.cb_lead_source = QComboBox(self.card_workflow)
        self.cb_priority = QComboBox(self.card_workflow)
        self.dt_expected_arrival = _make_optional_date_edit()
        self.dt_next_action = _make_optional_date_edit()
        self.txt_next_action = QTextEdit(self.card_workflow)
        self.txt_next_action.setMaximumHeight(78)
        self.txt_blocked = QTextEdit(self.card_workflow)
        self.txt_blocked.setMaximumHeight(78)
        self.txt_notes = QTextEdit(self.card_workflow)
        self.txt_notes.setMaximumHeight(96)

        self.txt_next_action.setPlaceholderText("Что сделать дальше по сделке.")
        self.txt_blocked.setPlaceholderText("Почему сделка зависла.")
        self.txt_notes.setPlaceholderText("Короткие рабочие заметки.")

        workflow_form.addRow("Ответственный:", self.cb_responsible)
        workflow_form.addRow("Статус:", self.cb_status)
        workflow_form.addRow("Этап:", self.cb_stage)
        workflow_form.addRow("Источник лида:", self.cb_lead_source)
        workflow_form.addRow("Приоритет:", self.cb_priority)
        workflow_form.addRow("План прибытия:", self.dt_expected_arrival)
        workflow_form.addRow("Следующее действие до:", self.dt_next_action)
        workflow_form.addRow("Следующее действие:", self.txt_next_action)
        workflow_form.addRow("Причина блокировки:", self.txt_blocked)
        workflow_form.addRow("Примечание:", self.txt_notes)
        root.addWidget(self.card_workflow)

        client_card = QFrame(self.content)
        client_card.setProperty("card", True)
        client_layout = QVBoxLayout(client_card)
        client_layout.setContentsMargins(16, 16, 16, 16)
        client_layout.setSpacing(10)

        client_title = QLabel("Данные клиента", client_card)
        client_title.setObjectName("SectionTitle")
        client_layout.addWidget(client_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        client_layout.addLayout(grid)

        self.lbl_client_name = QLabel("—", client_card)
        self.lbl_client_phone = QLabel("—", client_card)
        self.lbl_client_email = QLabel("—", client_card)
        self.lbl_client_passport = QLabel("—", client_card)
        self.lbl_client_address = QLabel("—", client_card)
        self.lbl_client_address.setWordWrap(True)
        self.lbl_car_summary = QLabel("—", client_card)
        self.lbl_car_summary.setWordWrap(True)

        rows = [
            ("ФИО:", self.lbl_client_name),
            ("Телефон:", self.lbl_client_phone),
            ("E-mail:", self.lbl_client_email),
            ("Паспорт:", self.lbl_client_passport),
            ("Адрес:", self.lbl_client_address),
            ("Выбранное авто:", self.lbl_car_summary),
        ]
        for row_index, (label, widget) in enumerate(rows):
            title = QLabel(label, client_card)
            title.setObjectName("InlineMutedLabel")
            grid.addWidget(title, row_index, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(widget, row_index, 1)
        root.addWidget(client_card)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.cb_client.currentIndexChanged.connect(self._on_client_changed)
        self.cb_car.currentIndexChanged.connect(self._on_car_changed)

        self._populate_lookups()
        if self.deal_id:
            self._load_deal()
            self._lock_link_fields()
        else:
            self._on_client_changed()

    def closeEvent(self, event):
        try:
            self.session.close()
        finally:
            super().closeEvent(event)

    def _combo_data_from_text(self, combo: QComboBox):
        value = combo.currentData()
        if value is not None:
            return value
        text = combo.currentText().strip()
        if not text:
            return None
        index = combo.findText(text, Qt.MatchFlag.MatchExactly)
        if index >= 0:
            combo.setCurrentIndex(index)
            return combo.itemData(index)
        return None

    def _selected_client(self) -> Optional[Client]:
        client_id = self._combo_data_from_text(self.cb_client)
        if not client_id:
            return None
        return self.session.get(Client, int(client_id))

    def _selected_car(self) -> Optional[Car]:
        car_id = self._combo_data_from_text(self.cb_car)
        if not car_id:
            return None
        return self.session.get(Car, int(car_id))

    def _format_car_label(self, car: Car) -> str:
        brand = getattr(getattr(car, "brand", None), "name", "") or ""
        model = getattr(getattr(car, "model", None), "name", "") or ""
        build = car.build_date.strftime("%m.%Y") if getattr(car, "build_date", None) else ""
        parts = [part for part in [f"#{car.id}", brand, model] if part]
        if car.vin:
            parts.append(car.vin)
        if build:
            parts.append(build)
        return " • ".join(parts)

    def _populate_lookups(self):
        self.cb_client.blockSignals(True)
        self.cb_client.clear()
        self.cb_client.addItem("Выберите клиента", None)
        clients = self.session.query(Client).order_by(Client.full_name.asc(), Client.id.asc()).all()
        for client in clients:
            label = client.full_name or f"Клиент #{client.id}"
            if client.phone:
                label = f"{label} • {client.phone}"
            self.cb_client.addItem(label, client.id)
        self.cb_client.blockSignals(False)

        self.cb_responsible.clear()
        self.cb_responsible.addItem("Не назначен", None)
        for user in self.session.query(User).order_by(User.full_name.asc(), User.login.asc()).all():
            label = user.full_name or user.login or f"Сотрудник #{user.id}"
            self.cb_responsible.addItem(label, user.id)

        self.cb_stage.clear()
        self.cb_stage.addItem("Без этапа", None)
        for stage in (
            self.session.query(DealStage)
            .filter(DealStage.is_active.is_(True))
            .order_by(DealStage.sort_order.asc(), DealStage.id.asc())
            .all()
        ):
            self.cb_stage.addItem(stage.name, stage.id)

        self.cb_status.clear()
        self.cb_status.addItem("")
        for status in self.session.query(DealStatus).order_by(DealStatus.name.asc()).all():
            self.cb_status.addItem(status.name)

        fill_lead_source_combo(self.cb_lead_source)
        fill_priority_combo(self.cb_priority, "normal")
        self._populate_car_combo()

    def _populate_car_combo(self, client_id: Optional[int] = None, current_car_id: Optional[int] = None):
        current_text = self.cb_car.currentText().strip()
        self.cb_car.blockSignals(True)
        self.cb_car.clear()
        self.cb_car.addItem("Без привязки к авто", None)

        query = (
            self.session.query(Car)
            .options(joinedload(Car.brand), joinedload(Car.model))
            .filter(or_(Car.is_archived.is_(False), Car.is_archived.is_(None)))
        )
        if client_id:
            query = query.filter(Car.client_id == client_id)
        cars = query.order_by(Car.id.desc()).all()
        for car in cars:
            self.cb_car.addItem(self._format_car_label(car), car.id)

        if current_car_id:
            index = self.cb_car.findData(current_car_id)
            if index >= 0:
                self.cb_car.setCurrentIndex(index)
            else:
                self.cb_car.setCurrentIndex(0)
        elif current_text:
            self.cb_car.setEditText(current_text)
        else:
            self.cb_car.setCurrentIndex(0)
        self.cb_car.blockSignals(False)
        self._on_car_changed()

    def _set_client_preview(self, client: Optional[Client]):
        if not client:
            self.lbl_client_name.setText("—")
            self.lbl_client_phone.setText("—")
            self.lbl_client_email.setText("—")
            self.lbl_client_passport.setText("—")
            self.lbl_client_address.setText("—")
            return

        self.lbl_client_name.setText(client.full_name or "—")
        self.lbl_client_phone.setText(client.phone or "—")
        self.lbl_client_email.setText(client.email or "—")
        self.lbl_client_passport.setText(client.passport_no or "—")
        self.lbl_client_address.setText(client.registration_address or "—")

    def _set_car_preview(self, car: Optional[Car]):
        if not car:
            self.lbl_car_summary.setText("Не привязано")
            return
        self.lbl_car_summary.setText(self._format_car_label(car))

    def _suggest_title_if_empty(self):
        if self.deal_id or self.ed_title.text().strip():
            return
        client = self._selected_client()
        car = self._selected_car()
        if client and car:
            self.ed_title.setText(build_deal_title(car, client))
        elif client:
            self.ed_title.setText(f"Сделка • {client.full_name}")

    def _on_client_changed(self):
        client = self._selected_client()
        self._set_client_preview(client)

        current_car_id = None
        deal = self.session.get(Deal, self.deal_id) if self.deal_id else None
        if deal and deal.car_id:
            current_car_id = deal.car_id
        self._populate_car_combo(client.id if client else None, current_car_id=current_car_id)

        if not client:
            return

        if self.cb_responsible.currentData() is None and client.responsible_user_id:
            index = self.cb_responsible.findData(client.responsible_user_id)
            if index >= 0:
                self.cb_responsible.setCurrentIndex(index)

        if not self.cb_lead_source.currentText().strip() and client.lead_source:
            self.cb_lead_source.setEditText(client.lead_source)

        current_priority = self.cb_priority.currentData() or ""
        if current_priority in ("", "normal") and client.priority:
            index = self.cb_priority.findData(client.priority)
            if index >= 0:
                self.cb_priority.setCurrentIndex(index)

        self._suggest_title_if_empty()

    def _on_car_changed(self):
        self._set_car_preview(self._selected_car())
        self._suggest_title_if_empty()

    def _ensure_status(self, name: str | None):
        title = (name or "").strip()
        if not title:
            return None
        row = self.session.query(DealStatus).filter(DealStatus.name == title).first()
        if row:
            return row
        row = DealStatus(name=title)
        self.session.add(row)
        self.session.flush()
        return row

    def _load_deal(self):
        deal = self.session.get(Deal, self.deal_id)
        if not deal:
            return

        self.ed_title.setText(deal.title or "")

        client_index = self.cb_client.findData(deal.client_id)
        if client_index >= 0:
            self.cb_client.setCurrentIndex(client_index)
        else:
            self._populate_car_combo(current_car_id=deal.car_id)

        user_index = self.cb_responsible.findData(deal.responsible_user_id)
        if user_index >= 0:
            self.cb_responsible.setCurrentIndex(user_index)

        self.cb_status.setEditText(deal.deal_status or "")

        stage_index = self.cb_stage.findData(deal.deal_stage_id)
        if stage_index >= 0:
            self.cb_stage.setCurrentIndex(stage_index)

        fill_lead_source_combo(self.cb_lead_source, deal.lead_source)
        fill_priority_combo(self.cb_priority, deal.priority or "normal")

        if deal.expected_arrival_date:
            self.dt_expected_arrival.setDate(
                QDate(deal.expected_arrival_date.year, deal.expected_arrival_date.month, deal.expected_arrival_date.day)
            )
        else:
            self.dt_expected_arrival.setDate(self.dt_expected_arrival.minimumDate())

        if deal.next_action_date:
            self.dt_next_action.setDate(QDate(deal.next_action_date.year, deal.next_action_date.month, deal.next_action_date.day))
        else:
            self.dt_next_action.setDate(self.dt_next_action.minimumDate())

        self.txt_next_action.setPlainText(deal.next_action_note or "")
        self.txt_blocked.setPlainText(deal.blocked_reason or "")
        self.txt_notes.setPlainText(deal.notes or "")
        self._set_client_preview(deal.client)
        self._set_car_preview(deal.car)

    def _lock_link_fields(self):
        self.ed_title.setReadOnly(True)
        self.cb_client.setEnabled(False)
        self.cb_car.setEnabled(False)

    def _save(self):
        if not self.deal_id:
            raise ValueError("Новая сделка создаётся автоматически из карточки автомобиля с выбранным клиентом.")

        client = self._selected_client()
        if not client:
            raise ValueError("Для сделки нужно выбрать существующего клиента.")

        car = self._selected_car()
        if car and car.client_id and car.client_id != client.id:
            raise ValueError("Выбранное авто закреплено за другим клиентом.")

        status = self._ensure_status(self.cb_status.currentText())
        title = self.ed_title.text().strip()
        if not title:
            self._suggest_title_if_empty()
            title = self.ed_title.text().strip()
        if not title:
            raise ValueError("Укажите название сделки.")

        stage_id = self.cb_stage.currentData()
        responsible_user_id = self.cb_responsible.currentData()
        lead_source = self.cb_lead_source.currentText().strip() or None
        priority = self.cb_priority.currentData() or "normal"

        deal = self.session.get(Deal, self.deal_id)
        if not deal:
            raise ValueError("Сделка не найдена.")

        deal.title = title
        deal.client_id = client.id
        deal.car_id = car.id if car else None
        deal.responsible_user_id = responsible_user_id
        deal.deal_status = status.name if status else None
        deal.deal_stage_id = stage_id
        deal.lead_source = lead_source
        deal.priority = priority
        deal.expected_arrival_date = _optional_qdate_to_date(self.dt_expected_arrival)
        deal.next_action_date = _optional_qdate_to_date(self.dt_next_action)
        deal.next_action_note = self.txt_next_action.toPlainText().strip() or None
        deal.blocked_reason = self.txt_blocked.toPlainText().strip() or None
        deal.notes = self.txt_notes.toPlainText().strip() or None

        self.session.commit()
        self.deal_id = deal.id

    def accept(self):
        try:
            self._save()
        except Exception as exc:
            QMessageBox.warning(self, "Сделка", str(exc))
            return
        super().accept()
