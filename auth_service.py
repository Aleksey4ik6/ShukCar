import os
import hashlib
import datetime as dt
from typing import Optional, Tuple, List

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import SessionLocal
from models import User, UserRole
from audit import log_action


LOCK_MINUTES_STEPS = [5, 10, 30, 60]


def _pbkdf2(password: str, salt: bytes, iterations: int = 200_000) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def _coerce_date(value):
    if value in (None, "", 0):
        return None
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        return dt.date.fromisoformat(value)
    raise ValueError("Некорректная дата.")


def _count_active_admins(db: Session) -> int:
    return len(
        list(
            db.execute(
                select(User).where(User.role == UserRole.admin, User.is_active == True)
            ).scalars()
        )
    )


def _ensure_not_last_active_admin(db: Session, user: User, *, removing_admin_access: bool):
    if not removing_admin_access:
        return
    if user.role == UserRole.admin and user.is_active and _count_active_admins(db) <= 1:
        raise ValueError("Нельзя оставить систему без активного администратора.")


def hash_password(password: str) -> Tuple[bytes, bytes]:
    salt = os.urandom(32)
    return _pbkdf2(password, salt), salt


def verify_password(password: str, password_hash: bytes, salt: bytes) -> bool:
    return _pbkdf2(password, salt) == password_hash


def get_user_by_login(db: Session, login: str) -> Optional[User]:
    return db.execute(select(User).where(User.login == login)).scalar_one_or_none()


def get_any_admin(db: Session) -> Optional[User]:
    return db.execute(select(User).where(User.role == UserRole.admin)).scalar_one_or_none()


