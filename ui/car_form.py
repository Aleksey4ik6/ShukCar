# ShukCar/ui/car_form.py
import os
import shutil
from pathlib import Path
from typing import Optional, Dict, Set
from decimal import Decimal
import datetime as dt

from PyQt6 import QtWidgets
from PyQt6.QtWidgets import (
    QDialog, QTabWidget, QWidget, QFormLayout, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox,
    QDateEdit, QTextEdit, QHBoxLayout, QPushButton, QVBoxLayout, QFileDialog, QListWidget,
    QListWidgetItem, QMessageBox, QScrollArea, QCheckBox, QInputDialog, QLabel, QFrame, QGridLayout
)

from PyQt6.QtCore import QDate, Qt, QSize, QTimer
from PyQt6.QtGui import QIcon

from sqlalchemy.exc import IntegrityError

from db import SessionLocal
from models import (
    Brand, Model, BodyType, FuelType, Transmission, Color, Trim,
    Car, CarMedia, Client, CarStatus, DealStatus, DealStage, User,
    Option, CarOption
)
from services.crm import fill_lead_source_combo, fill_priority_combo
from services.deal_sync import ensure_deal_for_car, remove_deal_for_car

# Пытаемся использовать AddressWidget (как во вкладке "Клиенты")
try:
    from ui.address_widget import AddressWidget  # автоподсказки по адресу
    HAS_ADDRESS_WIDGET = True
except Exception:
    AddressWidget = None
    HAS_ADDRESS_WIDGET = False

from services.deal_flow import move_car_to_stage

PKG_ROOT = Path(__file__).resolve().parents[1]
IMG_ROOT = PKG_ROOT / "img" / "cars"
ICON_PATH = PKG_ROOT / "img" / "logo_shukcar.jpg"


def _ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def _qdate_to_date(qd: QDate) -> Optional[dt.date]:
    if not qd or not qd.isValid():
        return None
    try:
        return dt.date(qd.year(), qd.month(), qd.day())
    except Exception:
        return None


def _month_year_to_date(qd: QDate) -> Optional[dt.date]:
    if not qd or not qd.isValid():
        return None
    try:
        return dt.date(qd.year(), qd.month(), 1)
    except Exception:
        return None


def _make_optional_date_edit() -> QDateEdit:
    edit = QDateEdit()
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("dd.MM.yyyy")
    edit.setMinimumDate(QDate(2000, 1, 1))
    edit.setDate(QDate(2000, 1, 1))
    edit.setSpecialValueText("Не указано")
    return edit


def _optional_qdate_to_date(edit: QDateEdit) -> Optional[dt.date]:
    qd = edit.date()
    if not qd or not qd.isValid():
        return None
    if qd == edit.minimumDate():
        return None
    return _qdate_to_date(qd)


