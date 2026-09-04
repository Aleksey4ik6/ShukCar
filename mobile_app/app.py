from __future__ import annotations

import datetime as dt
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from starlette.middleware.sessions import SessionMiddleware

from auth_service import try_login
from db import SessionLocal
from models import Car, ChatRoom, Client, ExchangeRate, User
from services.auto_cost_calculator import (
    AGE_3_TO_5,
    AGE_OVER_5,
    AGE_UNDER_3,
    CalculationInput,
    MoneyAmount,
    calculate_import_cost,
    format_rub,
)
from services.chat_service import ensure_general_room, list_messages, list_rooms_for_user, mark_room_read, send_message
from services.runtime_schema import ensure_runtime_schema


APP_ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_ROOT / "templates"))

app = FastAPI(title="ShukCar Mobile", version="1.0.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("MOBILE_SESSION_SECRET", "shukcar-mobile-secret"),
    same_site="lax",
    https_only=False,
    max_age=60 * 60 * 24 * 7,
)
app.mount("/mobile/static", StaticFiles(directory=str(APP_ROOT / "static")), name="mobile-static")


def _money_or_zero(value: str | None) -> Decimal:
    raw = (value or "").strip().replace(",", ".")
    if not raw:
        return Decimal("0")
    return Decimal(raw)


def _to_date(value: str | None, fallback: dt.date | None = None) -> dt.date:
    if not value:
        if fallback is None:
            raise ValueError("Дата не указана.")
        return fallback
    return dt.date.fromisoformat(value)


def _to_int(value: str | None, default: int = 0) -> int:
    raw = (value or "").strip()
    if not raw:
        return default
    return int(raw)


def _get_all_rates() -> dict[str, Decimal]:
    with SessionLocal() as db:
        rows = db.query(ExchangeRate).all()
    rates = {"RUB": Decimal("1")}
    for row in rows:
        rates[row.code.upper()] = Decimal(str(row.rate_to_rub))
    return rates


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=303)


def _current_user(request: Request) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    with SessionLocal() as db:
        user = db.get(User, int(user_id))
        if not user or not user.is_active:
            request.session.clear()
            return None
        return user


def _require_user(request: Request) -> User | RedirectResponse:
    user = _current_user(request)
    if user is None:
        return _redirect("/mobile/login")
    return user


def _base_context(request: Request, *, user: User | None = None, active: str = "") -> dict[str, Any]:
    return {
        "request": request,
        "current_user": user,
        "active_page": active,
    }


def _render(request: Request, template_name: str, *, user: User | None = None, active: str = "", **context: Any):
    full_context = _base_context(request, user=user, active=active)
    full_context.update(context)
    return templates.TemplateResponse(request, template_name, full_context)


@app.on_event("startup")
def _startup():
    ensure_runtime_schema()


@app.get("/")
def root():
    return _redirect("/mobile")


@app.get("/mobile/")
@app.get("/mobile")
def mobile_home(request: Request):
    user = _require_user(request)
    if isinstance(user, RedirectResponse):
        return user

    with SessionLocal() as db:
        car_count = db.query(Car).count()
        client_count = db.query(Client).count()
        rooms = list_rooms_for_user(db, user.id)
        chat_count = len(rooms)
        recent_cars = (
            db.query(Car)
            .options(joinedload(Car.brand), joinedload(Car.model))
            .order_by(Car.created_at.desc(), Car.id.desc())
            .limit(6)
            .all()
        )
        recent_clients = db.query(Client).order_by(Client.created_at.desc(), Client.id.desc()).limit(6).all()

    return _render(
        request,
        "dashboard.html",
        user=user,
        active="dashboard",
        car_count=car_count,
        client_count=client_count,
        chat_count=chat_count,
        recent_cars=recent_cars,
        recent_clients=recent_clients,
    )


@app.get("/mobile/login")
def mobile_login_page(request: Request):
    user = _current_user(request)
    if user is not None:
        return _redirect("/mobile")
    return _render(request, "login.html")


@app.post("/mobile/login")
def mobile_login(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
):
    ok, user, message = try_login(login, password)
    if not ok or user is None:
        return _render(request, "login.html", error=message, login_value=login)

    request.session["user_id"] = int(user.id)
    return _redirect("/mobile")


@app.post("/mobile/logout")
def mobile_logout(request: Request):
    request.session.clear()
    return _redirect("/mobile/login")


