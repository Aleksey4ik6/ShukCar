# ShukCar/ui/danger_wipe_dialog.py
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt

from db import SessionLocal
from services.danger_wipe import wipe_all_data
from config import WIPE_SECRET
from models import User, AuditLog


class DangerWipeDialog(QDialog):
    """
    Диалог «Очистить все данные» с 3 степенями защиты:
      1) Подтверждение диалога
      2) Ввод фразы: ОЧИСТИТЬ ВСЕ
      3) Ввод пароля администратора (WIPE_SECRET в config.py)

    ВАЖНО: доступ теперь НЕ зависит от роли пользователя.
           Если пароль верный — очистка разрешена, событие логируется.
    """
    def __init__(self, parent=None, current_user: User | None = None):
        super().__init__(parent)
        self.setWindowTitle("Очистка всех данных")
        self.resize(520, 220)
        self.user = current_user

        root = QVBoxLayout(self)
        root.setSpacing(10)

        lbl = QLabel(
            "<b>ВНИМАНИЕ!</b> Это действие <u>безвозвратно</u> удалит все автомобили, клиентов, справочники, медиа и журналы."
            "<br>Откат невозможен. Сделайте резервную копию БД перед применением.",
            self
        )
        lbl.setWordWrap(True)
        root.addWidget(lbl)

        # Подтверждение фразой
        self.ed_phrase = QLineEdit(self)
        self.ed_phrase.setPlaceholderText("Введите: ОЧИСТИТЬ ВСЕ")
        root.addWidget(self.ed_phrase)

        # Пароль администратора
        self.ed_pass = QLineEdit(self)
        self.ed_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_pass.setPlaceholderText("Пароль администратора (WIPE_SECRET)")
        root.addWidget(self.ed_pass)

        # Кнопки
        hb = QHBoxLayout()
        self.btn_cancel = QPushButton("Отмена", self)
        self.btn_cancel.setProperty("accent", "secondary")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_wipe = QPushButton("Удалить всё", self)
        self.btn_wipe.setProperty("accent", "danger")
        self.btn_wipe.clicked.connect(self._do_wipe)

        hb.addStretch(1)
        hb.addWidget(self.btn_cancel)
        hb.addWidget(self.btn_wipe)
        root.addLayout(hb)

    def _do_wipe(self):
        # Шаг 1: подтверждение кликом
        if QMessageBox.question(
            self, "Подтверждение",
            "Вы уверены, что хотите удалить ВСЕ данные?\nДействие безвозвратно."
        ) != QMessageBox.StandardButton.Yes:
            return

        # Шаг 2: фраза
        phrase = (self.ed_phrase.text() or "").strip()
        if phrase.upper() != "ОЧИСТИТЬ ВСЕ":
            QMessageBox.information(self, "Подтверждение", "Введите точную фразу: ОЧИСТИТЬ ВСЕ")
            return

        # Шаг 3: пароль
        secret_input = (self.ed_pass.text() or "").strip()
        configured_secret = (WIPE_SECRET or "").strip()
        if not configured_secret:
            QMessageBox.critical(self, "Ошибка конфигурации", "В config.py не задан WIPE_SECRET.")
            return
        if secret_input != configured_secret:
            QMessageBox.critical(self, "Неверный пароль", "Пароль администратора введён неверно.")
            return

        # Выполняем очистку + аудит
        try:
            s = SessionLocal()

            # Аудит — записываем, КТО запустил
            try:
                s.add(AuditLog(
                    user_id=getattr(self.user, "id", None),
                    action="wipe_all",
                    entity="system",
                    entity_id=None,
                    details=f"Full wipe initiated by user_id={getattr(self.user, 'id', None)}"
                ))
                s.commit()
            except Exception:
                s.rollback()

            stats = wipe_all_data(s)

            # Аудит — завершение
            try:
                s.add(AuditLog(
                    user_id=getattr(self.user, "id", None),
                    action="wipe_all_completed",
                    entity="system",
                    entity_id=None,
                    details="Full wipe completed"
                ))
                s.commit()
            except Exception:
                s.rollback()

            s.close()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось завершить очистку:\n{e}")
            return

        details = "\n".join(f"{k}: {v}" for k, v in stats.items())
        QMessageBox.information(self, "Готово", f"Все данные удалены.\n\n{details}")
        self.accept()
