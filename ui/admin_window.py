from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Optional

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from auth_service import (
    create_user,
    delete_user,
    list_users,
    reset_user_password,
    set_user_active,
    unlock_user,
    update_user,
)
from db import SessionLocal
from models import AuditLog, Car, ChatMessage, ChatRoom, Client, Deal, User, UserRole
from services.workspace_insights import build_staff_snapshot
from theme import populate_theme_menu
from .user_form import UserForm


PKG_ROOT = Path(__file__).resolve().parents[1]
ICON_PATH = PKG_ROOT / "img" / "logo_shukcar.jpg"


class MetricCard(QFrame):
    def __init__(self, title: str, tone: str = "accent", parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        self.setProperty("metric", True)
        self.setProperty("tone", tone)
        self.setMinimumHeight(104)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(4)

        self.lbl_title = QLabel(title, self)
        self.lbl_title.setProperty("role", "title")
        self.lbl_value = QLabel("0", self)
        self.lbl_value.setProperty("role", "value")
        self.lbl_subtitle = QLabel("", self)
        self.lbl_subtitle.setProperty("role", "sub")
        self.lbl_subtitle.setWordWrap(True)

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_subtitle)

    def set_data(self, value: str, subtitle: str):
        self.lbl_value.setText(value)
        self.lbl_subtitle.setText(subtitle)


