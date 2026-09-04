# ShukCar/main.py
import sys
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)

from auth_service import set_user_online_status
from db import SessionLocal
from theme import theme_controller
from services.runtime_schema import ensure_runtime_schema
from ui.login_window import LoginWindow
from ui.main_window import MainWindow
from ui.admin_window import AdminWindow

class AppController:
    """
    Управляет окнами: Авторизация -> (Админка | Рабочее место) -> Выход (обратно на Авторизацию)
    """
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setStyle("Fusion")
        self.app.setOrganizationName("ShukCar")
        self.app.setApplicationName("ShukCar")
        ensure_runtime_schema()
        theme_controller.apply_saved_theme(self.app)
        self.app.aboutToQuit.connect(self._mark_current_user_offline)
        self._windows = []  # держим ссылки, чтобы окна не схлопывались
        self.login = None
        self.current = None
        self.current_user_id = None

    def _format_error(self, exc: Exception) -> str:
        text = str(exc).strip() or exc.__class__.__name__
        if "cryptography" in text.lower():
            return (
                "Не удалось подключиться к MySQL при открытии следующего окна.\n\n"
                "Для текущего метода авторизации MySQL нужен пакет `cryptography`.\n"
                "Установите его командой:\n"
                ".venv\\Scripts\\python.exe -m pip install cryptography"
            )
        return f"Произошла ошибка:\n{text}"

    def _show_error(self, title: str, exc: Exception):
        QMessageBox.critical(self.login or self.current, title, self._format_error(exc))

    def _mark_current_user_offline(self):
        if not self.current_user_id:
            return
        try:
            with SessionLocal() as db:
                set_user_online_status(db, int(self.current_user_id), False)
        except Exception:
            pass
        self.current_user_id = None

    # ===== Переходы =====
    def show_login(self):
        # закрываем текущее окно (если есть)
        if self.current:
            self.current.close()
            self.current = None
        if self.login:
            try:
                self.login.close()
            except Exception:
                pass
        self.login = LoginWindow()
        self._windows.append(self.login)

        # обработчик успешного входа
        def on_logged_in(user_or_none, is_admin_menu: bool):
            try:
                self.current_user_id = getattr(user_or_none, "id", None)
                if is_admin_menu:
                    self.show_admin()
                else:
                    # если у пользователя роль admin — в админку, иначе — в рабочее место
                    if getattr(user_or_none, "role", None) and getattr(user_or_none.role, "value", "") == "admin":
                        self.show_admin()
                    else:
                        self.show_main(user_or_none)
            except Exception as exc:
                self._show_error("Ошибка входа", exc)

        self.login.logged_in.connect(on_logged_in)
        self.login.show()

    def show_admin(self):
        old_login = self.login
        try:
            wnd = AdminWindow(on_logout=self.logout)
        except Exception as exc:
            if old_login:
                old_login.show()
                old_login.raise_()
                old_login.activateWindow()
            self._show_error("Ошибка открытия админки", exc)
            return
        if old_login:
            old_login.close()
            self.login = None
        self._windows.append(wnd)
        self.current = wnd
        wnd.show()

    def show_main(self, user):
        try:
            wnd = MainWindow(user, on_logout=self.logout)
        except Exception as exc:
            self._show_error("Ошибка открытия рабочего места", exc)
            return
        if self.login:
            self.login.close()
            self.login = None
        self._windows.append(wnd)
        self.current = wnd
        wnd.show()

    def logout(self):
        # перейти обратно на экран авторизации
        self._mark_current_user_offline()
        self.show_login()

    def run(self):
        self.show_login()
        sys.exit(self.app.exec())

def run():
    AppController().run()

if __name__ == "__main__":
    run()
