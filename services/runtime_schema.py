from __future__ import annotations

from sqlalchemy import inspect, text

from db import Base, engine
import models  # noqa: F401


def _ensure_columns(table_name: str, columns: dict[str, str]):
    inspector = inspect(engine)
    existing = {col["name"] for col in inspector.get_columns(table_name)}
    missing = [(name, ddl) for name, ddl in columns.items() if name not in existing]
    if not missing:
        return

    with engine.begin() as conn:
        for name, ddl in missing:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {ddl}"))


def ensure_runtime_schema():
    Base.metadata.create_all(bind=engine)

    _ensure_columns(
        "users",
        {
            "last_login": "DATETIME NULL",
            "last_activity": "DATETIME NULL",
            "is_online": "TINYINT(1) NOT NULL DEFAULT 0",
        },
    )

    _ensure_columns(
        "clients",
        {
            "country": "VARCHAR(128) NULL",
            "region": "VARCHAR(128) NULL",
            "city": "VARCHAR(128) NULL",
            "street": "VARCHAR(255) NULL",
            "house": "VARCHAR(64) NULL",
            "block": "VARCHAR(64) NULL",
            "flat": "VARCHAR(64) NULL",
            "postal_code": "VARCHAR(16) NULL",
            "fias_id": "VARCHAR(64) NULL",
            "kladr_id": "VARCHAR(64) NULL",
            "geo_lat": "DECIMAL(10,6) NULL",
            "geo_lon": "DECIMAL(10,6) NULL",
            "responsible_user_id": "BIGINT NULL",
            "lead_source": "VARCHAR(64) NULL",
            "priority": "VARCHAR(16) NULL DEFAULT 'normal'",
        },
    )

    _ensure_columns(
        "cars",
        {
            "responsible_user_id": "BIGINT NULL",
            "lead_source": "VARCHAR(64) NULL",
            "priority": "VARCHAR(16) NULL DEFAULT 'normal'",
            "expected_arrival_date": "DATE NULL",
            "next_action_date": "DATE NULL",
            "next_action_note": "TEXT NULL",
            "blocked_reason": "TEXT NULL",
            "is_archived": "TINYINT(1) NOT NULL DEFAULT 0",
            "archived_at": "DATETIME NULL",
        },
    )

    _ensure_columns(
        "deals",
        {
            "car_id": "BIGINT UNSIGNED NULL",
            "responsible_user_id": "BIGINT UNSIGNED NULL",
            "deal_status": "VARCHAR(64) NULL",
            "deal_stage_id": "BIGINT UNSIGNED NULL",
            "lead_source": "VARCHAR(64) NULL",
            "priority": "VARCHAR(16) NULL DEFAULT 'normal'",
            "expected_arrival_date": "DATE NULL",
            "next_action_date": "DATE NULL",
            "next_action_note": "TEXT NULL",
            "blocked_reason": "TEXT NULL",
            "notes": "TEXT NULL",
            "is_archived": "TINYINT(1) NOT NULL DEFAULT 0",
            "archived_at": "DATETIME NULL",
        },
    )