@app.get("/mobile/cars")
def mobile_cars(request: Request, q: str = Query(default="")):
    user = _require_user(request)
    if isinstance(user, RedirectResponse):
        return user

    with SessionLocal() as db:
        query = (
            db.query(Car)
            .options(joinedload(Car.brand), joinedload(Car.model), joinedload(Car.client))
            .order_by(Car.created_at.desc(), Car.id.desc())
        )
        search = q.strip()
        if search:
            like = f"%{search}%"
            query = query.outerjoin(Client, Client.id == Car.client_id).filter(
                or_(
                    Car.vin.ilike(like),
                    Car.status.ilike(like),
                    Car.deal_status.ilike(like),
                    Client.full_name.ilike(like),
                )
            )
        cars = query.limit(60).all()

    return _render(request, "cars.html", user=user, active="cars", cars=cars, search=q)


@app.get("/mobile/clients")
def mobile_clients(request: Request, q: str = Query(default="")):
    user = _require_user(request)
    if isinstance(user, RedirectResponse):
        return user

    with SessionLocal() as db:
        query = db.query(Client).order_by(Client.created_at.desc(), Client.id.desc())
        search = q.strip()
        if search:
            like = f"%{search}%"
            query = query.filter(
                or_(
                    Client.full_name.ilike(like),
                    Client.phone.ilike(like),
                    Client.email.ilike(like),
                    Client.registration_address.ilike(like),
                )
            )
        clients = query.limit(60).all()

    return _render(request, "clients.html", user=user, active="clients", clients=clients, search=q)


@app.get("/mobile/chat")
def mobile_chat(request: Request, room_id: int | None = Query(default=None)):
    user = _require_user(request)
    if isinstance(user, RedirectResponse):
        return user

    with SessionLocal() as db:
        ensure_general_room(db, created_by_user_id=user.id)
        rooms = list_rooms_for_user(db, user.id)
        selected_room = None
        if rooms:
            if room_id is None:
                selected_room = rooms[0]
            else:
                selected_room = next((room for room in rooms if room.id == room_id), rooms[0])
            room_id = selected_room.id
            messages = list_messages(db, room_id)
            last_message_id = messages[-1].id if messages else None
            mark_room_read(db, room_id, user.id, last_message_id)
        else:
            messages = []

    return _render(
        request,
        "chat.html",
        user=user,
        active="chat",
        rooms=rooms,
        selected_room_id=room_id,
        selected_room=selected_room,
        messages=messages,
    )


