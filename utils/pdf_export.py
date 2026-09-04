from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from typing import Iterable

from PyQt6.QtCore import QMarginsF, QUrl
from PyQt6.QtGui import QPageLayout, QPageSize, QTextDocument
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtWidgets import QApplication
from sqlalchemy.orm import joinedload, selectinload

from db import SessionLocal
from models import Car, CarMedia, CarOption, Client, Deal, DealStageHistory

PKG_ROOT = Path(__file__).resolve().parents[1]


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _escape(value, fallback: str = "—") -> str:
    if _is_blank(value):
        return fallback
    return escape(str(value))


def _html_multiline(value, fallback: str = "—") -> str:
    if _is_blank(value):
        return fallback
    return "<br/>".join(escape(part) for part in str(value).splitlines() if part.strip()) or fallback


def _fmt_date(value) -> str:
    if not value:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return escape(str(value))


def _fmt_datetime(value) -> str:
    if not value:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return escape(str(value))


def _to_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _fmt_money(value, currency: str = "₽") -> str:
    amount = _to_decimal(value)
    if amount is None:
        return "—"
    amount = amount.quantize(Decimal("0.01"))
    if amount == amount.to_integral():
        text = f"{int(amount):,}".replace(",", " ")
    else:
        text = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{text} {currency}".strip()


def _fmt_int(value, suffix: str = "") -> str:
    if value is None or value == "":
        return "—"
    try:
        number = int(value)
    except (ValueError, TypeError):
        return escape(str(value))
    return f"{number:,}".replace(",", " ") + (f" {suffix}" if suffix else "")


def _join_nonempty(values: Iterable[object], sep: str = " • ") -> str:
    parts = [str(v).strip() for v in values if not _is_blank(v)]
    return sep.join(parts) if parts else "—"


def _has_any(values: Iterable[object]) -> bool:
    return any(not _is_blank(value) for value in values)


def _chip(label: object, tone: str = "default") -> str:
    if _is_blank(label):
        return ""
    return f'<span class="chip {tone}">{escape(str(label))}</span>'


def _priority_chip(priority: object) -> str:
    value = str(priority or "").strip().lower()
    label_map = {
        "low": "Низкий",
        "normal": "Обычный",
        "medium": "Обычный",
        "high": "Высокий",
        "urgent": "Срочный",
    }
    tone_map = {
        "low": "mint",
        "normal": "default",
        "medium": "default",
        "high": "sand",
        "urgent": "rose",
    }
    return _chip(label_map.get(value, str(priority or "Приоритет")), tone_map.get(value, "default"))


def _status_chip(label: object) -> str:
    return _chip(label, "blue")


def _archive_chip(is_archived: bool) -> str:
    return _chip("В архиве" if is_archived else "В работе", "slate" if is_archived else "mint")


def _resolve_media_path(file_path: str | None) -> Path | None:
    if _is_blank(file_path):
        return None
    candidate = Path(str(file_path))
    options = []
    if candidate.is_absolute():
        options.append(candidate)
    else:
        options.append(PKG_ROOT / candidate)
        options.append(candidate)
    for path in options:
        if path.exists():
            return path.resolve()
    return None


def _first_image_uri(media_items: list[CarMedia]) -> str | None:
    for media in media_items:
        if str(getattr(media, "media_type", "")).lower() != "image":
            continue
        path = _resolve_media_path(media.file_path)
        if path:
            return path.as_uri()
    return None


def _info_table(rows: list[tuple[str, str]]) -> str:
    body = "".join(
        f"""
        <tr>
            <td class="label">{escape(label)}</td>
            <td class="value">{value}</td>
        </tr>
        """
        for label, value in rows
    )
    return f'<table class="info-table" width="100%" cellspacing="0" cellpadding="0">{body}</table>'


