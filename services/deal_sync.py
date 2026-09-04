from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from models import Car, Client, Deal


def _car_title(car: Car) -> str:
    brand = getattr(getattr(car, "brand", None), "name", "") or ""
    model = getattr(getattr(car, "model", None), "name", "") or ""
    build = car.build_date.strftime("%m.%Y") if getattr(car, "build_date", None) else ""
    vin = (car.vin or "").strip()
    parts = [part for part in [brand, model] if part]
    title = " ".join(parts) if parts else f"Авто #{car.id}"
    extra = [part for part in [build, vin] if part]
    if extra:
        title = f"{title} • {' • '.join(extra)}"
    return title


def build_deal_title(car: Car, client: Client | None) -> str:
    client_name = getattr(client, "full_name", None) or "Без клиента"
    return f"{client_name} • {_car_title(car)}"


def ensure_deal_for_car(session: Session, car: Car) -> Deal | None:
    if not car or not car.id or not car.client_id:
        return None

    client = getattr(car, "client", None) or session.get(Client, car.client_id)
    deal = session.query(Deal).filter(Deal.car_id == car.id).order_by(Deal.id.asc()).first()
    created = False
    if deal is None:
        deal = Deal(
            car_id=car.id,
            client_id=car.client_id,
            title=build_deal_title(car, client),
            responsible_user_id=car.responsible_user_id,
            deal_status=car.deal_status,
            deal_stage_id=car.deal_stage_id,
            lead_source=car.lead_source,
            priority=car.priority or "normal",
            expected_arrival_date=car.expected_arrival_date,
            next_action_date=car.next_action_date,
            next_action_note=car.next_action_note,
            blocked_reason=car.blocked_reason,
            notes=car.notes,
        )
        session.add(deal)
        session.flush()
        created = True

    deal.car_id = car.id
    deal.client_id = car.client_id
    deal.title = build_deal_title(car, client)
    deal.responsible_user_id = car.responsible_user_id
    deal.is_archived = bool(car.is_archived)
    deal.archived_at = car.archived_at if car.is_archived else None

    if created:
        deal.deal_status = car.deal_status
        deal.deal_stage_id = car.deal_stage_id
        deal.lead_source = car.lead_source
        deal.priority = car.priority or "normal"
        deal.expected_arrival_date = car.expected_arrival_date
        deal.next_action_date = car.next_action_date
        deal.next_action_note = car.next_action_note
        deal.blocked_reason = car.blocked_reason
        deal.notes = car.notes

    return deal


def remove_deal_for_car(session: Session, car_id: int | None) -> None:
    if not car_id:
        return
    rows = session.query(Deal).filter(Deal.car_id == car_id).all()
    for row in rows:
        session.delete(row)


def sync_deals_from_cars(session: Session) -> int:
    synced = 0

    valid_cars = (
        session.query(Car)
        .filter(Car.client_id.is_not(None))
        .order_by(Car.id.asc())
        .all()
    )
    valid_car_ids = set()
    for car in valid_cars:
        valid_car_ids.add(car.id)
        deal = ensure_deal_for_car(session, car)
        if deal is not None:
            synced += 1

    orphan_query = session.query(Deal).filter(Deal.car_id.is_(None))
    if valid_car_ids:
        orphan_query = session.query(Deal).filter((Deal.car_id.is_(None)) | (~Deal.car_id.in_(valid_car_ids)))

    orphan_deals = orphan_query.all()
    for row in orphan_deals:
        session.delete(row)

    return synced


def set_deal_archive_state(session: Session, deal: Deal, archived: bool) -> None:
    stamp = dt.datetime.now() if archived else None
    deal.is_archived = archived
    deal.archived_at = stamp

    if deal.car_id:
        car = session.get(Car, deal.car_id)
        if car is not None:
            car.is_archived = archived
            car.archived_at = stamp


def set_car_archive_state(session: Session, car: Car, archived: bool) -> None:
    stamp = dt.datetime.now() if archived else None
    car.is_archived = archived
    car.archived_at = stamp

    deals = session.query(Deal).filter(Deal.car_id == car.id).all()
    for deal in deals:
        deal.is_archived = archived
        deal.archived_at = stamp
