from __future__ import annotations

import datetime as dt

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from db import SessionLocal
from models import Deal, DealComment, DealTask
from services.crm import fill_priority_combo, priority_label


def _make_optional_date_edit() -> QDateEdit:
    edit = QDateEdit()
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("dd.MM.yyyy")
    edit.setMinimumDate(QDate(2000, 1, 1))
    edit.setDate(QDate(2000, 1, 1))
    edit.setSpecialValueText("Не указано")
    return edit


def _qdate_to_date(edit: QDateEdit) -> dt.date | None:
    value = edit.date()
    if not value.isValid() or value == edit.minimumDate():
        return None
    return dt.date(value.year(), value.month(), value.day())


class TaskDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Задача по сделке")
        self.resize(420, 220)

        self.ed_title = QTextEdit(self)
        self.ed_title.setMaximumHeight(68)
        self.dt_due = _make_optional_date_edit()
        self.cb_priority = QComboBox(self)
        fill_priority_combo(self.cb_priority, "normal")
        self.txt_notes = QTextEdit(self)
        self.txt_notes.setMaximumHeight(88)

        form = QFormLayout(self)
        form.addRow("Задача:", self.ed_title)
        form.addRow("Срок:", self.dt_due)
        form.addRow("Приоритет:", self.cb_priority)
        form.addRow("Комментарий:", self.txt_notes)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def get_data(self) -> dict:
        return {
            "title": self.ed_title.toPlainText().strip(),
            "due_date": _qdate_to_date(self.dt_due),
            "priority": self.cb_priority.currentData() or "normal",
            "notes": self.txt_notes.toPlainText().strip() or None,
        }

    def accept(self):
        if not self.ed_title.toPlainText().strip():
            QMessageBox.information(self, "Задача", "Введите текст задачи.")
            return
        super().accept()


class CommentDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Комментарий по сделке")
        self.resize(420, 220)

        self.txt_body = QTextEdit(self)
        self.txt_body.setPlaceholderText("Зафиксируйте важную договорённость, статус или замечание.")

        layout = QVBoxLayout(self)
        layout.addWidget(self.txt_body)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_body(self) -> str:
        return self.txt_body.toPlainText().strip()

    def accept(self):
        if not self.get_body():
            QMessageBox.information(self, "Комментарий", "Введите комментарий.")
            return
        super().accept()