def _section(title: str, body_html: str, subtitle: str | None = None) -> str:
    subtitle_html = f'<div class="section-subtitle">{escape(subtitle)}</div>' if subtitle else ""
    return f"""
    <div class="section">
        <div class="section-head">
            <div class="section-title">{escape(title)}</div>
            {subtitle_html}
        </div>
        <div class="section-body">
            {body_html}
        </div>
    </div>
    """


def _list_block(items: list[str], empty_text: str) -> str:
    if not items:
        return f'<div class="empty-box">{escape(empty_text)}</div>'
    rows = "".join(f'<div class="bullet-item">{item}</div>' for item in items)
    return f'<div class="bullet-list">{rows}</div>'


def _comment_cards(items: list[tuple[str, object, str]], empty_text: str) -> str:
    if not items:
        return f'<div class="empty-box">{escape(empty_text)}</div>'
    cards = []
    for source, created_at, body in items:
        cards.append(
            f"""
            <div class="timeline-card">
                <div class="timeline-meta">
                    <span class="meta-badge">{escape(source)}</span>
                    <span class="muted">{_fmt_datetime(created_at)}</span>
                </div>
                <div class="timeline-text">{_html_multiline(body)}</div>
            </div>
            """
        )
    return "".join(cards)


def _stage_history_cards(items: list[DealStageHistory], empty_text: str) -> str:
    if not items:
        return f'<div class="empty-box">{escape(empty_text)}</div>'
    rows = []
    for entry in items:
        stage_name = getattr(getattr(entry, "stage", None), "name", None) or "Этап не указан"
        user_name = getattr(getattr(entry, "user", None), "full_name", None) or getattr(
            getattr(entry, "user", None), "login", None
        )
        note = getattr(entry, "note", None)
        rows.append(
            f"""
            <div class="timeline-card">
                <div class="timeline-meta">
                    <span class="meta-badge">{escape(stage_name)}</span>
                    <span class="muted">{_fmt_datetime(entry.changed_at)}</span>
                </div>
                <div class="timeline-text">
                    {_escape(user_name, "Сотрудник не указан")}
                    {"<br/><span class=\"muted\">" + _html_multiline(note) + "</span>" if note else ""}
                </div>
            </div>
            """
        )
    return "".join(rows)


