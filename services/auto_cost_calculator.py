from __future__ import annotations

"""
Автоматический калькулятор привоза легкового авто для физлица в РФ.

Текущая логика покрывает режим личного ввоза и ставки, актуальные для 2026 года:
- единая таможенная пошлина по возрасту/стоимости/объему двигателя;
- таможенный сбор по таможенной стоимости;
- утилизационный сбор для легковых авто физлица по объему двигателя и мощности.

Перед обновлением таблиц сверяйте значения с действующими нормами и тарифами.
"""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Optional


ZERO = Decimal("0")
ONE = Decimal("1")


def dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return ZERO
    return Decimal(str(value))


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_rub(value: Decimal) -> str:
    amount = quantize_money(value)
    return f"{amount:,.2f} ₽".replace(",", " ")


def format_eur(value: Decimal) -> str:
    amount = quantize_money(value)
    return f"{amount:,.2f} €".replace(",", " ")


class CalculatorError(ValueError):
    pass


@dataclass(slots=True)
class MoneyAmount:
    amount: Decimal
    currency: str = "RUB"

    def to_rub(self, rate_resolver: Callable[[str], Decimal]) -> Decimal:
        code = (self.currency or "RUB").upper()
        rate = rate_resolver(code)
        if rate <= ZERO:
            raise CalculatorError(f"Нет курса для валюты {code}.")
        return quantize_money(self.amount * rate)


@dataclass(slots=True)
class CalculationInput:
    purchase_price: MoneyAmount
    auction_fee: MoneyAmount
    export_fee: MoneyAmount
    delivery_to_border: MoneyAmount
    broker_fee: MoneyAmount
    sbkts_fee: MoneyAmount
    epts_fee: MoneyAmount
    glonass_fee: MoneyAmount
    logistics_fee: MoneyAmount
    company_fee: MoneyAmount
    other_fee: MoneyAmount
    engine_cc: int
    horsepower: int
    production_date: dt.date
    clearance_date: dt.date
    age_override: str | None = None


@dataclass(slots=True)
class CalculationResult:
    age_group: str
    age_label: str
    customs_value_rub: Decimal
    customs_value_eur: Decimal
    duty_eur: Decimal
    duty_rub: Decimal
    duty_rule: str
    customs_fee_rub: Decimal
    util_fee_rub: Decimal
    pre_border_rub: Decimal
    local_costs_rub: Decimal
    total_rub: Decimal
    euro_rate: Decimal

    def summary_text(self) -> str:
        lines = [
            f"Возраст авто: {self.age_label}",
            f"Таможенная стоимость: {format_rub(self.customs_value_rub)} ({format_eur(self.customs_value_eur)})",
            f"Курс EUR: {self.euro_rate}",
            f"Единая пошлина: {format_rub(self.duty_rub)} ({format_eur(self.duty_eur)})",
            f"Правило пошлины: {self.duty_rule}",
            f"Таможенный сбор: {format_rub(self.customs_fee_rub)}",
            f"Утилизационный сбор: {format_rub(self.util_fee_rub)}",
            f"Расходы до границы: {format_rub(self.pre_border_rub)}",
            f"Расходы после границы: {format_rub(self.local_costs_rub)}",
            f"Итого под ключ: {format_rub(self.total_rub)}",
        ]
        return "\n".join(lines)


AGE_UNDER_3 = "under_3"
AGE_3_TO_5 = "three_to_five"
AGE_OVER_5 = "over_5"


def age_label(code: str) -> str:
    return {
        AGE_UNDER_3: "До 3 лет",
        AGE_3_TO_5: "От 3 до 5 лет",
        AGE_OVER_5: "Старше 5 лет",
    }[code]


def add_years(date_value: dt.date, years: int) -> dt.date:
    try:
        return date_value.replace(year=date_value.year + years)
    except ValueError:
        return date_value.replace(month=2, day=28, year=date_value.year + years)


def detect_age_group(production_date: dt.date, clearance_date: dt.date) -> str:
    if clearance_date <= add_years(production_date, 3):
        return AGE_UNDER_3
    if clearance_date <= add_years(production_date, 5):
        return AGE_3_TO_5
    return AGE_OVER_5


CUSTOMS_DUTY_UNDER_3 = [
    (Decimal("8500"), Decimal("0.54"), Decimal("2.5")),
    (Decimal("16700"), Decimal("0.48"), Decimal("3.5")),
    (Decimal("42300"), Decimal("0.48"), Decimal("5.5")),
    (Decimal("84500"), Decimal("0.48"), Decimal("7.5")),
    (Decimal("169000"), Decimal("0.48"), Decimal("15")),
    (None, Decimal("0.48"), Decimal("20")),
]

CUSTOMS_DUTY_3_TO_5 = [
    (1000, Decimal("1.5")),
    (1500, Decimal("1.7")),
    (1800, Decimal("2.5")),
    (2300, Decimal("2.7")),
    (3000, Decimal("3.0")),
    (None, Decimal("3.6")),
]

