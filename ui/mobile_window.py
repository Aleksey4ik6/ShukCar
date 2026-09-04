from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import or_
from sqlalchemy.orm import joinedload, selectinload

from db import SessionLocal
from models import Car, Client, Deal, User
from services.chat_service import (
    ensure_general_room,
    get_or_create_direct_room,
    list_messages,
    list_rooms_for_user,
    mark_room_read,
    room_display_name,
    send_message,
)
from theme import THEMES, theme_controller
from ui.calculator_view import CalculatorView
from ui.chat_view import DirectChatDialog


PKG_ROOT = Path(__file__).resolve().parents[1]
ICON_PATH = PKG_ROOT / "img" / "logo_shukcar.jpg"


def _make_card(parent: QWidget | None = None, object_name: str | None = None) -> QFrame:
    card = QFrame(parent)
    card.setProperty("card", True)
    if object_name:
        card.setObjectName(object_name)
    return card


def _make_chip(text: str, parent: QWidget | None = None) -> QLabel:
    label = QLabel(text, parent)
    label.setProperty("chip", True)
    return label


def _avatar_text(user: User | None) -> str:
    raw = ""
    if user is not None:
        raw = (user.full_name or user.login or "").strip()
    parts = [part for part in raw.split() if part]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    if raw:
        return raw[:2].upper()
    return "SC"


def _money(value) -> str:
    if value in (None, ""):
        return "—"
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    if amount == amount.to_integral():
        return f"{int(amount):,}".replace(",", " ") + " ₽"
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",") + " ₽"


def _car_title(car: Car) -> str:
    parts = [
        getattr(car.brand, "name", None),
        getattr(car.model, "name", None),
        getattr(car.trim, "name", None),
    ]
    text = " ".join(part for part in parts if part)
    return text or f"Автомобиль #{car.id}"


def _role_label(user: User) -> str:
    value = str(getattr(user, "role", "") or "").split(".")[-1]
    return {
        "admin": "Администратор",
        "manager": "Менеджер",
        "trainee": "Стажёр",
        "user": "Сотрудник",
    }.get(value, "Сотрудник")