def ensure_admin_exists(db: Session) -> User:
    admin = get_any_admin(db)
    if admin:
        return admin
    h, s = hash_password("Admin")
    admin = User(
        login="Admin",
        password_hash=h,
        password_salt=s,
        full_name="Администратор",
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def list_users(db: Session) -> List[User]:
    return list(db.execute(select(User).order_by(User.id.desc())).scalars())


def create_user(
    db: Session,
    *,
    login: str,
    password: str,
    full_name: str,
    date_of_birth=None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    role: UserRole = UserRole.user,
    is_active: bool = True,
) -> User:
    h, s = hash_password(password)
    user = User(
        login=login,
        password_hash=h,
        password_salt=s,
        full_name=full_name,
        date_of_birth=_coerce_date(date_of_birth),
        phone=phone,
        email=email,
        role=role,
        is_active=is_active,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("Пользователь с таким логином уже существует")
    db.refresh(user)
    log_action(db, user_id=None, action="create", entity="user", entity_id=user.id, details=f"login={login}, role={role.value}")
    return user


def update_user(db: Session, user_id: int, **fields) -> User:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("Пользователь не найден")

    new_role = fields.get("role", user.role)
    new_is_active = fields.get("is_active", user.is_active)
    removing_admin_access = (new_role != UserRole.admin) or (not bool(new_is_active))
    _ensure_not_last_active_admin(db, user, removing_admin_access=removing_admin_access)

    if "password" in fields and fields["password"]:
        h, s = hash_password(fields.pop("password"))
        user.password_hash = h
        user.password_salt = s

    for key in ["login", "full_name", "phone", "email", "role", "is_active"]:
        if key in fields and fields[key] is not None:
            setattr(user, key, fields[key])

    if "date_of_birth" in fields and fields["date_of_birth"] is not None:
        user.date_of_birth = _coerce_date(fields["date_of_birth"])

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("Логин уже используется")
    db.refresh(user)
    log_action(db, user_id=None, action="update", entity="user", entity_id=user.id, details=f"fields={list(fields.keys())}")
    return user


def delete_user(db: Session, user_id: int):
    user = db.get(User, user_id)
    if not user:
        raise ValueError("Пользователь не найден")
    _ensure_not_last_active_admin(db, user, removing_admin_access=True)
    db.delete(user)
    db.commit()
    log_action(db, user_id=None, action="delete", entity="user", entity_id=user_id)


def set_user_active(db: Session, user_id: int, is_active: bool) -> User:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("Пользователь не найден")
    _ensure_not_last_active_admin(db, user, removing_admin_access=not is_active)
    user.is_active = bool(is_active)
    db.commit()
    db.refresh(user)
    log_action(db, user_id=None, action="activate" if is_active else "deactivate", entity="user", entity_id=user.id)
    return user


def unlock_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("Пользователь не найден")
    user.failed_attempts = 0
    user.lock_until = None
    db.commit()
    db.refresh(user)
    log_action(db, user_id=None, action="unlock", entity="user", entity_id=user.id)
    return user


def reset_user_password(db: Session, user_id: int, new_password: str) -> User:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("Пользователь не найден")
    if not new_password.strip():
        raise ValueError("Новый пароль не может быть пустым.")
    h, s = hash_password(new_password)
    user.password_hash = h
    user.password_salt = s
    user.failed_attempts = 0
    user.lock_until = None
    db.commit()
    db.refresh(user)
    log_action(db, user_id=None, action="password_reset", entity="user", entity_id=user.id)
    return user


def set_user_online_status(db: Session, user_id: int, is_online: bool) -> User | None:
    user = db.get(User, user_id)
    if not user:
        return None
    user.is_online = bool(is_online)
    user.last_activity = dt.datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def record_failed_attempt(db: Session, user: User):
    user.failed_attempts += 1
    lock_until = user.lock_until
    if user.failed_attempts % 3 == 0:
        step_idx = min(user.failed_attempts // 3, len(LOCK_MINUTES_STEPS)) - 1
        minutes = LOCK_MINUTES_STEPS[step_idx]
        lock_until = dt.datetime.utcnow() + dt.timedelta(minutes=minutes)
        user.lock_until = lock_until
    user.last_activity = dt.datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user.failed_attempts, lock_until


def reset_fail_counter(db: Session, user: User):
    user.failed_attempts = 0
    user.lock_until = None
    db.commit()
    db.refresh(user)


def check_locked(user: User) -> Optional[int]:
    if user.lock_until:
        now = dt.datetime.utcnow()
        if now < user.lock_until:
            remaining = int((user.lock_until - now).total_seconds() // 60) + 1
            return remaining
    return None


def try_login(login: str, password: str):
    try:
        with SessionLocal() as db:
            if login == "Admin" and password == "Admin":
                admin = ensure_admin_exists(db)
                admin.last_login = dt.datetime.utcnow()
                admin.last_activity = dt.datetime.utcnow()
                admin.is_online = True
                db.commit()
                db.refresh(admin)
                log_action(db, user_id=admin.id, action="login", entity="user", entity_id=admin.id, details="bootstrap Admin/Admin")
                return True, admin, "Вход как Администратор."

            user = get_user_by_login(db, login)
            if not user:
                return False, None, "Неверный логин или пароль."

            if not user.is_active:
                return False, None, "Пользователь деактивирован. Обратитесь к администратору."

            remaining = check_locked(user)
            if remaining:
                return False, None, f"Ввод заблокирован. Повторите через ~{remaining} мин."

            if verify_password(password, user.password_hash, user.password_salt):
                reset_fail_counter(db, user)
                user.last_login = dt.datetime.utcnow()
                user.last_activity = dt.datetime.utcnow()
                user.is_online = True
                db.commit()
                db.refresh(user)
                log_action(db, user_id=user.id, action="login", entity="user", entity_id=user.id)
                return True, user, f"Добро пожаловать, {user.full_name}!"

            attempts, lock_until = record_failed_attempt(db, user)
            log_action(db, user_id=user.id, action="login_fail", entity="user", entity_id=user.id, details=f"attempts={attempts}")
            if lock_until and attempts % 3 == 0:
                level = min(attempts // 3, len(LOCK_MINUTES_STEPS))
                minutes = LOCK_MINUTES_STEPS[level - 1]
                return False, None, f"Неверно. Доступ заблокирован на {minutes} мин."
            return False, None, "Неверный логин или пароль."
    except Exception as exc:
        text = str(exc).strip() or exc.__class__.__name__
        if "cryptography" in text.lower():
            return False, None, (
                "MySQL требует пакет `cryptography` для авторизации.\n"
                "Установите его в виртуальное окружение и попробуйте снова."
            )
        return False, None, f"Ошибка подключения к базе данных: {text}"
