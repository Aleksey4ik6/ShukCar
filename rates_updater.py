# ShukCar/rates_updater.py
from __future__ import annotations
import json
import urllib.request
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Tuple

from sqlalchemy.orm import Session
from models import ExchangeRate

CBR_JSON_URL = "https://www.cbr-xml-daily.ru/daily_json.js"

class RatesProviderError(Exception):
    pass

def fetch_cbr_rates() -> Dict[str, Decimal]:
    """
    Возвращает словарь { 'USD': Decimal('83.59'), ... } — СКОЛЬКО РУБЛЕЙ за 1 единицу валюты.
    Источник: https://www.cbr-xml-daily.ru/daily_json.js
    """
    try:
        with urllib.request.urlopen(CBR_JSON_URL, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise RatesProviderError(f"CBR fetch failed: {e}")

    valute = data.get("Valute") or {}
    rates: Dict[str, Decimal] = {"RUB": Decimal("1")}
    for code, obj in valute.items():
        value = Decimal(str(obj.get("Value")))
        nominal = Decimal(str(obj.get("Nominal")))
        if nominal <= 0:
            continue
        per_one = (value / nominal).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        rates[code.upper()] = per_one
    return rates

def upsert_rates(db: Session, rates: Dict[str, Decimal]) -> int:
    """
    Записывает словарь в таблицу exchange_rates. Возвращает кол-во обновлённых записей.
    """
    count = 0
    for code, rate in rates.items():
        row = db.query(ExchangeRate).filter(ExchangeRate.code == code).first()
        if row:
            row.rate_to_rub = rate
        else:
            row = ExchangeRate(code=code, rate_to_rub=rate)
            db.add(row)
        count += 1
    db.commit()
    return count
