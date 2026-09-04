# ShukCar/ui/login_window.py
from pathlib import Path
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QLineEdit, QPushButton, QGraphicsDropShadowEffect, QToolButton
)
from PyQt6.QtGui import QIcon, QFont

from auth_service import try_login
from theme import populate_theme_menu, theme_controller

PKG_ROOT = Path(__file__).resolve().parents[1]
ICON_PATH = PKG_ROOT / "img" / "logo_shukcar.jpg"

class LoginWindow(QMainWindow):
    logged_in = QtCore.pyqtSignal(object, bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ShukCar — Авторизация")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setMinimumSize(900, 600)
        self.showMaximized()

        # Центральный фон
        self.bg = QWidget(self)
        self.bg.setObjectName("LoginRoot")
        self.setCentralWidget(self.bg)

        # Карточка авторизации
        self.card = QFrame(self.bg)
        self.card.setObjectName("LoginCard")
        self.card.setFixedWidth(400)

        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 8)
        shadow.setColor(QtGui.QColor(0, 0, 0, 40))
        self.card.setGraphicsEffect(shadow)

        v = QVBoxLayout(self.card)
        v.setContentsMargins(28, 28, 28, 28)
        v.setSpacing(14)

        # Заголовки
        title = QLabel("ShukCar")
        title.setObjectName("LoginTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)

        subtitle = QLabel("Авторизация")
        subtitle.setObjectName("MutedLabel")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(subtitle)

        # Поле логина
        self.login = QLineEdit()
        self.login.setPlaceholderText("Логин")
        v.addWidget(self.login)

        # Поле пароля + «глаз»
        pw_row = QHBoxLayout()
        pw_row.setSpacing(8)

        self.password = QLineEdit()
        self.password.setPlaceholderText("Пароль")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)

        # Кнопка-глаз (иконки эмодзи, без внешних файлов)
        self.btn_eye = QToolButton()
        self.btn_eye.setCheckable(True)
        self.btn_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_eye.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_eye.setObjectName("ThemeButton")
        self.btn_eye.setText("👁")  # скрыт по умолчанию -> показать
        f = QFont()
        f.setPointSize(12)
        self.btn_eye.setFont(f)
        self.btn_eye.setToolTip("Показать/скрыть пароль")
        self.btn_eye.toggled.connect(self._toggle_password_eye)

        # Чтобы глаз был «внутри» строки справа — завернём в горизонтальный лэйаут
        pw_row.addWidget(self.password)
        pw_row.addWidget(self.btn_eye)
        v.addLayout(pw_row)

        # Кнопка входа (жёсткий стиль на случай отсутствия QSS)
        self.btn_login = QPushButton("Войти")
        self.btn_login.setFixedHeight(44)
        self.btn_login.setDefault(True)
        self.btn_login.clicked.connect(self._on_login_clicked)
        v.addWidget(self.btn_login)

        # Инфо-лейбл
        self.info = QLabel("")
        self.info.setObjectName("LoginInfo")
        self.info.setProperty("state", "muted")
        self.info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.info)

        # Центрирование карточки
        grid = QtWidgets.QGridLayout(self.bg)
        grid.setContentsMargins(24, 24, 24, 24)

        top_bar = QHBoxLayout()
        top_bar.addStretch(1)

        self.btn_theme = QToolButton(self.bg)
        self.btn_theme.setObjectName("ThemeButton")
        self.btn_theme.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_theme_menu = QtWidgets.QMenu(self)
        populate_theme_menu(self.btn_theme_menu, self)
        self.btn_theme.setMenu(self.btn_theme_menu)
        top_bar.addWidget(self.btn_theme)

        grid.addLayout(top_bar, 0, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.card, 1, 0, Qt.AlignmentFlag.AlignCenter)
        grid.setRowStretch(1, 1)

        # Enter = Войти
        self.login.returnPressed.connect(self.btn_login.click)
        self.password.returnPressed.connect(self.btn_login.click)
        theme_controller.theme_changed.connect(self._sync_theme_button)
        self._sync_theme_button(theme_controller.current_theme())

    # === ЛОГИКА ===
    def _toggle_password_eye(self, checked: bool):
        if checked:
            self.password.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_eye.setText("🙈")  # показан -> «скрыть»
        else:
            self.password.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_eye.setText("👁")  # скрыт -> «показать»

    def _sync_theme_button(self, theme_name: str):
        label = "Тема: Светлая" if theme_name == "light" else "Тема: Тёмная"
        self.btn_theme.setText(label)

    def _on_login_clicked(self):
        login = self.login.text().strip()
        password = self.password.text()

        # Bootstrap-вход для первичного админа
        if login == "Admin" and password == "Admin":
            self._notify("Успешный вход как Администратор (режим Admin/Admin).")
            self.logged_in.emit(None, True)
            return

        ok, user, msg = try_login(login, password)
        if ok:
            self._notify(msg)
            # если роль admin — в админку, иначе — в рабочее место
            self.logged_in.emit(user, False)
        else:
            self._notify(msg, error=True)

    def _notify(self, text: str, error: bool = False):
        self.info.setProperty("state", "error" if error else "success")
        self.info.style().unpolish(self.info)
        self.info.style().polish(self.info)
        self.info.setText(text)