class AdminWindow(QMainWindow):
    def __init__(self, on_logout: Callable[[], None] | None = None):
        super().__init__()
        self.on_logout = on_logout

        self.setWindowTitle("ShukCar - Администрирование")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

        central = QWidget(self)
        central.setObjectName("AppRoot")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        header = QFrame(self)
        header.setObjectName("TopBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Панель администратора и владельца", header)
        title.setObjectName("HeaderTitle")
        caption = QLabel(
            "Сотрудники, сделки, качество данных, журнал действий и руководительский контроль в одном месте.",
            header,
        )
        caption.setObjectName("PageSubtitle")
        caption.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(caption)
        header_layout.addLayout(title_box, 1)

        self.btn_refresh_all = QPushButton("Обновить всё", header)
        self.btn_refresh_all.setProperty("accent", "secondary")
        theme_button = QToolButton(header)
        theme_button.setText("Оформление")
        theme_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        theme_button.setMenu(QtWidgets.QMenu(theme_button))
        populate_theme_menu(theme_button.menu(), theme_button)
        self.btn_logout = QPushButton("Выйти", header)
        self.btn_logout.setProperty("accent", "danger-secondary")
        self.btn_logout.clicked.connect(self._do_logout)
        self.btn_refresh_all.clicked.connect(self.refresh_all)
        header_layout.addWidget(self.btn_refresh_all, 0)
        header_layout.addWidget(theme_button, 0)
        header_layout.addWidget(self.btn_logout, 0)
        root.addWidget(header, 0)

        metrics_wrap = QWidget(self)
        metrics = QGridLayout(metrics_wrap)
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setHorizontalSpacing(14)
        metrics.setVerticalSpacing(14)

        self.metric_users = MetricCard("Сотрудники", "accent", metrics_wrap)
        self.metric_deals = MetricCard("Сделки в работе", "success", metrics_wrap)
        self.metric_overdue = MetricCard("Просрочки", "danger", metrics_wrap)
        self.metric_archive = MetricCard("Архив", "warning", metrics_wrap)
        self.metric_chats = MetricCard("Коммуникации", "accent", metrics_wrap)
        self.metric_margin = MetricCard("Потенциал маржи", "success", metrics_wrap)

        metrics.addWidget(self.metric_users, 0, 0)
        metrics.addWidget(self.metric_deals, 0, 1)
        metrics.addWidget(self.metric_overdue, 0, 2)
        metrics.addWidget(self.metric_archive, 1, 0)
        metrics.addWidget(self.metric_chats, 1, 1)
        metrics.addWidget(self.metric_margin, 1, 2)
        root.addWidget(metrics_wrap, 0)

        self.tabs = QTabWidget(self)
        root.addWidget(self.tabs, 1)

        self._build_overview_tab()
        self._build_staff_tab()
        self._build_deals_tab()
        self._build_quality_tab()
        self._build_audit_tab()
        self._build_owner_tab()

        self.refresh_all()

    def _build_overview_tab(self):
        page = QWidget(self)
        root = QVBoxLayout(page)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(14)

        self.overview_focus = self._create_table(["Контур", "Значение", "Комментарий"])
        root.addWidget(self._wrap_section("Сводка по системе", self.overview_focus))

        bottom = QHBoxLayout()
        bottom.setSpacing(14)

        self.overview_alerts = QListWidget(page)
        self.overview_recent = QListWidget(page)
        bottom.addWidget(self._wrap_section("Требует внимания", self.overview_alerts), 1)
        bottom.addWidget(self._wrap_section("Последние действия", self.overview_recent), 1)
        root.addLayout(bottom, 1)

        self.tabs.addTab(page, "Обзор")

    def _build_staff_tab(self):
        page = QWidget(self)
        root = QVBoxLayout(page)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)

        toolbar_card = QFrame(page)
        toolbar_card.setProperty("card", True)
        toolbar_layout = QVBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(16, 16, 16, 16)
        toolbar_layout.setSpacing(12)

        heading = QHBoxLayout()
        heading.setSpacing(12)
        heading_text = QVBoxLayout()
        heading_text.setSpacing(2)
        heading_title = QLabel("Команда и доступы", toolbar_card)
        heading_title.setObjectName("SectionTitle")
        heading_caption = QLabel(
            "Управление сотрудниками, ролями и доступом без перегруженного экрана. Список команды слева, живая карточка сотрудника справа.",
            toolbar_card,
        )
        heading_caption.setObjectName("SectionCaption")
        heading_caption.setWordWrap(True)
        heading_text.addWidget(heading_title)
        heading_text.addWidget(heading_caption)
        heading.addLayout(heading_text, 1)
        self.btn_refresh_staff = QPushButton("Обновить", toolbar_card)
        self.btn_refresh_staff.setProperty("accent", "secondary")
        heading.addWidget(self.btn_refresh_staff, 0)
        toolbar_layout.addLayout(heading)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.ed_search = QLineEdit(self)
        self.ed_search.setPlaceholderText("Поиск по ФИО, логину, телефону, e-mail...")
        self.cb_role = QComboBox(self)
        self.cb_role.addItem("Все роли", "")
        for role in (UserRole.admin, UserRole.manager, UserRole.trainee, UserRole.user):
            self.cb_role.addItem(role.value, role.value)
        self.cb_active = QComboBox(self)
        self.cb_active.addItem("Все статусы", "")
        self.cb_active.addItem("Только активные", "active")
        self.cb_active.addItem("Только неактивные", "inactive")
        self.cb_lock = QComboBox(self)
        self.cb_lock.addItem("Любая блокировка", "")
        self.cb_lock.addItem("Только заблокированные", "locked")
        self.cb_lock.addItem("Только без блокировки", "unlocked")
        self.btn_apply_filters = QPushButton("Применить")
        self.btn_apply_filters.setProperty("accent", "secondary")
        filters.addWidget(self.ed_search, 1)
        filters.addWidget(self.cb_role)
        filters.addWidget(self.cb_active)
        filters.addWidget(self.cb_lock)
        filters.addWidget(self.btn_apply_filters)
        toolbar_layout.addLayout(filters)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_add = QPushButton("Новый сотрудник")
        self.btn_edit = QPushButton("Открыть профиль")
        self.btn_reset_password = QPushButton("Сбросить пароль")
        self.btn_unlock = QPushButton("Разблокировать")
        self.btn_toggle_active = QPushButton("Активировать / деактивировать")
        self.btn_del = QPushButton("Удалить")
        self.btn_edit.setProperty("accent", "secondary")
        self.btn_reset_password.setProperty("accent", "secondary")
        self.btn_unlock.setProperty("accent", "secondary")
        self.btn_toggle_active.setProperty("accent", "secondary")
        self.btn_del.setProperty("accent", "danger-secondary")
        self.btn_staff_actions = QToolButton(toolbar_card)
        self.btn_staff_actions.setText("Быстрые действия")
        self.btn_staff_actions.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.staff_actions_menu = QtWidgets.QMenu(self.btn_staff_actions)
        self.staff_actions_menu.addAction("Сбросить пароль", self.on_reset_password)
        self.staff_actions_menu.addAction("Разблокировать вход", self.on_unlock)
        self.staff_actions_menu.addAction("Активировать / деактивировать", self.on_toggle_active)
        self.staff_actions_menu.addSeparator()
        self.staff_actions_menu.addAction("Удалить сотрудника", self.on_delete)
        self.btn_staff_actions.setMenu(self.staff_actions_menu)

        self.btn_reset_password.hide()
        self.btn_unlock.hide()
        self.btn_toggle_active.hide()
        self.btn_del.hide()

        actions.addWidget(self.btn_add)
        actions.addWidget(self.btn_edit)
        actions.addWidget(self.btn_staff_actions)
        actions.addStretch(1)
        toolbar_layout.addLayout(actions)
        root.addWidget(toolbar_card, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal, page)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        left_panel = QFrame(splitter)
        left_panel.setProperty("card", True)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(10)

        list_header = QHBoxLayout()
        list_header.setSpacing(12)
        list_title = QLabel("Сотрудники", left_panel)
        list_title.setObjectName("SectionTitle")
        self.summary_label = QLabel("", left_panel)
        self.summary_label.setObjectName("InlineMutedLabel")
        list_header.addWidget(list_title)
        list_header.addStretch(1)
        list_header.addWidget(self.summary_label)
        left_layout.addLayout(list_header)

        self.tbl = self._create_table(
            [
                "ID",
                "ФИО",
                "Логин",
                "Роль",
                "Активен",
                "Онлайн",
                "Последний вход",
            ]
        )
        left_layout.addWidget(self.tbl, 1)

        self.selection_label = QLabel("Выбрано: —", left_panel)
        self.selection_label.setObjectName("SelectionHint")
        left_layout.addWidget(self.selection_label)

        right_scroll = QScrollArea(splitter)
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)

        right_host = QWidget(right_scroll)
        right_scroll.setWidget(right_host)
        right_layout = QVBoxLayout(right_host)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        profile_card = QFrame(right_host)
        profile_card.setProperty("card", True)
        profile_layout = QVBoxLayout(profile_card)
        profile_layout.setContentsMargins(16, 16, 16, 16)
        profile_layout.setSpacing(12)

        profile_head = QHBoxLayout()
        profile_head.setSpacing(14)
        self.staff_avatar = QLabel("SC", profile_card)
        self.staff_avatar.setObjectName("AvatarBadge")
        self.staff_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.staff_avatar.setFixedSize(58, 58)
        profile_head.addWidget(self.staff_avatar, 0, Qt.AlignmentFlag.AlignTop)

        profile_info = QVBoxLayout()
        profile_info.setSpacing(6)
        self.staff_profile_title = QLabel("Сотрудник не выбран", profile_card)
        self.staff_profile_title.setObjectName("SectionTitle")
        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.staff_role_chip = QLabel("Роль", profile_card)
        self.staff_role_chip.setProperty("chip", True)
        self.staff_status_chip = QLabel("Статус", profile_card)
        self.staff_status_chip.setProperty("chip", True)
        self.staff_online_chip = QLabel("Оффлайн", profile_card)
        self.staff_online_chip.setProperty("chip", True)
        chips.addWidget(self.staff_role_chip, 0, Qt.AlignmentFlag.AlignLeft)
        chips.addWidget(self.staff_status_chip, 0, Qt.AlignmentFlag.AlignLeft)
        chips.addWidget(self.staff_online_chip, 0, Qt.AlignmentFlag.AlignLeft)
        chips.addStretch(1)
        self.staff_login_label = QLabel("Логин, контакты и статус будут показаны здесь.", profile_card)
        self.staff_login_label.setObjectName("SectionCaption")
        self.staff_profile_note = QLabel("Выберите сотрудника, чтобы увидеть нагрузку, просрочки и недавнюю активность.", profile_card)
        self.staff_profile_note.setObjectName("SectionCaption")
        self.staff_profile_note.setWordWrap(True)
        self.staff_security_label = QLabel("Детали по входам, блокировкам и безопасности появятся после выбора.", profile_card)
        self.staff_security_label.setObjectName("InlineMutedLabel")
        self.staff_security_label.setWordWrap(True)
        profile_info.addWidget(self.staff_profile_title)
        profile_info.addLayout(chips)
        profile_info.addWidget(self.staff_login_label)
        profile_info.addWidget(self.staff_profile_note)
        profile_info.addWidget(self.staff_security_label)
        profile_head.addLayout(profile_info, 1)
        profile_layout.addLayout(profile_head)
        right_layout.addWidget(profile_card, 0)

        metrics_wrap = QWidget(right_host)
        metrics = QGridLayout(metrics_wrap)
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        self.staff_metric_deals = MetricCard("Сделки в работе", "accent", metrics_wrap)
        self.staff_metric_clients = MetricCard("Клиенты", "neutral", metrics_wrap)
        self.staff_metric_overdue = MetricCard("Просроченные задачи", "danger", metrics_wrap)
        self.staff_metric_urgent = MetricCard("Срочные кейсы", "warning", metrics_wrap)
        self.staff_metric_blocked = MetricCard("Блокировки", "warning", metrics_wrap)
        self.staff_metric_arrivals = MetricCard("Прибытия 7 дней", "success", metrics_wrap)
        metrics.addWidget(self.staff_metric_deals, 0, 0)
        metrics.addWidget(self.staff_metric_clients, 0, 1)
        metrics.addWidget(self.staff_metric_overdue, 1, 0)
        metrics.addWidget(self.staff_metric_urgent, 1, 1)
        metrics.addWidget(self.staff_metric_blocked, 2, 0)
        metrics.addWidget(self.staff_metric_arrivals, 2, 1)
        right_layout.addWidget(metrics_wrap, 0)

        lower = QHBoxLayout()
        lower.setSpacing(12)
        self.staff_deals_list = QListWidget(right_host)
        self.staff_activity_list = QListWidget(right_host)
        self.staff_deals_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.staff_activity_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.staff_deals_list.setMinimumHeight(220)
        self.staff_activity_list.setMinimumHeight(220)
        lower.addWidget(self._wrap_section("Что у сотрудника в работе", self.staff_deals_list), 1)
        lower.addWidget(self._wrap_section("Последняя активность", self.staff_activity_list), 1)
        right_layout.addLayout(lower, 1)

        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([900, 760])

        self.btn_apply_filters.clicked.connect(self.load_users)
        self.btn_add.clicked.connect(self.on_add)
        self.btn_edit.clicked.connect(self.on_edit)
        self.btn_refresh_staff.clicked.connect(self.load_users)
        self.tbl.itemSelectionChanged.connect(self._update_selection_label)
        self.tbl.itemSelectionChanged.connect(self._load_staff_snapshot)
        self.ed_search.returnPressed.connect(self.load_users)
        self._reset_staff_snapshot()

        self.tabs.addTab(page, "Сотрудники")

    def _build_deals_tab(self):
        page = QWidget(self)
        root = QVBoxLayout(page)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.deals_search = QLineEdit(page)
        self.deals_search.setPlaceholderText("Поиск по сделке, клиенту, VIN, статусу...")
        self.deals_scope = QComboBox(page)
        self.deals_scope.addItem("В работе", "active")
        self.deals_scope.addItem("Архив", "archived")
        self.deals_scope.addItem("Все сделки", "all")
        self.btn_refresh_deals = QPushButton("Показать", page)
        self.btn_refresh_deals.setProperty("accent", "secondary")
        filters.addWidget(self.deals_search, 1)
        filters.addWidget(self.deals_scope)
        filters.addWidget(self.btn_refresh_deals)
        root.addLayout(filters)

        self.deals_table = self._create_table(
            [
                "ID",
                "Сделка",
                "Клиент",
                "Автомобиль",
                "Этап",
                "Статус",
                "Менеджер",
                "Следующий шаг",
                "План прибытия",
                "Архив",
                "Создана",
            ]
        )
        root.addWidget(self.deals_table, 1)

        self.deals_summary_label = QLabel("", page)
        self.deals_summary_label.setObjectName("InlineMutedLabel")
        root.addWidget(self.deals_summary_label)

        self.btn_refresh_deals.clicked.connect(self.load_deals)
        self.deals_search.returnPressed.connect(self.load_deals)
        self.deals_scope.currentIndexChanged.connect(self.load_deals)
        self.tabs.addTab(page, "Сделки")

    def _build_quality_tab(self):
        page = QWidget(self)
        root = QVBoxLayout(page)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)

        self.quality_table = self._create_table(
            ["Контур", "ID", "Объект", "Проблема", "Рекомендация"]
        )
        root.addWidget(self.quality_table, 1)

        self.quality_summary_label = QLabel("", page)
        self.quality_summary_label.setObjectName("InlineMutedLabel")
        root.addWidget(self.quality_summary_label)

        self.tabs.addTab(page, "Качество данных")

    def _build_audit_tab(self):
        page = QWidget(self)
        root = QVBoxLayout(page)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(12)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.audit_search = QLineEdit(page)
        self.audit_search.setPlaceholderText("Поиск по действию, сущности, пользователю, деталям...")
        self.audit_entity = QComboBox(page)
        self.audit_entity.addItem("Все сущности", "")
        for value in ("user", "deal", "car", "client", "chat"):
            self.audit_entity.addItem(value, value)
        self.audit_action = QComboBox(page)
        self.audit_action.addItem("Все действия", "")
        for value in ("create", "update", "delete", "login", "login_fail", "unlock", "password_reset", "activate", "deactivate"):
            self.audit_action.addItem(value, value)
        self.btn_refresh_audit = QPushButton("Показать", page)
        self.btn_refresh_audit.setProperty("accent", "secondary")
        filters.addWidget(self.audit_search, 1)
        filters.addWidget(self.audit_entity)
        filters.addWidget(self.audit_action)
        filters.addWidget(self.btn_refresh_audit)
        root.addLayout(filters)

        self.audit_table = self._create_table(
            ["Время", "Действие", "Сущность", "ID сущности", "ID пользователя", "Детали"]
        )
        root.addWidget(self.audit_table, 1)

        self.audit_summary_label = QLabel("", page)
        self.audit_summary_label.setObjectName("InlineMutedLabel")
        root.addWidget(self.audit_summary_label)

        self.btn_refresh_audit.clicked.connect(self.load_audit)
        self.audit_search.returnPressed.connect(self.load_audit)
        self.audit_entity.currentIndexChanged.connect(self.load_audit)
        self.audit_action.currentIndexChanged.connect(self.load_audit)
        self.tabs.addTab(page, "Журнал действий")

    def _build_owner_tab(self):
        page = QWidget(self)
        root = QVBoxLayout(page)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(14)

        cards_wrap = QWidget(page)
        cards = QGridLayout(cards_wrap)
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setHorizontalSpacing(14)
        cards.setVerticalSpacing(14)

        self.owner_revenue = MetricCard("Оборот", "accent", cards_wrap)
        self.owner_cost = MetricCard("Себестоимость", "warning", cards_wrap)
        self.owner_margin = MetricCard("Потенциал маржи", "success", cards_wrap)
        self.owner_risk = MetricCard("Зоны риска", "danger", cards_wrap)
        cards.addWidget(self.owner_revenue, 0, 0)
        cards.addWidget(self.owner_cost, 0, 1)
        cards.addWidget(self.owner_margin, 0, 2)
        cards.addWidget(self.owner_risk, 0, 3)
        root.addWidget(cards_wrap, 0)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        self.owner_managers = self._create_table(["Менеджер", "Активные сделки", "Архив", "Всего"])
        self.owner_sources = self._create_table(["Источник", "Сделки", "Клиенты"])
        self.owner_stages = self._create_table(["Этап", "Количество"])
        grid.addWidget(self._wrap_section("Нагрузка по менеджерам", self.owner_managers), 0, 0)
        grid.addWidget(self._wrap_section("Источники лидов", self.owner_sources), 0, 1)
        grid.addWidget(self._wrap_section("Воронка по этапам", self.owner_stages), 1, 0, 1, 2)
        root.addLayout(grid, 1)

        self.owner_note_label = QLabel("", page)
        self.owner_note_label.setObjectName("InlineMutedLabel")
        self.owner_note_label.setWordWrap(True)
        root.addWidget(self.owner_note_label)

        self.tabs.addTab(page, "Владелец")

    def _create_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers), self)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)
        return table

    def _wrap_section(self, title: str, widget: QWidget) -> QFrame:
        card = QFrame(self)
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        label = QLabel(title, card)
        label.setObjectName("SectionTitle")
        layout.addWidget(label)
        layout.addWidget(widget, 1)
        return card

    def _do_logout(self):
        if callable(self.on_logout):
            self.on_logout()

    def _format_dt(self, value) -> str:
        return value.strftime("%d.%m.%Y %H:%M") if value else ""

    def _format_date(self, value) -> str:
        return value.strftime("%d.%m.%Y") if value else ""

    def _role_label(self, role) -> str:
        mapping = {
            UserRole.admin: "Администратор",
            UserRole.manager: "Менеджер",
            UserRole.trainee: "Стажёр",
            UserRole.user: "Пользователь",
        }
        return mapping.get(role, getattr(role, "value", None) or str(role))

    def _initials(self, value: str | None) -> str:
        text = (value or "").strip()
        if not text:
            return "SC"
        parts = [part for part in text.replace("-", " ").split() if part]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return text[:2].upper()

    def _format_money(self, value) -> str:
        if value in (None, ""):
            return "—"
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return str(value)
        if amount == amount.to_integral():
            return f"{int(amount):,}".replace(",", " ") + " ₽"
        return f"{amount:,.2f}".replace(",", " ").replace(".", ",") + " ₽"

    def _car_label(self, car: Car | None) -> str:
        if not car:
            return "—"
        parts = [
            getattr(car.brand, "name", None),
            getattr(car.model, "name", None),
            getattr(car.trim, "name", None),
        ]
        text = " ".join(part for part in parts if part)
        if text:
            return text
        return car.vin or f"Авто #{car.id}"

    def _selected_user_id(self) -> Optional[int]:
        selected = self.tbl.selectedItems()
        if not selected:
            return None
        row = self.tbl.currentRow()
        item = self.tbl.item(row, 0)
        return int(item.text()) if item else None

    def _selected_user(self) -> Optional[User]:
        user_id = self._selected_user_id()
        if user_id is None:
            return None
        with SessionLocal() as db:
            return db.get(User, user_id)

    def _reset_staff_snapshot(self, note: str | None = None):
        self.staff_avatar.setText("SC")
        self.staff_profile_title.setText("Сотрудник не выбран")
        self.staff_role_chip.hide()
        self.staff_status_chip.hide()
        self.staff_online_chip.hide()
        self.staff_login_label.setText("Логин, контакты и статус будут показаны здесь.")
        self.staff_profile_note.setText(
            note or "Выберите сотрудника, чтобы увидеть нагрузку, просрочки и недавнюю активность."
        )
        self.staff_security_label.setText("Детали по входам, блокировкам и безопасности появятся после выбора.")
        self.staff_metric_deals.set_data("—", "Активные и архивные сделки сотрудника.")
        self.staff_metric_clients.set_data("—", "Закреплённые клиенты.")
        self.staff_metric_overdue.set_data("—", "Просрочки по сделкам и авто.")
        self.staff_metric_urgent.set_data("—", "Сделки с высоким и срочным приоритетом.")
        self.staff_metric_blocked.set_data("—", "Кейсы, где есть явная блокировка.")
        self.staff_metric_arrivals.set_data("—", "Контроль прибытия в ближайшие 7 дней.")
        self.staff_deals_list.clear()
        self.staff_activity_list.clear()
        self.staff_deals_list.addItem("Выберите сотрудника в таблице выше.")
        self.staff_activity_list.addItem("История активности появится после выбора сотрудника.")

    def _load_staff_snapshot(self):
        user_id = self._selected_user_id()
        if not user_id:
            self._reset_staff_snapshot()
            return

        with SessionLocal() as db:
            snapshot = build_staff_snapshot(db, user_id)

        user = snapshot.get("user")
        if user is None:
            self._reset_staff_snapshot("Сотрудник не найден.")
            return

        metrics = snapshot["metrics"]
        online_state = "онлайн" if user.is_online else "оффлайн"
        self.staff_avatar.setText(self._initials(user.full_name or user.login))
        self.staff_profile_title.setText(user.full_name or user.login or "Сотрудник")
        self.staff_role_chip.setText(self._role_label(user.role))
        self.staff_status_chip.setText("Активен" if user.is_active else "Выключен")
        self.staff_online_chip.setText("Онлайн" if user.is_online else "Оффлайн")
        self.staff_role_chip.show()
        self.staff_status_chip.show()
        self.staff_online_chip.show()
        self.staff_login_label.setText(
            f"Логин: {user.login or '—'} · Телефон: {user.phone or '—'} · E-mail: {user.email or '—'}"
        )
        self.staff_profile_note.setText(
            f"Последний вход: {self._format_dt(user.last_login) or '—'} · "
            f"Последняя активность: {self._format_dt(user.last_activity) or '—'}"
        )
        self.staff_security_label.setText(
            f"Ошибок входа: {user.failed_attempts or 0} · Блок до: {self._format_dt(user.lock_until) or '—'} · "
            f"Статус в системе: {online_state}"
        )
        self.staff_metric_deals.set_data(
            str(metrics["active_deals"]),
            f"В архиве: {metrics['archived_deals']}",
        )
        self.staff_metric_clients.set_data(
            str(metrics["active_clients"]),
            "Клиенты, закреплённые за сотрудником.",
        )
        self.staff_metric_overdue.set_data(
            str(metrics["overdue_tasks"]),
            "Сначала нужно разбирать эти задачи.",
        )
        self.staff_metric_urgent.set_data(
            str(metrics["urgent_deals"]),
            "Высокий и срочный приоритет.",
        )
        self.staff_metric_blocked.set_data(
            str(metrics["blocked_deals"]),
            "Сделки со стоп-факторами.",
        )
        self.staff_metric_arrivals.set_data(
            str(metrics["arrivals_soon"]),
            "Прибытия в ближайшие 7 дней.",
        )

        self.staff_deals_list.clear()
        for row in snapshot["deal_rows"]:
            self.staff_deals_list.addItem(
                f"{row['title']}\n{row['client']} · {row['stage']} · {row['priority']}\n"
                f"{row['next_action']} · {row['next_action_date']}"
            )
        if self.staff_deals_list.count() == 0:
            self.staff_deals_list.addItem("У сотрудника сейчас нет активных сделок.")

        self.staff_activity_list.clear()
        for row in snapshot["activity_rows"]:
            created = self._format_dt(row["created_at"]) or "—"
            self.staff_activity_list.addItem(f"{created} · {row['title']}\n{row['details']}")
        if self.staff_activity_list.count() == 0:
            self.staff_activity_list.addItem("Недавней активности пока нет.")

    def _passes_filters(self, user: User) -> bool:
        search = self.ed_search.text().strip().lower()
        if search:
            haystack = " ".join(filter(None, [user.full_name or "", user.login or "", user.phone or "", user.email or ""])).lower()
            if search not in haystack:
                return False
        role_value = self.cb_role.currentData()
        if role_value and user.role.value != role_value:
            return False
        active_value = self.cb_active.currentData()
        if active_value == "active" and not user.is_active:
            return False
        if active_value == "inactive" and user.is_active:
            return False
        lock_value = self.cb_lock.currentData()
        is_locked = user.lock_until is not None
        if lock_value == "locked" and not is_locked:
            return False
        if lock_value == "unlocked" and is_locked:
            return False
        return True

    def _set_table_rows(self, table: QTableWidget, rows: list[list[str]]):
        table.setRowCount(0)
        for values in rows:
            row = table.rowCount()
            table.insertRow(row)
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        table.resizeColumnsToContents()

    def refresh_all(self):
        self.load_overview()
        self.load_users()
        self.load_deals()
        self.load_quality()
        self.load_audit()
        self.load_owner()

    def load_overview(self):
        today = date.today()
        start_today = datetime.combine(today, datetime.min.time())
        with SessionLocal() as db:
            users_total = db.query(User).count()
            users_active = db.query(User).filter(User.is_active.is_(True)).count()
            users_online = db.query(User).filter(User.is_online.is_(True)).count()
            users_locked = db.query(User).filter(User.lock_until.is_not(None)).count()
            deals_active = db.query(Deal).filter(or_(Deal.is_archived.is_(False), Deal.is_archived.is_(None))).count()
            deals_archived = db.query(Deal).filter(Deal.is_archived.is_(True)).count()
            deals_overdue = db.query(Deal).filter(
                or_(Deal.is_archived.is_(False), Deal.is_archived.is_(None)),
                Deal.next_action_date.is_not(None),
                Deal.next_action_date < today,
            ).count()
            cars_total = db.query(Car).count()
            cars_without_client = db.query(Car).filter(Car.client_id.is_(None)).count()
            clients_total = db.query(Client).count()
            clients_without_phone = db.query(Client).filter(or_(Client.phone.is_(None), Client.phone == "")).count()
            chat_rooms = db.query(ChatRoom).count()
            messages_today = db.query(ChatMessage).filter(ChatMessage.created_at >= start_today).count()
            active_cars = db.query(Car).filter(or_(Car.is_archived.is_(False), Car.is_archived.is_(None))).all()
            recent_logs = db.query(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(8).all()

        revenue = sum(Decimal(str(car.price_customer or 0)) for car in active_cars)
        cost = sum(Decimal(str(car.price_to_vladivostok or 0)) for car in active_cars)
        margin = revenue - cost

        self.metric_users.set_data(f"{users_active}/{users_total}", f"Активные сотрудники · онлайн: {users_online}")
        self.metric_deals.set_data(str(deals_active), "Сделки, которые сейчас в работе.")
        self.metric_overdue.set_data(str(deals_overdue), f"Заблокировано сотрудников: {users_locked}")
        self.metric_archive.set_data(str(deals_archived), f"Архивных сделок · авто без клиента: {cars_without_client}")
        self.metric_chats.set_data(str(chat_rooms), f"Чатов всего · сообщений сегодня: {messages_today}")
        self.metric_margin.set_data(self._format_money(margin), f"Оборот {self._format_money(revenue)} · себестоимость {self._format_money(cost)}")

        focus_rows = [
            ["Сотрудники", f"{users_total}", f"Активных {users_active}, онлайн {users_online}, блокировок {users_locked}"],
            ["Сделки", f"{deals_active}", f"В архиве {deals_archived}, просрочено {deals_overdue}"],
            ["Автопарк", f"{cars_total}", f"Без клиента {cars_without_client}"],
            ["Клиенты", f"{clients_total}", f"Без телефона {clients_without_phone}"],
            ["Чаты", f"{chat_rooms}", f"Сообщений за сегодня {messages_today}"],
            ["Финансы", self._format_money(margin), "Потенциальная маржа по активным карточкам"],
        ]
        self._set_table_rows(self.overview_focus, focus_rows)

        self.overview_alerts.clear()
        alerts = []
        if deals_overdue:
            alerts.append(f"Просроченные сделки: {deals_overdue}")
        if cars_without_client:
            alerts.append(f"Автомобили без клиента: {cars_without_client}")
        if clients_without_phone:
            alerts.append(f"Клиенты без телефона: {clients_without_phone}")
        if users_locked:
            alerts.append(f"Заблокированные сотрудники: {users_locked}")
        if not alerts:
            alerts.append("Критичных проблем сейчас не обнаружено.")
        for text in alerts:
            self.overview_alerts.addItem(QListWidgetItem(text))

        self.overview_recent.clear()
        for row in recent_logs:
            text = f"{self._format_dt(row.created_at)} · {row.action} · {row.entity} #{row.entity_id or '—'}"
            if row.details:
                text += f"\n{row.details}"
            self.overview_recent.addItem(QListWidgetItem(text))

    def load_users(self):
        previous_user_id = self._selected_user_id()
        with SessionLocal() as db:
            users = [user for user in list_users(db) if self._passes_filters(user)]

        active_count = sum(1 for user in users if user.is_active)
        online_count = sum(1 for user in users if user.is_online)
        locked_count = sum(1 for user in users if user.lock_until)
        rows = []
        for user in users:
            rows.append(
                [
                    str(user.id),
                    user.full_name or "",
                    user.login or "",
                    user.role.value,
                    "Да" if user.is_active else "Нет",
                    "Да" if user.is_online else "Нет",
                    self._format_dt(user.last_login),
                ]
            )
        self._set_table_rows(self.tbl, rows)
        self.summary_label.setText(
            f"Всего: {len(users)} · Активных: {active_count} · Онлайн: {online_count} · Заблокировано: {locked_count}"
        )
        if self.tbl.rowCount() > 0:
            target_row = 0
            if previous_user_id is not None:
                for row in range(self.tbl.rowCount()):
                    item = self.tbl.item(row, 0)
                    if item and item.text() == str(previous_user_id):
                        target_row = row
                        break
            self.tbl.setCurrentCell(target_row, 0)
        else:
            self._reset_staff_snapshot("Сотрудники по выбранным фильтрам не найдены.")
        self._update_selection_label()

    def _update_selection_label(self):
        selected = self.tbl.selectedItems()
        if not selected:
            self.selection_label.setText("Выбрано: —")
            return
        row = self.tbl.currentRow()
        uid = self.tbl.item(row, 0).text()
        fio = self.tbl.item(row, 1).text()
        role = self.tbl.item(row, 3).text()
        active = self.tbl.item(row, 4).text()
        self.selection_label.setText(f"Выбрано: ID {uid} — {fio} · {role} · Активен: {active}")

    def load_deals(self):
        search = self.deals_search.text().strip()
        scope = self.deals_scope.currentData()
        with SessionLocal() as db:
            query = (
                db.query(Deal)
                .options(
                    joinedload(Deal.client),
                    joinedload(Deal.responsible_user),
                    joinedload(Deal.deal_stage),
                    joinedload(Deal.car).joinedload(Car.brand),
                    joinedload(Deal.car).joinedload(Car.model),
                    joinedload(Deal.car).joinedload(Car.trim),
                )
                .order_by(Deal.created_at.desc(), Deal.id.desc())
            )
            if scope == "active":
                query = query.filter(or_(Deal.is_archived.is_(False), Deal.is_archived.is_(None)))
            elif scope == "archived":
                query = query.filter(Deal.is_archived.is_(True))
            if search:
                like = f"%{search}%"
                query = query.outerjoin(Client, Client.id == Deal.client_id).outerjoin(Car, Car.id == Deal.car_id).filter(
                    or_(
                        Deal.title.ilike(like),
                        Deal.deal_status.ilike(like),
                        Client.full_name.ilike(like),
                        Car.vin.ilike(like),
                    )
                )
            deals = query.limit(200).all()

        rows = []
        active_count = 0
        archived_count = 0
        overdue_count = 0
        today = date.today()
        for deal in deals:
            if deal.is_archived:
                archived_count += 1
            else:
                active_count += 1
            if deal.next_action_date and deal.next_action_date < today and not deal.is_archived:
                overdue_count += 1
            manager = getattr(deal.responsible_user, "full_name", None) or getattr(deal.responsible_user, "login", None) or ""
            rows.append(
                [
                    str(deal.id),
                    deal.title or "",
                    deal.client.full_name if deal.client else "",
                    self._car_label(deal.car),
                    getattr(deal.deal_stage, "name", None) or "",
                    deal.deal_status or "",
                    manager,
                    self._format_date(deal.next_action_date),
                    self._format_date(deal.expected_arrival_date),
                    "Да" if deal.is_archived else "Нет",
                    self._format_dt(deal.created_at),
                ]
            )
        self._set_table_rows(self.deals_table, rows)
        self.deals_summary_label.setText(
            f"Найдено: {len(deals)} · В работе: {active_count} · Архив: {archived_count} · Просрочено: {overdue_count}"
        )

    def load_quality(self):
        with SessionLocal() as db:
            cars_no_client = db.query(Car).options(joinedload(Car.brand), joinedload(Car.model), joinedload(Car.trim)).filter(Car.client_id.is_(None)).limit(8).all()
            cars_no_vin = db.query(Car).options(joinedload(Car.brand), joinedload(Car.model), joinedload(Car.trim)).filter(or_(Car.vin.is_(None), Car.vin == "")).limit(8).all()
            deals_no_action = db.query(Deal).options(joinedload(Deal.client), joinedload(Deal.car).joinedload(Car.brand), joinedload(Deal.car).joinedload(Car.model), joinedload(Deal.car).joinedload(Car.trim)).filter(
                or_(Deal.is_archived.is_(False), Deal.is_archived.is_(None)),
                Deal.next_action_date.is_(None),
            ).limit(8).all()
            deals_overdue = db.query(Deal).options(joinedload(Deal.client), joinedload(Deal.car).joinedload(Car.brand), joinedload(Deal.car).joinedload(Car.model), joinedload(Deal.car).joinedload(Car.trim)).filter(
                or_(Deal.is_archived.is_(False), Deal.is_archived.is_(None)),
                Deal.next_action_date.is_not(None),
                Deal.next_action_date < date.today(),
            ).limit(8).all()
            clients_no_phone = db.query(Client).filter(or_(Client.phone.is_(None), Client.phone == "")).limit(8).all()
            clients_no_email = db.query(Client).filter(or_(Client.email.is_(None), Client.email == "")).limit(8).all()
            all_clients = db.query(Client).all()

        rows = []
        duplicate_phones = Counter((client.phone or "").strip() for client in all_clients if (client.phone or "").strip())
        duplicate_phones = {value for value, count in duplicate_phones.items() if count > 1}

        for car in cars_no_client:
            rows.append(["Авто", str(car.id), self._car_label(car), "Не привязан клиент", "Назначить клиента или отправить в архив"])
        for car in cars_no_vin:
            rows.append(["Авто", str(car.id), self._car_label(car), "Не заполнен VIN", "Проверить карточку и внести VIN"])
        for deal in deals_no_action:
            rows.append(["Сделка", str(deal.id), deal.title or self._car_label(deal.car), "Нет следующего действия", "Назначить дату и заметку следующего шага"])
        for deal in deals_overdue:
            rows.append(["Сделка", str(deal.id), deal.title or self._car_label(deal.car), "Просрочено следующее действие", "Связаться с менеджером и обновить план"])
        for client in clients_no_phone:
            rows.append(["Клиент", str(client.id), client.full_name, "Нет телефона", "Добавить контакт для связи"])
        for client in clients_no_email:
            rows.append(["Клиент", str(client.id), client.full_name, "Нет e-mail", "Уточнить e-mail или пометить как не требуется"])
        for client in all_clients:
            phone = (client.phone or "").strip()
            if phone and phone in duplicate_phones:
                rows.append(["Клиент", str(client.id), client.full_name, f"Дублируется телефон {phone}", "Проверить на дубль карточки"])

        self._set_table_rows(self.quality_table, rows[:200])
        self.quality_summary_label.setText(
            f"Проблемы: {len(rows)} · Без клиента: {len(cars_no_client)} · Без VIN: {len(cars_no_vin)} · Без шага: {len(deals_no_action)} · Просрочки: {len(deals_overdue)}"
        )

    def load_audit(self):
        search = self.audit_search.text().strip().lower()
        entity = self.audit_entity.currentData()
        action = self.audit_action.currentData()
        with SessionLocal() as db:
            logs = db.query(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(250).all()

        filtered = []
        for log in logs:
            if entity and log.entity != entity:
                continue
            if action and log.action != action:
                continue
            if search:
                haystack = " ".join(
                    filter(
                        None,
                        [
                            log.action or "",
                            log.entity or "",
                            str(log.entity_id or ""),
                            str(log.user_id or ""),
                            log.details or "",
                        ],
                    )
                ).lower()
                if search not in haystack:
                    continue
            filtered.append(log)

        rows = [
            [
                self._format_dt(log.created_at),
                log.action or "",
                log.entity or "",
                str(log.entity_id or ""),
                str(log.user_id or ""),
                log.details or "",
            ]
            for log in filtered
        ]
        self._set_table_rows(self.audit_table, rows)
        self.audit_summary_label.setText(f"Показано записей: {len(filtered)}")

    def load_owner(self):
        today = date.today()
        with SessionLocal() as db:
            deals = db.query(Deal).options(joinedload(Deal.responsible_user), joinedload(Deal.deal_stage)).all()
            cars = db.query(Car).all()
            clients = db.query(Client).all()

        active_deals = [deal for deal in deals if not deal.is_archived]
        archived_deals = [deal for deal in deals if deal.is_archived]
        overdue_deals = [deal for deal in active_deals if deal.next_action_date and deal.next_action_date < today]
        active_cars = [car for car in cars if not bool(car.is_archived)]

        revenue = sum(Decimal(str(car.price_customer or 0)) for car in active_cars)
        cost = sum(Decimal(str(car.price_to_vladivostok or 0)) for car in active_cars)
        margin = revenue - cost

        self.owner_revenue.set_data(self._format_money(revenue), "Потенциальный оборот по активным авто.")
        self.owner_cost.set_data(self._format_money(cost), "Ориентир по себестоимости активного парка.")
        self.owner_margin.set_data(self._format_money(margin), f"Активных сделок: {len(active_deals)}")
        self.owner_risk.set_data(str(len(overdue_deals)), f"Просрочки · архивных сделок: {len(archived_deals)}")

        manager_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"active": 0, "archived": 0})
        for deal in deals:
            name = getattr(deal.responsible_user, "full_name", None) or getattr(deal.responsible_user, "login", None) or "Не назначен"
            if deal.is_archived:
                manager_stats[name]["archived"] += 1
            else:
                manager_stats[name]["active"] += 1

        manager_rows = []
        for name, stats in sorted(manager_stats.items(), key=lambda item: (item[1]["active"] + item[1]["archived"]), reverse=True):
            total = stats["active"] + stats["archived"]
            manager_rows.append([name, str(stats["active"]), str(stats["archived"]), str(total)])
        self._set_table_rows(self.owner_managers, manager_rows)

        deal_sources = Counter((deal.lead_source or "Не указан").strip() or "Не указан" for deal in deals)
        client_sources = Counter((client.lead_source or "Не указан").strip() or "Не указан" for client in clients)
        source_rows = []
        for source in sorted(set(deal_sources.keys()) | set(client_sources.keys()), key=lambda value: deal_sources[value] + client_sources[value], reverse=True):
            source_rows.append([source, str(deal_sources[source]), str(client_sources[source])])
        self._set_table_rows(self.owner_sources, source_rows)

        stage_rows = []
        stage_counts = Counter((getattr(deal.deal_stage, "name", None) or "Без этапа") for deal in active_deals)
        for stage, count in stage_counts.most_common():
            stage_rows.append([stage, str(count)])
        self._set_table_rows(self.owner_stages, stage_rows)

        self.owner_note_label.setText(
            f"Сейчас под особым вниманием: просроченных сделок {len(overdue_deals)}, автомобилей без клиента "
            f"{sum(1 for car in cars if car.client_id is None)} и клиентов без телефона "
            f"{sum(1 for client in clients if not (client.phone or '').strip())}."
        )

    def on_add(self):
        dlg = UserForm(self)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        if not data["full_name"] or not data["login"]:
            QMessageBox.warning(self, "Ошибка", "ФИО и логин обязательны.")
            return
        if not data["password"]:
            QMessageBox.warning(self, "Ошибка", "Пароль обязателен.")
            return
        with SessionLocal() as db:
            try:
                create_user(
                    db,
                    login=data["login"],
                    password=data["password"],
                    full_name=data["full_name"],
                    date_of_birth=data["date_of_birth"],
                    phone=data["phone"],
                    email=data["email"],
                    role=data["role"],
                    is_active=data["is_active"],
                )
            except ValueError as exc:
                QMessageBox.critical(self, "Ошибка", str(exc))
                return
        self.refresh_all()

    def on_edit(self):
        user_id = self._selected_user_id()
        if not user_id:
            QMessageBox.information(self, "Выбор", "Выберите пользователя в списке.")
            return
        with SessionLocal() as db:
            user = db.get(User, user_id)
            if not user:
                QMessageBox.warning(self, "Ошибка", "Пользователь не найден.")
                return
            dlg = UserForm(self, user=user)
            if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                return
            data = dlg.get_data()
            try:
                update_user(
                    db,
                    user_id,
                    login=data["login"] or user.login,
                    full_name=data["full_name"] or user.full_name,
                    date_of_birth=data["date_of_birth"] if data["date_of_birth"] is not None else user.date_of_birth,
                    phone=data["phone"],
                    email=data["email"],
                    role=data["role"],
                    is_active=data["is_active"],
                    password=data["password"] or None,
                )
            except ValueError as exc:
                QMessageBox.critical(self, "Ошибка", str(exc))
                return
        self.refresh_all()

    def on_reset_password(self):
        user_id = self._selected_user_id()
        if not user_id:
            QMessageBox.information(self, "Выбор", "Выберите сотрудника.")
            return
        password, ok = QInputDialog.getText(self, "Сброс пароля", "Новый пароль:", QtWidgets.QLineEdit.EchoMode.Password)
        if not ok:
            return
        if not password.strip():
            QMessageBox.warning(self, "Пароль", "Пароль не может быть пустым.")
            return
        with SessionLocal() as db:
            try:
                reset_user_password(db, user_id, password)
            except ValueError as exc:
                QMessageBox.critical(self, "Ошибка", str(exc))
                return
        QMessageBox.information(self, "Готово", "Пароль сотрудника обновлён.")
        self.refresh_all()

    def on_unlock(self):
        user_id = self._selected_user_id()
        if not user_id:
            QMessageBox.information(self, "Выбор", "Выберите сотрудника.")
            return
        with SessionLocal() as db:
            try:
                unlock_user(db, user_id)
            except ValueError as exc:
                QMessageBox.critical(self, "Ошибка", str(exc))
                return
        QMessageBox.information(self, "Готово", "Блокировка и ошибки входа сброшены.")
        self.refresh_all()

    def on_toggle_active(self):
        user = self._selected_user()
        if not user:
            QMessageBox.information(self, "Выбор", "Выберите сотрудника.")
            return
        target_active = not bool(user.is_active)
        action_text = "активировать" if target_active else "деактивировать"
        result = QMessageBox.question(
            self,
            "Подтверждение",
            f"Вы действительно хотите {action_text} сотрудника «{user.full_name or user.login}»?",
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as db:
            try:
                set_user_active(db, int(user.id), target_active)
            except ValueError as exc:
                QMessageBox.critical(self, "Ошибка", str(exc))
                return
        self.refresh_all()

    def on_delete(self):
        user = self._selected_user()
        if not user:
            QMessageBox.information(self, "Выбор", "Выберите сотрудника.")
            return
        result = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить сотрудника «{user.full_name or user.login}»?",
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        with SessionLocal() as db:
            try:
                delete_user(db, int(user.id))
            except ValueError as exc:
                QMessageBox.critical(self, "Ошибка", str(exc))
                return
        self.refresh_all()
