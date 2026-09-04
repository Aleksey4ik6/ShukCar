from __future__ import annotations

import datetime as dt
from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func, or_

from db import SessionLocal
from models import Client, User, UserRole
from services.workspace_insights import build_attention_snapshot


class MetricCard(QFrame):
    def __init__(self, title: str, tone: str = "neutral", parent=None):
        super().__init__(parent)
        self.setProperty("metric", True)
        self.setProperty("tone", tone)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        self.lbl_title = QLabel(title, self)
        self.lbl_title.setProperty("role", "title")
        self.lbl_value = QLabel("—", self)
        self.lbl_value.setProperty("role", "value")
        self.lbl_note = QLabel("", self)
        self.lbl_note.setProperty("role", "sub")
        self.lbl_note.setWordWrap(True)

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_note)

    def set_value(self, value: str, note: str = ""):
        self.lbl_value.setText(value)
        self.lbl_note.setText(note)


class QuickActionTile(QPushButton):
    def __init__(self, title: str, caption: str, parent=None):
        super().__init__(parent)
        self.setProperty("quickTile", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(88)
        self.setText(f"{title}\n{caption}")


class SectionCard(QFrame):
    def __init__(self, title: str, caption: str = "", parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title_label = QLabel(title, self)
        title_label.setObjectName("SectionTitle")
        layout.addWidget(title_label)

        if caption:
            caption_label = QLabel(caption, self)
            caption_label.setObjectName("SectionCaption")
            caption_label.setWordWrap(True)
            layout.addWidget(caption_label)

        self.list_widget = QListWidget(self)
        self.list_widget.setProperty("overviewList", True)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_widget.setSpacing(6)
        layout.addWidget(self.list_widget, 1)


class HomeOverview(QWidget):
    def __init__(
        self,
        current_user: User,
        *,
        open_attention: Optional[Callable[[], None]] = None,
        open_deals: Optional[Callable[[], None]] = None,
        open_cars: Optional[Callable[[], None]] = None,
        open_clients: Optional[Callable[[], None]] = None,
        open_dashboard: Optional[Callable[[], None]] = None,
        open_calc: Optional[Callable[[], None]] = None,
        open_chat: Optional[Callable[[], None]] = None,
        open_rates: Optional[Callable[[], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.user = current_user
        self.open_attention = open_attention
        self.open_deals = open_deals
        self.open_cars = open_cars
        self.open_clients = open_clients
        self.open_dashboard = open_dashboard
        self.open_calc = open_calc
        self.open_chat = open_chat
        self.open_rates = open_rates

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self.scroll)

        self.content = QWidget(self.scroll)
        self.scroll.setWidget(self.content)

        root = QVBoxLayout(self.content)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(14)

        hero = QFrame(self.content)
        hero.setObjectName("HomeHero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(22, 22, 22, 22)
        hero_layout.setSpacing(18)

        hero_left = QVBoxLayout()
        hero_left.setSpacing(10)
        self.lbl_kicker = QLabel("РАБОЧИЙ ЦЕНТР SHUKCAR", hero)
        self.lbl_kicker.setObjectName("HeroKicker")
        self.lbl_welcome = QLabel("", hero)
        self.lbl_welcome.setObjectName("HomeWelcome")
        self.lbl_caption = QLabel("", hero)
        self.lbl_caption.setObjectName("HeroCaption")
        self.lbl_caption.setWordWrap(True)
        hero_left.addWidget(self.lbl_kicker)
        hero_left.addWidget(self.lbl_welcome)
        hero_left.addWidget(self.lbl_caption)

        hero_actions = QHBoxLayout()
        hero_actions.setSpacing(8)
        self.btn_attention = QPushButton("Фокус дня", hero)
        self.btn_deals = QPushButton("Сделки", hero)
        self.btn_clients = QPushButton("Клиенты", hero)
        self.btn_dashboard = QPushButton("Аналитика", hero)
        self.btn_refresh = QPushButton("Обновить", hero)
        self.btn_attention.setProperty("accent", "secondary")
        self.btn_clients.setProperty("accent", "secondary")
        self.btn_dashboard.setProperty("accent", "secondary")
        self.btn_refresh.setProperty("accent", "secondary")
        hero_actions.addWidget(self.btn_attention)
        hero_actions.addWidget(self.btn_deals)
        hero_actions.addWidget(self.btn_clients)
        hero_actions.addWidget(self.btn_dashboard)
        hero_actions.addStretch(1)
        hero_actions.addWidget(self.btn_refresh)
        hero_left.addLayout(hero_actions)
        hero_layout.addLayout(hero_left, 2)

        hero_aside = QFrame(hero)
        hero_aside.setObjectName("HeroSpotlight")
        hero_aside_layout = QVBoxLayout(hero_aside)
        hero_aside_layout.setContentsMargins(16, 16, 16, 16)
        hero_aside_layout.setSpacing(8)
        self.lbl_today_title = QLabel("Фокус на сегодня", hero_aside)
        self.lbl_today_title.setObjectName("SectionTitle")
        self.lbl_today_date = QLabel("", hero_aside)
        self.lbl_today_date.setObjectName("SectionCaption")
        self.lbl_today_role = QLabel("", hero_aside)
        self.lbl_today_role.setProperty("chip", True)
        self.lbl_today_focus = QLabel("", hero_aside)
        self.lbl_today_focus.setWordWrap(True)
        self.lbl_today_focus.setObjectName("MutedLabel")
        hero_aside_layout.addWidget(self.lbl_today_title)
        hero_aside_layout.addWidget(self.lbl_today_date)
        hero_aside_layout.addWidget(self.lbl_today_role, 0, Qt.AlignmentFlag.AlignLeft)
        hero_aside_layout.addWidget(self.lbl_today_focus)
        hero_aside_layout.addStretch(1)
        hero_layout.addWidget(hero_aside, 1)
        root.addWidget(hero)

        actions_frame = QFrame(self.content)
        actions_frame.setProperty("card", True)
        actions_layout = QGridLayout(actions_frame)
        actions_layout.setContentsMargins(16, 16, 16, 16)
        actions_layout.setHorizontalSpacing(12)
        actions_layout.setVerticalSpacing(12)

        self.tile_attention = QuickActionTile("Центр внимания", "Просрочки, блокировки, прибытия и проблемы данных под рукой.", actions_frame)
        self.tile_deals = QuickActionTile("Сделки", "Воронка, архив, статусы и контроль активных кейсов.", actions_frame)
        self.tile_clients = QuickActionTile("Клиентская база", "Контакты, документы, адреса и закрепление сотрудников.", actions_frame)
        self.tile_calc = QuickActionTile("Калькулятор привоза", "Расчёт стоимости, пошлин и расходов под ключ.", actions_frame)
        self.tile_chat = QuickActionTile("Командный чат", "Связь между сотрудниками и быстрые личные диалоги.", actions_frame)
        self.tile_rates = QuickActionTile("Курсы валют", "Онлайн-курсы для расчётов и контроля изменений.", actions_frame)
        self.tile_dashboard = QuickActionTile("Панель контроля", "Общая картина по срокам, задачам и активности.", actions_frame)

        actions_layout.addWidget(self.tile_attention, 0, 0)
        actions_layout.addWidget(self.tile_deals, 0, 1)
        actions_layout.addWidget(self.tile_clients, 0, 2)
        actions_layout.addWidget(self.tile_calc, 1, 0)
        actions_layout.addWidget(self.tile_chat, 1, 1)
        actions_layout.addWidget(self.tile_rates, 1, 2)
        actions_layout.addWidget(self.tile_dashboard, 2, 0, 1, 3)
        root.addWidget(actions_frame)

        metrics_grid = QGridLayout()
        metrics_grid.setHorizontalSpacing(12)
        metrics_grid.setVerticalSpacing(12)
        self.card_my_cars = MetricCard("Сделки под контролем", "accent")
        self.card_clients = MetricCard("Клиенты в работе", "neutral")
        self.card_overdue = MetricCard("Просроченные задачи", "danger")
        self.card_no_next = MetricCard("Без следующего шага", "warning")
        self.card_arriving = MetricCard("Прибытие за 7 дней", "success")
        self.card_priority = MetricCard("Срочные кейсы", "accent")
        metrics_grid.addWidget(self.card_my_cars, 0, 0)
        metrics_grid.addWidget(self.card_clients, 0, 1)
        metrics_grid.addWidget(self.card_overdue, 0, 2)
        metrics_grid.addWidget(self.card_no_next, 1, 0)
        metrics_grid.addWidget(self.card_arriving, 1, 1)
        metrics_grid.addWidget(self.card_priority, 1, 2)
        root.addLayout(metrics_grid)

        lower = QGridLayout()
        lower.setHorizontalSpacing(12)
        lower.setVerticalSpacing(12)
        self.tasks_card = SectionCard("Ближайшие задачи", "Что нужно закрыть в первую очередь.", self.content)
        self.focus_card = SectionCard("Сделки под фокусом", "Кейсы, где нужен следующий шаг, контроль сроков или разбор блокировки.", self.content)
        self.sources_card = SectionCard("Откуда приходят клиенты", "Быстрый срез по источникам лидов в текущей базе.", self.content)
        lower.addWidget(self.tasks_card, 0, 0)
        lower.addWidget(self.focus_card, 0, 1)
        lower.addWidget(self.sources_card, 0, 2)
        lower.setColumnStretch(0, 1)
        lower.setColumnStretch(1, 1)
        lower.setColumnStretch(2, 1)
        root.addLayout(lower)
        root.addStretch(1)

        self.btn_attention.clicked.connect(lambda: self.open_attention() if callable(self.open_attention) else None)
        self.btn_deals.clicked.connect(lambda: self.open_deals() if callable(self.open_deals) else None)
        self.btn_clients.clicked.connect(lambda: self.open_clients() if callable(self.open_clients) else None)
        self.btn_dashboard.clicked.connect(lambda: self.open_dashboard() if callable(self.open_dashboard) else None)
        self.btn_refresh.clicked.connect(self.refresh)

        self.tile_attention.clicked.connect(lambda: self.open_attention() if callable(self.open_attention) else None)
        self.tile_deals.clicked.connect(lambda: self.open_deals() if callable(self.open_deals) else None)
        self.tile_clients.clicked.connect(lambda: self.open_clients() if callable(self.open_clients) else None)
        self.tile_calc.clicked.connect(lambda: self.open_calc() if callable(self.open_calc) else None)
        self.tile_chat.clicked.connect(lambda: self.open_chat() if callable(self.open_chat) else None)
        self.tile_rates.clicked.connect(lambda: self.open_rates() if callable(self.open_rates) else None)
        self.tile_dashboard.clicked.connect(lambda: self.open_dashboard() if callable(self.open_dashboard) else None)

        self.refresh()

    def _scope_filter(self):
        role_value = getattr(getattr(self.user, "role", None), "value", None) or str(getattr(self.user, "role", ""))
        if role_value == UserRole.admin.value:
            return None
        return self.user.id

    def refresh(self):
        today = dt.date.today()
        scope_user_id = self._scope_filter()
        name = self.user.full_name or getattr(self.user, "login", "Пользователь")
        role_name = self._role_to_text(getattr(self.user, "role", None))

        with SessionLocal() as session:
            attention = build_attention_snapshot(session, user_id=scope_user_id)
            client_query = session.query(Client)
            lead_query = session.query(Client.lead_source, func.count(Client.id))

            if scope_user_id is not None:
                client_query = client_query.filter(
                    or_(Client.responsible_user_id == scope_user_id, Client.responsible_user_id.is_(None))
                )
                lead_query = lead_query.filter(
                    or_(Client.responsible_user_id == scope_user_id, Client.responsible_user_id.is_(None))
                )

            clients = client_query.count()
            lead_rows = (
                lead_query.group_by(Client.lead_source)
                .order_by(func.count(Client.id).desc(), Client.lead_source.asc())
                .all()
            )
        metrics = attention["metrics"]
        my_deals = metrics["active_deals"]
        overdue = metrics["overdue_tasks"]
        no_next = metrics["no_next"]
        arriving_soon = metrics["arrivals_soon"]
        urgent_cases = metrics["urgent_deals"]

        self.lbl_welcome.setText(f"Добро пожаловать, {name}")
        scope_label = "по всей команде" if scope_user_id is None else "по вашим закреплённым сделкам"
        self.lbl_caption.setText(
            f"Собрали в одном месте сводку {scope_label}: задачи, сделки под риском, приоритетные кейсы и быстрые переходы."
        )
        self.lbl_today_date.setText(today.strftime("%d.%m.%Y"))
        self.lbl_today_role.setText(role_name)
        self.lbl_today_focus.setText(
            f"Просрочено задач: {overdue}\n"
            f"Срочных кейсов: {urgent_cases}\n"
            f"Прибытие в ближайшие 7 дней: {arriving_soon}"
        )

        self.card_my_cars.set_value(str(my_deals), "Сделки, которые сейчас требуют контроля.")
        self.card_clients.set_value(str(clients), "Клиенты в текущем рабочем контуре.")
        self.card_overdue.set_value(str(overdue), "Сначала закройте просрочки и задержки.")
        self.card_no_next.set_value(str(no_next), "Сделки без плана следующего шага.")
        self.card_arriving.set_value(str(arriving_soon), "Ожидаемое прибытие в течение недели.")
        self.card_priority.set_value(str(urgent_cases), "Высокий и срочный приоритет по сделкам.")

        self.tasks_card.list_widget.clear()
        for task in attention["overdue_items"][:8]:
            due = task["due_date"].strftime("%d.%m.%Y") if task["due_date"] else "без срока"
            self.tasks_card.list_widget.addItem(
                f"{due} · {task['priority']}\n{task['title']}\n{task['entity']} · {task['extra']}"
            )
        if self.tasks_card.list_widget.count() == 0:
            self.tasks_card.list_widget.addItem("Активных задач сейчас нет.")

        self.focus_card.list_widget.clear()
        focus_rows = attention["blocked_items"][:4] + attention["arrival_items"][:4]
        for row in focus_rows[:8]:
            if "reason" in row:
                self.focus_card.list_widget.addItem(
                    f"{row['title']}\n{row['client']} · {row['manager']} · блокировка: {row['reason']}"
                )
            else:
                arrival = row["arrival_date"].strftime("%d.%m.%Y") if row["arrival_date"] else "без даты"
                self.focus_card.list_widget.addItem(
                    f"{row['title']}\n{row['client']} · {row['car']} · прибытие {arrival}"
                )
        if self.focus_card.list_widget.count() == 0:
            self.focus_card.list_widget.addItem("Пока нет сделок, которые требуют срочного внимания.")

        self.sources_card.list_widget.clear()
        for source, count in lead_rows[:8]:
            source_label = (source or "").strip() or "Без источника"
            suffix = "клиент" if int(count) == 1 else "клиентов"
            self.sources_card.list_widget.addItem(f"{source_label}\n{count} {suffix}")
        if self.sources_card.list_widget.count() == 0:
            self.sources_card.list_widget.addItem("Источники лидов пока не заполнены.")

    @staticmethod
    def _role_to_text(role) -> str:
        mapping = {
            UserRole.admin: "Роль: администратор",
            UserRole.manager: "Роль: менеджер",
            UserRole.trainee: "Роль: стажёр",
            UserRole.user: "Роль: пользователь",
        }
        return mapping.get(role, "Роль: пользователь")
