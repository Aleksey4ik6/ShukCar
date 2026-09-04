from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from models import User, UserRole
from theme import THEMES, populate_theme_menu, theme_controller
from ui.attention_center import AttentionCenter
from ui.calculator_view import CalculatorView
from ui.cars_view import CarsView
from ui.chat_view import ChatView
from ui.clients_view import ClientsView
from ui.dashboard_view import DashboardView
from ui.deals_view import DealsView
from ui.home_overview import HomeOverview
from ui.rates_realtime_view import RatesRealtimeView

try:
    from ui.catalog_import_dialog import CatalogImportDialog
except Exception:
    CatalogImportDialog = None  # type: ignore

from ui.danger_wipe_dialog import DangerWipeDialog


PKG_ROOT = Path(__file__).resolve().parents[1]
ICON_PATH = PKG_ROOT / "img" / "logo_shukcar.jpg"


class ClickableFrame(QFrame):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class NavigationButton(QPushButton):
    def __init__(self, title: str, subtitle: str, compact_label: str | None = None, parent=None):
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self._compact_label = compact_label or title[:2].upper()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("nav", True)
        self.setProperty("compact", False)
        self.setToolTip(f"{title}\n{subtitle}")
        self.set_compact(False)

    def set_compact(self, compact: bool):
        self.setProperty("compact", compact)
        self.setText(self._compact_label if compact else f"{self._title}\n{self._subtitle}")
        if compact:
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.setFixedSize(52, 52)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.setFixedHeight(68)
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class WorkspaceSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки интерфейса")
        self.setModal(True)
        self.resize(480, 320)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        title = QLabel("Оформление рабочего места", self)
        title.setObjectName("SectionTitle")
        caption = QLabel(
            "Здесь можно быстро переключить тему и посмотреть базовые настройки оболочки приложения.",
            self,
        )
        caption.setWordWrap(True)
        caption.setObjectName("MutedLabel")
        root.addWidget(title)
        root.addWidget(caption)

        card = QFrame(self)
        card.setProperty("card", True)
        grid = QGridLayout(card)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self.theme_combo = QComboBox(card)
        for name, theme in THEMES.items():
            self.theme_combo.addItem(theme.label, name)
        self.theme_combo.currentIndexChanged.connect(self._apply_theme)
        grid.addWidget(QLabel("Тема"), 0, 0)
        grid.addWidget(self.theme_combo, 0, 1)

        hint = QLabel(
            "Боковое меню теперь сворачивается по нажатию на логотип ShukCar в левом верхнем углу.",
            card,
        )
        hint.setObjectName("InlineMutedLabel")
        hint.setWordWrap(True)
        grid.addWidget(hint, 1, 0, 1, 2)
        root.addWidget(card)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)
        root.addWidget(button_box)

        self._sync_theme(theme_controller.current_theme())
        theme_controller.theme_changed.connect(self._sync_theme)

    def _sync_theme(self, theme_name: str):
        index = self.theme_combo.findData(theme_name)
        if index >= 0 and index != self.theme_combo.currentIndex():
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(index)
            self.theme_combo.blockSignals(False)

    def _apply_theme(self):
        theme_name = self.theme_combo.currentData()
        if theme_name:
            theme_controller.set_theme(str(theme_name))