@app.get("/mobile/api/chat/messages")
def mobile_chat_messages(request: Request, room_id: int = Query(...)):
    user = _require_user(request)
    if isinstance(user, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    with SessionLocal() as db:
        rooms = list_rooms_for_user(db, user.id)
        if not any(room.id == room_id for room in rooms):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        messages = list_messages(db, room_id)
        last_message_id = messages[-1].id if messages else None
        mark_room_read(db, room_id, user.id, last_message_id)

    payload = [
        {
            "id": int(message.id),
            "author": "Система"
            if message.is_system
            else ((message.user.full_name or message.user.login) if message.user else "Сотрудник"),
            "body": message.body,
            "created_at": message.created_at.strftime("%d.%m.%Y %H:%M") if message.created_at else "",
        }
        for message in messages
    ]
    return JSONResponse({"messages": payload})


@app.post("/mobile/chat/send")
def mobile_chat_send(
    request: Request,
    room_id: int = Form(...),
    body: str = Form(...),
):
    user = _require_user(request)
    if isinstance(user, RedirectResponse):
        return user

    try:
        with SessionLocal() as db:
            send_message(db, room_id, user.id, body)
    except Exception as exc:
        return _render(
            request,
            "chat.html",
            user=user,
            active="chat",
            rooms=[],
            selected_room_id=room_id,
            selected_room=None,
            messages=[],
            error=str(exc),
        )
    return _redirect(f"/mobile/chat?room_id={room_id}")


@app.get("/mobile/calculator")
def mobile_calculator(request: Request):
    user = _require_user(request)
    if isinstance(user, RedirectResponse):
        return user

    initial = {
        "production_date": (dt.date.today() - dt.timedelta(days=365 * 3)).isoformat(),
        "clearance_date": dt.date.today().isoformat(),
        "age_override": "",
        "purchase_price": "0",
        "purchase_currency": "USD",
        "auction_fee": "0",
        "auction_currency": "JPY",
        "export_fee": "0",
        "export_currency": "JPY",
        "delivery_to_border": "0",
        "delivery_currency": "USD",
        "broker_fee": "0",
        "sbkts_fee": "0",
        "epts_fee": "0",
        "glonass_fee": "0",
        "logistics_fee": "0",
        "company_fee": "0",
        "other_fee": "0",
        "engine_cc": "0",
        "horsepower": "0",
    }
    return _render(request, "calculator.html", user=user, active="calculator", form_data=initial, result=None)


@app.post("/mobile/calculator")
def mobile_calculator_calculate(
    request: Request,
    production_date: str = Form(...),
    clearance_date: str = Form(...),
    age_override: str = Form(default=""),
    purchase_price: str = Form(default="0"),
    purchase_currency: str = Form(default="USD"),
    auction_fee: str = Form(default="0"),
    auction_currency: str = Form(default="JPY"),
    export_fee: str = Form(default="0"),
    export_currency: str = Form(default="JPY"),
    delivery_to_border: str = Form(default="0"),
    delivery_currency: str = Form(default="USD"),
    broker_fee: str = Form(default="0"),
    sbkts_fee: str = Form(default="0"),
    epts_fee: str = Form(default="0"),
    glonass_fee: str = Form(default="0"),
    logistics_fee: str = Form(default="0"),
    company_fee: str = Form(default="0"),
    other_fee: str = Form(default="0"),
    engine_cc: str = Form(default="0"),
    horsepower: str = Form(default="0"),
):
    user = _require_user(request)
    if isinstance(user, RedirectResponse):
        return user

    form_data = {
        "production_date": production_date,
        "clearance_date": clearance_date,
        "age_override": age_override,
        "purchase_price": purchase_price,
        "purchase_currency": purchase_currency,
        "auction_fee": auction_fee,
        "auction_currency": auction_currency,
        "export_fee": export_fee,
        "export_currency": export_currency,
        "delivery_to_border": delivery_to_border,
        "delivery_currency": delivery_currency,
        "broker_fee": broker_fee,
        "sbkts_fee": sbkts_fee,
        "epts_fee": epts_fee,
        "glonass_fee": glonass_fee,
        "logistics_fee": logistics_fee,
        "company_fee": company_fee,
        "other_fee": other_fee,
        "engine_cc": engine_cc,
        "horsepower": horsepower,
    }

    try:
        rates = _get_all_rates()
        calc_input = CalculationInput(
            purchase_price=MoneyAmount(_money_or_zero(purchase_price), purchase_currency),
            auction_fee=MoneyAmount(_money_or_zero(auction_fee), auction_currency),
            export_fee=MoneyAmount(_money_or_zero(export_fee), export_currency),
            delivery_to_border=MoneyAmount(_money_or_zero(delivery_to_border), delivery_currency),
            broker_fee=MoneyAmount(_money_or_zero(broker_fee), "RUB"),
            sbkts_fee=MoneyAmount(_money_or_zero(sbkts_fee), "RUB"),
            epts_fee=MoneyAmount(_money_or_zero(epts_fee), "RUB"),
            glonass_fee=MoneyAmount(_money_or_zero(glonass_fee), "RUB"),
            logistics_fee=MoneyAmount(_money_or_zero(logistics_fee), "RUB"),
            company_fee=MoneyAmount(_money_or_zero(company_fee), "RUB"),
            other_fee=MoneyAmount(_money_or_zero(other_fee), "RUB"),
            engine_cc=_to_int(engine_cc),
            horsepower=_to_int(horsepower),
            production_date=_to_date(production_date),
            clearance_date=_to_date(clearance_date),
            age_override=age_override or None,
        )
        result = calculate_import_cost(calc_input, lambda code: rates.get(code.upper(), Decimal("0")))
        result_view = {
            "age_label": result.age_label,
            "euro_rate": f"{result.euro_rate:,.4f} ₽".replace(",", " "),
            "pre_border": format_rub(result.pre_border_rub),
            "customs_value": f"{format_rub(result.customs_value_rub)} / {result.customs_value_eur:,.2f} €".replace(",", " "),
            "duty": f"{format_rub(result.duty_rub)} / {result.duty_eur:,.2f} €".replace(",", " "),
            "customs_fee": format_rub(result.customs_fee_rub),
            "util_fee": format_rub(result.util_fee_rub),
            "local_costs": format_rub(result.local_costs_rub),
            "total": format_rub(result.total_rub),
            "duty_rule": result.duty_rule,
        }
        return _render(
            request,
            "calculator.html",
            user=user,
            active="calculator",
            form_data=form_data,
            result=result_view,
            age_options=[
                ("", "Определять по датам"),
                (AGE_UNDER_3, "До 3 лет"),
                (AGE_3_TO_5, "От 3 до 5 лет"),
                (AGE_OVER_5, "Старше 5 лет"),
            ],
        )
    except Exception as exc:
        return _render(
            request,
            "calculator.html",
            user=user,
            active="calculator",
            form_data=form_data,
            result=None,
            error=str(exc),
            age_options=[
                ("", "Определять по датам"),
                (AGE_UNDER_3, "До 3 лет"),
                (AGE_3_TO_5, "От 3 до 5 лет"),
                (AGE_OVER_5, "Старше 5 лет"),
            ],
        )


@app.get("/mobile/health")
def mobile_health():
    return {"status": "ok"}
