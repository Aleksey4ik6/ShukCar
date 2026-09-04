from PyQt6 import QtWidgets
from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from models import UserRole


class UserForm(QDialog):
    def __init__(self, parent=None, user=None):
        super().__init__(parent)
        self.setWindowTitle("Пользователь")
        self.resize(440, 10)

        self.ed_fullname = QLineEdit()
        self.ed_dob = QDateEdit()
        self.ed_dob.setCalendarPopup(True)
        self.ed_dob.setDisplayFormat("dd.MM.yyyy")
        self.ed_phone = QLineEdit()
        self.ed_email = QLineEdit()
        self.ed_login = QLineEdit()
        self.ed_password = QLineEdit()
        self.ed_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.cb_show_password = QCheckBox("Показать пароль")
        self.cb_show_password.toggled.connect(self._toggle_password)
        self.cb_role = QComboBox()
        self.cb_role.addItems([UserRole.trainee.value, UserRole.manager.value, UserRole.admin.value, UserRole.user.value])
        self.cb_active = QCheckBox("Активен")

        root = QVBoxLayout(self)
        form_wrap = QWidget(self)
        form = QFormLayout(form_wrap)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.addRow("ФИО:", self.ed_fullname)
        form.addRow("Дата рождения:", self.ed_dob)
        form.addRow("Телефон:", self.ed_phone)
        form.addRow("E-mail:", self.ed_email)
        form.addRow("Логин:", self.ed_login)
        form.addRow("Пароль:", self.ed_password)
        form.addRow("", self.cb_show_password)
        form.addRow("Роль:", self.cb_role)
        form.addRow("", self.cb_active)
        root.addWidget(form_wrap)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self.user = user
        if user:
            self.ed_fullname.setText(user.full_name or "")
            if user.date_of_birth:
                self.ed_dob.setDate(QDate(user.date_of_birth.year, user.date_of_birth.month, user.date_of_birth.day))
            self.ed_phone.setText(user.phone or "")
            self.ed_email.setText(user.email or "")
            self.ed_login.setText(user.login or "")
            self.cb_role.setCurrentText(user.role.value)
            self.cb_active.setChecked(bool(user.is_active))
        else:
            self.cb_role.setCurrentText(UserRole.trainee.value)
            self.cb_active.setChecked(True)
            self.ed_dob.setDate(QDate(2000, 1, 1))

    def _toggle_password(self, checked: bool):
        self.ed_password.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)

    def get_data(self):
        dob = None
        if self.ed_dob.date().isValid():
            d = self.ed_dob.date()
            dob = f"{d.year():04d}-{d.month():02d}-{d.day():02d}"
        return {
            "full_name": self.ed_fullname.text().strip(),
            "date_of_birth": dob,
            "phone": self.ed_phone.text().strip() or None,
            "email": self.ed_email.text().strip() or None,
            "login": self.ed_login.text().strip(),
            "password": self.ed_password.text(),
            "role": UserRole(self.cb_role.currentText()),
            "is_active": self.cb_active.isChecked(),
        }