class DealDetailsWindow(QMainWindow):
    def __init__(self, deal_id: int, parent=None):
        super().__init__(parent)
        self.deal_id = deal_id
        self.session = SessionLocal()
        self.setWindowTitle(f"Сделка #{deal_id}")
        self.resize(1140, 760)

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        info_card = QFrame(left)
        info_card.setProperty("card", True)
        info_form = QFormLayout(info_card)
        info_form.setContentsMargins(16, 16, 16, 16)

        self.lbl_title = QLabel("—", info_card)
        self.lbl_title.setObjectName("SectionTitle")
        info_form.addRow(self.lbl_title)

        self.v_client = QLabel("—", info_card)
        self.v_client_phone = QLabel("—", info_card)
        self.v_client_email = QLabel("—", info_card)
        self.v_client_address = QLabel("—", info_card)
        self.v_client_address.setWordWrap(True)
        self.v_car = QLabel("—", info_card)
        self.v_stage = QLabel("—", info_card)
        self.v_status = QLabel("—", info_card)
        self.v_manager = QLabel("—", info_card)
        self.v_source = QLabel("—", info_card)
        self.v_priority = QLabel("—", info_card)
        self.v_arrival = QLabel("—", info_card)
        self.v_next_action = QLabel("—", info_card)
        self.v_blocked = QLabel("—", info_card)
        self.v_blocked.setWordWrap(True)
        self.v_notes = QLabel("—", info_card)
        self.v_notes.setWordWrap(True)

        rows = [
            ("Клиент:", self.v_client),
            ("Телефон:", self.v_client_phone),
            ("E-mail:", self.v_client_email),
            ("Адрес:", self.v_client_address),
            ("Автомобиль:", self.v_car),
            ("Этап:", self.v_stage),
            ("Статус:", self.v_status),
            ("Ответственный:", self.v_manager),
            ("Источник:", self.v_source),
            ("Приоритет:", self.v_priority),
            ("План прибытия:", self.v_arrival),
            ("Следующее действие:", self.v_next_action),
            ("Блокировка:", self.v_blocked),
            ("Примечание:", self.v_notes),
        ]
        for title_text, widget in rows:
            title = QLabel(title_text, info_card)
            title.setObjectName("InlineMutedLabel")
            info_form.addRow(title, widget)

        left_layout.addWidget(info_card)

        tasks_card = QFrame(left)
        tasks_card.setProperty("card", True)
        tasks_layout = QVBoxLayout(tasks_card)
        tasks_layout.setContentsMargins(12, 12, 12, 12)
        tasks_layout.setSpacing(8)
        tasks_title = QLabel("Задачи по сделке", tasks_card)
        tasks_title.setObjectName("SectionTitle")
        tasks_layout.addWidget(tasks_title)

        self.list_tasks = QListWidget(tasks_card)
        tasks_layout.addWidget(self.list_tasks, 1)

        task_buttons = QHBoxLayout()
        self.btn_add_task = QPushButton("Добавить", tasks_card)
        self.btn_toggle_task = QPushButton("Готово / вернуть", tasks_card)
        self.btn_delete_task = QPushButton("Удалить", tasks_card)
        self.btn_toggle_task.setProperty("accent", "secondary")
        self.btn_delete_task.setProperty("accent", "danger-secondary")
        task_buttons.addWidget(self.btn_add_task)
        task_buttons.addWidget(self.btn_toggle_task)
        task_buttons.addWidget(self.btn_delete_task)
        task_buttons.addStretch(1)
        tasks_layout.addLayout(task_buttons)
        left_layout.addWidget(tasks_card, 1)

        comments_card = QFrame(self)
        comments_card.setProperty("card", True)
        comments_layout = QVBoxLayout(comments_card)
        comments_layout.setContentsMargins(12, 12, 12, 12)
        comments_layout.setSpacing(8)
        comments_title = QLabel("Комментарии по сделке", comments_card)
        comments_title.setObjectName("SectionTitle")
        comments_layout.addWidget(comments_title)

        self.list_comments = QListWidget(comments_card)
        comments_layout.addWidget(self.list_comments, 1)

        comment_buttons = QHBoxLayout()
        self.btn_add_comment = QPushButton("Добавить", comments_card)
        self.btn_delete_comment = QPushButton("Удалить", comments_card)
        self.btn_delete_comment.setProperty("accent", "danger-secondary")
        comment_buttons.addWidget(self.btn_add_comment)
        comment_buttons.addWidget(self.btn_delete_comment)
        comment_buttons.addStretch(1)
        comments_layout.addLayout(comment_buttons)

        root.addWidget(left, 7)
        root.addWidget(comments_card, 6)

        self.btn_add_task.clicked.connect(self._add_task)
        self.btn_toggle_task.clicked.connect(self._toggle_task)
        self.btn_delete_task.clicked.connect(self._delete_task)
        self.btn_add_comment.clicked.connect(self._add_comment)
        self.btn_delete_comment.clicked.connect(self._delete_comment)

        self._load_deal()
        self._load_tasks()
        self._load_comments()

    def closeEvent(self, event):
        try:
            self.session.close()
        finally:
            super().closeEvent(event)

    @staticmethod
    def _fmt_date(value: dt.date | None) -> str:
        return value.strftime("%d.%m.%Y") if value else "—"

    def _load_deal(self):
        deal = self.session.get(Deal, self.deal_id)
        if not deal:
            return

        self.lbl_title.setText(deal.title or f"Сделка #{deal.id}")
        self.v_client.setText(getattr(getattr(deal, "client", None), "full_name", None) or "—")
        self.v_client_phone.setText(getattr(getattr(deal, "client", None), "phone", None) or "—")
        self.v_client_email.setText(getattr(getattr(deal, "client", None), "email", None) or "—")
        self.v_client_address.setText(getattr(getattr(deal, "client", None), "registration_address", None) or "—")

        car = getattr(deal, "car", None)
        if car:
            brand = getattr(getattr(car, "brand", None), "name", "") or ""
            model = getattr(getattr(car, "model", None), "name", "") or ""
            car_label = f"{brand} {model}".strip() or f"Авто #{car.id}"
            if car.vin:
                car_label = f"{car_label} • {car.vin}"
            self.v_car.setText(car_label)
        else:
            self.v_car.setText("Не привязано")

        self.v_stage.setText(getattr(getattr(deal, "deal_stage", None), "name", None) or "—")
        self.v_status.setText(deal.deal_status or "—")
        self.v_manager.setText(
            getattr(getattr(deal, "responsible_user", None), "full_name", None)
            or getattr(getattr(deal, "responsible_user", None), "login", None)
            or "—"
        )
        self.v_source.setText(deal.lead_source or "—")
        self.v_priority.setText(priority_label(deal.priority))
        self.v_arrival.setText(self._fmt_date(deal.expected_arrival_date))

        next_action_parts = []
        if deal.next_action_date:
            next_action_parts.append(self._fmt_date(deal.next_action_date))
        if deal.next_action_note:
            next_action_parts.append(deal.next_action_note)
        self.v_next_action.setText(" • ".join(next_action_parts) if next_action_parts else "—")
        self.v_blocked.setText(deal.blocked_reason or "—")
        self.v_notes.setText(deal.notes or "—")

    def _load_tasks(self):
        self.list_tasks.clear()
        rows = (
            self.session.query(DealTask)
            .filter(DealTask.deal_id == self.deal_id)
            .order_by(DealTask.is_done.asc(), DealTask.due_date.asc(), DealTask.id.desc())
            .all()
        )
        for task in rows:
            status = "✓" if task.is_done else "•"
            due = self._fmt_date(task.due_date)
            text = f"{status} {task.title} [{priority_label(task.priority)}]"
            if task.due_date:
                text += f" • до {due}"
            if task.notes:
                text += f"\n{task.notes}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, task.id)
            self.list_tasks.addItem(item)

    def _current_task(self) -> DealTask | None:
        item = self.list_tasks.currentItem()
        if not item:
            return None
        task_id = item.data(Qt.ItemDataRole.UserRole)
        return self.session.get(DealTask, int(task_id)) if task_id else None

    def _add_task(self):
        dialog = TaskDialog(self)
        if not dialog.exec():
            return
        payload = dialog.get_data()
        row = DealTask(deal_id=self.deal_id, **payload)
        self.session.add(row)
        self.session.commit()
        self._load_tasks()

    def _toggle_task(self):
        task = self._current_task()
        if not task:
            return
        task.is_done = not bool(task.is_done)
        task.done_at = dt.datetime.now() if task.is_done else None
        self.session.commit()
        self._load_tasks()

    def _delete_task(self):
        task = self._current_task()
        if not task:
            return
        if QMessageBox.question(self, "Задача", "Удалить выбранную задачу?") != QMessageBox.StandardButton.Yes:
            return
        self.session.delete(task)
        self.session.commit()
        self._load_tasks()

    def _load_comments(self):
        self.list_comments.clear()
        rows = (
            self.session.query(DealComment)
            .filter(DealComment.deal_id == self.deal_id)
            .order_by(DealComment.id.desc())
            .all()
        )
        for comment in rows:
            stamp = comment.created_at.strftime("%d.%m.%Y %H:%M") if comment.created_at else ""
            text = comment.body
            if stamp:
                text = f"{stamp}\n{text}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, comment.id)
            self.list_comments.addItem(item)

    def _current_comment(self) -> DealComment | None:
        item = self.list_comments.currentItem()
        if not item:
            return None
        comment_id = item.data(Qt.ItemDataRole.UserRole)
        return self.session.get(DealComment, int(comment_id)) if comment_id else None

    def _add_comment(self):
        dialog = CommentDialog(self)
        if not dialog.exec():
            return
        row = DealComment(deal_id=self.deal_id, body=dialog.get_body())
        self.session.add(row)
        self.session.commit()
        self._load_comments()

    def _delete_comment(self):
        row = self._current_comment()
        if not row:
            return
        if QMessageBox.question(self, "Комментарий", "Удалить выбранный комментарий?") != QMessageBox.StandardButton.Yes:
            return
        self.session.delete(row)
        self.session.commit()
        self._load_comments()