def _build_pdf_html(
    car: Car,
    deal: Deal | None,
    media_items: list[CarMedia],
    option_names: list[str],
    stage_history: list[DealStageHistory],
) -> str:
    client = car.client
    manager = getattr(deal, "responsible_user", None) or car.responsible_user or getattr(client, "responsible_user", None)
    manager_name = getattr(manager, "full_name", None) or getattr(manager, "login", None)
    client_name = getattr(client, "full_name", None)
    title = _join_nonempty(
        [
            getattr(car.brand, "name", None),
            getattr(car.model, "name", None),
            getattr(car.trim, "name", None),
        ],
        sep=" ",
    )
    subtitle = _join_nonempty(
        [
            _fmt_date(car.build_date) if car.build_date else None,
            getattr(car.color, "name", None),
            getattr(car.body_type, "name", None),
        ]
    )
    current_stage = (
        getattr(getattr(deal, "deal_stage", None), "name", None)
        or getattr(getattr(car, "deal_stage", None), "name", None)
        or "Этап не указан"
    )
    lead_source = getattr(deal, "lead_source", None) or car.lead_source or getattr(client, "lead_source", None)
    priority_html = _priority_chip(getattr(deal, "priority", None) or car.priority or getattr(client, "priority", None))
    hero_total = car.price_customer if car.price_customer is not None else car.price_to_vladivostok
    hero_total_label = "Стоимость для клиента" if car.price_customer is not None else "Цена до Владивостока"
    image_uri = _first_image_uri(media_items)

    finance_rows = [
        ("Цена покупки", _fmt_money(car.purchase_price, car.purchase_currency or "₽")),
        ("Прочие расходы", _fmt_money(car.other_costs)),
        ("Цена до Владивостока", _fmt_money(car.price_to_vladivostok)),
        ("Стоимость для клиента", _fmt_money(car.price_customer)),
    ]

    car_rows = [
        ("VIN", _escape(car.vin)),
        ("Марка / модель", _escape(title)),
        ("Комплектация", _escape(getattr(car.trim, "name", None))),
        ("Дата выпуска", _fmt_date(car.build_date)),
        ("Объём двигателя", _fmt_int(car.engine_cc, "см3")),
        ("Мощность", _fmt_int(car.horsepower, "л.с.")),
        ("Пробег", _fmt_int(car.mileage_km, "км")),
        ("Топливо", _escape(getattr(car.fuel_type, "name", None))),
        ("Коробка", _escape(getattr(car.transmission, "name", None))),
        ("Привод", _escape(car.drive)),
        ("Цвет", _escape(getattr(car.color, "name", None))),
        ("Локация", _escape(_join_nonempty([car.location_country, car.location_city, car.location_note], sep=", "))),
        ("Рынок", _escape(car.market)),
        ("Статус авто", _escape(car.status)),
    ]

    client_rows = [
        ("Клиент", _escape(client_name)),
        ("Телефон", _escape(getattr(client, "phone", None))),
        ("Email", _escape(getattr(client, "email", None))),
        ("Дата рождения", _fmt_date(getattr(client, "date_of_birth", None))),
        ("Паспорт", _escape(getattr(client, "passport_no", None))),
        ("Кем выдан", _escape(getattr(client, "passport_issuer", None))),
        ("Дата выдачи", _fmt_date(getattr(client, "passport_issue_date", None))),
        ("Код подразделения", _escape(getattr(client, "passport_division_code", None))),
        ("СНИЛС", _escape(getattr(client, "snils", None))),
        ("ИНН", _escape(getattr(client, "inn", None))),
        ("Адрес регистрации", _html_multiline(getattr(client, "registration_address", None))),
    ]

    deal_rows = [
        ("Название сделки", _escape(getattr(deal, "title", None) or title)),
        ("Этап", _escape(current_stage)),
        ("Статус сделки", _escape(getattr(deal, "deal_status", None) or car.deal_status)),
        ("Менеджер", _escape(manager_name)),
        ("Источник лида", _escape(lead_source)),
        ("План прибытия", _fmt_date(getattr(deal, "expected_arrival_date", None) or car.expected_arrival_date)),
        ("Следующее действие", _fmt_date(getattr(deal, "next_action_date", None) or car.next_action_date)),
        (
            "Комментарий к следующему шагу",
            _html_multiline(getattr(deal, "next_action_note", None) or car.next_action_note),
        ),
        ("Причина блокировки", _html_multiline(getattr(deal, "blocked_reason", None) or car.blocked_reason)),
        ("Заметки", _html_multiline(getattr(deal, "notes", None) or car.notes)),
    ]

    document_rows = [
        ("PTS / ПТС", _escape(car.pts_number)),
        ("Таможенная декларация", _escape(car.customs_decl_no)),
        ("СБКТС", _escape(car.sbkts_no)),
        ("Клиент", _escape(client_name)),
        ("ID автомобиля", _escape(car.id)),
        ("ID сделки", _escape(getattr(deal, "id", None))),
    ]

    specs_rows = [
        ("Длина", _fmt_int(car.length_mm, "мм")),
        ("Ширина", _fmt_int(car.width_mm, "мм")),
        ("Высота", _fmt_int(car.height_mm, "мм")),
        ("Колёсная база", _fmt_int(car.wheelbase_mm, "мм")),
        ("Клиренс", _fmt_int(car.ground_clearance_mm, "мм")),
        ("Снаряжённая масса", _fmt_int(car.curb_weight_kg, "кг")),
        ("Разгон 0-100", _escape(f"{car.accel_0_100_s} с" if car.accel_0_100_s is not None else None)),
        ("Макс. скорость", _fmt_int(car.max_speed_kmh, "км/ч")),
        ("Колёса", _escape(car.wheel_size)),
        ("Шины перед", _escape(car.tire_front)),
        ("Шины зад", _escape(car.tire_rear)),
    ]

    task_items = []
    all_tasks = list(getattr(deal, "tasks", []) or []) + list(car.tasks or [])
    all_tasks.sort(key=lambda item: (item.is_done, item.due_date or date.max, item.created_at or datetime.max))
    for task in all_tasks[:8]:
        task_items.append(
            f"<strong>{_escape(task.title)}</strong> "
            f"<span class=\"muted\">• {_fmt_date(task.due_date)} • "
            f"{'Готово' if task.is_done else 'В работе'}</span>"
            f"{('<br/>' + _html_multiline(task.notes)) if task.notes else ''}"
        )

    comments = []
    for comment in list(getattr(deal, "comments", []) or [])[:6]:
        comments.append(("Сделка", comment.created_at, comment.body))
    for comment in list(car.comments or [])[:6]:
        comments.append(("Автомобиль", comment.created_at, comment.body))
    comments.sort(key=lambda item: item[1] or datetime.min, reverse=True)
    comments = comments[:8]

    option_html = (
        "".join(f'<span class="chip mint">{escape(name)}</span>' for name in option_names)
        if option_names
        else '<div class="empty-box">Комплектация и опции пока не заполнены.</div>'
    )

    summary_chips = "".join(
        chip
        for chip in [
            _status_chip(current_stage),
            _status_chip(getattr(deal, "deal_status", None) or car.deal_status),
            _archive_chip(bool(getattr(deal, "is_archived", False) or getattr(car, "is_archived", False))),
            priority_html,
        ]
        if chip
    )

    image_block = (
        f'<img class="cover-photo" src="{image_uri}" alt="Фото автомобиля"/>'
        if image_uri
        else """
        <div class="cover-placeholder">
            <div class="cover-placeholder-title">ShukCar</div>
            <div class="cover-placeholder-text">Фото автомобиля не добавлено</div>
        </div>
        """
    )

    optional_sections = []
    if _has_any(
        [
            car.length_mm,
            car.width_mm,
            car.height_mm,
            car.wheelbase_mm,
            car.ground_clearance_mm,
            car.curb_weight_kg,
            car.accel_0_100_s,
            car.max_speed_kmh,
            car.wheel_size,
            car.tire_front,
            car.tire_rear,
        ]
    ):
        optional_sections.append(_section("Технические параметры", _info_table(specs_rows)))

    optional_sections.append(_section("Комплектация и опции", f'<div class="chip-cloud">{option_html}</div>'))
    optional_sections.append(_section("Рабочие задачи", _list_block(task_items, "Активные задачи пока не добавлены.")))
    optional_sections.append(_section("Комментарии и наблюдения", _comment_cards(comments, "Комментарии пока не добавлены.")))
    optional_sections.append(
        _section(
            "История этапов",
            _stage_history_cards(stage_history[:8], "История этапов пока не зафиксирована."),
        )
    )

    generated_at = datetime.now().strftime("%d.%m.%Y %H:%M")
    report_code = f"CAR-{car.id}"

    return f"""
    <html>
    <head>
        <meta charset="utf-8"/>
        <style>
            body {{
                font-family: "Segoe UI", Arial, sans-serif;
                color: #1f2937;
                font-size: 10pt;
                line-height: 1.35;
                margin: 0;
            }}
            .page {{ padding: 6px; }}
            .header {{
                background: #24313f;
                color: #ffffff;
                border: 1px solid #24313f;
                padding: 16px 18px;
                margin-bottom: 14px;
            }}
            .brand {{
                font-size: 20pt;
                font-weight: 700;
                letter-spacing: 0.2px;
            }}
            .header-table, .hero-table, .summary-table, .grid {{
                width: 100%;
            }}
            .header-left {{ width: 60%; }}
            .header-right {{
                width: 40%;
                text-align: right;
            }}
            .header-kicker {{
                font-size: 8pt;
                letter-spacing: 1.8px;
                text-transform: uppercase;
                color: #b9c8d6;
            }}
            .header-meta {{
                font-size: 9pt;
                color: #d7e1ea;
                margin-top: 6px;
            }}
            .hero {{
                background: #eef4f8;
                border: 1px solid #d8e3ec;
                padding: 16px;
                margin-bottom: 14px;
            }}
            .hero-cover {{
                width: 34%;
                padding-right: 14px;
                vertical-align: top;
            }}
            .hero-summary {{
                width: 66%;
                vertical-align: top;
            }}
            .cover-photo {{
                width: 100%;
                max-height: 260px;
                border: 1px solid #ccd8e2;
                background: #ffffff;
            }}
            .cover-placeholder {{
                height: 248px;
                border: 1px solid #ccd8e2;
                background: #dfe8ee;
                text-align: center;
                color: #425466;
            }}
            .cover-placeholder-title {{
                font-size: 22pt;
                font-weight: 700;
                padding-top: 78px;
            }}
            .cover-placeholder-text {{
                font-size: 9pt;
                margin-top: 8px;
            }}
            .eyebrow {{
                font-size: 8pt;
                letter-spacing: 1.6px;
                text-transform: uppercase;
                color: #607287;
            }}
            .hero-title {{
                font-size: 22pt;
                font-weight: 700;
                color: #142334;
                margin-top: 6px;
            }}
            .hero-subtitle {{
                font-size: 10pt;
                color: #5f7287;
                margin-top: 4px;
            }}
            .chip-row {{
                margin-top: 12px;
                margin-bottom: 12px;
            }}
            .chip {{
                display: inline-block;
                border: 1px solid #cfdae4;
                background: #ffffff;
                color: #233141;
                padding: 4px 9px;
                margin-right: 6px;
                margin-bottom: 6px;
                font-size: 8.5pt;
            }}
            .chip.blue {{ background: #dfeaf1; border-color: #c1d3df; }}
            .chip.mint {{ background: #e6f3ee; border-color: #c7ddd4; }}
            .chip.rose {{ background: #f6e7e8; border-color: #e4c8cb; }}
            .chip.sand {{ background: #f5efe2; border-color: #e2d6bb; }}
            .chip.slate {{ background: #e8edf1; border-color: #d4dde4; }}
            .summary-card {{
                width: 50%;
                border: 1px solid #d6e0e8;
                background: #ffffff;
                padding: 10px 12px;
                vertical-align: top;
            }}
            .summary-gap {{ width: 12px; }}
            .summary-label {{
                font-size: 8pt;
                color: #6b7c8f;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            .summary-main {{
                font-size: 11pt;
                font-weight: 700;
                color: #17293b;
                margin-top: 4px;
            }}
            .summary-big {{
                font-size: 18pt;
                font-weight: 800;
                color: #193149;
                margin-top: 4px;
            }}
            .summary-note {{
                font-size: 9pt;
                color: #5e7387;
                margin-top: 4px;
            }}
            .grid {{
                border-collapse: collapse;
            }}
            .grid td {{
                width: 50%;
                vertical-align: top;
                padding-bottom: 12px;
            }}
            .grid .left {{ padding-right: 6px; }}
            .grid .right {{ padding-left: 6px; }}
            .section {{
                border: 1px solid #d9e2ea;
                background: #fbfdfe;
                margin-bottom: 12px;
            }}
            .section-head {{
                background: #eff4f8;
                border-bottom: 1px solid #d9e2ea;
                padding: 10px 12px 9px 12px;
            }}
            .section-title {{
                font-size: 10pt;
                font-weight: 700;
                color: #203245;
            }}
            .section-subtitle {{
                font-size: 8.5pt;
                color: #6c7d90;
                margin-top: 2px;
            }}
            .section-body {{ padding: 10px 12px 12px 12px; }}
            .info-table {{
                width: 100%;
                border-collapse: collapse;
            }}
            .info-table td {{
                padding: 6px 0;
                border-bottom: 1px solid #edf2f6;
                vertical-align: top;
            }}
            .label {{
                width: 38%;
                color: #6a7a8c;
                padding-right: 14px;
            }}
            .value {{
                color: #182838;
                font-weight: 600;
            }}
            .chip-cloud {{ line-height: 2.2; }}
            .bullet-item, .timeline-card {{
                border: 1px solid #e0e8ef;
                background: #ffffff;
                padding: 9px 10px;
                margin-bottom: 8px;
            }}
            .timeline-meta {{ margin-bottom: 5px; }}
            .timeline-text {{ color: #223244; }}
            .meta-badge {{
                display: inline-block;
                padding: 2px 7px;
                background: #edf3f7;
                border: 1px solid #d7e2eb;
                font-size: 8pt;
                margin-right: 8px;
            }}
            .empty-box {{
                border: 1px solid #dde6ee;
                background: #f8fbfd;
                color: #6c7d90;
                padding: 12px;
            }}
            .muted {{ color: #6c7d90; }}
            .footer {{
                margin-top: 14px;
                padding: 12px 14px;
                border: 1px solid #d9e2ea;
                background: #f4f8fb;
                font-size: 8.8pt;
                color: #57697c;
            }}
        </style>
    </head>
    <body>
        <div class="page">
            <div class="header">
                <table class="header-table" cellspacing="0" cellpadding="0">
                    <tr>
                        <td class="header-left">
                            <div class="header-kicker">ShukCar Auto Import</div>
                            <div class="brand">Отчёт по автомобилю и сделке</div>
                            <div class="header-meta">Документ для контроля сделки, клиента и ключевых параметров автомобиля.</div>
                        </td>
                        <td class="header-right">
                            <div class="header-meta">Отчёт: {escape(report_code)}</div>
                            <div class="header-meta">Сформирован: {escape(generated_at)}</div>
                            <div class="header-meta">Статус: {_escape(getattr(deal, "deal_status", None) or car.deal_status, "Не указан")}</div>
                        </td>
                    </tr>
                </table>
            </div>

            <div class="hero">
                <table class="hero-table" cellspacing="0" cellpadding="0">
                    <tr>
                        <td class="hero-cover">{image_block}</td>
                        <td class="hero-summary">
                            <div class="eyebrow">Карточка сделки</div>
                            <div class="hero-title">{_escape(title, "Автомобиль без названия")}</div>
                            <div class="hero-subtitle">{_escape(subtitle, "Дата выпуска, цвет и кузов будут отображаться здесь")}</div>
                            <div class="chip-row">{summary_chips}</div>

                            <table class="summary-table" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td class="summary-card">
                                        <div class="summary-label">Клиент</div>
                                        <div class="summary-main">{_escape(client_name, "Клиент не выбран")}</div>
                                        <div class="summary-note">{_escape(lead_source, "Источник не указан")}</div>
                                    </td>
                                    <td class="summary-gap"></td>
                                    <td class="summary-card">
                                        <div class="summary-label">{escape(hero_total_label)}</div>
                                        <div class="summary-big">{_fmt_money(hero_total)}</div>
                                        <div class="summary-note">{_escape(manager_name, "Менеджер не назначен")}</div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </div>

            <table class="grid" cellspacing="0" cellpadding="0">
                <tr>
                    <td class="left">
                        {_section("Контроль сделки", _info_table(deal_rows), "Основной статус, следующий шаг и рабочие заметки")}
                    </td>
                    <td class="right">
                        {_section("Финансы", _info_table(finance_rows), "Ориентиры по закупке, расходам и цене для клиента")}
                    </td>
                </tr>
                <tr>
                    <td class="left">
                        {_section("Автомобиль", _info_table(car_rows), "Технические и логистические данные по машине")}
                    </td>
                    <td class="right">
                        {_section("Клиент", _info_table(client_rows), "Контактные данные и реквизиты клиента")}
                    </td>
                </tr>
                <tr>
                    <td class="left">
                        {_section("Документы и идентификаторы", _info_table(document_rows))}
                    </td>
                    <td class="right">
                        {_section(
                            "Ключевые ориентиры",
                            _info_table(
                                [
                                    ("Этап сделки", _escape(current_stage)),
                                    ("Архив", _escape("Да" if getattr(deal, "is_archived", False) or getattr(car, "is_archived", False) else "Нет")),
                                    ("Приоритет", _escape((str(getattr(deal, "priority", None) or car.priority or getattr(client, "priority", None) or "normal")).upper())),
                                    ("Ответственный", _escape(manager_name)),
                                    ("План прибытия", _fmt_date(getattr(deal, "expected_arrival_date", None) or car.expected_arrival_date)),
                                    ("VIN", _escape(car.vin)),
                                ]
                            ),
                        )}
                    </td>
                </tr>
            </table>

            {"".join(optional_sections)}

            <div class="footer">
                Отчёт сформирован автоматически системой ShukCar. Документ предназначен для внутренней работы:
                контроль сделки, подготовка к коммуникации с клиентом, сверка статусов, документов, задач и бюджета.
            </div>
        </div>
    </body>
    </html>
    """


