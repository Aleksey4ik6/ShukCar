from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from db import SessionLocal
from models import User, UserRole
from services.workspace_insights import build_attention_snapshot


class AttentionMetricCard(QFrame):
    def __init__(self, title: str, tone: str = "neutral", parent=None):
        super().__init__(parent)
        self.setProperty("metric", True)
        self.setProperty("tone", tone)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        self.lbl_title = QLabel(title, self)
        self.lbl_title.setProperty("role", "title")
        self.lbl_value = QLabel("0", self)
        self.lbl_value.setProperty("role", "value")
        self.lbl_note = QLabel("", self)
        self.lbl_note.setProperty("role", "sub")
        self.lbl_note.setWordWrap(True)

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_note)

    def set_data(self, value: str, note: str):
        self.lbl_value.setText(value)
        self.lbl_note.setText(note)


class AttentionSection(QFrame):
    def __init__(self, title: str, caption: str = "", parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        label = QLabel(title, self)
        label.setObjectName("SectionTitle")
        layout.addWidget(label)

        if caption:
            text = QLabel(caption, self)
            text.setObjectName("SectionCaption")
            text.setWordWrap(True)
            layout.addWidget(text)

        self.body_layout = QVBoxLayout()
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(8)
        layout.addLayout(self.body_layout, 1)


class AttentionCenter(QWidget):
    def __init__(
        self,
        current_user: User,
        *,
        open_deals: Optional[Callable[[], None]] = None,
        open_cars: Optional[Callable[[], None]] = None,
        open_clients: Optional[Callable[[], None]] = None,
        open_chat: Optional[Callable[[], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.user = current_user
        self.open_deals = open_deals
        self.open_cars = open_cars
        self.open_clients = open_clients
        self.open_chat = open_chat

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget(scroll)
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(14)

        hero = QFrame(content)
        hero.setObjectName("HomeHero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(22, 22, 22, 22)
        hero_layout.setSpacing(18)

        left = QVBoxLayout()
        left.setSpacing(10)
        kicker = QLabel("ЦЕНТР ВНИМАНИЯ", hero)
        kicker.setObjectName("HeroKicker")
        self.lbl_title = QLabel("Что требует внимания прямо сейчас", hero)
        self.lbl_title.setObjectName("HomeWelcome")
        self.lbl_caption = QLabel(
            "Просрочки, блокировки, прибытия, сделки без следующего шага и проблемы данных в одном месте.",
            hero,
        )
        self.lbl_caption.setObjectName("HeroCaption")
        self.lbl_caption.setWordWrap(True)
        left.addWidget(kicker)
        left.addWidget(self.lbl_title)
        left.addWidget(self.lbl_caption)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_open_deals = QPushButton("Сделки", hero)
        self.btn_open_cars = QPushButton("Авто", hero)
        self.btn_open_clients = QPushButton("Клиенты", hero)
        self.btn_open_chat = QPushButton("Чат", hero)
        self.btn_refresh = QPushButton("Обновить", hero)
        self.btn_open_cars.setProperty("accent", "secondary")
        self.btn_open_clients.setProperty("accent", "secondary")
        self.btn_open_chat.setProperty("accent", "secondary")
        self.btn_refresh.setProperty("accent", "secondary")
        actions.addWidget(self.btn_open_deals)
        actions.addWidget(self.btn_open_cars)
        actions.addWidget(self.btn_open_clients)
        actions.addWidget(self.btn_open_chat)
        actions.addStretch(1)
        actions.addWidget(self.btn_refresh)
        left.addLayout(actions)
        hero_layout.addLayout(left, 2)

        aside = QFrame(hero)
        aside.setObjectName("HeroSpotlight")
        aside_layout = QVBoxLayout(aside)
        aside_layout.setContentsMargins(16, 16, 16, 16)
        aside_layout.setSpacing(8)
        title = QLabel("Контур контроля", aside)
        title.setObjectName("SectionTitle")
        self.lbl_scope = QLabel("", aside)
        self.lbl_scope.setObjectName("SectionCaption")
        self.lbl_scope.setWordWrap(True)
        self.lbl_focus = QLabel("", aside)
        self.lbl_focus.setObjectName("MutedLabel")
        self.lbl_focus.setWordWrap(True)
        aside_layout.addWidget(title)
        aside_layout.addWidget(self.lbl_scope)
        aside_layout.addWidget(self.lbl_focus)
        aside_layout.addStretch(1)
        hero_layout.addWidget(aside, 1)
        root.addWidget(hero)

        metrics_grid = QGridLayout()
        metrics_grid.setHorizontalSpacing(12)
        metrics_grid.setVerticalSpacing(12)
        self.metric_active = AttentionMetricCard("Активные сделки", "accent", content)
        self.metric_overdue = AttentionMetricCard("Просроченные задачи", "danger", content)
        self.metric_blocked = AttentionMetricCard("Блокировки", "warning", content)
        self.metric_no_next = AttentionMetricCard("Без следующего шага", "warning", content)
        self.metric_arriving = AttentionMetricCard("Прибытие 7 дней", "success", content)
        self.metric_quality = AttentionMetricCard("Проблемы данных", "accent", content)
        metrics_grid.addWidget(self.metric_active, 0, 0)
        metrics_grid.addWidget(self.metric_overdue, 0, 1)
        metrics_grid.addWidget(self.metric_blocked, 0, 2)
        metrics_grid.addWidget(self.metric_no_next, 1, 0)
        metrics_grid.addWidget(self.metric_arriving, 1, 1)
        metrics_grid.addWidget(self.metric_quality, 1, 2)
        root.addLayout(metrics_grid)

        upper = QGridLayout()
        upper.setHorizontalSpacing(12)
        upper.setVerticalSpacing(12)
        self.tbl_overdue = self._create_table(["Срок", "Приоритет", "Задача", "Контур", "Клиент"])
        self.tbl_blocked = self._create_table(["Сделка", "Клиент", "Менеджер", "Причина"])
        overdue_section = AttentionSection("Просроченные задачи", "Незакрытые задачи по сделкам и автомобилям.", content)
        overdue_section.body_layout.addWidget(self.tbl_overdue)
        blocked_section = AttentionSection("Сделки с блокировкой", "Кейсы, где уже есть явная причина остановки.", content)
        blocked_section.body_layout.addWidget(self.tbl_blocked)
        upper.addWidget(overdue_section, 0, 0)
        upper.addWidget(blocked_section, 0, 1)
        root.addLayout(upper)

        middle = QGridLayout()
        middle.setHorizontalSpacing(12)
        middle.setVerticalSpacing(12)
        self.tbl_no_next = self._create_table(["Сделка", "Клиент", "Этап", "Менеджер"])
        self.tbl_arrival = self._create_table(["Дата", "Сделка", "Клиент", "Авто"])
        no_next_section = AttentionSection("Нет следующего шага", "Сделки, по которым сотрудник ещё не зафиксировал следующий ход.", content)
        no_next_section.body_layout.addWidget(self.tbl_no_next)
        arrival_section = AttentionSection("Скорое прибытие", "Что нужно держать в поле зрения в ближайшие 7 дней.", content)
        arrival_section.body_layout.addWidget(self.tbl_arrival)
        middle.addWidget(no_next_section, 0, 0)
        middle.addWidget(arrival_section, 0, 1)
        root.addLayout(middle)

        lower = QGridLayout()
        lower.setHorizontalSpacing(12)
        lower.setVerticalSpacing(12)
        self.tbl_quality = self._create_table(["Контур", "Кол-во", "Проблема", "Что сделать"])
        self.lst_recent = QListWidget(content)
        self.lst_recent.setProperty("overviewList", True)
        self.lst_recent.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.lst_recent.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        quality_section = AttentionSection("Качество данных", "Проблемы, которые ломают рабочий контур и отчёты.", content)
        quality_section.body_layout.addWidget(self.tbl_quality)
        recent_section = AttentionSection("Последняя активность", "Свежие системные события и изменения.", content)
        recent_section.body_layout.addWidget(self.lst_recent)
        lower.addWidget(quality_section, 0, 0)
        lower.addWidget(recent_section, 0, 1)
        root.addLayout(lower)
        root.addStretch(1)

        self.btn_open_deals.clicked.connect(lambda: self._open_route("deals"))
        self.btn_open_cars.clicked.connect(lambda: self._open_route("cars"))
        self.btn_open_clients.clicked.connect(lambda: self._open_route("clients"))
        self.btn_open_chat.clicked.connect(lambda: self._open_route("chat"))
        self.btn_refresh.clicked.connect(self.refresh)

        self.tbl_overdue.itemDoubleClicked.connect(self._handle_table_route)
        self.tbl_blocked.itemDoubleClicked.connect(self._handle_table_route)
        self.tbl_no_next.itemDoubleClicked.connect(self._handle_table_route)
        self.tbl_arrival.itemDoubleClicked.connect(self._handle_table_route)
        self.tbl_quality.itemDoubleClicked.connect(self._handle_table_route)

        self.refresh()

    def _scope_user_id(self) -> int | None:
        role_value = getattr(getattr(self.user, "role", None), "value", None) or str(getattr(self.user, "role", ""))
        if role_value == UserRole.admin.value:
            return None
        return int(self.user.id)

    def _create_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers), self)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def _set_rows(self, table: QTableWidget, rows: list[dict], columns: list[str], route_field: str = "route"):
        table.setRowCount(0)
        for row_data in rows:
            row = table.rowCount()
            table.insertRow(row)
            for column_index, key in enumerate(columns):
                text = row_data.get(key, "")
                if hasattr(text, "strftime"):
                    text = text.strftime("%d.%m.%Y")
                item = QTableWidgetItem("" if text is None else str(text))
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row_data.get(route_field))
                table.setItem(row, column_index, item)
        table.resizeColumnsToContents()

    def _handle_table_route(self, item: QTableWidgetItem):
        route = item.data(Qt.ItemDataRole.UserRole)
        if not route:
            first_item = item.tableWidget().item(item.row(), 0)
            route = first_item.data(Qt.ItemDataRole.UserRole) if first_item is not None else None
        if route:
            self._open_route(str(route))

    def _open_route(self, route: str):
        callbacks = {
            "deals": self.open_deals,
            "cars": self.open_cars,
            "clients": self.open_clients,
            "chat": self.open_chat,
        }
        callback = callbacks.get(route)
        if callable(callback):
            callback()

    def refresh(self):
        scope_user_id = self._scope_user_id()
        with SessionLocal() as session:
            snapshot = build_attention_snapshot(session, user_id=scope_user_id)

        scope_text = (
            "Контроль по всей команде и по всей базе."
            if scope_user_id is None
            else "Контроль только по закреплённым за вами сделкам и задачам."
        )
        metrics = snapshot["metrics"]
        self.lbl_scope.setText(scope_text)
        self.lbl_focus.setText(
            f"Просрочено задач: {metrics['overdue_tasks']}\n"
            f"Сделок с блокировкой: {metrics['blocked_deals']}\n"
            f"Сообщений в чатах за сегодня: {metrics['messages_today']}"
        )

        self.metric_active.set_data(str(metrics["active_deals"]), "В работе прямо сейчас.")
        self.metric_overdue.set_data(str(metrics["overdue_tasks"]), "Нужно разбирать в первую очередь.")
        self.metric_blocked.set_data(str(metrics["blocked_deals"]), "Есть явная причина стопа.")
        self.metric_no_next.set_data(str(metrics["no_next"]), "Нет следующего шага по сделке.")
        self.metric_arriving.set_data(str(metrics["arrivals_soon"]), "Контроль прибытия на горизонте недели.")
        self.metric_quality.set_data(str(metrics["data_issues"]), "Проблемы, которые портят рабочий контур.")

        self._set_rows(
            self.tbl_overdue,
            snapshot["overdue_items"],
            ["due_date", "priority", "title", "entity", "extra"],
        )
        self._set_rows(
            self.tbl_blocked,
            snapshot["blocked_items"],
            ["title", "client", "manager", "reason"],
            route_field="route",
        )
        self._set_rows(
            self.tbl_no_next,
            snapshot["no_next_items"],
            ["title", "client", "stage", "manager"],
            route_field="route",
        )
        self._set_rows(
            self.tbl_arrival,
            snapshot["arrival_items"],
            ["arrival_date", "title", "client", "car"],
            route_field="route",
        )
        self._set_rows(
            self.tbl_quality,
            snapshot["quality_items"],
            ["scope", "value", "label", "recommendation"],
        )

        self.lst_recent.clear()
        for row in snapshot["recent_items"]:
            item = QListWidgetItem(
                f"{row['created_at'].strftime('%d.%m.%Y %H:%M') if row['created_at'] else '—'} · {row['title']}\n{row['details']}"
            )
            self.lst_recent.addItem(item)
        if self.lst_recent.count() == 0:
            self.lst_recent.addItem("Последних действий пока нет.")
