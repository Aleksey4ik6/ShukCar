from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from db import SessionLocal
from models import ChatMessage, User
from services.chat_service import (
    ensure_general_room,
    get_or_create_direct_room,
    list_chat_users,
    list_messages,
    list_rooms_for_user,
    mark_room_read,
    room_display_name,
    room_tooltip,
    send_message,
)


class DirectChatDialog(QDialog):
    def __init__(self, current_user: User, parent=None):
        super().__init__(parent)
        self.current_user = current_user
        self.setWindowTitle("Личный чат")
        self.resize(380, 10)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Выберите сотрудника для личного чата", self)
        title.setWordWrap(True)
        layout.addWidget(title)

        self.cb_users = QComboBox(self)
        layout.addWidget(self.cb_users)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._load_users()

    def _load_users(self):
        self.cb_users.clear()
        with SessionLocal() as session:
            users = list_chat_users(session, int(self.current_user.id))
        for user in users:
            label = user.full_name or user.login or f"Сотрудник #{user.id}"
            self.cb_users.addItem(label, int(user.id))

    def selected_user_id(self) -> int | None:
        value = self.cb_users.currentData()
        return int(value) if value is not None else None


class ChatView(QWidget):
    def __init__(self, current_user: User, parent=None):
        super().__init__(parent)
        self.current_user = current_user
        self._current_room_id: int | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        left = QWidget(self)
        left.setProperty("card", True)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(10)

        rooms_title = QLabel("Чаты")
        rooms_title.setObjectName("SectionTitle")
        left_layout.addWidget(rooms_title)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_direct_chat = QPushButton("Личный чат")
        self.btn_direct_chat.setProperty("accent", "secondary")
        self.btn_refresh = QPushButton("Обновить")
        self.btn_refresh.setProperty("accent", "secondary")
        actions.addWidget(self.btn_direct_chat)
        actions.addWidget(self.btn_refresh)
        left_layout.addLayout(actions)

        self.rooms_list = QListWidget(left)
        self.rooms_list.itemSelectionChanged.connect(self._on_room_changed)
        left_layout.addWidget(self.rooms_list, 1)

        right = QWidget(self)
        right.setProperty("card", True)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(10)

        self.lbl_room_title = QLabel("Выберите чат")
        self.lbl_room_title.setObjectName("SectionTitle")
        right_layout.addWidget(self.lbl_room_title)

        self.messages_list = QListWidget(right)
        self.messages_list.setWordWrap(True)
        right_layout.addWidget(self.messages_list, 1)

        self.ed_message = QTextEdit(right)
        self.ed_message.setPlaceholderText("Сообщение...")
        self.ed_message.setMaximumHeight(100)
        right_layout.addWidget(self.ed_message)

        send_bar = QHBoxLayout()
        send_bar.addStretch(1)
        self.btn_send = QPushButton("Отправить")
        self.btn_send.clicked.connect(self.send_current_message)
        send_bar.addWidget(self.btn_send)
        right_layout.addLayout(send_bar)

        root.addWidget(left, 2)
        root.addWidget(right, 5)

        self.btn_refresh.clicked.connect(self.refresh_rooms)
        self.btn_direct_chat.clicked.connect(self.create_direct_chat)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(3000)
        self.refresh_timer.timeout.connect(self._refresh_messages_only)
        self.refresh_timer.start()

        self.refresh_rooms()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.refresh_timer.isActive():
            self.refresh_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self.refresh_timer.isActive():
            self.refresh_timer.stop()

    def refresh_rooms(self):
        selected_room_id = self._current_room_id
        self.rooms_list.clear()

        with SessionLocal() as session:
            ensure_general_room(session, created_by_user_id=self.current_user.id)
            rooms = list_rooms_for_user(session, self.current_user.id)

        if not rooms:
            self._current_room_id = None
            self.lbl_room_title.setText("Чаты недоступны")
            self.messages_list.clear()
            return

        selected_item = None
        for room in rooms:
            item = QListWidgetItem(room_display_name(room, int(self.current_user.id)))
            item.setData(Qt.ItemDataRole.UserRole, int(room.id))
            item.setToolTip(room_tooltip(room, int(self.current_user.id)))
            self.rooms_list.addItem(item)
            if selected_room_id == room.id or (selected_room_id is None and selected_item is None):
                selected_item = item

        if selected_item is not None:
            self.rooms_list.setCurrentItem(selected_item)
        else:
            self._on_room_changed()

    def create_direct_chat(self):
        dlg = DirectChatDialog(self.current_user, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        target_user_id = dlg.selected_user_id()
        if target_user_id is None:
            QMessageBox.information(self, "Чат", "Выберите сотрудника для личного чата.")
            return

        try:
            with SessionLocal() as session:
                room = get_or_create_direct_room(session, int(self.current_user.id), int(target_user_id))
                room_id = int(room.id)
            self._current_room_id = room_id
            self.refresh_rooms()
        except Exception as exc:
            QMessageBox.warning(self, "Чат", f"Не удалось создать личный чат: {exc}")

    def _on_room_changed(self):
        item = self.rooms_list.currentItem()
        if item is None:
            self._current_room_id = None
            self.lbl_room_title.setText("Выберите чат")
            self.messages_list.clear()
            return

        self._current_room_id = int(item.data(Qt.ItemDataRole.UserRole))
        self.lbl_room_title.setText(item.text())
        self._load_messages()

    def _refresh_messages_only(self):
        if self._current_room_id is not None:
            self._load_messages()

    def _load_messages(self):
        if self._current_room_id is None:
            return

        with SessionLocal() as session:
            messages = list_messages(session, self._current_room_id)
            last_message_id = messages[-1].id if messages else None
            mark_room_read(session, self._current_room_id, self.current_user.id, last_message_id)

        self._render_messages(messages)

    def _render_messages(self, messages: list[ChatMessage]):
        current_scroll = self.messages_list.verticalScrollBar().value()
        at_bottom = current_scroll >= self.messages_list.verticalScrollBar().maximum() - 8

        self.messages_list.clear()
        for message in messages:
            author = "Система" if message.is_system else (message.user.full_name if message.user and message.user.full_name else "Сотрудник")
            timestamp = message.created_at.strftime("%d.%m.%Y %H:%M") if message.created_at else ""
            item = QListWidgetItem(f"{author} · {timestamp}\n{message.body}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self.messages_list.addItem(item)

        if at_bottom or self.messages_list.count() <= 1:
            self.messages_list.scrollToBottom()

    def send_current_message(self):
        room_id = self._current_room_id
        if room_id is None:
            QMessageBox.information(self, "Чат", "Сначала выберите чат.")
            return

        body = self.ed_message.toPlainText().strip()
        if not body:
            return

        try:
            with SessionLocal() as session:
                send_message(session, room_id, self.current_user.id, body)
            self.ed_message.clear()
            self._load_messages()
        except Exception as exc:
            QMessageBox.warning(self, "Чат", f"Не удалось отправить сообщение: {exc}")