CUSTOMS_DUTY_OVER_5 = [
    (1000, Decimal("3.0")),
    (1500, Decimal("3.2")),
    (1800, Decimal("3.5")),
    (2300, Decimal("4.8")),
    (3000, Decimal("5.0")),
    (None, Decimal("5.7")),
]

CUSTOMS_FEE_TABLE_2026 = [
    (Decimal("200000"), Decimal("1231")),
    (Decimal("450000"), Decimal("2462")),
    (Decimal("1200000"), Decimal("4924")),
    (Decimal("2700000"), Decimal("13541")),
    (Decimal("4200000"), Decimal("18465")),
    (Decimal("5500000"), Decimal("21344")),
    (Decimal("10000000"), Decimal("49240")),
    (None, Decimal("73860")),
]

HP_BANDS = [
    (160, "До 160 л.с."),
    (190, "160.01–190 л.с."),
    (220, "190.01–220 л.с."),
    (250, "220.01–250 л.с."),
    (280, "250.01–280 л.с."),
    (310, "280.01–310 л.с."),
    (340, "310.01–340 л.с."),
    (370, "340.01–370 л.с."),
    (400, "370.01–400 л.с."),
    (430, "400.01–430 л.с."),
    (460, "430.01–460 л.с."),
    (500, "460.01–500 л.с."),
    (None, "Свыше 500 л.с."),
]

UTIL_TABLE_2026 = {
    1000: {
        160: (Decimal("3400"), Decimal("5200")),
        190: (Decimal("307200"), Decimal("568600")),
        220: (Decimal("316800"), Decimal("585600")),
        250: (Decimal("324000"), Decimal("602400")),
        None: (Decimal("345600"), Decimal("602400")),
    },
    2000: {
        160: (Decimal("3400"), Decimal("5200")),
        190: (Decimal("900000"), Decimal("1492800")),
        220: (Decimal("952800"), Decimal("1584000")),
        250: (Decimal("1010400"), Decimal("1677600")),
        280: (Decimal("1142400"), Decimal("1838400")),
        310: (Decimal("1291200"), Decimal("2011200")),
        340: (Decimal("1459200"), Decimal("2203200")),
        370: (Decimal("1663200"), Decimal("2412000")),
        400: (Decimal("1896000"), Decimal("2640000")),
        430: (Decimal("2160000"), Decimal("2892000")),
        460: (Decimal("2464800"), Decimal("3168000")),
        500: (Decimal("2808000"), Decimal("3468000")),
        None: (Decimal("3201600"), Decimal("3796800")),
    },
    3000: {
        160: (Decimal("3400"), Decimal("5200")),
        190: (Decimal("2306800"), Decimal("3456000")),
        220: (Decimal("2364000"), Decimal("3501600")),
        250: (Decimal("2402400"), Decimal("3552000")),
        280: (Decimal("2520000"), Decimal("3660000")),
        310: (Decimal("2620800"), Decimal("3770400")),
        340: (Decimal("2726400"), Decimal("3873600")),
        370: (Decimal("2834400"), Decimal("3981600")),
        400: (Decimal("2949600"), Decimal("4094400")),
        430: (Decimal("3067200"), Decimal("4209600")),
        460: (Decimal("3189600"), Decimal("4327200")),
        500: (Decimal("3316800"), Decimal("4447200")),
        None: (Decimal("3448800"), Decimal("4572000")),
    },
    3500: {
        160: (Decimal("2584000"), Decimal("3956200")),
        190: (Decimal("2635200"), Decimal("4000800")),
        220: (Decimal("2688000"), Decimal("4044000")),
        250: (Decimal("2743200"), Decimal("4087200")),
        280: (Decimal("2810400"), Decimal("4144800")),
        310: (Decimal("2880000"), Decimal("4248000")),
        340: (Decimal("3038400"), Decimal("4356000")),
        370: (Decimal("3206400"), Decimal("4485600")),
        400: (Decimal("3384000"), Decimal("4620000")),
        430: (Decimal("3568800"), Decimal("4759200")),
        460: (Decimal("3765600"), Decimal("4900800")),
        500: (Decimal("3972000"), Decimal("5049600")),
        None: (Decimal("4190400"), Decimal("5200800")),
    },
    None: {
        160: (Decimal("3290600"), Decimal("4325800")),
        190: (Decimal("3345600"), Decimal("4389600")),
        220: (Decimal("3403200"), Decimal("4456800")),
        250: (Decimal("3460800"), Decimal("4524000")),
        280: (Decimal("3530400"), Decimal("4627200")),
        310: (Decimal("3600000"), Decimal("4732800")),
        340: (Decimal("3727200"), Decimal("4992000")),
        370: (Decimal("3857600"), Decimal("5268000")),
        400: (Decimal("3993600"), Decimal("5558400")),
        430: (Decimal("4132800"), Decimal("5863200")),
        460: (Decimal("4276800"), Decimal("6187200")),
        500: (Decimal("4425600"), Decimal("6528000")),
        None: (Decimal("4581600"), Decimal("6885600")),
    },
}


def resolve_age_group(production_date: dt.date, clearance_date: dt.date, override: str | None) -> str:
    if override in {AGE_UNDER_3, AGE_3_TO_5, AGE_OVER_5}:
        return override
    return detect_age_group(production_date, clearance_date)


