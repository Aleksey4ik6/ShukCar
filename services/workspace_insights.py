from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from models import AuditLog, Car, CarTask, ChatMessage, Client, Deal, DealTask, User
from services.crm import priority_label, priority_sort_key
from services.deal_sync import sync_deals_from_cars


def _trimmed(expr):
    return func.trim(func.coalesce(expr, ""))


def _car_label(car: Car | None) -> str:
    if car is None:
        return "Авто не привязано"
    parts = [
        getattr(getattr(car, "brand", None), "name", None),
        getattr(getattr(car, "model", None), "name", None),
    ]
    label = " ".join(part for part in parts if part)
    return label or car.vin or f"Авто #{car.id}"


def _deal_label(deal: Deal | None) -> str:
    if deal is None:
        return "Сделка не привязана"
    return deal.title or f"Сделка #{deal.id}"


def _client_label(client: Client | None) -> str:
    if client is None:
        return "Клиент не указан"
    return client.full_name or f"Клиент #{client.id}"


def _user_label(user: User | None) -> str:
    if user is None:
        return "Не назначен"
    return user.full_name or user.login or f"Сотрудник #{user.id}"


def _format_date(value) -> str:
    return value.strftime("%d.%m.%Y") if value else "—"


def _deal_base_query(session: Session, *, user_id: int | None = None):
    query = (
        session.query(Deal)
        .options(
            joinedload(Deal.client),
            joinedload(Deal.car).joinedload(Car.brand),
            joinedload(Deal.car).joinedload(Car.model),
            joinedload(Deal.deal_stage),
            joinedload(Deal.responsible_user),
        )
        .filter(or_(Deal.is_archived.is_(False), Deal.is_archived.is_(None)))
    )
    if user_id is not None:
        query = query.filter(Deal.responsible_user_id == user_id)
    return query


def _car_base_query(session: Session, *, user_id: int | None = None):
    query = (
        session.query(Car)
        .options(
            joinedload(Car.client),
            joinedload(Car.brand),
            joinedload(Car.model),
            joinedload(Car.responsible_user),
        )
        .filter(or_(Car.is_archived.is_(False), Car.is_archived.is_(None)))
    )
    if user_id is not None:
        query = query.filter(Car.responsible_user_id == user_id)
    return query