def export_car_pdf(car_id: int, output_path: str) -> None:
    app = QApplication.instance()
    created_app = False
    if app is None:
        app = QApplication([])
        created_app = True

    with SessionLocal() as session:
        car = (
            session.query(Car)
            .options(
                joinedload(Car.brand),
                joinedload(Car.model),
                joinedload(Car.trim),
                joinedload(Car.body_type),
                joinedload(Car.fuel_type),
                joinedload(Car.transmission),
                joinedload(Car.color),
                joinedload(Car.responsible_user),
                joinedload(Car.deal_stage),
                joinedload(Car.client).joinedload(Client.responsible_user),
                selectinload(Car.tasks),
                selectinload(Car.comments),
                selectinload(Car.stage_history).joinedload(DealStageHistory.stage),
                selectinload(Car.stage_history).joinedload(DealStageHistory.user),
                selectinload(Car.deals).joinedload(Deal.client),
                selectinload(Car.deals).joinedload(Deal.responsible_user),
                selectinload(Car.deals).joinedload(Deal.deal_stage),
                selectinload(Car.deals).selectinload(Deal.tasks),
                selectinload(Car.deals).selectinload(Deal.comments),
            )
            .filter(Car.id == car_id)
            .first()
        )
        if not car:
            raise ValueError(f"Автомобиль с ID {car_id} не найден.")

        media_items = (
            session.query(CarMedia)
            .filter(CarMedia.car_id == car.id)
            .order_by(CarMedia.id.asc())
            .all()
        )
        option_rows = (
            session.query(CarOption)
            .options(joinedload(CarOption.option))
            .filter(CarOption.car_id == car.id)
            .order_by(CarOption.id.asc())
            .all()
        )

        active_deals = [item for item in car.deals if not getattr(item, "is_archived", False)]
        deal = active_deals[0] if active_deals else (car.deals[0] if car.deals else None)
        option_names = [row.option.name for row in option_rows if getattr(row, "option", None) and row.option.name]
        stage_history = sorted(car.stage_history or [], key=lambda item: item.changed_at or datetime.min, reverse=True)
        html = _build_pdf_html(
            car=car,
            deal=deal,
            media_items=media_items,
            option_names=option_names,
            stage_history=stage_history,
        )

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(destination))
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageMargins(QMarginsF(10, 12, 10, 12), QPageLayout.Unit.Millimeter)

    document = QTextDocument()
    document.setDocumentMargin(24)
    document.setBaseUrl(QUrl.fromLocalFile(str(PKG_ROOT) + "/"))
    document.setHtml(html)
    document.print(printer)

    if created_app:
        app.quit()
