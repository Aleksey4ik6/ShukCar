import sys

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)

from auth_service import set_user_online_status
from db import SessionLocal
from services.runtime_schema import ensure_runtime_schema
from theme import theme_controller
from ui.mobile_login_window import MobileLoginWindow
from ui.mobile_window import MobileWindow


class MobileAppController:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setStyle("Fusion")
        self.app.setOrganizationName("ShukCar")
        self.app.setApplicationName("ShukCar Mobile Workspace")
        ensure_runtime_schema()
        theme_controller.apply_saved_theme(self.app)
        self.app.aboutToQuit.connect(self._mark_current_user_offline)
        self.login = None
        self.current = None
        self._windows = []
        self.current_user_id = None

    def _show_error(self, title: str, exc: Exception):
        QMessageBox.critical(self.login or self.current, title, str(exc).strip() or exc.__class__.__name__)

    def _mark_current_user_offline(self):
        if not self.current_user_id:
            return
        try:
            with SessionLocal() as db:
                set_user_online_status(db, int(self.current_user_id), False)
        except Exception:
            pass
        self.current_user_id = None

    def show_login(self):
        if self.current:
            self.current.close()
            self.current = None
        if self.login:
            try:
                self.login.close()
            except Exception:
                pass
        self.login = MobileLoginWindow()
        self._windows.append(self.login)
        self.login.logged_in.connect(self.show_main)
        self.login.show()

    def show_main(self, user):
        try:
            self.current_user_id = getattr(user, "id", None)
            wnd = MobileWindow(user, on_logout=self.logout)
        except Exception as exc:
            self._show_error("Ошибка открытия мобильного режима", exc)
            return
        if self.login:
            self.login.close()
            self.login = None
        self._windows.append(wnd)
        self.current = wnd
        wnd.show()

    def logout(self):
        self._mark_current_user_offline()
        self.show_login()

    def run(self):
        self.show_login()
        sys.exit(self.app.exec())


def run():
    MobileAppController().run()


if __name__ == "__main__":
    run()