class DismissOverlay(QWidget):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class _MetricCard(QFrame):
    def __init__(self, title: str, tone: str = "accent", parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        self.setProperty("metric", True)
        self.setProperty("tone", tone)

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


class MobileSettingsDialog(QDialog):
    def __init__(self, current_user: User, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки mobile-режима")
        self.resize(460, 300)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        title = QLabel("Оформление и рабочая среда", self)
        title.setObjectName("SectionTitle")
        caption = QLabel(
            "Здесь можно переключить тему и посмотреть краткую информацию о текущем сотруднике.",
            self,
        )
        caption.setWordWrap(True)
        caption.setObjectName("InlineMutedLabel")
        root.addWidget(title)
        root.addWidget(caption)

        info_card = _make_card(self)
        info_layout = QGridLayout(info_card)
        info_layout.setContentsMargins(16, 16, 16, 16)
        info_layout.setHorizontalSpacing(12)
        info_layout.setVerticalSpacing(8)

        info_layout.addWidget(QLabel("Сотрудник", info_card), 0, 0)
        info_layout.addWidget(QLabel(current_user.full_name or current_user.login or "—", info_card), 0, 1)
        info_layout.addWidget(QLabel("Роль", info_card), 1, 0)
        info_layout.addWidget(QLabel(_role_label(current_user), info_card), 1, 1)

        self.theme_combo = QComboBox(info_card)
        for name, theme in THEMES.items():
            self.theme_combo.addItem(theme.label, name)
        self.theme_combo.currentIndexChanged.connect(self._apply_theme)
        info_layout.addWidget(QLabel("Тема", info_card), 2, 0)
        info_layout.addWidget(self.theme_combo, 2, 1)
        root.addWidget(info_card)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        button_box.rejected.connect(self.reject)
        root.addWidget(button_box)

        self._sync_theme(theme_controller.current_theme())
        theme_controller.theme_changed.connect(self._sync_theme)

    def _sync_theme(self, theme_name: str):
        index = self.theme_combo.findData(theme_name)
        if index >= 0 and index != self.theme_combo.currentIndex():
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(index)
            self.theme_combo.blockSignals(False)

    def _apply_theme(self):
        theme_name = self.theme_combo.currentData()
        if theme_name:
            theme_controller.set_theme(str(theme_name))


class MobileHomeView(QWidget):
    navigate = pyqtSignal(str)

    def __init__(self, current_user: User, parent=None):
        super().__init__(parent)
        self.current_user = current_user

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll, 1)

        content = QWidget(scroll)
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(14)
        scroll.setWidget(content)

        hero = _make_card(content, "MobileHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 22, 22, 22)
        hero_layout.setSpacing(10)

        hero_kicker = QLabel("SHUKCAR MOBILE WORKSPACE", hero)
        hero_kicker.setObjectName("HeroKicker")
        self.lbl_welcome = QLabel("Добро пожаловать", hero)
        self.lbl_welcome.setObjectName("HomeWelcome")
        self.lbl_caption = QLabel("", hero)
        self.lbl_caption.setObjectName("HeroCaption")
        self.lbl_caption.setWordWrap(True)

        quick_grid = QGridLayout()
        quick_grid.setHorizontalSpacing(10)
        quick_grid.setVerticalSpacing(10)
        self.quick_buttons: dict[str, QPushButton] = {}
        for key, text in (
            ("deals", "Сделки"),
            ("cars", "Автомобили"),
            ("clients", "Клиенты"),
            ("chat", "Чат"),
            ("calc", "Калькулятор"),
        ):
            button = QPushButton(text, hero)
            button.setProperty("quickTile", True)
            button.clicked.connect(lambda _=False, page=key: self.navigate.emit(page))
            self.quick_buttons[key] = button

        for index, key in enumerate(("deals", "cars", "clients", "chat", "calc")):
            button = self.quick_buttons.get(key)
            if button is None:
                continue
            quick_grid.addWidget(button, index // 2, index % 2)

        hero_layout.addWidget(hero_kicker)
        hero_layout.addWidget(self.lbl_welcome)
        hero_layout.addWidget(self.lbl_caption)
        hero_layout.addSpacing(4)
        hero_layout.addLayout(quick_grid)
        self.content_layout.addWidget(hero)

        metrics_wrap = QWidget(content)
        self.metrics_grid = QGridLayout(metrics_wrap)
        self.metrics_grid.setContentsMargins(0, 0, 0, 0)
        self.metrics_grid.setHorizontalSpacing(14)
        self.metrics_grid.setVerticalSpacing(14)

        self.metric_cars = _MetricCard("Автомобили", "accent", metrics_wrap)
        self.metric_deals = _MetricCard("Сделки в работе", "success", metrics_wrap)
        self.metric_archive = _MetricCard("Архив", "warning", metrics_wrap)
        self.metric_chat = _MetricCard("Чаты", "accent", metrics_wrap)

        self.metrics_grid.addWidget(self.metric_cars, 0, 0)
        self.metrics_grid.addWidget(self.metric_deals, 0, 1)
        self.metrics_grid.addWidget(self.metric_archive, 1, 0)
        self.metrics_grid.addWidget(self.metric_chat, 1, 1)
        self.content_layout.addWidget(metrics_wrap)

        self.focus_card = _make_card(content)
        focus_layout = QVBoxLayout(self.focus_card)
        focus_layout.setContentsMargins(18, 18, 18, 18)
        focus_layout.setSpacing(8)
        focus_title = QLabel("Фокус на сегодня", self.focus_card)
        focus_title.setObjectName("SectionTitle")
        self.lbl_focus = QLabel("", self.focus_card)
        self.lbl_focus.setObjectName("InlineMutedLabel")
        self.lbl_focus.setWordWrap(True)
        focus_layout.addWidget(focus_title)
        focus_layout.addWidget(self.lbl_focus)
        self.content_layout.addWidget(self.focus_card)

        columns = QWidget(content)
        columns_layout = QVBoxLayout(columns)
        columns_layout.setContentsMargins(0, 0, 0, 0)
        columns_layout.setSpacing(14)

        self.latest_cars_card = _make_card(columns)
        latest_cars_layout = QVBoxLayout(self.latest_cars_card)
        latest_cars_layout.setContentsMargins(18, 18, 18, 18)
        latest_cars_layout.setSpacing(8)
        latest_cars_title = QLabel("Последние автомобили", self.latest_cars_card)
        latest_cars_title.setObjectName("SectionTitle")
        self.lbl_latest_cars = QLabel("", self.latest_cars_card)
        self.lbl_latest_cars.setWordWrap(True)
        latest_cars_layout.addWidget(latest_cars_title)
        latest_cars_layout.addWidget(self.lbl_latest_cars)

        self.latest_clients_card = _make_card(columns)
        latest_clients_layout = QVBoxLayout(self.latest_clients_card)
        latest_clients_layout.setContentsMargins(18, 18, 18, 18)
        latest_clients_layout.setSpacing(8)
        latest_clients_title = QLabel("Последние клиенты", self.latest_clients_card)
        latest_clients_title.setObjectName("SectionTitle")
        self.lbl_latest_clients = QLabel("", self.latest_clients_card)
        self.lbl_latest_clients.setWordWrap(True)
        latest_clients_layout.addWidget(latest_clients_title)
        latest_clients_layout.addWidget(self.lbl_latest_clients)

        columns_layout.addWidget(self.latest_cars_card)
        columns_layout.addWidget(self.latest_clients_card)
        self.content_layout.addWidget(columns)
        self.content_layout.addStretch(1)

    def refresh(self):
        with SessionLocal() as db:
            cars_total = db.query(Car).count()
            deals_active = db.query(Deal).filter(or_(Deal.is_archived.is_(False), Deal.is_archived.is_(None))).count()
            archived_total = db.query(Deal).filter(Deal.is_archived.is_(True)).count()
            rooms_total = len(list_rooms_for_user(db, self.current_user.id))
            no_action = db.query(Deal).filter(
                or_(Deal.is_archived.is_(False), Deal.is_archived.is_(None)),
                Deal.next_action_date.is_(None),
            ).count()
            without_client = db.query(Car).filter(Car.client_id.is_(None)).count()
            latest_cars = (
                db.query(Car)
                .options(joinedload(Car.brand), joinedload(Car.model), joinedload(Car.trim), joinedload(Car.client))
                .order_by(Car.created_at.desc(), Car.id.desc())
                .limit(4)
                .all()
            )
            latest_clients = (
                db.query(Client)
                .order_by(Client.created_at.desc(), Client.id.desc())
                .limit(4)
                .all()
            )

        user_name = self.current_user.full_name or self.current_user.login or "сотрудник"
        self.lbl_welcome.setText(f"Добро пожаловать, {user_name}")
        self.lbl_caption.setText(
            "Собрали в одном месте быстрые переходы, рабочую сводку, последние карточки и командную связь."
        )
        self.metric_cars.set_data(str(cars_total), "Все автомобили в текущей базе.")
        self.metric_deals.set_data(str(deals_active), "Активные сделки, которые сейчас в работе.")
        self.metric_archive.set_data(str(archived_total), "Архивные сделки для истории и контроля.")
        self.metric_chat.set_data(str(rooms_total), "Командные и личные диалоги сотрудника.")
        self.lbl_focus.setText(
            f"Сделок без следующего шага: {no_action}. Автомобилей без клиента: {without_client}. "
            f"Если что-то выпадает из процесса, удобнее всего начать с разделов «Автомобили» и «Сделки»."
        )

        if latest_cars:
            self.lbl_latest_cars.setText(
                "\n".join(
                    f"• {_car_title(car)} — {car.client.full_name if car.client else 'без клиента'}"
                    for car in latest_cars
                )
            )
        else:
            self.lbl_latest_cars.setText("Карточки автомобилей пока не добавлены.")

        if latest_clients:
            self.lbl_latest_clients.setText(
                "\n".join(
                    f"• {client.full_name} — {client.phone or 'телефон не указан'}"
                    for client in latest_clients
                )
            )
        else:
            self.lbl_latest_clients.setText("Клиентская база пока пустая.")


class _ResponsiveCardsPage(QWidget):
    def __init__(self, title: str, subtitle: str, placeholder: str, parent=None):
        super().__init__(parent)
        self._cards: list[QWidget] = []
        self._columns = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        header = _make_card(self, "MobileHero")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 20, 20, 20)
        header_layout.setSpacing(10)

        lbl_title = QLabel(title, header)
        lbl_title.setObjectName("SectionTitle")
        lbl_caption = QLabel(subtitle, header)
        lbl_caption.setObjectName("SectionCaption")
        lbl_caption.setWordWrap(True)
        header_layout.addWidget(lbl_title)
        header_layout.addWidget(lbl_caption)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.ed_search = QLineEdit(header)
        self.ed_search.setPlaceholderText(placeholder)
        controls.addWidget(self.ed_search, 1)
        self.filters_layout = QHBoxLayout()
        self.filters_layout.setSpacing(8)
        controls.addLayout(self.filters_layout)
        self.btn_refresh = QPushButton("Показать", header)
        self.btn_refresh.setProperty("accent", "secondary")
        controls.addWidget(self.btn_refresh)
        header_layout.addLayout(controls)

        self.lbl_status = QLabel("", header)
        self.lbl_status.setObjectName("InlineMutedLabel")
        header_layout.addWidget(self.lbl_status)
        root.addWidget(header)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(self.scroll, 1)

        self.container = QWidget(self.scroll)
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(14)
        self.scroll.setWidget(self.container)

        self.btn_refresh.clicked.connect(self.refresh)
        self.ed_search.returnPressed.connect(self.refresh)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = self._resolve_columns()
        if columns != self._columns:
            self._rebuild_cards()

    def _resolve_columns(self) -> int:
        width = max(0, self.scroll.viewport().width())
        if width >= 1280:
            return 3
        if width >= 760:
            return 2
        return 1

    def _clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def _set_cards(self, cards: list[QWidget], status_text: str, empty_text: str):
        self._cards = cards
        self.lbl_status.setText(status_text)
        self._clear_grid()
        self._columns = self._resolve_columns()
        if not cards:
            empty = _make_card(self.container)
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(20, 20, 20, 20)
            empty_layout.addWidget(QLabel(empty_text, empty))
            self.grid.addWidget(empty, 0, 0)
            return
        self._rebuild_cards()

    def _rebuild_cards(self):
        if not self._cards:
            return
        self._clear_grid()
        self._columns = self._resolve_columns()
        for index, card in enumerate(self._cards):
            row = index // self._columns
            col = index % self._columns
            self.grid.addWidget(card, row, col)


class MobileCarsView(_ResponsiveCardsPage):
    def __init__(self, parent=None):
        super().__init__(
            "Автомобили",
            "Быстрый просмотр карточек авто, статусов, клиента и стоимости без перегруженной таблицы.",
            "VIN, статус, клиент...",
            parent,
        )
        self.cb_scope = QComboBox(self)
        self.cb_scope.addItem("В работе", "active")
        self.cb_scope.addItem("Архив", "archived")
        self.cb_scope.addItem("Все авто", "all")
        self.filters_layout.addWidget(self.cb_scope)
        self.cb_scope.currentIndexChanged.connect(self.refresh)

    def refresh(self):
        search = self.ed_search.text().strip()
        scope = self.cb_scope.currentData()
        with SessionLocal() as db:
            query = (
                db.query(Car)
                .options(joinedload(Car.brand), joinedload(Car.model), joinedload(Car.trim), joinedload(Car.client))
                .order_by(Car.created_at.desc(), Car.id.desc())
            )
            if scope == "active":
                query = query.filter(or_(Car.is_archived.is_(False), Car.is_archived.is_(None)))
            elif scope == "archived":
                query = query.filter(Car.is_archived.is_(True))
            if search:
                like = f"%{search}%"
                query = query.outerjoin(Client, Client.id == Car.client_id).filter(
                    or_(
                        Car.vin.ilike(like),
                        Car.status.ilike(like),
                        Car.deal_status.ilike(like),
                        Client.full_name.ilike(like),
                    )
                )
            rows = query.limit(90).all()

        cards: list[QWidget] = []
        for car in rows:
            card = _make_card(self.container)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(10)

            title = QLabel(_car_title(car), card)
            title.setObjectName("SectionTitle")
            layout.addWidget(title)

            chips = QHBoxLayout()
            chips.setSpacing(8)
            if car.status:
                chips.addWidget(_make_chip(car.status, card))
            if car.deal_status:
                chips.addWidget(_make_chip(car.deal_status, card))
            chips.addWidget(_make_chip("Архив" if car.is_archived else "В работе", card))
            chips.addStretch(1)
            layout.addLayout(chips)

            for text in (
                f"VIN: {car.vin or 'не указан'}",
                f"Клиент: {car.client.full_name if car.client else 'не привязан'}",
                f"Двигатель: {car.engine_cc or 0} см3 · {car.horsepower or 0} л.с.",
                f"Цена до Владивостока: {_money(car.price_to_vladivostok)}",
                f"Цена для клиента: {_money(car.price_customer)}",
            ):
                label = QLabel(text, card)
                label.setWordWrap(True)
                layout.addWidget(label)

            cards.append(card)

        self._set_cards(
            cards,
            f"Найдено автомобилей: {len(rows)}",
            "По текущему фильтру автомобили не найдены.",
        )


class MobileDealsView(_ResponsiveCardsPage):
    def __init__(self, parent=None):
        super().__init__(
            "Сделки",
            "Контроль статусов, архива, клиента, автомобиля и следующего действия в одном месте.",
            "Клиент, статус, VIN, сделка...",
            parent,
        )
        self.cb_scope = QComboBox(self)
        self.cb_scope.addItem("В работе", "active")
        self.cb_scope.addItem("Архив", "archived")
        self.cb_scope.addItem("Все сделки", "all")
        self.filters_layout.addWidget(self.cb_scope)
        self.cb_scope.currentIndexChanged.connect(self.refresh)

    def refresh(self):
        search = self.ed_search.text().strip()
        scope = self.cb_scope.currentData()
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
            rows = query.limit(90).all()

        cards: list[QWidget] = []
        for deal in rows:
            card = _make_card(self.container)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(10)

            title = QLabel(deal.title or (_car_title(deal.car) if deal.car else f"Сделка #{deal.id}"), card)
            title.setObjectName("SectionTitle")
            layout.addWidget(title)

            chips = QHBoxLayout()
            chips.setSpacing(8)
            if getattr(deal.deal_stage, "name", None):
                chips.addWidget(_make_chip(deal.deal_stage.name, card))
            if deal.deal_status:
                chips.addWidget(_make_chip(deal.deal_status, card))
            chips.addWidget(_make_chip("Архив" if deal.is_archived else "В работе", card))
            chips.addStretch(1)
            layout.addLayout(chips)

            manager_name = getattr(deal.responsible_user, "full_name", None) or getattr(deal.responsible_user, "login", None)
            for text in (
                f"Клиент: {deal.client.full_name if deal.client else 'не привязан'}",
                f"Автомобиль: {_car_title(deal.car) if deal.car else 'не выбран'}",
                f"Менеджер: {manager_name or 'не назначен'}",
                f"Следующее действие: {deal.next_action_date.strftime('%d.%m.%Y') if deal.next_action_date else 'не назначено'}",
                f"План прибытия: {deal.expected_arrival_date.strftime('%d.%m.%Y') if deal.expected_arrival_date else 'не указан'}",
            ):
                label = QLabel(text, card)
                label.setWordWrap(True)
                layout.addWidget(label)

            cards.append(card)

        self._set_cards(
            cards,
            f"Найдено сделок: {len(rows)}",
            "По текущему фильтру сделки не найдены.",
        )


class MobileClientsView(_ResponsiveCardsPage):
    def __init__(self, parent=None):
        super().__init__(
            "Клиенты",
            "Карточки клиентов с контактами, адресом, источником и связанной работой.",
            "ФИО, телефон, e-mail...",
            parent,
        )

    def refresh(self):
        search = self.ed_search.text().strip()
        with SessionLocal() as db:
            query = (
                db.query(Client)
                .options(joinedload(Client.responsible_user), selectinload(Client.deals))
                .order_by(Client.created_at.desc(), Client.id.desc())
            )
            if search:
                like = f"%{search}%"
                query = query.filter(
                    or_(
                        Client.full_name.ilike(like),
                        Client.phone.ilike(like),
                        Client.email.ilike(like),
                        Client.registration_address.ilike(like),
                    )
                )
            rows = query.limit(90).all()

        cards: list[QWidget] = []
        for client in rows:
            card = _make_card(self.container)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setSpacing(10)

            title = QLabel(client.full_name, card)
            title.setObjectName("SectionTitle")
            layout.addWidget(title)

            chips = QHBoxLayout()
            chips.setSpacing(8)
            if client.lead_source:
                chips.addWidget(_make_chip(client.lead_source, card))
            if client.priority:
                chips.addWidget(_make_chip(str(client.priority).upper(), card))
            chips.addWidget(_make_chip(f"Сделок: {len(client.deals)}", card))
            chips.addStretch(1)
            layout.addLayout(chips)

            manager_name = getattr(client.responsible_user, "full_name", None) or getattr(client.responsible_user, "login", None)
            for text in (
                f"Телефон: {client.phone or 'не указан'}",
                f"E-mail: {client.email or 'не указан'}",
                f"Ответственный: {manager_name or 'не назначен'}",
                f"Адрес: {client.registration_address or 'не заполнен'}",
            ):
                label = QLabel(text, card)
                label.setWordWrap(True)
                layout.addWidget(label)

            cards.append(card)

        self._set_cards(
            cards,
            f"Найдено клиентов: {len(rows)}",
            "По текущему поиску клиенты не найдены.",
        )


class MobileChatView(QWidget):
    def __init__(self, current_user: User, parent=None):
        super().__init__(parent)
        self.current_user = current_user
        self._current_room_id: int | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        header = _make_card(self, "MobileHero")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 20, 20, 20)
        header_layout.setSpacing(10)

        title = QLabel("Чаты сотрудников", header)
        title.setObjectName("SectionTitle")
        caption = QLabel(
            "Здесь собраны командные и личные диалоги. Слева список комнат, справа переписка и быстрый ввод сообщений.",
            header,
        )
        caption.setObjectName("SectionCaption")
        caption.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(caption)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_direct_chat = QPushButton("Личный чат", header)
        self.btn_direct_chat.setProperty("accent", "secondary")
        self.btn_refresh = QPushButton("Обновить", header)
        self.btn_refresh.setProperty("accent", "secondary")
        actions.addWidget(self.btn_direct_chat)
        actions.addWidget(self.btn_refresh)
        actions.addStretch(1)
        header_layout.addLayout(actions)
        root.addWidget(header)

        body = QVBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, 1)

        rooms_card = _make_card(self)
        rooms_layout = QVBoxLayout(rooms_card)
        rooms_layout.setContentsMargins(14, 14, 14, 14)
        rooms_layout.setSpacing(10)
        rooms_title = QLabel("Комнаты", rooms_card)
        rooms_title.setObjectName("SectionTitle")
        self.list_rooms = QListWidget(rooms_card)
        self.list_rooms.setProperty("mobileList", True)
        self.list_rooms.setMaximumHeight(180)
        rooms_layout.addWidget(rooms_title)
        rooms_layout.addWidget(self.list_rooms, 1)
        body.addWidget(rooms_card, 0)

        chat_card = _make_card(self)
        chat_layout = QVBoxLayout(chat_card)
        chat_layout.setContentsMargins(14, 14, 14, 14)
        chat_layout.setSpacing(10)
        self.lbl_room_title = QLabel("Выберите чат", chat_card)
        self.lbl_room_title.setObjectName("SectionTitle")
        self.lbl_room_hint = QLabel("Откройте диалог слева или создайте новый личный чат.", chat_card)
        self.lbl_room_hint.setObjectName("InlineMutedLabel")
        self.lbl_room_hint.setWordWrap(True)
        self.list_messages = QListWidget(chat_card)
        self.list_messages.setProperty("mobileList", True)
        self.txt_message = QTextEdit(chat_card)
        self.txt_message.setPlaceholderText("Сообщение...")
        self.txt_message.setMaximumHeight(110)
        self.btn_send = QPushButton("Отправить", chat_card)
        chat_layout.addWidget(self.lbl_room_title)
        chat_layout.addWidget(self.lbl_room_hint)
        chat_layout.addWidget(self.list_messages, 1)
        chat_layout.addWidget(self.txt_message)
        chat_layout.addWidget(self.btn_send, 0, Qt.AlignmentFlag.AlignRight)
        body.addWidget(chat_card, 1)

        self.list_rooms.currentItemChanged.connect(self._room_changed)
        self.btn_send.clicked.connect(self.send_message)
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_direct_chat.clicked.connect(self.create_direct_chat)

        self._timer = QTimer(self)
        self._timer.setInterval(4000)
        self._timer.timeout.connect(self._refresh_messages)
        self._timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._timer.isActive():
            self._timer.stop()

    def refresh(self):
        selected_room_id = self._current_room_id
        with SessionLocal() as db:
            ensure_general_room(db, created_by_user_id=self.current_user.id)
            rooms = list_rooms_for_user(db, self.current_user.id)

        self.list_rooms.clear()
        for room in rooms:
            item = QListWidgetItem(room_display_name(room, int(self.current_user.id)))
            item.setData(Qt.ItemDataRole.UserRole, int(room.id))
            self.list_rooms.addItem(item)

        if not rooms:
            self._current_room_id = None
            self.lbl_room_title.setText("Чаты не найдены")
            self.lbl_room_hint.setText("Создайте личный диалог или дождитесь появления общей комнаты.")
            self.list_messages.clear()
            return

        target_row = 0
        if selected_room_id is not None:
            for row in range(self.list_rooms.count()):
                if self.list_rooms.item(row).data(Qt.ItemDataRole.UserRole) == selected_room_id:
                    target_row = row
                    break
        self.list_rooms.setCurrentRow(target_row)

    def create_direct_chat(self):
        dlg = DirectChatDialog(self.current_user, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        target_user_id = dlg.selected_user_id()
        if target_user_id is None:
            return
        try:
            with SessionLocal() as db:
                room = get_or_create_direct_room(db, int(self.current_user.id), int(target_user_id))
                self._current_room_id = int(room.id)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Чат", f"Не удалось создать личный чат: {exc}")

    def _room_changed(self, current: QListWidgetItem | None):
        self._current_room_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.lbl_room_title.setText(current.text() if current else "Выберите чат")
        self._refresh_messages()

    def _refresh_messages(self):
        if self._current_room_id is None:
            self.list_messages.clear()
            return

        with SessionLocal() as db:
            messages = list_messages(db, int(self._current_room_id))
            last_message_id = messages[-1].id if messages else None
            mark_room_read(db, int(self._current_room_id), int(self.current_user.id), last_message_id)

        self.list_messages.clear()
        if not messages:
            self.lbl_room_hint.setText("Сообщений пока нет. Начните диалог первым.")
            return

        self.lbl_room_hint.setText("Переписка обновляется автоматически.")
        for message in messages:
            author = "Система" if message.is_system else ((message.user.full_name or message.user.login) if message.user else "Сотрудник")
            created = message.created_at.strftime("%d.%m.%Y %H:%M") if message.created_at else ""
            item = QListWidgetItem(f"{author} · {created}\n{message.body}")
            self.list_messages.addItem(item)
        self.list_messages.scrollToBottom()

    def send_message(self):
        if self._current_room_id is None:
            return
        body = self.txt_message.toPlainText().strip()
        if not body:
            return
        try:
            with SessionLocal() as db:
                send_message(db, int(self._current_room_id), int(self.current_user.id), body)
            self.txt_message.clear()
            self._refresh_messages()
        except Exception as exc:
            QMessageBox.warning(self, "Чат", f"Не удалось отправить сообщение: {exc}")


class MobileWindow(QMainWindow):
    def __init__(self, current_user: User, on_logout=None):
        super().__init__()
        self.user = current_user
        self.on_logout = on_logout

        self.setWindowTitle("ShukCar - Mobile Workspace")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(430, 900)
        self.setMinimumSize(390, 760)
        self.setMaximumSize(520, 1040)

        self._page_titles = {
            "home": ("Обзор", "Ежедневная рабочая сводка и быстрые переходы."),
            "deals": ("Сделки", "Статусы, архив и контроль следующего шага."),
            "cars": ("Автомобили", "Карточки автомобилей и связанная информация."),
            "clients": ("Клиенты", "Контакты, адреса и база работы с клиентами."),
            "chat": ("Чат", "Командные и личные диалоги сотрудников."),
            "calc": ("Калькулятор", "Расчёт стоимости привоза и расходов."),
        }

        self._central = QWidget(self)
        self._central.setObjectName("AppRoot")
        self.setCentralWidget(self._central)
        root = QVBoxLayout(self._central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        topbar = _make_card(self._central, "MobileTopBar")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(14, 12, 14, 12)
        topbar_layout.setSpacing(12)

        self.btn_menu = QPushButton("☰", topbar)
        self.btn_menu.setObjectName("MenuButton")
        self.btn_menu.setFixedWidth(48)
        self.btn_menu.clicked.connect(self._toggle_drawer)
        topbar_layout.addWidget(self.btn_menu, 0)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.lbl_title = QLabel("", topbar)
        self.lbl_title.setObjectName("HeaderTitle")
        self.lbl_caption = QLabel("", topbar)
        self.lbl_caption.setObjectName("PageSubtitle")
        self.lbl_caption.setWordWrap(True)
        title_box.addWidget(self.lbl_title)
        title_box.addWidget(self.lbl_caption)
        topbar_layout.addLayout(title_box, 1)

        self.lbl_user_avatar = QLabel(_avatar_text(self.user), topbar)
        self.lbl_user_avatar.setObjectName("AvatarBadge")
        self.lbl_user_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_user_avatar.setFixedSize(42, 42)
        topbar_layout.addWidget(self.lbl_user_avatar, 0)
        root.addWidget(topbar, 0)

        self.stack = QStackedWidget(self._central)
        root.addWidget(self.stack, 1)

        self.home_view = MobileHomeView(self.user, self)
        self.deals_view = MobileDealsView(self)
        self.cars_view = MobileCarsView(self)
        self.clients_view = MobileClientsView(self)
        self.chat_view = MobileChatView(self.user, self)
        self.calc_view = CalculatorView(self)
        self.home_view.navigate.connect(self.open_page)

        self.pages = {
            "home": self.home_view,
            "deals": self.deals_view,
            "cars": self.cars_view,
            "clients": self.clients_view,
            "chat": self.chat_view,
            "calc": self.calc_view,
        }
        for widget in self.pages.values():
            self.stack.addWidget(widget)

        self.nav_buttons: dict[str, QPushButton] = {}
        self.drawer_scrim = DismissOverlay(self._central)
        self.drawer_scrim.setObjectName("MobileScrim")
        self.drawer_scrim.hide()
        self.drawer_scrim.clicked.connect(self._hide_drawer)

        self.drawer = _make_card(self.drawer_scrim, "MobileDrawer")
        drawer_layout = QVBoxLayout(self.drawer)
        drawer_layout.setContentsMargins(16, 16, 16, 16)
        drawer_layout.setSpacing(12)

        drawer_title = QLabel("ShukCar", self.drawer)
        drawer_title.setObjectName("BrandTitle")
        drawer_caption = QLabel("mobile navigation", self.drawer)
        drawer_caption.setObjectName("BrandCaption")
        drawer_layout.addWidget(drawer_title)
        drawer_layout.addWidget(drawer_caption)

        profile_card = _make_card(self.drawer)
        profile_layout = QHBoxLayout(profile_card)
        profile_layout.setContentsMargins(12, 12, 12, 12)
        profile_layout.setSpacing(10)
        profile_badge = QLabel(_avatar_text(self.user), profile_card)
        profile_badge.setObjectName("AvatarBadge")
        profile_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        profile_badge.setFixedSize(40, 40)
        profile_layout.addWidget(profile_badge, 0)
        profile_text = QVBoxLayout()
        profile_text.setSpacing(0)
        profile_name = QLabel(self.user.full_name or self.user.login or "Сотрудник", profile_card)
        profile_name.setObjectName("SectionTitle")
        profile_role = QLabel(_role_label(self.user), profile_card)
        profile_role.setObjectName("InlineMutedLabel")
        profile_text.addWidget(profile_name)
        profile_text.addWidget(profile_role)
        profile_layout.addLayout(profile_text, 1)
        drawer_layout.addWidget(profile_card)

        for key, text in (
            ("home", "Обзор"),
            ("deals", "Сделки"),
            ("cars", "Авто"),
            ("clients", "Клиенты"),
            ("chat", "Чат"),
            ("calc", "Калькулятор"),
        ):
            button = QPushButton(text, self.drawer)
            button.setCheckable(True)
            button.setProperty("mobileDrawerNav", True)
            button.clicked.connect(lambda _=False, page=key: self.open_page(page))
            drawer_layout.addWidget(button)
            self.nav_buttons[key] = button

        drawer_layout.addStretch(1)

        self.btn_settings = QPushButton("Настройки", self.drawer)
        self.btn_settings.setProperty("accent", "secondary")
        self.btn_settings.clicked.connect(self._open_settings)
        self.btn_logout = QPushButton("Выйти", self.drawer)
        self.btn_logout.setProperty("accent", "danger-secondary")
        self.btn_logout.clicked.connect(self._logout)
        drawer_layout.addWidget(self.btn_settings)
        drawer_layout.addWidget(self.btn_logout)

        self.open_page("home")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.drawer_scrim.setGeometry(self._central.rect())
        drawer_width = min(290, max(250, self._central.width() - 56))
        self.drawer.setGeometry(0, 0, drawer_width, self._central.height())

    def _toggle_drawer(self):
        if self.drawer_scrim.isVisible():
            self._hide_drawer()
        else:
            self._show_drawer()

    def _show_drawer(self):
        self.drawer_scrim.setGeometry(self._central.rect())
        self.drawer_scrim.show()
        self.drawer.raise_()

    def _hide_drawer(self):
        self.drawer_scrim.hide()

    def _open_settings(self):
        self._hide_drawer()
        MobileSettingsDialog(self.user, self).exec()

    def _logout(self):
        self._hide_drawer()
        if callable(self.on_logout):
            self.on_logout()

    def open_page(self, key: str):
        widget = self.pages.get(key)
        if widget is None:
            return
        self._hide_drawer()
        self.stack.setCurrentWidget(widget)
        title, caption = self._page_titles.get(key, ("ShukCar", ""))
        self.lbl_title.setText(title)
        self.lbl_caption.setText(caption)
        for btn_key, button in self.nav_buttons.items():
            button.setChecked(btn_key == key)
        refresh = getattr(widget, "refresh", None)
        if callable(refresh):
            refresh()