def customs_duty_eur(engine_cc: int, customs_value_eur: Decimal, age_group: str) -> tuple[Decimal, str]:
    if age_group == AGE_UNDER_3:
        for limit, percent, min_per_cc in CUSTOMS_DUTY_UNDER_3:
            if limit is None or customs_value_eur <= limit:
                percent_part = customs_value_eur * percent
                volume_part = Decimal(engine_cc) * min_per_cc
                duty = percent_part if percent_part >= volume_part else volume_part
                rule = (
                    f"До 3 лет: max({(percent * Decimal('100')).quantize(Decimal('0.01'))}% от стоимости, "
                    f"{min_per_cc} €/см³ × {engine_cc})"
                )
                return quantize_money(duty), rule

    rates = CUSTOMS_DUTY_3_TO_5 if age_group == AGE_3_TO_5 else CUSTOMS_DUTY_OVER_5
    for limit, rate in rates:
        if limit is None or engine_cc <= limit:
            duty = Decimal(engine_cc) * rate
            rule = f"{age_label(age_group)}: {rate} €/см³ × {engine_cc}"
            return quantize_money(duty), rule

    raise CalculatorError("Не удалось определить ставку пошлины.")


def customs_fee_rub(customs_value_rub: Decimal) -> Decimal:
    for limit, fee in CUSTOMS_FEE_TABLE_2026:
        if limit is None or customs_value_rub <= limit:
            return fee
    raise CalculatorError("Не удалось определить таможенный сбор.")


def util_fee_rub_2026(engine_cc: int, horsepower: int, age_group: str) -> Decimal:
    if engine_cc <= 0:
        raise CalculatorError("Укажите объём двигателя.")
    if horsepower <= 0:
        raise CalculatorError("Укажите мощность двигателя в л.с. для расчёта утильсбора.")

    engine_band = None
    for limit in UTIL_TABLE_2026:
        if limit is None or engine_cc <= limit:
            engine_band = limit
            break
    if engine_band not in UTIL_TABLE_2026:
        raise CalculatorError("Не найден диапазон объёма двигателя для утильсбора.")

    hp_table = UTIL_TABLE_2026[engine_band]
    hp_band = None
    for limit, _label in HP_BANDS:
        if limit is None or horsepower <= limit:
            hp_band = limit
            break
    if hp_band not in hp_table:
        raise CalculatorError("Не найден диапазон мощности для утильсбора.")

    amount_under_3, amount_over_3 = hp_table[hp_band]
    return amount_under_3 if age_group == AGE_UNDER_3 else amount_over_3


def calculate_import_cost(input_data: CalculationInput, rate_resolver: Callable[[str], Decimal]) -> CalculationResult:
    if input_data.engine_cc <= 0:
        raise CalculatorError("Укажите объём двигателя в см³.")
    if not input_data.production_date:
        raise CalculatorError("Укажите дату выпуска автомобиля.")
    if not input_data.clearance_date:
        raise CalculatorError("Укажите дату расчёта/растаможки.")

    euro_rate = rate_resolver("EUR")
    if euro_rate <= ZERO:
        raise CalculatorError("Нет курса EUR для расчёта пошлины.")

    pre_border_items = [
        input_data.purchase_price,
        input_data.auction_fee,
        input_data.export_fee,
        input_data.delivery_to_border,
    ]
    local_items = [
        input_data.broker_fee,
        input_data.sbkts_fee,
        input_data.epts_fee,
        input_data.glonass_fee,
        input_data.logistics_fee,
        input_data.company_fee,
        input_data.other_fee,
    ]

    pre_border_rub = sum((item.to_rub(rate_resolver) for item in pre_border_items), ZERO)
    local_costs_rub = sum((item.to_rub(rate_resolver) for item in local_items), ZERO)
    customs_value_rub = quantize_money(pre_border_rub)
    customs_value_eur = quantize_money(customs_value_rub / euro_rate) if euro_rate > ZERO else ZERO

    age_group = resolve_age_group(input_data.production_date, input_data.clearance_date, input_data.age_override)
    duty_eur, duty_rule = customs_duty_eur(input_data.engine_cc, customs_value_eur, age_group)
    duty_rub = quantize_money(duty_eur * euro_rate)
    fee_rub = customs_fee_rub(customs_value_rub)
    util_rub = util_fee_rub_2026(input_data.engine_cc, input_data.horsepower, age_group)
    total_rub = quantize_money(customs_value_rub + duty_rub + fee_rub + util_rub + local_costs_rub)

    return CalculationResult(
        age_group=age_group,
        age_label=age_label(age_group),
        customs_value_rub=customs_value_rub,
        customs_value_eur=customs_value_eur,
        duty_eur=duty_eur,
        duty_rub=duty_rub,
        duty_rule=duty_rule,
        customs_fee_rub=fee_rub,
        util_fee_rub=util_rub,
        pre_border_rub=quantize_money(pre_border_rub),
        local_costs_rub=quantize_money(local_costs_rub),
        total_rub=total_rub,
        euro_rate=euro_rate,
    )