def build_attention_snapshot(session: Session, *, user_id: int | None = None) -> dict:
    today = dt.date.today()
    week_limit = today + dt.timedelta(days=7)
    start_today = dt.datetime.combine(today, dt.time.min)

    sync_deals_from_cars(session)
    session.commit()

    deal_query = _deal_base_query(session, user_id=user_id)
    car_query = _car_base_query(session, user_id=user_id)
    deal_task_query = (
        session.query(DealTask)
        .join(Deal, Deal.id == DealTask.deal_id)
        .options(
            joinedload(DealTask.deal).joinedload(Deal.client),
            joinedload(DealTask.deal).joinedload(Deal.car).joinedload(Car.brand),
            joinedload(DealTask.deal).joinedload(Deal.car).joinedload(Car.model),
        )
        .filter(
            or_(Deal.is_archived.is_(False), Deal.is_archived.is_(None)),
            DealTask.is_done.is_(False),
        )
    )
    car_task_query = (
        session.query(CarTask)
        .join(Car, Car.id == CarTask.car_id)
        .options(
            joinedload(CarTask.car).joinedload(Car.client),
            joinedload(CarTask.car).joinedload(Car.brand),
            joinedload(CarTask.car).joinedload(Car.model),
        )
        .filter(
            or_(Car.is_archived.is_(False), Car.is_archived.is_(None)),
            CarTask.is_done.is_(False),
        )
    )
    client_query = session.query(Client)
    if user_id is not None:
        client_query = client_query.filter(
            or_(Client.responsible_user_id == user_id, Client.responsible_user_id.is_(None))
        )
        deal_task_query = deal_task_query.filter(Deal.responsible_user_id == user_id)
        car_task_query = car_task_query.filter(Car.responsible_user_id == user_id)

    active_deals = deal_query.count()
    overdue_deal_tasks = deal_task_query.filter(DealTask.due_date.is_not(None), DealTask.due_date < today).all()
    overdue_car_tasks = car_task_query.filter(CarTask.due_date.is_not(None), CarTask.due_date < today).all()
    blocked_deals = (
        deal_query.filter(_trimmed(Deal.blocked_reason) != "")
        .order_by(Deal.priority.asc(), Deal.next_action_date.asc(), Deal.id.desc())
        .all()
    )
    no_next_deals = (
        deal_query.filter(
            or_(Deal.next_action_date.is_(None), _trimmed(Deal.next_action_note) == "")
        )
        .order_by(Deal.priority.asc(), Deal.created_at.desc(), Deal.id.desc())
        .all()
    )
    arriving_deals = (
        deal_query.filter(
            Deal.expected_arrival_date.is_not(None),
            Deal.expected_arrival_date >= today,
            Deal.expected_arrival_date <= week_limit,
        )
        .order_by(Deal.expected_arrival_date.asc(), Deal.id.desc())
        .all()
    )
    urgent_deals = deal_query.filter(Deal.priority.in_(["urgent", "high"])).count()
    deals_without_manager = deal_query.filter(Deal.responsible_user_id.is_(None)).count()
    deals_without_stage = deal_query.filter(Deal.deal_stage_id.is_(None)).count()
    cars_without_client = car_query.filter(Car.client_id.is_(None)).count()
    clients_without_phone = client_query.filter(or_(Client.phone.is_(None), Client.phone == "")).count()
    messages_today = session.query(ChatMessage).filter(ChatMessage.created_at >= start_today).count()

    recent_logs_query = session.query(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if user_id is not None:
        recent_logs_query = recent_logs_query.filter(AuditLog.user_id == user_id)
    recent_logs = recent_logs_query.limit(10).all()

    overdue_items = []
    for task in overdue_deal_tasks:
        deal = task.deal
        overdue_items.append(
            {
                "kind": "deal_task",
                "id": int(task.id),
                "title": task.title,
                "due_date": task.due_date,
                "priority_code": task.priority,
                "priority": priority_label(task.priority),
                "entity": _deal_label(deal),
                "extra": _client_label(getattr(deal, "client", None)),
                "route": "deals",
            }
        )
    for task in overdue_car_tasks:
        car = task.car
        overdue_items.append(
            {
                "kind": "car_task",
                "id": int(task.id),
                "title": task.title,
                "due_date": task.due_date,
                "priority_code": task.priority,
                "priority": priority_label(task.priority),
                "entity": _car_label(car),
                "extra": _client_label(getattr(car, "client", None)),
                "route": "cars",
            }
        )
    overdue_items.sort(
        key=lambda row: (
            row["due_date"] or dt.date.max,
            priority_sort_key(row.get("priority_code")),
            -row["id"],
        )
    )

    blocked_items = [
        {
            "id": int(deal.id),
            "title": _deal_label(deal),
            "client": _client_label(deal.client),
            "manager": _user_label(deal.responsible_user),
            "reason": (deal.blocked_reason or "").strip() or "Причина не указана",
            "route": "deals",
        }
        for deal in blocked_deals[:12]
    ]
    no_next_items = [
        {
            "id": int(deal.id),
            "title": _deal_label(deal),
            "client": _client_label(deal.client),
            "stage": getattr(getattr(deal, "deal_stage", None), "name", None) or "Без этапа",
            "manager": _user_label(deal.responsible_user),
            "route": "deals",
        }
        for deal in no_next_deals[:12]
    ]
    arrival_items = [
        {
            "id": int(deal.id),
            "title": _deal_label(deal),
            "client": _client_label(deal.client),
            "arrival_date": deal.expected_arrival_date,
            "car": _car_label(deal.car),
            "route": "deals",
        }
        for deal in arriving_deals[:12]
    ]

    quality_items = []
    if cars_without_client:
        quality_items.append(
            {
                "scope": "Авто",
                "value": cars_without_client,
                "label": "Автомобили без клиента",
                "recommendation": "Привяжите клиента в карточке авто, чтобы сделка попала в рабочий контур.",
                "route": "cars",
            }
        )
    if clients_without_phone:
        quality_items.append(
            {
                "scope": "Клиенты",
                "value": clients_without_phone,
                "label": "Клиенты без телефона",
                "recommendation": "Заполните контакт, чтобы не терять связь по сделке.",
                "route": "clients",
            }
        )
    if deals_without_manager:
        quality_items.append(
            {
                "scope": "Сделки",
                "value": deals_without_manager,
                "label": "Сделки без ответственного",
                "recommendation": "Назначьте менеджера, чтобы сделки попадали в личный контур сотрудника.",
                "route": "deals",
            }
        )
    if deals_without_stage:
        quality_items.append(
            {
                "scope": "Сделки",
                "value": deals_without_stage,
                "label": "Сделки без этапа",
                "recommendation": "Укажите этап воронки, чтобы видеть реальный статус привоза.",
                "route": "deals",
            }
        )

    recent_items = [
        {
            "created_at": row.created_at,
            "title": f"{row.action} · {row.entity}",
            "details": row.details or f"ID объекта: {row.entity_id or '—'}",
        }
        for row in recent_logs
    ]

    return {
        "metrics": {
            "active_deals": active_deals,
            "overdue_tasks": len(overdue_items),
            "blocked_deals": len(blocked_deals),
            "no_next": len(no_next_deals),
            "arrivals_soon": len(arriving_deals),
            "urgent_deals": urgent_deals,
            "data_issues": sum(item["value"] for item in quality_items),
            "messages_today": messages_today,
        },
        "overdue_items": overdue_items[:14],
        "blocked_items": blocked_items,
        "no_next_items": no_next_items,
        "arrival_items": arrival_items,
        "quality_items": quality_items,
        "recent_items": recent_items,
    }


def build_staff_snapshot(session: Session, user_id: int) -> dict:
    today = dt.date.today()
    week_limit = today + dt.timedelta(days=7)

    sync_deals_from_cars(session)
    session.commit()

    user = session.get(User, user_id)
    if user is None:
        return {
            "user": None,
            "metrics": {},
            "deal_rows": [],
            "activity_rows": [],
        }

    active_deals_query = _deal_base_query(session, user_id=user_id)
    archived_deals_query = (
        session.query(Deal)
        .filter(Deal.responsible_user_id == user_id, Deal.is_archived.is_(True))
    )
    active_clients = session.query(Client).filter(Client.responsible_user_id == user_id).count()
    overdue_deal_tasks = (
        session.query(DealTask)
        .join(Deal, Deal.id == DealTask.deal_id)
        .filter(
            Deal.responsible_user_id == user_id,
            or_(Deal.is_archived.is_(False), Deal.is_archived.is_(None)),
            DealTask.is_done.is_(False),
            DealTask.due_date.is_not(None),
            DealTask.due_date < today,
        )
        .count()
    )
    overdue_car_tasks = (
        session.query(CarTask)
        .join(Car, Car.id == CarTask.car_id)
        .filter(
            Car.responsible_user_id == user_id,
            or_(Car.is_archived.is_(False), Car.is_archived.is_(None)),
            CarTask.is_done.is_(False),
            CarTask.due_date.is_not(None),
            CarTask.due_date < today,
        )
        .count()
    )
    active_deals = active_deals_query.count()
    archived_deals = archived_deals_query.count()
    urgent_deals = active_deals_query.filter(Deal.priority.in_(["urgent", "high"])).count()
    blocked_deals = active_deals_query.filter(_trimmed(Deal.blocked_reason) != "").count()
    arrivals_soon = active_deals_query.filter(
        Deal.expected_arrival_date.is_not(None),
        Deal.expected_arrival_date >= today,
        Deal.expected_arrival_date <= week_limit,
    ).count()

    deal_rows = (
        active_deals_query.order_by(
            Deal.priority.asc(),
            func.coalesce(Deal.next_action_date, dt.date(9999, 12, 31)).asc(),
            Deal.id.desc(),
        )
        .limit(8)
        .all()
    )
    logs = (
        session.query(AuditLog)
        .filter(AuditLog.user_id == user_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(8)
        .all()
    )

    return {
        "user": user,
        "metrics": {
            "active_deals": active_deals,
            "archived_deals": archived_deals,
            "active_clients": active_clients,
            "overdue_tasks": overdue_deal_tasks + overdue_car_tasks,
            "urgent_deals": urgent_deals,
            "blocked_deals": blocked_deals,
            "arrivals_soon": arrivals_soon,
        },
        "deal_rows": [
            {
                "title": _deal_label(deal),
                "client": _client_label(deal.client),
                "stage": getattr(getattr(deal, "deal_stage", None), "name", None) or "Без этапа",
                "next_action": (deal.next_action_note or "").strip() or "Следующий шаг не указан",
                "next_action_date": _format_date(deal.next_action_date),
                "priority": priority_label(deal.priority),
            }
            for deal in deal_rows
        ],
        "activity_rows": [
            {
                "created_at": row.created_at,
                "title": f"{row.action} · {row.entity}",
                "details": row.details or f"ID объекта: {row.entity_id or '—'}",
            }
            for row in logs
        ],
    }


def calculate_portfolio_finance(session: Session, *, user_id: int | None = None) -> dict:
    car_query = _car_base_query(session, user_id=user_id)
    cars = car_query.all()
    revenue = sum(Decimal(str(car.price_customer or 0)) for car in cars)
    cost = sum(Decimal(str((car.price_to_vladivostok or 0) + (car.other_costs or 0))) for car in cars)
    return {
        "revenue": revenue,
        "cost": cost,
        "margin": revenue - cost,
    }
