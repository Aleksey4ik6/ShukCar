from __future__ import annotations

import datetime as dt
from typing import Optional

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import joinedload

from db import SessionLocal
from models import Brand, Car, Client, Deal, Model, User, UserRole
from services.crm import priority_label
from services.deal_sync import set_deal_archive_state, sync_deals_from_cars
from ui.deal_details import DealDetailsWindow
from ui.deal_form import DealFormDialog


def _format_date(value) -> str:
    if not value:
        return ""
    try:
        return value.strftime("%d.%m.%Y")
    except Exception:
        return str(value)


class DealsView(QWidget):
    def __init__(self, parent=None, current_role: UserRole = UserRole.user):
        super().__init__(parent)
        self.current_role = current_role
        self._details_window = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.ed_search = QLineEdit(self)
        self.ed_search.setPlaceholderText("Поиск по клиенту, VIN, менеджеру, автомобилю или статусу...")
        self.lbl_scope = QLabel("Показывать:", self)
        self.cb_scope = QComboBox(self)
        self.cb_scope.addItem("В работе", "active")
        self.cb_scope.addItem("Архив", "archived")
        self.cb_scope.addItem("Все сделки", "all")
        self.btn_search = QPushButton("Найти", self)
        self.btn_clear = QPushButton("Сброс", self)
        self.btn_clear.setProperty("accent", "secondary")
        filters.addWidget(self.ed_search, 1)
        filters.addWidget(self.lbl_scope)
        filters.addWidget(self.cb_scope)
        filters.addWidget(self.btn_search)
        filters.addWidget(self.btn_clear)
        root.addLayout(filters)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_edit = QPushButton("Изменить", self)
        self.btn_open = QPushButton("Открыть сделку", self)
        self.btn_archive = QPushButton("В архив", self)
        self.btn_delete = QPushButton("Удалить", self)
        self.btn_refresh = QPushButton("Обновить", self)
        self.btn_edit.setProperty("accent", "secondary")
        self.btn_open.setProperty("accent", "secondary")
        self.btn_archive.setProperty("accent", "secondary")
        self.btn_delete.setProperty("accent", "danger-secondary")
        self.btn_refresh.setProperty("accent", "secondary")
        actions.addWidget(self.btn_edit)
        actions.addWidget(self.btn_open)
        actions.addWidget(self.btn_archive)
        actions.addWidget(self.btn_delete)
        actions.addStretch(1)
        actions.addWidget(self.btn_refresh)
        root.addLayout(actions)
        self.btn_delete.hide()
        self.btn_delete.setEnabled(False)

        self.lbl_auto_hint = QLabel(
            "Сделки создаются автоматически из карточек авто, где уже выбран клиент. Здесь вы управляете только этапом, статусом, заметками и архивом.",
            self,
        )
        self.lbl_auto_hint.setObjectName("InlineMutedLabel")
        self.lbl_auto_hint.setWordWrap(True)
        root.addWidget(self.lbl_auto_hint)

        self.table = QTableWidget(0, 11, self)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "Название",
                "Клиент",
                "Автомобиль",
                "VIN",
                "Этап",
                "Статус",
                "Менеджер",
                "Следующее действие",
                "Прибытие",
                "Приоритет",
            ]
        )
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table, 1)

        footer_wrap = QFrame(self)
        footer_wrap.setProperty("card", True)
        footer = QHBoxLayout(footer_wrap)
        footer.setContentsMargins(12, 10, 12, 10)
        footer.setSpacing(12)
        self.selection_label = QLabel("Выбрано: —", self)
        self.selection_label.setObjectName("SelectionHint")
        self.summary_label = QLabel("", self)
        self.summary_label.setObjectName("InlineMutedLabel")
        footer.addWidget(self.selection_label)
        footer.addStretch(1)
        footer.addWidget(self.summary_label)
        root.addWidget(footer_wrap, 0)

        if self.current_role == UserRole.trainee:
            self.btn_edit.setEnabled(False)
            self.btn_archive.setEnabled(False)

        self.btn_search.clicked.connect(self.load_data)
        self.btn_clear.clicked.connect(self._clear_filters)
        self.btn_refresh.clicked.connect(self.load_data)
        self.cb_scope.currentIndexChanged.connect(self.load_data)
        self.ed_search.returnPressed.connect(self.load_data)
        self.btn_edit.clicked.connect(self.on_edit)
        self.btn_open.clicked.connect(self.on_open)
        self.btn_archive.clicked.connect(self.on_toggle_archive)
        self.table.itemSelectionChanged.connect(self._update_selection)
        self.table.itemDoubleClicked.connect(lambda *_: self.on_open())

        self._last_query = ""
        self.load_data()

    def _base_query(self, session):
        return (
            session.query(Deal)
            .filter(Deal.car_id.is_not(None), Deal.client_id.is_not(None))
            .outerjoin(Client, Client.id == Deal.client_id)
            .outerjoin(Car, Car.id == Deal.car_id)
            .outerjoin(Brand, Brand.id == Car.brand_id)
            .outerjoin(Model, Model.id == Car.model_id)
            .outerjoin(User, User.id == Deal.responsible_user_id)
            .options(
                joinedload(Deal.client),
                joinedload(Deal.car).joinedload(Car.brand),
                joinedload(Deal.car).joinedload(Car.model),
                joinedload(Deal.deal_stage),
                joinedload(Deal.responsible_user),
            )
        )

    def _query(self, session, search: str | None = None):
        query = self._base_query(session)

        scope = self.cb_scope.currentData()
        if scope == "active":
            query = query.filter(or_(Deal.is_archived.is_(False), Deal.is_archived.is_(None)))
        elif scope == "archived":
            query = query.filter(Deal.is_archived.is_(True))

        if search:
            qtext = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    func.lower(func.coalesce(Deal.title, "")).like(qtext),
                    func.lower(func.coalesce(Client.full_name, "")).like(qtext),
                    func.lower(func.coalesce(Client.phone, "")).like(qtext),
                    func.lower(func.coalesce(Brand.name, "")).like(qtext),
                    func.lower(func.coalesce(Model.name, "")).like(qtext),
                    func.lower(func.coalesce(Car.vin, "")).like(qtext),
                    func.lower(func.coalesce(User.full_name, "")).like(qtext),
                    func.lower(func.coalesce(User.login, "")).like(qtext),
                    func.lower(func.coalesce(Deal.deal_status, "")).like(qtext),
                    func.lower(func.coalesce(Deal.next_action_note, "")).like(qtext),
                    cast(Deal.id, String).like(f"%{search}%"),
                )
            )
        return query

    def load_data(self):
        self._last_query = self.ed_search.text().strip()
        with SessionLocal() as session:
            sync_deals_from_cars(session)
            session.commit()
            rows = self._query(session, self._last_query or None).order_by(Deal.is_archived.asc(), Deal.id.desc()).all()
            active_count = self._base_query(session).filter(or_(Deal.is_archived.is_(False), Deal.is_archived.is_(None))).count()
            archived_count = self._base_query(session).filter(Deal.is_archived.is_(True)).count()

        self.table.setRowCount(0)
        for row in rows:
            self._append_row(row)
        self.table.resizeColumnsToContents()
        self.summary_label.setText(
            f"В работе: {active_count} · В архиве: {archived_count} · Показано: {len(rows)}"
        )
        if self.table.rowCount() > 0:
            self.table.setCurrentCell(0, 0)
        else:
            self._update_selection()

    def _append_row(self, deal: Deal):
        row_index = self.table.rowCount()
        self.table.insertRow(row_index)

        client = getattr(getattr(deal, "client", None), "full_name", None) or "Без клиента"
        car = getattr(deal, "car", None)
        if car:
            brand = getattr(getattr(car, "brand", None), "name", "") or ""
            model = getattr(getattr(car, "model", None), "name", "") or ""
            car_label = f"{brand} {model}".strip() or f"Авто #{car.id}"
            vin = car.vin or "—"
        else:
            car_label = "Не привязано"
            vin = "—"

        manager = (
            getattr(getattr(deal, "responsible_user", None), "full_name", None)
            or getattr(getattr(deal, "responsible_user", None), "login", None)
            or "—"
        )
        stage = getattr(getattr(deal, "deal_stage", None), "name", None) or "Без этапа"
        next_action = (deal.next_action_note or "").strip() or "—"
        if len(next_action) > 70:
            next_action = next_action[:67] + "..."

        values = [
            str(deal.id),
            deal.title or f"Сделка #{deal.id}",
            client,
            car_label,
            vin,
            stage,
            deal.deal_status or "—",
            manager,
            next_action,
            _format_date(deal.expected_arrival_date) or "—",
            priority_label(deal.priority),
        ]

        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, deal.id)
            self.table.setItem(row_index, column, item)

    def _current_deal_id(self) -> Optional[int]:
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

    def _current_deal(self) -> Optional[Deal]:
        deal_id = self._current_deal_id()
        if not deal_id:
            return None
        with SessionLocal() as session:
            return (
                self._base_query(session)
                .filter(Deal.id == deal_id)
                .first()
            )

    def _update_selection(self):
        deal = self._current_deal()
        has_selection = deal is not None
        self.btn_open.setEnabled(has_selection)
        self.btn_edit.setEnabled(has_selection and self.current_role != UserRole.trainee)
        self.btn_archive.setEnabled(has_selection and self.current_role != UserRole.trainee)

        if not deal:
            self.selection_label.setText("Выбрано: —")
            self.btn_archive.setText("В архив")
            return

        client = getattr(getattr(deal, "client", None), "full_name", None) or "Без клиента"
        stage = getattr(getattr(deal, "deal_stage", None), "name", None) or "Без этапа"
        archive_text = "Вернуть в работу" if getattr(deal, "is_archived", False) else "В архив"
        self.selection_label.setText(f"Выбрано: сделка #{deal.id} · {client} · {stage}")
        self.btn_archive.setText(archive_text)

    def _clear_filters(self):
        self.ed_search.clear()
        self.cb_scope.setCurrentIndex(0)
        self.load_data()

    def on_edit(self):
        if self.current_role == UserRole.trainee:
            return
        deal_id = self._current_deal_id()
        if not deal_id:
            QMessageBox.information(self, "Сделки", "Выберите сделку в списке.")
            return
        dialog = DealFormDialog(self, deal_id=deal_id)
        if dialog.exec():
            self.load_data()

    def on_open(self):
        deal_id = self._current_deal_id()
        if not deal_id:
            QMessageBox.information(self, "Сделки", "Выберите сделку в списке.")
            return
        window = DealDetailsWindow(deal_id=deal_id, parent=self)
        window.show()
        window.raise_()
        window.activateWindow()
        self._details_window = window

    def on_toggle_archive(self):
        if self.current_role == UserRole.trainee:
            return
        deal_id = self._current_deal_id()
        if not deal_id:
            QMessageBox.information(self, "Сделки", "Выберите сделку в списке.")
            return

        with SessionLocal() as session:
            deal = session.get(Deal, deal_id)
            if not deal:
                QMessageBox.warning(self, "Сделки", "Сделка не найдена.")
                return

            target_archived = not bool(deal.is_archived)
            action_text = "отправить в архив" if target_archived else "вернуть в работу"
            answer = QMessageBox.question(
                self,
                "Подтверждение",
                f"Вы действительно хотите {action_text} сделку #{deal.id}?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

            set_deal_archive_state(session, deal, target_archived)
            session.commit()

        self.load_data()
