# ShukCar/services/danger_wipe.py
from sqlalchemy.orm import Session
from sqlalchemy import text

from db import SessionLocal
from models import (
    CarMedia, Car, Client,
    Trim, Model, Brand,
    BodyType, FuelType, Transmission, Color,
    CarStatus, DealStatus,
    ExchangeRate, WatchedCurrency,
    AuditLog
)

def wipe_all_data(session: Session) -> dict:
    """
    Полная очистка бизнес-данных приложения.
    Удаляет в корректном порядке с учётом FK.
    Возвращает словарь с количеством удалённых записей по таблицам.
    """
    stats = {}

    # Отключим проверку ключей на время массового удаления для MySQL/MariaDB (если нужно)
    try:
        session.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    except Exception:
        pass

    # Удаляем «детей» → «родителей» (важен порядок)
    for model in [
        CarMedia,
        Car,
        Client,
        Trim, Model, Brand,
        BodyType, FuelType, Transmission, Color,
        CarStatus, DealStatus,
        ExchangeRate, WatchedCurrency,
        AuditLog,
    ]:
        cnt = session.query(model).delete(synchronize_session=False)
        stats[model.__tablename__] = cnt

    session.commit()

    # Включим обратно FK-проверки
    try:
        session.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    except Exception:
        pass

    return stats