# ---------- строка опции: чекбокс + удалить ----------
# --- ЗАМЕНА класса OptionRow в ShukCar/ui/car_form.py ---
class OptionRow(QWidget):
    """Строка опции: красивая галочка + кнопка удалить."""
    def __init__(self, option_id: int, name: str, checked: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.option_id = option_id

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(8)

        self.cb = QCheckBox(name)
        self.cb.setChecked(checked)

        # Кнопка удаления
        self.btn_del = QPushButton("✕")
        self.btn_del.setFixedSize(26, 26)
        self.btn_del.setToolTip("Удалить опцию из справочника (и убрать из всех авто)")
        self.btn_del.setProperty("accent", "danger-secondary")

        lay.addWidget(self.cb, 1)
        lay.addStretch(1)
        lay.addWidget(self.btn_del, 0)

    def isChecked(self) -> bool:
        return self.cb.isChecked()

    def setChecked(self, v: bool):
        self.cb.setChecked(v)



# ---------- диалог ввода адреса (фоллбек) ----------
class AddressPickerDialog(QDialog):
    def __init__(self, parent=None, initial_text: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Поиск адреса")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(600, 320)

        lay = QVBoxLayout(self)
        hint = QLabel("Введите адрес полностью (страна, регион, город, улица, дом, кв., индекс).")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.addr_text = QLineEdit()
        self.addr_text.setText(initial_text or "")
        self.addr_text.setPlaceholderText("Россия, Приморский край, Владивосток, ул. Примерная, 10, кв. 5, 690000")
        lay.addWidget(self.addr_text)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def get_address_text(self) -> str:
        return self.addr_text.text().strip()


class CarFormDialog(QDialog):
    """
    Вкладки:
      1) Основное         — марка/модель/кузов/цвет/год/пробег/статусы/этап.
      2) Двигатель/КПП    — объём, л.с., привод, расход, эко-класс.
      3) Габариты/масса   — длина/ширина/высота/база/клиренс/масса/места.
      4) Шасси/колёса     — диски, шины, 0-100, макс. скорость.
      5) Документы        — VIN, ПТС, ГТД, рынок, СБКТС.
      6) Финансы          — цена до Влд, закупка/валюта/прочее/клиентская, заметки.
      7) Клиент           — ФИО/паспорт/прописка (с автоподсказками, как в «Клиенты»).
      8) Опции            — чекбоксы + добавление/удаление опций + комментарий.
      9) Медиа
    """
    def __init__(self, parent=None, car_id: Optional[int] = None):
        super().__init__(parent)
        self.setWindowTitle("Автомобиль")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1060, 780)

        self.car_id = car_id
        self.session = SessionLocal()

        # Корневой таб
        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setElideMode(Qt.TextElideMode.ElideRight)

        # ---- вкладки ----
        self.tab_main = QWidget()
        self.tab_engine = QWidget()
        self.tab_dims = QWidget()
        self.tab_chassis = QWidget()
        self.tab_docs = QWidget()
        self.tab_finance = QWidget()
        self.tab_crm = QWidget()
        self.tab_client = QWidget()
        self.tab_options = QWidget()
        self.tab_media = QWidget()

        self.tabs.addTab(self.tab_main, "Основное")
        self.tabs.addTab(self.tab_engine, "Двигатель/КПП")
        self.tabs.addTab(self.tab_dims, "Габариты/масса")
        self.tabs.addTab(self.tab_chassis, "Шасси/колёса")
        self.tabs.addTab(self.tab_docs, "Документы")
        self.tabs.addTab(self.tab_finance, "Финансы")
        self.tabs.addTab(self.tab_crm, "CRM/Сделка")
        self.tabs.addTab(self.tab_client, "Клиент")
        self.tabs.addTab(self.tab_options, "Опции")
        self.tabs.addTab(self.tab_media, "Медиа")

        # ====== Основное ======
        fm = QFormLayout(self.tab_main)

        self.cb_brand = QComboBox(); self.cb_brand.setEditable(True)
        self.cb_model = QComboBox(); self.cb_model.setEditable(True)
        self.cb_trim  = QComboBox(); self.cb_trim.setEditable(True)
        self.cb_body  = QComboBox(); self.cb_body.setEditable(True)
        self.cb_fuel  = QComboBox(); self.cb_fuel.setEditable(True)
        self.cb_trans = QComboBox(); self.cb_trans.setEditable(True)
        self.cb_color = QComboBox(); self.cb_color.setEditable(True)

        self.dt_build = QDateEdit(); self.dt_build.setCalendarPopup(True); self.dt_build.setDisplayFormat("MM.yyyy")
        self.sp_mileage = QSpinBox(); self.sp_mileage.setMaximum(10_000_000)

        self.cb_status = QComboBox(); self.cb_status.setEditable(True)
        self.cb_deal_status = QComboBox(); self.cb_deal_status.setEditable(True)
        self.cb_stage = QComboBox()

        fm.addRow("Марка:", self.cb_brand)
        fm.addRow("Модель:", self.cb_model)
        fm.addRow("Комплектация:", self.cb_trim)
        fm.addRow("Кузов:", self.cb_body)
        fm.addRow("Топливо:", self.cb_fuel)
        fm.addRow("КПП:", self.cb_trans)
        fm.addRow("Цвет:", self.cb_color)
        fm.addRow("Месяц/год выпуска:", self.dt_build)
        fm.addRow("Пробег (км):", self.sp_mileage)
        fm.addRow("Статус авто (текст):", self.cb_status)
        fm.addRow("Статус сделки (текст):", self.cb_deal_status)
        fm.addRow("Этап сделки:", self.cb_stage)

        # ====== Двигатель/КПП ======
        fe = QFormLayout(self.tab_engine)
        self.sp_engine = QSpinBox(); self.sp_engine.setMaximum(100000)
        self.sp_hp = QSpinBox(); self.sp_hp.setMaximum(3000)
        self.cb_drive = QComboBox(); self.cb_drive.setEditable(True); [self.cb_drive.addItem(x) for x in ("", "FWD", "RWD", "AWD", "4WD")]
        self.ed_euro_class = QLineEdit(); self.ed_euro_class.setMaxLength(16)
        self.sp_cons_mix = QDoubleSpinBox(); self.sp_cons_mix.setDecimals(1); self.sp_cons_mix.setRange(0.0, 60.0)

        fe.addRow("Объём (см³):", self.sp_engine)
        fe.addRow("Мощность (л.с.):", self.sp_hp)
        fe.addRow("Привод:", self.cb_drive)
        fe.addRow("Эко-класс (Euro):", self.ed_euro_class)
        fe.addRow("Расход смеш., л/100:", self.sp_cons_mix)

        # ====== Габариты/масса ======
        fd = QFormLayout(self.tab_dims)
        self.sp_length_mm = QSpinBox(); self.sp_length_mm.setMaximum(20000)
        self.sp_width_mm  = QSpinBox(); self.sp_width_mm.setMaximum(10000)
        self.sp_height_mm = QSpinBox(); self.sp_height_mm.setMaximum(10000)
        self.sp_wheelbase_mm = QSpinBox(); self.sp_wheelbase_mm.setMaximum(10000)
        self.sp_clearance_mm = QSpinBox(); self.sp_clearance_mm.setMaximum(1000)
        self.sp_curb_weight_kg = QSpinBox(); self.sp_curb_weight_kg.setMaximum(10000)
        self.sp_seats = QSpinBox(); self.sp_seats.setMaximum(99)

        fd.addRow("Длина (мм):", self.sp_length_mm)
        fd.addRow("Ширина (мм):", self.sp_width_mm)
        fd.addRow("Высота (мм):", self.sp_height_mm)
        fd.addRow("База (мм):", self.sp_wheelbase_mm)
        fd.addRow("Клиренс (мм):", self.sp_clearance_mm)
        fd.addRow("Снаряж. масса (кг):", self.sp_curb_weight_kg)
        fd.addRow("Кол-во мест:", self.sp_seats)

        # ====== Шасси/колёса ======
        fs = QFormLayout(self.tab_chassis)
        self.ed_wheel_size = QLineEdit(); self.ed_wheel_size.setMaxLength(32)
        self.ed_tire_front = QLineEdit(); self.ed_tire_front.setMaxLength(32)
        self.ed_tire_rear  = QLineEdit(); self.ed_tire_rear.setMaxLength(32)
        self.sp_accel_0_100 = QDoubleSpinBox(); self.sp_accel_0_100.setDecimals(1); self.sp_accel_0_100.setRange(0.0, 40.0)
        self.sp_max_speed_kmh = QSpinBox(); self.sp_max_speed_kmh.setMaximum(600)

        fs.addRow("Размер дисков:", self.ed_wheel_size)
        fs.addRow("Шины передние:", self.ed_tire_front)
        fs.addRow("Шины задние:", self.ed_tire_rear)
        fs.addRow("0–100 км/ч (с):", self.sp_accel_0_100)
        fs.addRow("Макс. скорость (км/ч):", self.sp_max_speed_kmh)

        # ====== Документы ======
        fdoc = QFormLayout(self.tab_docs)
        self.ed_vin = QLineEdit(); self.ed_vin.setMaxLength(32)
        self.ed_pts_number = QLineEdit(); self.ed_pts_number.setMaxLength(64)
        self.cb_market = QComboBox(); self.cb_market.setEditable(True); [self.cb_market.addItem(x) for x in ("", "JP", "KR", "US", "EU", "CN", "RU")]
        self.ed_customs_decl_no = QLineEdit(); self.ed_customs_decl_no.setMaxLength(64)
        self.ed_sbkts_no = QLineEdit(); self.ed_sbkts_no.setMaxLength(64)

        fdoc.addRow("VIN:", self.ed_vin)
        fdoc.addRow("ПТС №:", self.ed_pts_number)
        fdoc.addRow("Рынок:", self.cb_market)
        fdoc.addRow("Номер ГТД:", self.ed_customs_decl_no)
        fdoc.addRow("СБКТС №:", self.ed_sbkts_no)

        # ====== Финансы ======
        ff = QFormLayout(self.tab_finance)
        self.sp_price_to_vld = QDoubleSpinBox(); self.sp_price_to_vld.setMaximum(1_000_000_000); self.sp_price_to_vld.setDecimals(2)
        self.cb_purchase_currency = QComboBox(); self.cb_purchase_currency.setEditable(True); [self.cb_purchase_currency.addItem(x) for x in ("", "RUB", "JPY", "USD", "CNY", "EUR", "KZT")]
        self.sp_purchase_price = QDoubleSpinBox(); self.sp_purchase_price.setMaximum(1_000_000_000); self.sp_purchase_price.setDecimals(2)
        self.sp_other_costs = QDoubleSpinBox(); self.sp_other_costs.setMaximum(1_000_000_000); self.sp_other_costs.setDecimals(2)
        self.sp_price_customer = QDoubleSpinBox(); self.sp_price_customer.setMaximum(1_000_000_000); self.sp_price_customer.setDecimals(2)
        self.txt_notes = QTextEdit()

        ff.addRow("Стоимость до Владивостока:", self.sp_price_to_vld)
        ff.addRow("Валюта закупки:", self.cb_purchase_currency)
        ff.addRow("Цена закупки:", self.sp_purchase_price)
        ff.addRow("Прочие затраты:", self.sp_other_costs)
        ff.addRow("Цена клиенту:", self.sp_price_customer)
        ff.addRow("Примечание:", self.txt_notes)

        # ====== CRM / Сделка ======
        fcrm = QFormLayout(self.tab_crm)
        self.cb_responsible_user = QComboBox()
        self.cb_lead_source = QComboBox()
        self.cb_priority = QComboBox()
        self.dt_expected_arrival = _make_optional_date_edit()
        self.dt_next_action = _make_optional_date_edit()
        self.txt_next_action_note = QTextEdit()
        self.txt_next_action_note.setPlaceholderText("Что нужно сделать следующим шагом: связаться с клиентом, запросить инвойс, проверить отгрузку и т.д.")
        self.txt_next_action_note.setMaximumHeight(88)
        self.txt_blocked_reason = QTextEdit()
        self.txt_blocked_reason.setPlaceholderText("Если сделка тормозится, зафиксируйте причину.")
        self.txt_blocked_reason.setMaximumHeight(88)

        fcrm.addRow("Ответственный менеджер:", self.cb_responsible_user)
        fcrm.addRow("Источник лида:", self.cb_lead_source)
        fcrm.addRow("Приоритет:", self.cb_priority)
        fcrm.addRow("Плановая дата прибытия:", self.dt_expected_arrival)
        fcrm.addRow("Следующее действие до:", self.dt_next_action)
        fcrm.addRow("Следующее действие:", self.txt_next_action_note)
        fcrm.addRow("Причина блокировки:", self.txt_blocked_reason)

        # ====== Клиент ======
        fc = QFormLayout(self.tab_client)
        client_pick_row = QWidget(self.tab_client)
        client_pick_layout = QHBoxLayout(client_pick_row)
        client_pick_layout.setContentsMargins(0, 0, 0, 0)
        client_pick_layout.setSpacing(6)
        self.cb_client_existing = QComboBox()
        self.cb_client_existing.setEditable(True)
        self.btn_client_new = QPushButton("Новый клиент")
        self.btn_client_new.setProperty("accent", "secondary")
        client_pick_layout.addWidget(self.cb_client_existing, 1)
        client_pick_layout.addWidget(self.btn_client_new)
        fc.addRow("Клиент из базы:", client_pick_row)

        self.c_fullname = QLineEdit()
        self.c_phone = QLineEdit()
        self.c_email = QLineEdit()
        self.c_passport = QLineEdit()

        # Прописка:
        # если есть AddressWidget — ставим его (автоподсказки при вводе)
        # иначе — фоллбек: QTextEdit + кнопка «Найти адрес…»
        self.addr_widget = None
        if HAS_ADDRESS_WIDGET:
            try:
                self.addr_widget = AddressWidget(self)  # у тебя уже настроен в другом месте
                fc.addRow("Прописка:", self.addr_widget)
            except Exception as e:
                # если вдруг не получилось — откатываемся на фоллбек
                HAS_FALLBACK = True
            else:
                HAS_FALLBACK = False
        else:
            HAS_FALLBACK = True

        if HAS_FALLBACK:
            addr_container = QWidget()
            addr_layout = QHBoxLayout(addr_container)
            addr_layout.setContentsMargins(0, 0, 0, 0)
            addr_layout.setSpacing(6)
            self.c_addr_text = QTextEdit()
            self.c_addr_text.setPlaceholderText("Полный адрес (страна, регион, город, улица, дом, кв., индекс)")
            self.btn_addr_find = QPushButton("Найти адрес…")
            self.btn_addr_find.setFixedHeight(28)
            self.btn_addr_find.setProperty("accent", "secondary")
            self.btn_addr_find.clicked.connect(self._open_address_picker)
            addr_layout.addWidget(self.c_addr_text, 1)
            addr_layout.addWidget(self.btn_addr_find)
            fc.addRow("Прописка:", addr_container)

        self._addr_fallback = HAS_FALLBACK  # запомним, чем пользуемся

        self.c_snils = QLineEdit()
        self.c_inn = QLineEdit()
        self.c_dob = QDateEdit(); self.c_dob.setCalendarPopup(True); self.c_dob.setDisplayFormat("dd.MM.yyyy")
        self.c_pass_issuer = QLineEdit()
        self.c_pass_issue_date = QDateEdit(); self.c_pass_issue_date.setCalendarPopup(True); self.c_pass_issue_date.setDisplayFormat("dd.MM.yyyy")
        self.c_pass_code = QLineEdit()

        fc.addRow("ФИО:", self.c_fullname)
        fc.addRow("Телефон:", self.c_phone)
        fc.addRow("E-mail:", self.c_email)
        fc.addRow("Паспорт (серия/номер):", self.c_passport)
        fc.addRow("СНИЛС:", self.c_snils)
        fc.addRow("ИНН:", self.c_inn)
        fc.addRow("Дата рождения:", self.c_dob)
        fc.addRow("Кем выдан паспорт:", self.c_pass_issuer)
        fc.addRow("Дата выдачи паспорта:", self.c_pass_issue_date)
        fc.addRow("Код подразделения:", self.c_pass_code)

        # ====== Опции ======
        self._build_options_tab()

        # ====== Медиа ======
        vm = QVBoxLayout(self.tab_media)
        hb = QHBoxLayout()
        self.btn_add_images = QPushButton("Добавить фото")
        self.btn_add_videos = QPushButton("Добавить видео")
        self.btn_open_dir = QPushButton("Открыть папку медиа")
        self.btn_add_images.setProperty("accent", "secondary")
        self.btn_add_videos.setProperty("accent", "secondary")
        self.btn_open_dir.setProperty("accent", "secondary")
        hb.addWidget(self.btn_add_images)
        hb.addWidget(self.btn_add_videos)
        hb.addStretch(1)
        hb.addWidget(self.btn_open_dir)
        vm.addLayout(hb)

        self.media_list = QListWidget()
        self.media_list.setSpacing(8)
        vm.addWidget(self.media_list)

        self.btn_add_images.clicked.connect(self._add_images)
        self.btn_add_videos.clicked.connect(self._add_videos)
        self.btn_open_dir.clicked.connect(self._open_media_dir)

        # Кнопки диалога
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(self.tabs)
        root.addWidget(buttons)

        # Сигналы марка→модель→комплектация
        self.cb_brand.currentTextChanged.connect(self._on_brand_changed)
        self.cb_model.currentTextChanged.connect(self._on_model_changed)
        self.cb_client_existing.currentIndexChanged.connect(self._on_client_selected)
        self.btn_client_new.clicked.connect(self._start_new_client)

        # Инициализация (отложенно — устойчиво)
        QTimer.singleShot(0, self._load_lookups)
        if self.car_id:
            QTimer.singleShot(0, self._load_car)
        else:
            self.dt_build.setDate(QDate.currentDate())
        self._refresh_media_list()

    # ===== Address picker (фоллбек) =====
    def _open_address_picker(self):
        try:
            txt_init = ""
            if getattr(self, "_addr_fallback", True):
                txt_init = (self.c_addr_text.toPlainText().strip() if hasattr(self, "c_addr_text") else "")
            dlg = AddressPickerDialog(self, initial_text=txt_init)
            if dlg.exec():
                txt = dlg.get_address_text().strip()
                if txt and hasattr(self, "c_addr_text"):
                    self.c_addr_text.setPlainText(txt)
        except Exception as e:
            QMessageBox.warning(self, "Адрес", f"Не удалось открыть поиск адреса: {e}")

    def _get_addr_text(self) -> str | None:
        """Единая точка чтения адреса из виджета/фоллбека."""
        # AddressWidget: пытаемся получить текущий текст разными способами
        if not self._addr_fallback and self.addr_widget is not None:
            for attr in ("current_text", "text", "get_value", "value"):
                try:
                    fn = getattr(self.addr_widget, attr)
                except Exception:
                    continue
                try:
                    val = fn() if callable(fn) else str(fn)
                    if isinstance(val, str):
                        return val.strip() or None
                except Exception:
                    pass
        # Фоллбек
        if hasattr(self, "c_addr_text"):
            txt = self.c_addr_text.toPlainText().strip()
            return txt or None
        return None

    def _set_addr_text(self, text: str | None):
        value = (text or "").strip()
        if not self._addr_fallback and self.addr_widget is not None:
            for setter in ("set_address", "set_value", "setText", "set_text", "setAddress"):
                try:
                    fn = getattr(self.addr_widget, setter)
                except Exception:
                    continue
                try:
                    if callable(fn):
                        fn(value)
                        return
                except Exception:
                    continue
        if hasattr(self, "c_addr_text"):
            self.c_addr_text.setPlainText(value)

    def _client_combo_label(self, client: Client) -> str:
        phone = (client.phone or "").strip()
        if phone:
            return f"{client.full_name} · {phone}"
        return client.full_name

    def _populate_clients_combo(self, current_id: Optional[int] = None):
        s = self.session
        current_text = self.cb_client_existing.currentText().strip()
        self.cb_client_existing.blockSignals(True)
        self.cb_client_existing.clear()
        self.cb_client_existing.addItem("Новый клиент / без привязки", None)
        clients = s.query(Client).order_by(Client.full_name.asc(), Client.id.asc()).all()
        for client in clients:
            self.cb_client_existing.addItem(self._client_combo_label(client), client.id)
        index = 0
        if current_id:
            found = self.cb_client_existing.findData(current_id)
            if found >= 0:
                index = found
        elif current_text:
            self.cb_client_existing.setEditText(current_text)
        self.cb_client_existing.setCurrentIndex(index)
        self.cb_client_existing.blockSignals(False)

    def _set_client_fields(self, client: Client):
        self.c_fullname.setText(client.full_name or "")
        self.c_phone.setText(client.phone or "")
        self.c_email.setText(client.email or "")
        self.c_passport.setText(client.passport_no or "")
        self._set_addr_text(client.registration_address or "")
        self.c_snils.setText(client.snils or "")
        self.c_inn.setText(client.inn or "")
        if client.date_of_birth:
            self.c_dob.setDate(QDate(client.date_of_birth.year, client.date_of_birth.month, client.date_of_birth.day))
        else:
            self.c_dob.setDate(QDate.currentDate())
        self.c_pass_issuer.setText(client.passport_issuer or "")
        if client.passport_issue_date:
            self.c_pass_issue_date.setDate(
                QDate(client.passport_issue_date.year, client.passport_issue_date.month, client.passport_issue_date.day)
            )
        else:
            self.c_pass_issue_date.setDate(QDate.currentDate())
        self.c_pass_code.setText(client.passport_division_code or "")

    def _clear_client_fields(self):
        self.c_fullname.clear()
        self.c_phone.clear()
        self.c_email.clear()
        self.c_passport.clear()
        self._set_addr_text("")
        self.c_snils.clear()
        self.c_inn.clear()
        self.c_dob.setDate(QDate.currentDate())
        self.c_pass_issuer.clear()
        self.c_pass_issue_date.setDate(QDate.currentDate())
        self.c_pass_code.clear()

    def _on_client_selected(self):
        client_id = self.cb_client_existing.currentData()
        if not client_id:
            if self.cb_client_existing.currentIndex() == 0:
                self._clear_client_fields()
            return
        client = self.session.get(Client, int(client_id))
        if client:
            self._set_client_fields(client)

    def _start_new_client(self):
        self.cb_client_existing.blockSignals(True)
        self.cb_client_existing.setCurrentIndex(0)
        self.cb_client_existing.setEditText("")
        self.cb_client_existing.blockSignals(False)
        self._clear_client_fields()

    def _apply_client_form_to_entity(self, client: Client, responsible_user_id, lead_source, priority):
        client.full_name = self.c_fullname.text().strip()
        client.phone = self.c_phone.text().strip() or None
        client.email = self.c_email.text().strip() or None
        client.passport_no = self.c_passport.text().strip() or None
        client.registration_address = self._get_addr_text()
        client.snils = self.c_snils.text().strip() or None
        client.inn = self.c_inn.text().strip() or None
        client.date_of_birth = _qdate_to_date(self.c_dob.date())
        client.passport_issuer = self.c_pass_issuer.text().strip() or None
        client.passport_issue_date = _qdate_to_date(self.c_pass_issue_date.date())
        client.passport_division_code = self.c_pass_code.text().strip() or None
        client.responsible_user_id = responsible_user_id
        client.lead_source = lead_source
        client.priority = priority
        if not self._addr_fallback and self.addr_widget is not None and hasattr(self.addr_widget, "get_address_data"):
            try:
                payload = self.addr_widget.get_address_data()
            except Exception:
                payload = {}
            for key in (
                "country",
                "region",
                "city",
                "street",
                "house",
                "block",
                "flat",
                "postal_code",
                "fias_id",
                "kladr_id",
                "geo_lat",
                "geo_lon",
            ):
                if key in payload:
                    setattr(client, key, payload.get(key))

    # ===== Опции: UI =====
    def _build_options_tab(self):
        lay = QVBoxLayout(self.tab_options)

        hb = QHBoxLayout()
        self.btn_option_add = QPushButton("Добавить опцию…")
        self.btn_option_select_all = QPushButton("Выбрать все")
        self.btn_option_clear_all = QPushButton("Снять все")
        self.btn_option_add.setProperty("accent", "secondary")
        self.btn_option_select_all.setProperty("accent", "secondary")
        self.btn_option_clear_all.setProperty("accent", "secondary")
        hb.addWidget(self.btn_option_add)
        hb.addStretch(1)
        hb.addWidget(self.btn_option_select_all)
        hb.addWidget(self.btn_option_clear_all)
        lay.addLayout(hb)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        holder = QWidget()
        self.options_layout = QVBoxLayout(holder)
        self.options_layout.addStretch(1)
        self.scroll.setWidget(holder)
        lay.addWidget(self.scroll)

        self.txt_options_note = QTextEdit()
        self.txt_options_note.setPlaceholderText("Комментарий по опциям (не обязательно)")
        lay.addWidget(self.txt_options_note)

        self.btn_option_add.clicked.connect(self._on_add_option)
        self.btn_option_select_all.clicked.connect(lambda: self._toggle_all_options(True))
        self.btn_option_clear_all.clicked.connect(lambda: self._toggle_all_options(False))

        self._option_rows: Dict[int, OptionRow] = {}

    def _toggle_all_options(self, value: bool):
        for row in self._option_rows.values():
            row.setChecked(value)

    def _on_add_option(self):
        name, ok = QInputDialog.getText(self, "Новая опция", "Название опции:")
        if not ok or not name.strip():
            return
        s = self.session
        exists = s.query(Option).filter(Option.name == name.strip()).first()
        if exists:
            QMessageBox.information(self, "Уже есть", "Такая опция уже существует.")
            return
        op = Option(name=name.strip(), is_active=True)
        s.add(op); s.commit()
        self._add_option_row(op.id, op.name, checked=True)

    def _add_option_row(self, option_id: int, name: str, checked: bool = False):
        row = OptionRow(option_id, name, checked, self)
        row.btn_del.clicked.connect(lambda *_: self._delete_option_global(option_id, name))
        self.options_layout.insertWidget(self.options_layout.count() - 1, row)
        self._option_rows[option_id] = row

    def _delete_option_global(self, option_id: int, name: str):
        res = QMessageBox.question(
            self, "Удаление опции",
            f"Удалить опцию «{name}» из справочника?\n\n"
            f"Будут удалены связи этой опции со ВСЕМИ авто.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if res != QMessageBox.StandardButton.Yes:
            return

        s = self.session
        try:
            # удалим связи со всеми авто, затем саму опцию
            s.query(CarOption).filter(CarOption.option_id == option_id).delete()
            op = s.get(Option, option_id)
            if op:
                s.delete(op)
            s.commit()
        except IntegrityError as e:
            s.rollback()
            QMessageBox.critical(self, "Удаление опции", f"Не удалось удалить (связи или ограничения БД): {e}")
            return
        except Exception as e:
            s.rollback()
            QMessageBox.critical(self, "Удаление опции", str(e))
            return

        # убираем из UI
        row = self._option_rows.pop(option_id, None)
        if row:
            row.setParent(None)

    # ===== Lookups =====
    def _load_lookups(self):
        s = self.session
        try:
            self._fill_cb(self.cb_brand, [b.name for b in s.query(Brand).order_by(Brand.name).all()])
            self._fill_cb(self.cb_body, [x.name for x in s.query(BodyType).order_by(BodyType.name).all()])
            self._fill_cb(self.cb_fuel, [x.name for x in s.query(FuelType).order_by(FuelType.name).all()])
            self._fill_cb(self.cb_trans, [x.name for x in s.query(Transmission).order_by(Transmission.name).all()])
            self._fill_cb(self.cb_color, [x.name for x in s.query(Color).order_by(Color.name).all()])
            self._fill_cb(self.cb_status, [x.name for x in s.query(CarStatus).order_by(CarStatus.name).all()])
            self._fill_cb(self.cb_deal_status, [x.name for x in s.query(DealStatus).order_by(DealStatus.name).all()])
            self.cb_model.clear(); self.cb_trim.clear()

            stages = s.query(DealStage).filter(DealStage.is_active == True).order_by(DealStage.sort_order.asc()).all()
            self.cb_stage.clear()
            for st in stages:
                self.cb_stage.addItem(st.name, st.id)

            self.cb_responsible_user.clear()
            self.cb_responsible_user.addItem("Не назначен", None)
            users = s.query(User).order_by(User.full_name.asc(), User.login.asc()).all()
            for user in users:
                label = user.full_name or user.login or f"Пользователь #{user.id}"
                self.cb_responsible_user.addItem(label, user.id)
            self._populate_clients_combo()
            fill_lead_source_combo(self.cb_lead_source)
            fill_priority_combo(self.cb_priority, "normal")

            # опции
            for i in reversed(range(self.options_layout.count() - 1)):
                w = self.options_layout.itemAt(i).widget()
                if w:
                    w.setParent(None)
            self._option_rows.clear()
            options = s.query(Option).filter(Option.is_active == True).order_by(Option.name.asc()).all()
            for op in options:
                self._add_option_row(op.id, op.name, checked=False)
        except Exception as e:
            QMessageBox.warning(self, "Справочники", f"Не удалось загрузить справочники: {e}")

    def _fill_cb(self, cb: QComboBox, names):
        cb.clear()
        for n in names:
            cb.addItem(n)

    def _on_brand_changed(self, brand_name: str):
        s = self.session
        brand = s.query(Brand).filter(Brand.name == brand_name).first()
        self.cb_model.clear(); self.cb_trim.clear()
        if not brand:
            return
        models = s.query(Model).filter(Model.brand_id == brand.id).order_by(Model.name).all()
        for m in models:
            self.cb_model.addItem(m.name)

    def _on_model_changed(self, model_name: str):
        s = self.session
        from models import Brand as BrandM, Model as ModelM, Trim as TrimM
        brand_name = self.cb_brand.currentText().strip()
        brand = s.query(BrandM).filter(BrandM.name == brand_name).first()
        self.cb_trim.clear()
        if not brand:
            return
        model = s.query(ModelM).filter(ModelM.brand_id == brand.id, ModelM.name == model_name).first()
        if not model:
            return
        trims = s.query(TrimM).filter(TrimM.model_id == model.id).order_by(TrimM.name).all()
        for t in trims:
            self.cb_trim.addItem(t.name)

    # ===== Ensure rows =====
    def _ensure_lookup(self, cls, name: str, **extra):
        s = self.session
        name = (name or "").strip()
        if not name:
            return None
        row = s.query(cls).filter(cls.name == name).first()
        if row:
            return row
        row = cls(name=name, **extra)
        s.add(row); s.commit(); s.refresh(row)
        return row

    def _ensure_model(self, brand: Brand, name: str):
        s = self.session
        name = (name or "").strip()
        if not name or not brand:
            return None
        row = s.query(Model).filter(Model.brand_id == brand.id, Model.name == name).first()
        if row:
            return row
        row = Model(brand_id=brand.id, name=name)
        s.add(row); s.commit(); s.refresh(row)
        return row

    def _ensure_trim(self, model: Model, name: str):
        s = self.session
        name = (name or "").strip()
        if not name or not model:
            return None
        row = s.query(Trim).filter(Trim.model_id == model.id, Trim.name == name).first()
        if row:
            return row
        row = Trim(model_id=model.id, name=name)
        s.add(row); s.commit(); s.refresh(row)
        return row

    def _ensure_status(self, name: str):
        return self._ensure_lookup(CarStatus, name)

    def _ensure_deal_status(self, name: str):
        return self._ensure_lookup(DealStatus, name)

    # ===== Save =====
    def accept(self):
        try:
            self._save()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", f"{type(e).__name__}: {e}")
            return
        super().accept()

    def _to_dec(self, value: float, places: int = 2) -> Optional[Decimal]:
        try:
            return Decimal(f"{value:.{places}f}")
        except Exception:
            return None

    def _collect_selected_option_ids(self) -> Set[int]:
        return {opt_id for opt_id, row in self._option_rows.items() if row.isChecked()}

    def _save(self):
        s = self.session

        brand = self._ensure_lookup(Brand, self.cb_brand.currentText())
        model = self._ensure_model(brand, self.cb_model.currentText())
        body  = self._ensure_lookup(BodyType, self.cb_body.currentText())
        fuel  = self._ensure_lookup(FuelType, self.cb_fuel.currentText())
        trans = self._ensure_lookup(Transmission, self.cb_trans.currentText())
        color = self._ensure_lookup(Color, self.cb_color.currentText())
        trim  = self._ensure_trim(model, self.cb_trim.currentText()) if self.cb_trim.currentText().strip() else None

        st = self._ensure_status(self.cb_status.currentText()) if self.cb_status.currentText().strip() else None
        dst = self._ensure_deal_status(self.cb_deal_status.currentText()) if self.cb_deal_status.currentText().strip() else None

        if not brand or not model:
            raise ValueError("Марка и Модель обязательны.")

        build_date = _month_year_to_date(self.dt_build.date())

        price_to_vld   = self._to_dec(self.sp_price_to_vld.value(), 2)
        purchase_price = self._to_dec(self.sp_purchase_price.value(), 2)
        other_costs    = self._to_dec(self.sp_other_costs.value(), 2)
        price_customer = self._to_dec(self.sp_price_customer.value(), 2)

        cons_mix = self._to_dec(self.sp_cons_mix.value(), 1)
        accel    = self._to_dec(self.sp_accel_0_100.value(), 1)
        responsible_user_id = self.cb_responsible_user.currentData()
        lead_source = self.cb_lead_source.currentText().strip() or None
        priority = self.cb_priority.currentData() or "normal"
        expected_arrival_date = _optional_qdate_to_date(self.dt_expected_arrival)
        next_action_date = _optional_qdate_to_date(self.dt_next_action)
        next_action_note = self.txt_next_action_note.toPlainText().strip() or None
        blocked_reason = self.txt_blocked_reason.toPlainText().strip() or None

        # Клиент: либо выбираем из базы, либо создаём нового
        selected_client_id = self.cb_client_existing.currentData()
        client = None
        if selected_client_id:
            client = s.get(Client, int(selected_client_id))
            if not client:
                raise ValueError("Выбранный клиент не найден в базе.")
            self._apply_client_form_to_entity(client, responsible_user_id, lead_source, priority)
            s.flush()
        elif self.c_fullname.text().strip():
            client = Client()
            self._apply_client_form_to_entity(client, responsible_user_id, lead_source, priority)
            s.add(client)
            s.flush()

        selected_stage_id = self.cb_stage.currentData()
        selected_stage = s.get(DealStage, selected_stage_id) if selected_stage_id else None

        selected_option_ids = self._collect_selected_option_ids()
        options_note = self.txt_options_note.toPlainText().strip() or None

        if self.car_id:
            car = s.get(Car, self.car_id)
            if not car:
                raise ValueError("Автомобиль не найден.")

            # Основное
            car.brand_id = brand.id
            car.model_id = model.id
            car.trim_id = (trim.id if trim else None)
            car.body_type_id = (body.id if body else None)
            car.fuel_type_id = (fuel.id if fuel else None)
            car.transmission_id = (trans.id if trans else None)
            car.color_id = (color.id if color else None)
            car.build_date = build_date
            car.mileage_km = self.sp_mileage.value() or None
            car.status = (st.name if st else None)
            car.deal_status = (dst.name if dst else None)

            # Двигатель/КПП
            car.engine_cc = self.sp_engine.value() or None
            car.horsepower = self.sp_hp.value() or None
            car.drive = self.cb_drive.currentText().strip() or None
            car.euro_class = self.ed_euro_class.text().strip() or None
            car.cons_mix_l100 = cons_mix

            # Габариты/масса
            car.length_mm = self.sp_length_mm.value() or None
            car.width_mm = self.sp_width_mm.value() or None
            car.height_mm = self.sp_height_mm.value() or None
            car.wheelbase_mm = self.sp_wheelbase_mm.value() or None
            car.ground_clearance_mm = self.sp_clearance_mm.value() or None
            car.curb_weight_kg = self.sp_curb_weight_kg.value() or None
            car.seats = self.sp_seats.value() or None

            # Шасси/колёса
            car.wheel_size = self.ed_wheel_size.text().strip() or None
            car.tire_front = self.ed_tire_front.text().strip() or None
            car.tire_rear = self.ed_tire_rear.text().strip() or None
            car.accel_0_100_s = accel
            car.max_speed_kmh = self.sp_max_speed_kmh.value() or None

            # Документы
            car.vin = self.ed_vin.text().strip() or None
            car.pts_number = self.ed_pts_number.text().strip() or None
            car.market = self.cb_market.currentText().strip() or None
            car.customs_decl_no = self.ed_customs_decl_no.text().strip() or None
            car.sbkts_no = self.ed_sbkts_no.text().strip() or None

            # Финансы
            car.price_to_vladivostok = price_to_vld
            car.purchase_currency = self.cb_purchase_currency.currentText().strip() or None
            car.purchase_price = purchase_price
            car.other_costs = other_costs
            car.price_customer = price_customer
            car.responsible_user_id = responsible_user_id
            car.lead_source = lead_source
            car.priority = priority
            car.expected_arrival_date = expected_arrival_date
            car.next_action_date = next_action_date
            car.next_action_note = next_action_note
            car.blocked_reason = blocked_reason

            # Клиент
            if client:
                car.client_id = client.id

            # Этап
            if selected_stage and (car.deal_stage_id != selected_stage.id):
                move_car_to_stage(s, car, selected_stage, user_id=None, note="Смена стадии из формы авто")

            # Опции
            s.query(CarOption).filter(CarOption.car_id == car.id).delete()
            for oid in selected_option_ids:
                s.add(CarOption(car_id=car.id, option_id=oid))

            if options_note:
                base_note = (car.notes or "").strip()
                car.notes = (f"{base_note}\n\n[Опции] {options_note}" if base_note else f"[Опции] {options_note}")

        else:
            car = Car(
                brand_id=brand.id, model_id=model.id, trim_id=(trim.id if trim else None),
                body_type_id=(body.id if body else None), fuel_type_id=(fuel.id if fuel else None),
                transmission_id=(trans.id if trans else None), color_id=(color.id if color else None),

                build_date=build_date, mileage_km=self.sp_mileage.value() or None,
                status=(st.name if st else None), deal_status=(dst.name if dst else None),

                engine_cc=self.sp_engine.value() or None, horsepower=self.sp_hp.value() or None,
                drive=self.cb_drive.currentText().strip() or None, euro_class=self.ed_euro_class.text().strip() or None,
                cons_mix_l100=cons_mix,

                length_mm=self.sp_length_mm.value() or None, width_mm=self.sp_width_mm.value() or None,
                height_mm=self.sp_height_mm.value() or None, wheelbase_mm=self.sp_wheelbase_mm.value() or None,
                ground_clearance_mm=self.sp_clearance_mm.value() or None, curb_weight_kg=self.sp_curb_weight_kg.value() or None,
                seats=self.sp_seats.value() or None,

                wheel_size=self.ed_wheel_size.text().strip() or None,
                tire_front=self.ed_tire_front.text().strip() or None,
                tire_rear=self.ed_tire_rear.text().strip() or None,
                accel_0_100_s=accel, max_speed_kmh=self.sp_max_speed_kmh.value() or None,

                vin=self.ed_vin.text().strip() or None, pts_number=self.ed_pts_number.text().strip() or None,
                market=self.cb_market.currentText().strip() or None, customs_decl_no=self.ed_customs_decl_no.text().strip() or None,
                sbkts_no=self.ed_sbkts_no.text().strip() or None,

                price_to_vladivostok=price_to_vld, purchase_currency=self.cb_purchase_currency.currentText().strip() or None,
                purchase_price=purchase_price, other_costs=other_costs, price_customer=price_customer,
                responsible_user_id=responsible_user_id, lead_source=lead_source, priority=priority,
                expected_arrival_date=expected_arrival_date, next_action_date=next_action_date,
                next_action_note=next_action_note, blocked_reason=blocked_reason,

                notes=(f"[Опции] {options_note}" if options_note else None),
                client_id=(client.id if client else None)
            )
            s.add(car); s.flush()
            self.car_id = car.id

            if selected_stage:
                move_car_to_stage(s, car, selected_stage, user_id=None, note="Назначение стадии при создании")

            for oid in selected_option_ids:
                s.add(CarOption(car_id=car.id, option_id=oid))

        if car.client_id:
            ensure_deal_for_car(s, car)
        else:
            remove_deal_for_car(s, car.id)

        s.commit()
        self._refresh_media_list()

    # ===== Load / Media =====
    def _load_car(self):
        s = self.session
        c = s.get(Car, self.car_id)
        if not c:
            return

        # Основное
        self.cb_brand.setEditText(c.brand.name if c.brand else "")
        self._on_brand_changed(self.cb_brand.currentText())
        self.cb_model.setEditText(c.model.name if c.model else "")
        self._on_model_changed(self.cb_model.currentText())
        self.cb_trim.setEditText(c.trim.name if c.trim else "")
        self.cb_body.setEditText(c.body_type.name if c.body_type else "")
        self.cb_fuel.setEditText(c.fuel_type.name if c.fuel_type else "")
        self.cb_trans.setEditText(c.transmission.name if c.transmission else "")
        self.cb_color.setEditText(c.color.name if c.color else "")

        if c.build_date:
            self.dt_build.setDate(QDate(c.build_date.year, c.build_date.month, 1))
        self.sp_mileage.setValue(c.mileage_km or 0)

        self.cb_status.setEditText(c.status or "")
        self.cb_deal_status.setEditText(c.deal_status or "")

        if c.deal_stage_id:
            idx = self.cb_stage.findData(c.deal_stage_id)
            if idx >= 0:
                self.cb_stage.setCurrentIndex(idx)

        # Двигатель/КПП
        self.sp_engine.setValue(c.engine_cc or 0)
        self.sp_hp.setValue(c.horsepower or 0)
        self.cb_drive.setEditText(c.drive or "")
        self.ed_euro_class.setText(c.euro_class or "")
        try: self.sp_cons_mix.setValue(float(c.cons_mix_l100 or 0))
        except Exception: self.sp_cons_mix.setValue(0.0)

        # Габариты/масса
        self.sp_length_mm.setValue(c.length_mm or 0)
        self.sp_width_mm.setValue(c.width_mm or 0)
        self.sp_height_mm.setValue(c.height_mm or 0)
        self.sp_wheelbase_mm.setValue(c.wheelbase_mm or 0)
        self.sp_clearance_mm.setValue(c.ground_clearance_mm or 0)
        self.sp_curb_weight_kg.setValue(c.curb_weight_kg or 0)
        self.sp_seats.setValue(c.seats or 0)

        # Шасси/колёса
        self.ed_wheel_size.setText(c.wheel_size or "")
        self.ed_tire_front.setText(c.tire_front or "")
        self.ed_tire_rear.setText(c.tire_rear or "")
        try: self.sp_accel_0_100.setValue(float(c.accel_0_100_s or 0))
        except Exception: self.sp_accel_0_100.setValue(0.0)
        self.sp_max_speed_kmh.setValue(c.max_speed_kmh or 0)

        # Документы
        self.ed_vin.setText(c.vin or "")
        self.ed_pts_number.setText(c.pts_number or "")
        self.cb_market.setEditText(c.market or "")
        self.ed_customs_decl_no.setText(c.customs_decl_no or "")
        self.ed_sbkts_no.setText(c.sbkts_no or "")

        # Финансы
        try: self.sp_price_to_vld.setValue(float(c.price_to_vladivostok or 0))
        except Exception: self.sp_price_to_vld.setValue(0.0)
        self.cb_purchase_currency.setEditText(c.purchase_currency or "")
        for spin, val in (
            (self.sp_purchase_price, c.purchase_price),
            (self.sp_other_costs, c.other_costs),
            (self.sp_price_customer, c.price_customer),
        ):
            try: spin.setValue(float(val or 0))
            except Exception: spin.setValue(0.0)

        self.txt_notes.setPlainText(c.notes or "")

        # CRM / Сделка
        idx = self.cb_responsible_user.findData(c.responsible_user_id)
        if idx >= 0:
            self.cb_responsible_user.setCurrentIndex(idx)
        fill_lead_source_combo(self.cb_lead_source, c.lead_source)
        fill_priority_combo(self.cb_priority, c.priority or "normal")
        if c.expected_arrival_date:
            self.dt_expected_arrival.setDate(QDate(c.expected_arrival_date.year, c.expected_arrival_date.month, c.expected_arrival_date.day))
        else:
            self.dt_expected_arrival.setDate(self.dt_expected_arrival.minimumDate())
        if c.next_action_date:
            self.dt_next_action.setDate(QDate(c.next_action_date.year, c.next_action_date.month, c.next_action_date.day))
        else:
            self.dt_next_action.setDate(self.dt_next_action.minimumDate())
        self.txt_next_action_note.setPlainText(c.next_action_note or "")
        self.txt_blocked_reason.setPlainText(c.blocked_reason or "")

        # Клиент
        if c.client:
            cl = c.client
            self._populate_clients_combo(cl.id)
            idx = self.cb_client_existing.findData(cl.id)
            if idx >= 0:
                self.cb_client_existing.setCurrentIndex(idx)
            self._set_client_fields(cl)

        # Опции
        selected = {row.option_id for row in s.query(CarOption).filter(CarOption.car_id == c.id).all()}
        for oid, row in self._option_rows.items():
            row.setChecked(oid in selected)

        if c.notes and "[Опции]" in c.notes:
            try:
                part = c.notes.split("[Опции]", 1)[1].strip()
                self.txt_options_note.setPlainText(part)
            except Exception:
                pass

    # ===== Media =====
    def _car_dir(self) -> Optional[Path]:
        if not self.car_id:
            return None
        d = IMG_ROOT / str(self.car_id)
        _ensure_dir(d)
        return d

    def _refresh_media_list(self):
        self.media_list.clear()
        if not self.car_id:
            return
        s = self.session
        items = s.query(CarMedia).filter(CarMedia.car_id == self.car_id).order_by(CarMedia.id.asc()).all()
        for m in items:
            li = QListWidgetItem(f"{m.media_type}: {m.original_name or Path(m.file_path).name}")
            li.setData(Qt.ItemDataRole.UserRole, m.id)
            self.media_list.addItem(li)

    def _open_media_dir(self):
        d = self._car_dir()
        if d:
            try:
                os.startfile(str(d))
            except Exception:
                QFileDialog.getOpenFileName(self, "Открыть", str(d))

    def _add_images(self):
        if not self.car_id:
            QMessageBox.information(self, "Сначала сохраните авто", "Сохраните карточку авто (ОК), затем добавьте фото.")
            return
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Выбор фотографий", "", "Изображения (*.png *.jpg *.jpeg *.bmp)")
        if not files:
            return
        self._save_media(files, "image")

    def _add_videos(self):
        if not self.car_id:
            QMessageBox.information(self, "Сначала сохраните авто", "Сохраните карточку авто (ОК), затем добавьте видео.")
            return
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Выбор видео", "", "Видео (*.mp4 *.mov *.avi *.mkv)")
        if not files:
            return
        self._save_media(files, "video")

    def _save_media(self, src_files, mtype: str):
        d = self._car_dir()
        if not d:
            return
        s = self.session
        for src in src_files:
            src_p = Path(src)
            dst = d / src_p.name
            i = 1
            while dst.exists():
                dst = d / f"{src_p.stem}_{i}{src_p.suffix}"
                i += 1
            shutil.copy2(src_p, dst)
            cm = CarMedia(
                car_id=self.car_id,
                media_type=mtype,
                file_path=str(dst.relative_to(PKG_ROOT)).replace("\\", "/"),
                original_name=src_p.name
            )
            s.add(cm)
        s.commit()
        self._refresh_media_list()
