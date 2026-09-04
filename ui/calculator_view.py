from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import List

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from db import SessionLocal
from models import ExchangeRate
from services.auto_cost_calculator import (
    AGE_3_TO_5,
    AGE_OVER_5,
    AGE_UNDER_3,
    CalculatorError,
    CalculationInput,
    MoneyAmount,
    calculate_import_cost,
    format_eur,
    format_rub,
)


CODES: List[str] = ["RUB", "USD", "EUR", "CNY", "KRW", "JPY"]


def _get_all_rates() -> dict[str, Decimal]:
    with SessionLocal() as db:
        rows = db.query(ExchangeRate).all()
    rates = {"RUB": Decimal("1")}
    for row in rows:
        rates[row.code.upper()] = Decimal(str(row.rate_to_rub))
    return rates


def _qdate_to_date(value: QDate) -> dt.date:
    return dt.date(value.year(), value.month(), value.day())


def _configure_form_layout(form: QFormLayout):
    form.setContentsMargins(16, 16, 16, 16)
    form.setHorizontalSpacing(18)
    form.setVerticalSpacing(10)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)


class MoneyRow(QWidget):
    changed = QtCore.pyqtSignal()

    def __init__(self, codes: List[str] = CODES, default_code: str = "RUB", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.amount = QtWidgets.QDoubleSpinBox()
        self.amount.setDecimals(2)
        self.amount.setMaximum(1_000_000_000)
        self.amount.setMinimumWidth(220)
        self.amount.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.amount.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.amount.valueChanged.connect(self.changed.emit)

        self.code = QComboBox()
        self.code.addItems(codes)
        self.code.setCurrentText(default_code)
        self.code.setMinimumWidth(96)
        self.code.setMaximumWidth(112)
        self.code.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
        self.code.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.code.currentTextChanged.connect(self.changed.emit)

        layout.addWidget(self.amount, 1)
        layout.addWidget(self.code, 0)

    def get_value(self) -> MoneyAmount:
        return MoneyAmount(amount=Decimal(f"{self.amount.value():.2f}"), currency=self.code.currentText())


class ResultRow(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("InlineMutedLabel")
        self.lbl_title.setWordWrap(True)

        self.lbl_value = QLabel("—")
        self.lbl_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_value.setWordWrap(True)

        layout.addWidget(self.lbl_title, 3)
        layout.addStretch(1)
        layout.addWidget(self.lbl_value, 4)

    def set_value(self, text: str):
        self.lbl_value.setText(text)


class CalculatorView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_result = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(self.scroll)

        self.body = QWidget()
        self.scroll.setWidget(self.body)

        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(12, 12, 12, 12)
        body_layout.setSpacing(12)

        intro = QFrame(self.body)
        intro.setProperty("card", True)
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(18, 18, 18, 18)
        intro_layout.setSpacing(8)

        title = QLabel("Калькулятор привоза авто")
        title.setObjectName("SectionTitle")

        subtitle = QLabel(
            "Автоматически считает личный ввоз легкового автомобиля в РФ: "
            "таможенную стоимость, единую пошлину, таможенный сбор, утильсбор "
            "и итоговую себестоимость под ключ."
        )
        subtitle.setWordWrap(True)

        self.lbl_status = QLabel(
            "Формулы привязаны к ставкам 2026 года для легкового автомобиля физлица. "
            "Для юрлица и товарного импорта логика отличается."
        )
        self.lbl_status.setObjectName("InlineMutedLabel")
        self.lbl_status.setWordWrap(True)

        intro_layout.addWidget(title)
        intro_layout.addWidget(subtitle)
        intro_layout.addWidget(self.lbl_status)
        body_layout.addWidget(intro)

        self.panels = QWidget(self.body)
        self.panels_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.panels)
        self.panels_layout.setContentsMargins(0, 0, 0, 0)
        self.panels_layout.setSpacing(12)
        body_layout.addWidget(self.panels)

        self.left_panel = QWidget(self.panels)
        self.left_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        vehicle_card = QFrame(self.left_panel)
        vehicle_card.setProperty("card", True)
        vehicle_form = QFormLayout(vehicle_card)
        _configure_form_layout(vehicle_form)

        self.dt_production = QDateEdit()
        self.dt_production.setCalendarPopup(True)
        self.dt_production.setDisplayFormat("dd.MM.yyyy")
        self.dt_production.setDate(QDate.currentDate().addYears(-3))

        self.dt_clearance = QDateEdit()
        self.dt_clearance.setCalendarPopup(True)
        self.dt_clearance.setDisplayFormat("dd.MM.yyyy")
        self.dt_clearance.setDate(QDate.currentDate())

        self.cb_age_override = QComboBox()
        self.cb_age_override.addItem("Определять по датам", None)
        self.cb_age_override.addItem("До 3 лет", AGE_UNDER_3)
        self.cb_age_override.addItem("От 3 до 5 лет", AGE_3_TO_5)
        self.cb_age_override.addItem("Старше 5 лет", AGE_OVER_5)

        self.sp_engine_cc = QSpinBox()
        self.sp_engine_cc.setRange(0, 10000)
        self.sp_engine_cc.setSingleStep(100)
        self.sp_engine_cc.setSuffix(" см³")

        self.sp_horsepower = QSpinBox()
        self.sp_horsepower.setRange(0, 2000)
        self.sp_horsepower.setSuffix(" л.с.")

        vehicle_form.addRow("Дата выпуска:", self.dt_production)
        vehicle_form.addRow("Дата расчета:", self.dt_clearance)
        vehicle_form.addRow("Возраст вручную:", self.cb_age_override)
        vehicle_form.addRow("Объем двигателя:", self.sp_engine_cc)
        vehicle_form.addRow("Мощность:", self.sp_horsepower)
        left_layout.addWidget(vehicle_card)

        pre_border_card = QFrame(self.left_panel)
        pre_border_card.setProperty("card", True)
        pre_border_form = QFormLayout(pre_border_card)
        _configure_form_layout(pre_border_form)
        pre_title = QLabel("<b>Расходы до границы ЕАЭС</b>")
        pre_title.setWordWrap(True)
        pre_border_form.addRow(pre_title)

        self.price_row = MoneyRow(default_code="USD")
        self.auction_row = MoneyRow(default_code="JPY")
        self.export_row = MoneyRow(default_code="JPY")
        self.delivery_row = MoneyRow(default_code="USD")

        pre_border_form.addRow("Цена авто:", self.price_row)
        pre_border_form.addRow("Аукцион / комиссия:", self.auction_row)
        pre_border_form.addRow("Экспортные расходы:", self.export_row)
        pre_border_form.addRow("Доставка до границы:", self.delivery_row)
        left_layout.addWidget(pre_border_card)

        local_card = QFrame(self.left_panel)
        local_card.setProperty("card", True)
        local_form = QFormLayout(local_card)
        _configure_form_layout(local_form)
        local_title = QLabel("<b>Расходы после границы</b>")
        local_title.setWordWrap(True)
        local_form.addRow(local_title)

        self.broker_row = MoneyRow(default_code="RUB")
        self.sbkts_row = MoneyRow(default_code="RUB")
        self.epts_row = MoneyRow(default_code="RUB")
        self.glonass_row = MoneyRow(default_code="RUB")
        self.logistics_row = MoneyRow(default_code="RUB")
        self.company_row = MoneyRow(default_code="RUB")
        self.other_row = MoneyRow(default_code="RUB")

        local_form.addRow("Брокер:", self.broker_row)
        local_form.addRow("СБКТС:", self.sbkts_row)
        local_form.addRow("ЭПТС:", self.epts_row)
        local_form.addRow("ГЛОНАСС / кнопка:", self.glonass_row)
        local_form.addRow("Логистика по РФ:", self.logistics_row)
        local_form.addRow("Наши услуги:", self.company_row)
        local_form.addRow("Прочие расходы:", self.other_row)
        left_layout.addWidget(local_card)
        left_layout.addStretch(1)

        self.right_panel = QWidget(self.panels)
        self.right_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        result_card = QFrame(self.right_panel)
        result_card.setProperty("card", True)
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(18, 18, 18, 18)
        result_layout.setSpacing(10)

        result_title = QLabel("Расшифровка расчета")
        result_title.setObjectName("SectionTitle")
        result_layout.addWidget(result_title)

        self.row_age = ResultRow("Возраст авто:")
        self.row_eur_rate = ResultRow("Курс EUR:")
        self.row_pre_border = ResultRow("До границы:")
        self.row_customs_value = ResultRow("Таможенная стоимость:")
        self.row_duty = ResultRow("Единая пошлина:")
        self.row_customs_fee = ResultRow("Таможенный сбор:")
        self.row_util = ResultRow("Утилизационный сбор:")
        self.row_local = ResultRow("После границы:")
        self.row_total = ResultRow("Итого под ключ:")
        self.row_total.lbl_value.setObjectName("ResultLabel")

        for row in (
            self.row_age,
            self.row_eur_rate,
            self.row_pre_border,
            self.row_customs_value,
            self.row_duty,
            self.row_customs_fee,
            self.row_util,
            self.row_local,
            self.row_total,
        ):
            result_layout.addWidget(row)

        self.txt_details = QPlainTextEdit()
        self.txt_details.setReadOnly(True)
        self.txt_details.setPlaceholderText("Здесь появится подробная формула расчета.")
        self.txt_details.setMinimumHeight(280)
        result_layout.addWidget(self.txt_details, 1)
        right_layout.addWidget(result_card, 1)

        buttons = QHBoxLayout()
        self.btn_recalc = QPushButton("Обновить расчет")
        self.btn_copy = QPushButton("Скопировать расчет")
        self.btn_copy.setProperty("accent", "secondary")
        buttons.addWidget(self.btn_recalc)
        buttons.addWidget(self.btn_copy)
        buttons.addStretch(1)
        right_layout.addLayout(buttons)

        self.panels_layout.addWidget(self.left_panel, 5)
        self.panels_layout.addWidget(self.right_panel, 4)

        self.btn_recalc.clicked.connect(self.calculate)
        self.btn_copy.clicked.connect(self.copy_result)

        for widget in (
            self.dt_production,
            self.dt_clearance,
            self.cb_age_override,
            self.sp_engine_cc,
            self.sp_horsepower,
        ):
            if hasattr(widget, "dateChanged"):
                widget.dateChanged.connect(self.calculate)
            if hasattr(widget, "currentIndexChanged"):
                widget.currentIndexChanged.connect(self.calculate)
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self.calculate)

        for money_row in (
            self.price_row,
            self.auction_row,
            self.export_row,
            self.delivery_row,
            self.broker_row,
            self.sbkts_row,
            self.epts_row,
            self.glonass_row,
            self.logistics_row,
            self.company_row,
            self.other_row,
        ):
            money_row.changed.connect(self.calculate)

        self._apply_responsive_layout()
        self.calculate()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _apply_responsive_layout(self):
        wide_mode = self.width() >= 1450
        direction = QBoxLayout.Direction.LeftToRight if wide_mode else QBoxLayout.Direction.TopToBottom
        if self.panels_layout.direction() != direction:
            self.panels_layout.setDirection(direction)

        if wide_mode:
            self.right_panel.setMinimumWidth(500)
            self.right_panel.setMaximumWidth(760)
        else:
            self.right_panel.setMinimumWidth(0)
            self.right_panel.setMaximumWidth(16777215)

    def _set_status(self, text: str):
        self.lbl_status.setText(text)

    def _collect_input(self) -> CalculationInput:
        return CalculationInput(
            purchase_price=self.price_row.get_value(),
            auction_fee=self.auction_row.get_value(),
            export_fee=self.export_row.get_value(),
            delivery_to_border=self.delivery_row.get_value(),
            broker_fee=self.broker_row.get_value(),
            sbkts_fee=self.sbkts_row.get_value(),
            epts_fee=self.epts_row.get_value(),
            glonass_fee=self.glonass_row.get_value(),
            logistics_fee=self.logistics_row.get_value(),
            company_fee=self.company_row.get_value(),
            other_fee=self.other_row.get_value(),
            engine_cc=self.sp_engine_cc.value(),
            horsepower=self.sp_horsepower.value(),
            production_date=_qdate_to_date(self.dt_production.date()),
            clearance_date=_qdate_to_date(self.dt_clearance.date()),
            age_override=self.cb_age_override.currentData(),
        )

    def _reset_result_rows(self):
        for row in (
            self.row_age,
            self.row_eur_rate,
            self.row_pre_border,
            self.row_customs_value,
            self.row_duty,
            self.row_customs_fee,
            self.row_util,
            self.row_local,
            self.row_total,
        ):
            row.set_value("—")
        self.txt_details.clear()
        self._last_result = None

    def calculate(self):
        self._reset_result_rows()
        try:
            rates = _get_all_rates()
            input_data = self._collect_input()
            needed_codes = {
                "EUR",
                input_data.purchase_price.currency.upper(),
                input_data.auction_fee.currency.upper(),
                input_data.export_fee.currency.upper(),
                input_data.delivery_to_border.currency.upper(),
                input_data.broker_fee.currency.upper(),
                input_data.sbkts_fee.currency.upper(),
                input_data.epts_fee.currency.upper(),
                input_data.glonass_fee.currency.upper(),
                input_data.logistics_fee.currency.upper(),
                input_data.company_fee.currency.upper(),
                input_data.other_fee.currency.upper(),
            }
            missing = sorted(code for code in needed_codes if code not in rates)
            if missing:
                raise CalculatorError(
                    "Нет курсов для валют: "
                    + ", ".join(missing)
                    + ". Обновите раздел «Курсы (онлайн)»."
                )

            result = calculate_import_cost(input_data, lambda code: rates.get(code.upper(), Decimal("0")))
            self._last_result = result

            self.row_age.set_value(result.age_label)
            self.row_eur_rate.set_value(f"{result.euro_rate:,.4f} ₽".replace(",", " "))
            self.row_pre_border.set_value(format_rub(result.pre_border_rub))
            self.row_customs_value.set_value(f"{format_rub(result.customs_value_rub)} / {format_eur(result.customs_value_eur)}")
            self.row_duty.set_value(f"{format_rub(result.duty_rub)} / {format_eur(result.duty_eur)}")
            self.row_customs_fee.set_value(format_rub(result.customs_fee_rub))
            self.row_util.set_value(format_rub(result.util_fee_rub))
            self.row_local.set_value(format_rub(result.local_costs_rub))
            self.row_total.set_value(format_rub(result.total_rub))

            details = [
                f"Правило пошлины: {result.duty_rule}",
                "",
                "Что входит в таможенную стоимость:",
                f"- Цена авто + аукцион/комиссия + экспортные расходы + доставка до границы = {format_rub(result.pre_border_rub)}",
                "",
                "Что входит в расходы после границы:",
                f"- Брокер + СБКТС + ЭПТС + ГЛОНАСС + логистика по РФ + наши услуги + прочее = {format_rub(result.local_costs_rub)}",
                "",
                "Итог:",
                f"- Таможенная стоимость: {format_rub(result.customs_value_rub)}",
                f"- Пошлина: {format_rub(result.duty_rub)}",
                f"- Таможенный сбор: {format_rub(result.customs_fee_rub)}",
                f"- Утильсбор: {format_rub(result.util_fee_rub)}",
                f"- После границы: {format_rub(result.local_costs_rub)}",
                f"- Под ключ: {format_rub(result.total_rub)}",
            ]
            self.txt_details.setPlainText("\n".join(details))
            self._set_status("Автопересчет активен. Формулы применены по ставкам 2026 года для легкового авто физлица.")
        except CalculatorError as exc:
            self._set_status(str(exc))
        except Exception as exc:
            self._set_status(f"Ошибка расчета: {exc}")

    def copy_result(self):
        if not self._last_result:
            return
        QtWidgets.QApplication.clipboard().setText(self._last_result.summary_text())
        self._set_status("Расчет скопирован в буфер обмена.")
