from __future__ import annotations

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from db import SessionLocal
from models import User
from services.crm import fill_lead_source_combo, fill_priority_combo
from .address_widget import AddressWidget


class ClientForm(QDialog):
    def __init__(self, parent=None, client=None):
        super().__init__(parent)
        self.setWindowTitle("Клиент")
        self.resize(680, 760)
        self.setMinimumSize(620, 680)

        self.ed_fullname = QLineEdit()
        self.ed_phone = QLineEdit()
        self.ed_email = QLineEdit()
        self.ed_passport = QLineEdit()
        self.address_widget = AddressWidget(self)
        self.ed_snils = QLineEdit()
        self.ed_inn = QLineEdit()

        self.ed_dob = QDateEdit()
        self.ed_dob.setCalendarPopup(True)
        self.ed_dob.setDisplayFormat("dd.MM.yyyy")

        self.ed_pass_issuer = QLineEdit()

        self.ed_pass_issue_date = QDateEdit()
        self.ed_pass_issue_date.setCalendarPopup(True)
        self.ed_pass_issue_date.setDisplayFormat("dd.MM.yyyy")

        self.ed_pass_code = QLineEdit()
        self.cb_manager = QComboBox()
        self.cb_lead_source = QComboBox()
        self.cb_priority = QComboBox()

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        form = QFormLayout(container)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        form.addRow("ФИО:", self.ed_fullname)
        form.addRow("Телефон:", self.ed_phone)
        form.addRow("E-mail:", self.ed_email)
        form.addRow("Ответственный менеджер:", self.cb_manager)
        form.addRow("Источник лида:", self.cb_lead_source)
        form.addRow("Приоритет:", self.cb_priority)
        form.addRow("Паспорт (серия/номер):", self.ed_passport)
        form.addRow("Адрес:", self.address_widget)
        form.addRow("СНИЛС:", self.ed_snils)
        form.addRow("ИНН:", self.ed_inn)
        form.addRow("Дата рождения:", self.ed_dob)
        form.addRow("Кем выдан паспорт:", self.ed_pass_issuer)
        form.addRow("Дата выдачи паспорта:", self.ed_pass_issue_date)
        form.addRow("Код подразделения:", self.ed_pass_code)

        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons, 0)

        self._load_managers()
        fill_lead_source_combo(self.cb_lead_source, getattr(client, "lead_source", None))
        fill_priority_combo(self.cb_priority, getattr(client, "priority", None))

        self.client = client
        if client:
            self.ed_fullname.setText(client.full_name or "")
            self.ed_phone.setText(client.phone or "")
            self.ed_email.setText(client.email or "")
            idx = self.cb_manager.findData(getattr(client, "responsible_user_id", None))
            if idx >= 0:
                self.cb_manager.setCurrentIndex(idx)
            self.ed_passport.setText(client.passport_no or "")
            self.address_widget.set_address(client.registration_address or "")
            self.ed_snils.setText(client.snils or "")
            self.ed_inn.setText(client.inn or "")
            if client.date_of_birth:
                self.ed_dob.setDate(QDate(client.date_of_birth.year, client.date_of_birth.month, client.date_of_birth.day))
            if client.passport_issue_date:
                self.ed_pass_issue_date.setDate(
                    QDate(client.passport_issue_date.year, client.passport_issue_date.month, client.passport_issue_date.day)
                )
            self.ed_pass_issuer.setText(client.passport_issuer or "")
            self.ed_pass_code.setText(client.passport_division_code or "")

    def _load_managers(self):
        self.cb_manager.clear()
        self.cb_manager.addItem("Не назначен", None)
        with SessionLocal() as session:
            users = session.query(User).order_by(User.full_name.asc(), User.login.asc()).all()
            for user in users:
                label = user.full_name or user.login or f"Пользователь #{user.id}"
                self.cb_manager.addItem(label, user.id)

    def get_data(self) -> dict:
        dob = self.ed_dob.date()
        dob_s = f"{dob.year():04d}-{dob.month():02d}-{dob.day():02d}" if dob.isValid() else None
        issue_date = self.ed_pass_issue_date.date()
        issue_date_s = (
            f"{issue_date.year():04d}-{issue_date.month():02d}-{issue_date.day():02d}"
            if issue_date.isValid()
            else None
        )

        addr = self.address_widget.get_address_data()
        registration_address = addr.get("source") or addr.get("value")

        return {
            "full_name": self.ed_fullname.text().strip(),
            "phone": self.ed_phone.text().strip() or None,
            "email": self.ed_email.text().strip() or None,
            "responsible_user_id": self.cb_manager.currentData(),
            "lead_source": self.cb_lead_source.currentText().strip() or None,
            "priority": self.cb_priority.currentData() or None,
            "passport_no": self.ed_passport.text().strip() or None,
            "registration_address": registration_address,
            "country": addr.get("country"),
            "region": addr.get("region"),
            "city": addr.get("city"),
            "street": addr.get("street"),
            "house": addr.get("house"),
            "block": addr.get("block"),
            "flat": addr.get("flat"),
            "postal_code": addr.get("postal_code"),
            "fias_id": addr.get("fias_id"),
            "kladr_id": addr.get("kladr_id"),
            "geo_lat": addr.get("geo_lat"),
            "geo_lon": addr.get("geo_lon"),
            "snils": self.ed_snils.text().strip() or None,
            "inn": self.ed_inn.text().strip() or None,
            "date_of_birth": dob_s,
            "passport_issuer": self.ed_pass_issuer.text().strip() or None,
            "passport_issue_date": issue_date_s,
            "passport_division_code": self.ed_pass_code.text().strip() or None,
        }