class MainWindow(QMainWindow):
    def __init__(self, current_user: User, on_logout: Optional[Callable[[], None]] = None):
        super().__init__()
        self.user = current_user
        self.on_logout = on_logout
        self._sidebar_collapsed = False
        self._nav_buttons: dict[str, NavigationButton] = {}
        self._nav_stack: list[tuple[QWidget, str, str, str]] = []
        self._current: QWidget | None = None
        self._current_key = "home"

        self.setWindowTitle("ShukCar - Рабочее пространство")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.showMaximized()

        self._build_ui()
        self._build_menus()
        self.go_home()
        self.statusBar().showMessage("Готово к работе")

    def _build_ui(self):
        user_name = self.user.full_name or getattr(self.user, "login", "Пользователь")

        self._central = QWidget(self)
        self._central.setObjectName("AppRoot")
        outer = QVBoxLayout(self._central)
        outer.setContentsMargins(18, 18, 18, 14)
        outer.setSpacing(0)
        self.setCentralWidget(self._central)

        shell = QFrame(self._central)
        shell.setObjectName("ShellSurface")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(16)
        outer.addWidget(shell, 1)

        self.sidebar = QFrame(shell)
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setProperty("collapsed", False)
        self.sidebar.setFixedWidth(280)
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(16, 18, 16, 18)
        self.sidebar_layout.setSpacing(12)
        shell_layout.addWidget(self.sidebar, 0)

        self.brand_card = ClickableFrame(self.sidebar)
        self.brand_card.setObjectName("BrandCard")
        self.brand_card.setProperty("card", True)
        self.brand_card.setCursor(Qt.CursorShape.PointingHandCursor)
        self.brand_card.setToolTip("Свернуть или развернуть боковое меню")
        self.brand_card.clicked.connect(self._toggle_sidebar)
        self.brand_layout = QHBoxLayout(self.brand_card)
        self.brand_layout.setContentsMargins(14, 12, 14, 12)
        self.brand_layout.setSpacing(14)

        self.lbl_brand_mark = QLabel("SC", self.brand_card)
        self.lbl_brand_mark.setObjectName("AvatarBadge")
        self.lbl_brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_brand_mark.setFixedSize(52, 52)
        self.lbl_brand_mark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.brand_layout.addWidget(self.lbl_brand_mark, 0, Qt.AlignmentFlag.AlignVCenter)

        brand_text = QVBoxLayout()
        brand_text.setContentsMargins(0, 0, 0, 0)
        brand_text.setSpacing(0)
        self.lbl_brand_title = QLabel("ShukCar", self.brand_card)
        self.lbl_brand_title.setObjectName("BrandTitle")
        self.lbl_brand_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        brand_text.addWidget(self.lbl_brand_title)
        self.brand_layout.addLayout(brand_text, 1)
        self.brand_layout.addStretch(1)
        self.sidebar_layout.addWidget(self.brand_card)

        self.lbl_nav_section = QLabel("Навигация", self.sidebar)
        self.lbl_nav_section.setObjectName("InlineMutedLabel")
        self.sidebar_layout.addWidget(self.lbl_nav_section)

        self._register_nav_button("home", "Обзор", "Главный экран", self.go_home, "Об")
        self._register_nav_button("attention", "Фокус", "Просрочки и контроль", self.show_attention, "Фк")
        self._register_nav_button("deals", "Сделки", "В работе, архив и контроль", self.show_deals, "Сд")
        self._register_nav_button("cars", "Автомобили", "Карточки авто и медиа", self.show_cars, "Ав")
        self._register_nav_button("clients", "Клиенты", "База клиентов и контактов", self.show_clients, "Кл")
        self._register_nav_button("dashboard", "Аналитика", "Показатели и контроль", self.show_dashboard, "Ан")
        self._register_nav_button("calculator", "Калькулятор", "Стоимость привоза", self.show_calc, "Кр")
        self._register_nav_button("chat", "Чат", "Командная связь", self.show_chat, "Чт")
        self._register_nav_button("rates", "Курсы валют", "Онлайн-ставки и контроль", self.show_rates_realtime, "Ку")
        self.sidebar_layout.addStretch(1)

        workspace = QWidget(shell)
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(14)
        shell_layout.addWidget(workspace, 1)

        topbar = QFrame(workspace)
        topbar.setObjectName("TopBar")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(18, 16, 18, 16)
        topbar_layout.setSpacing(12)
        workspace_layout.addWidget(topbar, 0)

        self.btn_back = QPushButton("Назад", topbar)
        self.btn_back.setObjectName("BackButton")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.clicked.connect(self.go_back)
        self.btn_back.setEnabled(False)
        topbar_layout.addWidget(self.btn_back, 0)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)
        self.lbl_title = QLabel("Рабочее пространство", topbar)
        self.lbl_title.setObjectName("HeaderTitle")
        self.lbl_subtitle = QLabel("Главный экран с фокусом дня и быстрыми переходами.", topbar)
        self.lbl_subtitle.setObjectName("PageSubtitle")
        self.lbl_subtitle.setWordWrap(True)
        title_box.addWidget(self.lbl_title)
        title_box.addWidget(self.lbl_subtitle)
        topbar_layout.addLayout(title_box, 1)

        search_box = QHBoxLayout()
        search_box.setContentsMargins(0, 0, 0, 0)
        search_box.setSpacing(8)
        self.search_edit = QLineEdit(topbar)
        self.search_edit.setObjectName("TopSearch")
        self.search_edit.setPlaceholderText("Поиск по VIN, клиенту, телефону...")
        self.search_edit.setMinimumWidth(260)
        self.search_edit.setMaximumWidth(420)
        self.search_edit.returnPressed.connect(self._do_search)
        search_box.addWidget(self.search_edit)
        self.btn_search = QPushButton("Найти", topbar)
        self.btn_search.setObjectName("SearchButton")
        self.btn_search.setProperty("accent", "secondary")
        self.btn_search.clicked.connect(self._do_search)
        search_box.addWidget(self.btn_search)
        topbar_layout.addLayout(search_box, 0)

        self.btn_workspace_menu = QPushButton("Настройки", topbar)
        self.btn_workspace_menu.setObjectName("MenuButton")
        self.btn_workspace_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        topbar_layout.addWidget(self.btn_workspace_menu, 0)

        self.btn_profile = QPushButton(user_name, topbar)
        self.btn_profile.setObjectName("ProfileButton")
        self.btn_profile.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_profile.setMinimumWidth(170)
        self.btn_profile.setMaximumWidth(260)
        topbar_layout.addWidget(self.btn_profile, 0)

        self._content_host = QWidget(workspace)
        self._content_layout = QVBoxLayout(self._content_host)
        self._content_layout.setContentsMargins(2, 0, 2, 2)
        self._content_layout.setSpacing(0)
        workspace_layout.addWidget(self._content_host, 1)

        self._home = HomeOverview(
            self.user,
            open_attention=self.show_attention,
            open_deals=self.show_deals,
            open_cars=self.show_cars,
            open_clients=self.show_clients,
            open_dashboard=self.show_dashboard,
            open_calc=self.show_calc,
            open_chat=self.show_chat,
            open_rates=self.show_rates_realtime,
            parent=self,
        )

        self._deals_view = None
        self._attention_view = None
        self._cars_view = None
        self._clients_view = None
        self._dashboard_view = None
        self._calc_view = None
        self._chat_view = None
        self._rates_realtime_view = None

    def _build_menus(self):
        self.workspace_menu = QMenu(self)
        self.profile_menu = QMenu(self)
        self.btn_workspace_menu.setMenu(self.workspace_menu)
        self.btn_profile.setMenu(self.profile_menu)
        self.workspace_menu.aboutToShow.connect(self._fill_workspace_menu)
        self.profile_menu.aboutToShow.connect(self._fill_profile_menu)
        self._fill_workspace_menu()
        self._fill_profile_menu()

    def _register_nav_button(
        self,
        key: str,
        title: str,
        subtitle: str,
        callback: Callable[[], None],
        compact_label: str | None = None,
    ):
        button = NavigationButton(title, subtitle, compact_label, self.sidebar)
        button.clicked.connect(callback)
        self.sidebar_layout.addWidget(button)
        self._nav_buttons[key] = button

    def _fill_workspace_menu(self):
        self.workspace_menu.clear()
        act_interface = QAction("Настройки интерфейса...", self)
        act_interface.triggered.connect(self._open_settings_dialog)
        self.workspace_menu.addAction(act_interface)
        self.workspace_menu.addSeparator()
        theme_menu = self.workspace_menu.addMenu("Тема оформления")
        populate_theme_menu(theme_menu, self)
        self.workspace_menu.addSeparator()

        act_import = QAction("Импорт справочников...", self)
        act_import.triggered.connect(self._open_import_dialog)
        if CatalogImportDialog is None:
            act_import.setEnabled(False)
        self.workspace_menu.addAction(act_import)

        act_rates = QAction("Открыть онлайн-курсы", self)
        act_rates.triggered.connect(self.show_rates_realtime)
        self.workspace_menu.addAction(act_rates)

        if getattr(getattr(self.user, "role", None), "value", None) == UserRole.admin.value:
            self.workspace_menu.addSeparator()
            act_wipe = QAction("Очистить все данные...", self)
            act_wipe.triggered.connect(self._open_wipe_dialog)
            self.workspace_menu.addAction(act_wipe)

    def _fill_profile_menu(self):
        self.profile_menu.clear()
        user_name = self.user.full_name or getattr(self.user, "login", "Пользователь")
        role_name = self._role_to_text(self.user.role)
        header = QAction(f"{user_name} - {role_name}", self)
        header.setEnabled(False)
        self.profile_menu.addAction(header)
        self.profile_menu.addSeparator()

        act_home = QAction("Вернуться на главный экран", self)
        act_home.triggered.connect(self.go_home)
        self.profile_menu.addAction(act_home)
        self.profile_menu.addSeparator()

        act_logout = QAction("Выйти из аккаунта", self)
        act_logout.triggered.connect(self._do_logout)
        self.profile_menu.addAction(act_logout)

    def _open_settings_dialog(self):
        WorkspaceSettingsDialog(self).exec()

    def _open_import_dialog(self):
        if CatalogImportDialog is None:
            QMessageBox.information(self, "Импорт", "Диалог импорта пока недоступен.")
            return
        CatalogImportDialog(self).exec()

    def _open_wipe_dialog(self):
        DangerWipeDialog(self, current_user=self.user).exec()

    def _toggle_sidebar(self):
        self._set_sidebar_collapsed(not self._sidebar_collapsed)

    def _set_sidebar_collapsed(self, collapsed: bool):
        self._sidebar_collapsed = collapsed
        self.sidebar.setProperty("collapsed", collapsed)
        self.sidebar.setFixedWidth(88 if collapsed else 280)
        self.brand_card.setProperty("compact", collapsed)
        self.lbl_brand_title.setVisible(not collapsed)
        self.lbl_nav_section.setVisible(not collapsed)
        self.sidebar_layout.setContentsMargins(10 if collapsed else 16, 18, 10 if collapsed else 16, 18)
        self.sidebar_layout.setSpacing(10 if collapsed else 12)
        self.brand_layout.setContentsMargins(0 if collapsed else 14, 0 if collapsed else 12, 0 if collapsed else 14, 0 if collapsed else 12)
        self.brand_layout.setSpacing(0 if collapsed else 14)

        if collapsed:
            self.brand_card.setFixedSize(52, 52)
            self.brand_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sidebar_layout.setAlignment(self.brand_card, Qt.AlignmentFlag.AlignHCenter)
        else:
            self.brand_card.setMinimumHeight(78)
            self.brand_card.setMaximumHeight(78)
            self.brand_card.setMinimumWidth(0)
            self.brand_card.setMaximumWidth(16777215)
            self.brand_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.sidebar_layout.setAlignment(self.brand_card, Qt.AlignmentFlag.AlignLeft)

        for button in self._nav_buttons.values():
            button.set_compact(collapsed)
            self.sidebar_layout.setAlignment(button, Qt.AlignmentFlag.AlignHCenter if collapsed else Qt.AlignmentFlag.AlignLeft)

        self.brand_card.style().unpolish(self.brand_card)
        self.brand_card.style().polish(self.brand_card)
        self.sidebar.style().unpolish(self.sidebar)
        self.sidebar.style().polish(self.sidebar)
        self.sidebar.update()

    def _set_active_nav(self, key: str):
        self._current_key = key
        for nav_key, button in self._nav_buttons.items():
            button.blockSignals(True)
            button.setChecked(nav_key == key)
            button.blockSignals(False)

    def _set_center(self, widget: QWidget, title: str, subtitle: str, key: str):
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            old = item.widget()
            if old:
                old.setParent(None)
        self._content_layout.addWidget(widget)
        self._current = widget
        self.lbl_title.setText(title)
        self.lbl_subtitle.setText(subtitle)
        self._set_active_nav(key)
        self.btn_back.setEnabled(len(self._nav_stack) > 0)

    def _open_root_section(self, widget: QWidget, title: str, subtitle: str, key: str, push_history: bool = True):
        if push_history and self._current is not None and self._current is not widget:
            self._nav_stack.append((self._current, self.lbl_title.text(), self.lbl_subtitle.text(), self._current_key))
        self._set_center(widget, title, subtitle, key)

    def navigate_to(self, widget: QWidget, title: str, subtitle: str, key: str | None = None):
        if self._current is not None:
            self._nav_stack.append((self._current, self.lbl_title.text(), self.lbl_subtitle.text(), self._current_key))
        self._set_center(widget, title, subtitle, key or self._current_key)

    def go_back(self):
        if not self._nav_stack:
            return
        widget, title, subtitle, key = self._nav_stack.pop()
        self._set_center(widget, title, subtitle, key)

    def go_home(self):
        if hasattr(self._home, "refresh"):
            try:
                self._home.refresh()
            except Exception:
                pass
        self._open_root_section(
            self._home,
            "Рабочее пространство",
            "Главный экран с фокусом дня, сводкой задач и быстрыми переходами.",
            "home",
            push_history=self._current is not None,
        )

    def show_attention(self):
        if self._attention_view is None:
            self._attention_view = AttentionCenter(
                self.user,
                open_deals=self.show_deals,
                open_cars=self.show_cars,
                open_clients=self.show_clients,
                open_chat=self.show_chat,
                parent=self,
            )
        self._open_root_section(
            self._attention_view,
            "Центр внимания",
            "Просроченные задачи, блокировки, прибытия, проблемы данных и последние события в одном окне.",
            "attention",
        )

    def show_deals(self):
        if self._deals_view is None:
            self._deals_view = DealsView(self, current_role=self.user.role)
        self._open_root_section(
            self._deals_view,
            "Сделки",
            "Все сделки компании: в работе, в архиве, с фильтрами и быстрыми действиями.",
            "deals",
        )

    def show_cars(self):
        if self._cars_view is None:
            self._cars_view = CarsView(self, current_role=self.user.role)
        self._open_root_section(
            self._cars_view,
            "Автомобили",
            "Карточки авто, фото, комплектации и рабочие данные по привозу.",
            "cars",
        )

    def show_clients(self):
        if self._clients_view is None:
            self._clients_view = ClientsView(self)
        self._open_root_section(
            self._clients_view,
            "Клиенты",
            "Контакты, документы, адреса и сопровождение клиентской базы.",
            "clients",
        )

    def show_dashboard(self):
        if self._dashboard_view is None:
            self._dashboard_view = DashboardView(self)
        self._open_root_section(
            self._dashboard_view,
            "Аналитика",
            "Контроль показателей, сроков и общей картины по работе команды.",
            "dashboard",
        )

    def show_calc(self):
        if self._calc_view is None:
            self._calc_view = CalculatorView(self)
        self._open_root_section(
            self._calc_view,
            "Калькулятор привоза",
            "Быстрый расчёт пошлины, расходов и итоговой стоимости под ключ.",
            "calculator",
        )

    def show_chat(self):
        if self._chat_view is None:
            self._chat_view = ChatView(self.user, self)
        self._open_root_section(
            self._chat_view,
            "Командный чат",
            "Внутренняя связь между сотрудниками и быстрый обмен рабочей информацией.",
            "chat",
        )

    def show_rates_realtime(self):
        if self._rates_realtime_view is None:
            self._rates_realtime_view = RatesRealtimeView(self)
        self._open_root_section(
            self._rates_realtime_view,
            "Курсы валют",
            "Онлайн-ставки и контроль валют, которые влияют на расчёт привоза.",
            "rates",
        )

    def _do_search(self):
        text = self.search_edit.text().strip()
        if not text:
            return
        self.show_deals()
        deals_view = getattr(self, "_deals_view", None)
        if deals_view and hasattr(deals_view, "ed_search") and hasattr(deals_view, "load_data"):
            deals_view.ed_search.setText(text)
            deals_view.load_data()
            self.statusBar().showMessage(f"Поиск по сделкам: {text}", 5000)
            return
        QMessageBox.information(self, "Поиск", f"Запрос: {text}")

    def _do_logout(self):
        self._nav_stack.clear()
        if callable(self.on_logout):
            self.on_logout()

    @staticmethod
    def _role_to_text(role: UserRole) -> str:
        mapping = {
            UserRole.admin: "Администратор",
            UserRole.manager: "Менеджер",
            UserRole.trainee: "Стажёр",
            UserRole.user: "Пользователь",
        }
        try:
            return mapping.get(role, str(role.value))
        except Exception:
            return "Пользователь"
