from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from PyQt6 import QtGui
from PyQt6.QtCore import Qt, QSize, QDate
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from models import Car, CarComment, CarMedia, CarTask
from services.crm import fill_priority_combo, priority_label

PKG_ROOT = Path(__file__).resolve().parents[1]


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

        self.ed_title = QLineEdit()
        self.dt_due = _make_optional_date_edit()
        self.cb_priority = QComboBox()
        fill_priority_combo(self.cb_priority, "normal")
        self.txt_notes = QTextEdit()
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
            "title": self.ed_title.text().strip(),
            "due_date": _qdate_to_date(self.dt_due),
            "priority": self.cb_priority.currentData() or "normal",
            "notes": self.txt_notes.toPlainText().strip() or None,
        }

    def accept(self):
        if not self.ed_title.text().strip():
            QMessageBox.information(self, "Задача", "Введите название задачи.")
            return
        super().accept()


class CommentDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Комментарий по сделке")
        self.resize(420, 220)

        self.txt_body = QTextEdit()
        self.txt_body.setPlaceholderText("Зафиксируйте договорённость, статус или важное наблюдение.")

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


class CarDetailsWindow(QMainWindow):
    def __init__(self, car_id: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Авто #{car_id} — детали")
        self.resize(1260, 760)

        self.car_id = car_id
        self.session = SessionLocal()
        self.media: list[CarMedia] = []
        self.media_index = -1

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        left = QWidget()
        left_outer = QVBoxLayout(left)
        left_outer.setContentsMargins(0, 0, 0, 0)
        left_outer.setSpacing(12)

        info_card = QFrame()
        info_card.setProperty("card", True)
        info_form = QFormLayout(info_card)
        info_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.lbl_title = QLabel("")
        self.lbl_title.setObjectName("SectionTitle")
        info_form.addRow(self.lbl_title)

        self.v_trim = QLabel("")
        self.v_body = QLabel("")
        self.v_fuel = QLabel("")
        self.v_trans = QLabel("")
        self.v_color = QLabel("")
        self.v_build = QLabel("")
        self.v_engine = QLabel("")
        self.v_hp = QLabel("")
        self.v_mileage = QLabel("")
        self.v_location = QLabel("")
        self.v_price = QLabel("")
        self.v_status = QLabel("")
        self.v_deal = QLabel("")
        self.v_client = QLabel("")
        self.v_responsible = QLabel("")
        self.v_source = QLabel("")
        self.v_priority = QLabel("")
        self.v_eta = QLabel("")
        self.v_next_action = QLabel("")
        self.v_blocked = QLabel("")

        def row(label: str, widget: QLabel):
            title = QLabel(label)
            title.setObjectName("InlineMutedLabel")
            widget.setWordWrap(True)
            info_form.addRow(title, widget)

        row("Комплектация:", self.v_trim)
        row("Тип кузова:", self.v_body)
        row("Тип топлива:", self.v_fuel)
        row("Коробка:", self.v_trans)
        row("Цвет:", self.v_color)
        row("Год/месяц:", self.v_build)
        row("Объём (см³):", self.v_engine)
        row("Л.с.:", self.v_hp)
        row("Пробег (км):", self.v_mileage)
        row("Локация:", self.v_location)
        row("Цена до Владивостока:", self.v_price)
        row("Статус авто:", self.v_status)
        row("Статус сделки:", self.v_deal)
        row("Клиент:", self.v_client)
        row("Ответственный:", self.v_responsible)
        row("Источник:", self.v_source)
        row("Приоритет:", self.v_priority)
        row("План прибытия:", self.v_eta)
        row("Следующее действие:", self.v_next_action)
        row("Блокировка:", self.v_blocked)

        left_outer.addWidget(info_card)

        tasks_card = QFrame()
        tasks_card.setProperty("card", True)
        tasks_layout = QVBoxLayout(tasks_card)
        tasks_layout.setContentsMargins(12, 12, 12, 12)
        tasks_layout.setSpacing(8)
        tasks_title = QLabel("Задачи и напоминания")
        tasks_title.setObjectName("SectionTitle")
        tasks_layout.addWidget(tasks_title)
        self.list_tasks = QListWidget()
        self.list_tasks.setSpacing(6)
        tasks_layout.addWidget(self.list_tasks, 1)
        tasks_buttons = QHBoxLayout()
        self.btn_add_task = QPushButton("Добавить")
        self.btn_toggle_task = QPushButton("Готово / вернуть")
        self.btn_delete_task = QPushButton("Удалить")
        self.btn_toggle_task.setProperty("accent", "secondary")
        self.btn_delete_task.setProperty("accent", "danger-secondary")
        tasks_buttons.addWidget(self.btn_add_task)
        tasks_buttons.addWidget(self.btn_toggle_task)
        tasks_buttons.addWidget(self.btn_delete_task)
        tasks_buttons.addStretch(1)
        tasks_layout.addLayout(tasks_buttons)
        left_outer.addWidget(tasks_card, 1)

        comments_card = QFrame()
        comments_card.setProperty("card", True)
        comments_layout = QVBoxLayout(comments_card)
        comments_layout.setContentsMargins(12, 12, 12, 12)
        comments_layout.setSpacing(8)
        comments_title = QLabel("Комментарии по сделке")
        comments_title.setObjectName("SectionTitle")
        comments_layout.addWidget(comments_title)
        self.list_comments = QListWidget()
        self.list_comments.setSpacing(6)
        comments_layout.addWidget(self.list_comments, 1)
        comments_buttons = QHBoxLayout()
        self.btn_add_comment = QPushButton("Добавить")
        self.btn_delete_comment = QPushButton("Удалить")
        self.btn_delete_comment.setProperty("accent", "danger-secondary")
        comments_buttons.addWidget(self.btn_add_comment)
        comments_buttons.addWidget(self.btn_delete_comment)
        comments_buttons.addStretch(1)
        comments_layout.addLayout(comments_buttons)
        left_outer.addWidget(comments_card, 1)

        right = QWidget()
        right.setProperty("card", True)
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(8)

        self.preview = QLabel("Нет медиа")
        self.preview.setObjectName("MediaPreview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(QSize(420, 320))
        right_l.addWidget(self.preview, 1)

        nav = QHBoxLayout()
        self.btn_prev = QPushButton("⟨ Пред")
        self.btn_next = QPushButton("След ⟩")
        self.btn_open_video = QPushButton("Открыть видео")
        self.btn_prev.setProperty("accent", "secondary")
        self.btn_next.setProperty("accent", "secondary")
        self.btn_open_video.setProperty("accent", "secondary")
        self.btn_open_video.setVisible(False)
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.btn_next)
        nav.addStretch(1)
        nav.addWidget(self.btn_open_video)
        right_l.addLayout(nav)

        self.list_media = QListWidget()
        self.list_media.setSpacing(6)
        right_l.addWidget(self.list_media, 1)

        root.addWidget(left, 7)
        root.addWidget(right, 6)

        self.btn_prev.clicked.connect(self._prev_media)
        self.btn_next.clicked.connect(self._next_media)
        self.btn_open_video.clicked.connect(self._open_current_video)
        self.list_media.itemClicked.connect(self._on_media_item_clicked)
        self.btn_add_task.clicked.connect(self._add_task)
        self.btn_toggle_task.clicked.connect(self._toggle_task_done)
        self.btn_delete_task.clicked.connect(self._delete_task)
        self.btn_add_comment.clicked.connect(self._add_comment)
        self.btn_delete_comment.clicked.connect(self._delete_comment)

        self._load_car()
        self._load_tasks()
        self._load_comments()
        self._load_media()

    def _fmt_date(self, value: dt.date | None) -> str:
        return value.strftime("%d.%m.%Y") if value else "—"

    def _load_car(self):
        c: Car | None = self.session.get(Car, self.car_id)
        if not c:
            return

        year = c.build_date.strftime("%Y") if c.build_date else "—"
        month = c.build_date.strftime("%m") if c.build_date else "—"
        brand = c.brand.name if c.brand else "—"
        model = c.model.name if c.model else "—"
        manager = c.responsible_user.full_name if c.responsible_user and c.responsible_user.full_name else getattr(c.responsible_user, "login", None)
        next_action = []
        if c.next_action_date:
            next_action.append(self._fmt_date(c.next_action_date))
        if c.next_action_note:
            next_action.append(c.next_action_note)

        self.lbl_title.setText(f"{year} {brand} {model}")
        self.v_build.setText(f"{month}/{year}" if c.build_date else "—")
        self.v_trim.setText(c.trim.name if c.trim else "—")
        self.v_body.setText(c.body_type.name if c.body_type else "—")
        self.v_fuel.setText(c.fuel_type.name if c.fuel_type else "—")
        self.v_trans.setText(c.transmission.name if c.transmission else "—")
        self.v_color.setText(c.color.name if c.color else "—")
        self.v_engine.setText(str(c.engine_cc) if c.engine_cc else "—")
        self.v_hp.setText(str(c.horsepower) if c.horsepower else "—")
        self.v_mileage.setText(f"{c.mileage_km:,}".replace(",", " ") if c.mileage_km else "—")
        self.v_location.setText(c.location_city or c.location_country or "—")
        self.v_price.setText(f"{c.price_to_vladivostok:,.2f}".replace(",", " ").replace(".", ",") if c.price_to_vladivostok else "—")
        self.v_status.setText(c.status or "—")
        self.v_deal.setText(c.deal_status or "—")
        self.v_client.setText(c.client.full_name if c.client and c.client.full_name else "—")
        self.v_responsible.setText(manager or "—")
        self.v_source.setText(c.lead_source or "—")
        self.v_priority.setText(priority_label(c.priority))
        self.v_eta.setText(self._fmt_date(c.expected_arrival_date))
        self.v_next_action.setText("\n".join(next_action) if next_action else "—")
        self.v_blocked.setText(c.blocked_reason or "—")

    def _load_tasks(self):
        self.list_tasks.clear()
        rows = (
            self.session.query(CarTask)
            .filter(CarTask.car_id == self.car_id)
            .order_by(CarTask.is_done.asc(), CarTask.due_date.asc(), CarTask.id.desc())
            .all()
        )
        for row in rows:
            parts = [row.title]
            meta = [priority_label(row.priority)]
            if row.due_date:
                meta.append(self._fmt_date(row.due_date))
            if row.is_done:
                meta.append("выполнено")
            if meta:
                parts.append(" · ".join(meta))
            if row.notes:
                parts.append(row.notes)
            item = QListWidgetItem("\n".join(parts))
            item.setData(Qt.ItemDataRole.UserRole, row.id)
            self.list_tasks.addItem(item)

    def _load_comments(self):
        self.list_comments.clear()
        rows = (
            self.session.query(CarComment)
            .filter(CarComment.car_id == self.car_id)
            .order_by(CarComment.created_at.desc(), CarComment.id.desc())
            .all()
        )
        for row in rows:
            stamp = row.created_at.strftime("%d.%m.%Y %H:%M") if row.created_at else "—"
            item = QListWidgetItem(f"{stamp}\n{row.body}")
            item.setData(Qt.ItemDataRole.UserRole, row.id)
            self.list_comments.addItem(item)

    def _current_task(self) -> CarTask | None:
        item = self.list_tasks.currentItem()
        if not item:
            return None
        task_id = item.data(Qt.ItemDataRole.UserRole)
        return self.session.get(CarTask, task_id) if task_id else None

    def _current_comment(self) -> CarComment | None:
        item = self.list_comments.currentItem()
        if not item:
            return None
        comment_id = item.data(Qt.ItemDataRole.UserRole)
        return self.session.get(CarComment, comment_id) if comment_id else None

    def _add_task(self):
        dialog = TaskDialog(self)
        if not dialog.exec():
            return
        data = dialog.get_data()
        task = CarTask(
            car_id=self.car_id,
            title=data["title"],
            due_date=data["due_date"],
            priority=data["priority"],
            notes=data["notes"],
        )
        self.session.add(task)
        self.session.commit()
        self._load_tasks()

    def _toggle_task_done(self):
        task = self._current_task()
        if not task:
            QMessageBox.information(self, "Задачи", "Выберите задачу в списке.")
            return
        task.is_done = not bool(task.is_done)
        task.done_at = dt.datetime.now() if task.is_done else None
        self.session.commit()
        self._load_tasks()

    def _delete_task(self):
        task = self._current_task()
        if not task:
            QMessageBox.information(self, "Задачи", "Выберите задачу в списке.")
            return
        if QMessageBox.question(self, "Удалить задачу", "Удалить выбранную задачу?") != QMessageBox.StandardButton.Yes:
            return
        self.session.delete(task)
        self.session.commit()
        self._load_tasks()

    def _add_comment(self):
        dialog = CommentDialog(self)
        if not dialog.exec():
            return
        row = CarComment(car_id=self.car_id, body=dialog.get_body())
        self.session.add(row)
        self.session.commit()
        self._load_comments()

    def _delete_comment(self):
        comment = self._current_comment()
        if not comment:
            QMessageBox.information(self, "Комментарии", "Выберите комментарий в списке.")
            return
        if QMessageBox.question(self, "Удалить комментарий", "Удалить выбранный комментарий?") != QMessageBox.StandardButton.Yes:
            return
        self.session.delete(comment)
        self.session.commit()
        self._load_comments()

    def _load_media(self):
        self.list_media.clear()
        self.media_index = -1
        self.media = self.session.query(CarMedia).filter(CarMedia.car_id == self.car_id).order_by(CarMedia.id.asc()).all()
        for media in self.media:
            name = Path(media.file_path).name
            self.list_media.addItem(QListWidgetItem(f"{media.media_type}: {media.original_name or name}"))
        if self.media:
            self.media_index = 0
            self._show_media(self.media_index)
        else:
            self.preview.setText("Нет медиа")
            self.btn_open_video.setVisible(False)

    def _show_media(self, idx: int):
        if idx < 0 or idx >= len(self.media):
            return
        media = self.media[idx]
        full_path = PKG_ROOT / media.file_path

        if media.media_type == "image":
            self.btn_open_video.setVisible(False)
            pix = QtGui.QPixmap(str(full_path))
            if not pix.isNull():
                pix = pix.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.preview.setPixmap(pix)
            else:
                self.preview.setText("Не удалось загрузить изображение")
        else:
            self.preview.setPixmap(QtGui.QPixmap())
            self.preview.setText(f"Видео: {full_path.name}")
            self.btn_open_video.setVisible(True)

    def resizeEvent(self, event):
        if 0 <= self.media_index < len(self.media) and self.media[self.media_index].media_type == "image":
            self._show_media(self.media_index)
        super().resizeEvent(event)

    def _prev_media(self):
        if not self.media:
            return
        self.media_index = (self.media_index - 1) % len(self.media)
        self._show_media(self.media_index)

    def _next_media(self):
        if not self.media:
            return
        self.media_index = (self.media_index + 1) % len(self.media)
        self._show_media(self.media_index)

    def _on_media_item_clicked(self, item: QListWidgetItem):
        row = self.list_media.row(item)
        if 0 <= row < len(self.media):
            self.media_index = row
            self._show_media(self.media_index)

    def _open_current_video(self):
        if 0 <= self.media_index < len(self.media):
            media = self.media[self.media_index]
            if media.media_type == "video":
                full_path = PKG_ROOT / media.file_path
                if full_path.exists():
                    os.startfile(str(full_path))

    def closeEvent(self, event):
        try:
            self.session.close()
        finally:
            super().closeEvent(event)
