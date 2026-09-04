from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from auth_service import try_login


PKG_ROOT = Path(__file__).resolve().parents[1]
ICON_PATH = PKG_ROOT / "img" / "logo_shukcar.jpg"


def _make_chip(text: str, parent: QWidget | None = None) -> QLabel:
    label = QLabel(text, parent)
    label.setProperty("chip", True)
    return label


class MobileLoginWindow(QWidget):
    logged_in = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ShukCar - Mobile Workspace")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(980, 700)
        self.setMinimumSize(820, 620)
        self.setObjectName("LoginRoot")

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(0)

        shell = QWidget(self)
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(18)
        root.addWidget(shell, 1, Qt.AlignmentFlag.AlignCenter)

        hero = QFrame(shell)
        hero.setObjectName("LoginCard")
        hero.setMinimumWidth(360)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 30, 28, 30)
        hero_layout.setSpacing(14)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)
        brand_mark = QLabel("SC", hero)
        brand_mark.setObjectName("AvatarBadge")
        brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_mark.setFixedSize(48, 48)
        brand_row.addWidget(brand_mark, 0, Qt.AlignmentFlag.AlignTop)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(2)
        brand_title = QLabel("ShukCar", hero)
        brand_title.setObjectName("BrandTitle")
        brand_caption = QLabel("Mobile workspace для менеджеров и сотрудников", hero)
        brand_caption.setObjectName("BrandCaption")
        brand_caption.setWordWrap(True)
        brand_text.addWidget(brand_title)
        brand_text.addWidget(brand_caption)
        brand_row.addLayout(brand_text, 1)
        hero_layout.addLayout(brand_row)

        kicker = QLabel("БЫСТРЫЙ ДОСТУП", hero)
        kicker.setObjectName("HeroKicker")
        title = QLabel("Рабочее пространство без перегруза", hero)
        title.setObjectName("LoginTitle")
        title.setWordWrap(True)
        subtitle = QLabel(
            "Откройте автомобили, клиентов, сделки, чат и калькулятор в более лёгком и удобном режиме для повседневной работы.",
            hero,
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        hero_layout.addWidget(kicker)
        hero_layout.addWidget(title)
        hero_layout.addWidget(subtitle)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)
        chips_row.addWidget(_make_chip("Автомобили", hero))
        chips_row.addWidget(_make_chip("Клиенты", hero))
        chips_row.addWidget(_make_chip("Чат", hero))
        chips_row.addStretch(1)
        hero_layout.addLayout(chips_row)

        points_card = QFrame(hero)
        points_card.setProperty("card", True)
        points_layout = QVBoxLayout(points_card)
        points_layout.setContentsMargins(18, 18, 18, 18)
        points_layout.setSpacing(10)

        points_title = QLabel("Что внутри", points_card)
        points_title.setObjectName("SectionTitle")
        points_layout.addWidget(points_title)

        for text in (
            "Быстрый обзор активных автомобилей, клиентов и сделок.",
            "Командный и личный чат между сотрудниками.",
            "Калькулятор стоимости привоза и ежедневная рабочая сводка.",
        ):
            line = QLabel(text, points_card)
            line.setWordWrap(True)
            line.setObjectName("InlineMutedLabel")
            points_layout.addWidget(line)

        hero_layout.addWidget(points_card)
        hero_layout.addStretch(1)

        form = QFrame(shell)
        form.setObjectName("LoginCard")
        form.setMinimumWidth(360)
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(28, 30, 28, 30)
        form_layout.setSpacing(12)

        form_eyebrow = QLabel("Вход сотрудника", form)
        form_eyebrow.setObjectName("InlineMutedLabel")
        form_title = QLabel("Войдите в ShukCar", form)
        form_title.setObjectName("SectionTitle")
        form_subtitle = QLabel("Используйте ваш рабочий логин и пароль.", form)
        form_subtitle.setObjectName("InlineMutedLabel")
        form_subtitle.setWordWrap(True)

        self.ed_login = QLineEdit(form)
        self.ed_login.setPlaceholderText("Логин")
        self.ed_login.setMinimumHeight(46)

        self.ed_password = QLineEdit(form)
        self.ed_password.setPlaceholderText("Пароль")
        self.ed_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_password.setMinimumHeight(46)

        password_row = QHBoxLayout()
        password_row.setSpacing(8)
        password_row.addWidget(self.ed_password, 1)
        self.btn_show_password = QPushButton("Показать", form)
        self.btn_show_password.setCheckable(True)
        self.btn_show_password.setProperty("accent", "secondary")
        self.btn_show_password.clicked.connect(self._toggle_password_visibility)
        password_row.addWidget(self.btn_show_password, 0)

        self.lbl_status = QLabel("", form)
        self.lbl_status.setObjectName("LoginInfo")
        self.lbl_status.setProperty("state", "muted")
        self.lbl_status.setWordWrap(True)

        self.btn_login = QPushButton("Войти", form)
        self.btn_login.setMinimumHeight(48)
        self.btn_login.clicked.connect(self._handle_login)

        form_layout.addWidget(form_eyebrow)
        form_layout.addWidget(form_title)
        form_layout.addWidget(form_subtitle)
        form_layout.addSpacing(10)
        form_layout.addWidget(self.ed_login)
        form_layout.addLayout(password_row)
        form_layout.addWidget(self.lbl_status)
        form_layout.addStretch(1)
        form_layout.addWidget(self.btn_login)

        shell_layout.addWidget(hero, 1)
        shell_layout.addWidget(form, 1)

        self.ed_password.returnPressed.connect(self._handle_login)
        self.ed_login.returnPressed.connect(self.ed_password.setFocus)
        self._set_status("Введите логин и пароль сотрудника.", "muted")

    def _set_status(self, text: str, state: str):
        self.lbl_status.setText(text)
        self.lbl_status.setProperty("state", state)
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)
        self.lbl_status.update()

    def _toggle_password_visibility(self, checked: bool):
        self.ed_password.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )
        self.btn_show_password.setText("Скрыть" if checked else "Показать")

    def _handle_login(self):
        login = self.ed_login.text().strip()
        password = self.ed_password.text()
        ok, user, message = try_login(login, password)
        self._set_status(message, "success" if ok else "error")
        if not ok or user is None:
            QMessageBox.warning(self, "Вход", message)
            return
        self.logged_in.emit(user)
