# ShukCar/models.py
from sqlalchemy import (
    Column, BigInteger, String, LargeBinary, Enum, Integer, DateTime, Boolean, Date,
    ForeignKey, DECIMAL, Text, UniqueConstraint
)
from sqlalchemy.dialects.mysql import BIGINT as MYSQL_BIGINT
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db import Base
import enum

# ===== Роли =====
class UserRole(str, enum.Enum):
    trainee = "trainee"
    manager = "manager"
    admin = "admin"
    user = "user"

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    login = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(LargeBinary(255), nullable=False)
    password_salt = Column(LargeBinary(64), nullable=False)
    full_name = Column(String(255), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    phone = Column(String(32))
    email = Column(String(255))
    role = Column(Enum(UserRole), nullable=False, default=UserRole.user)
    is_active = Column(Boolean, nullable=False, default=True)
    failed_attempts = Column(Integer, nullable=False, default=0)
    lock_until = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)
    last_activity = Column(DateTime, nullable=True)
    is_online = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

# ===== Справочники =====
class Brand(Base):
    __tablename__ = "brands"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True, nullable=False)

class Model(Base):
    __tablename__ = "models"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    brand_id = Column(BigInteger, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    brand = relationship("Brand")

class BodyType(Base):
    __tablename__ = "body_types"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)

class FuelType(Base):
    __tablename__ = "fuel_types"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)

class Transmission(Base):
    __tablename__ = "transmissions"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)

class Color(Base):
    __tablename__ = "colors"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)

class Trim(Base):
    __tablename__ = "trims"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    model_id = Column(BigInteger, ForeignKey("models.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    model = relationship("Model")

# ===== Курсы валют =====
class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(8), unique=True, nullable=False)
    rate_to_rub = Column(DECIMAL(18, 6), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

# ===== Пресеты статусов (текстовые) =====
class CarStatus(Base):
    __tablename__ = "car_statuses"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)

class DealStatus(Base):
    __tablename__ = "deal_statuses"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)

# ===== Этапы сделки (воронка) =====
class DealStage(Base):
    __tablename__ = "deal_stages"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    color = Column(String(16))  # опционально: HEX/имя

class DealStageHistory(Base):
    __tablename__ = "deal_stage_history"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    car_id = Column(BigInteger, ForeignKey("cars.id", ondelete="CASCADE"), nullable=False, index=True)
    stage_id = Column(BigInteger, ForeignKey("deal_stages.id", ondelete="RESTRICT"), nullable=False, index=True)
    changed_at = Column(DateTime, server_default=func.now(), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note = Column(Text)

    car = relationship("Car", back_populates="stage_history")
    stage = relationship("DealStage")
    user = relationship("User")

# ===== Клиенты =====
class Client(Base):
    __tablename__ = "clients"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(32))
    email = Column(String(255))
    passport_no = Column(String(64))
    registration_address = Column(Text)
    snils = Column(String(32))
    inn = Column(String(32))
    date_of_birth = Column(Date)
    passport_issuer = Column(String(255))
    passport_issue_date = Column(Date)
    passport_division_code = Column(String(16))
    country = Column(String(128))
    region = Column(String(128))
    city = Column(String(128))
    street = Column(String(255))
    house = Column(String(64))
    block = Column(String(64))
    flat = Column(String(64))
    postal_code = Column(String(16))
    fias_id = Column(String(64))
    kladr_id = Column(String(64))
    geo_lat = Column(DECIMAL(10, 6))
    geo_lon = Column(DECIMAL(10, 6))
    responsible_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    lead_source = Column(String(64))
    priority = Column(String(16), default="normal")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    responsible_user = relationship("User", foreign_keys=[responsible_user_id])
    deals = relationship("Deal", back_populates="client")


class Deal(Base):
    __tablename__ = "deals"

    id = Column(MYSQL_BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    client_id = Column(MYSQL_BIGINT(unsigned=True), ForeignKey("clients.id"), nullable=False, index=True)
    car_id = Column(MYSQL_BIGINT(unsigned=True), ForeignKey("cars.id"), nullable=True, index=True)
    responsible_user_id = Column(MYSQL_BIGINT(unsigned=True), ForeignKey("users.id"), nullable=True, index=True)
    deal_status = Column(String(64))
    deal_stage_id = Column(MYSQL_BIGINT(unsigned=True), ForeignKey("deal_stages.id"), nullable=True, index=True)
    lead_source = Column(String(64))
    priority = Column(String(16), default="normal")
    expected_arrival_date = Column(Date)
    next_action_date = Column(Date)
    next_action_note = Column(Text)
    blocked_reason = Column(Text)
    notes = Column(Text)
    is_archived = Column(Boolean, nullable=False, default=False)
    archived_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    client = relationship("Client", back_populates="deals")
    car = relationship("Car", back_populates="deals")
    responsible_user = relationship("User", foreign_keys=[responsible_user_id])
    deal_stage = relationship("DealStage")
    tasks = relationship("DealTask", back_populates="deal", cascade="all, delete-orphan")
    comments = relationship("DealComment", back_populates="deal", cascade="all, delete-orphan")

# ===== Автомобили =====
class Car(Base):
    __tablename__ = "cars"
    id = Column(BigInteger, primary_key=True, autoincrement=True)

    brand_id = Column(BigInteger, ForeignKey("brands.id"), nullable=False)
    model_id = Column(BigInteger, ForeignKey("models.id"), nullable=False)
    trim_id  = Column(BigInteger, ForeignKey("trims.id"))
    body_type_id = Column(BigInteger, ForeignKey("body_types.id"))
    fuel_type_id = Column(BigInteger, ForeignKey("fuel_types.id"))
    transmission_id = Column(BigInteger, ForeignKey("transmissions.id"))
    color_id = Column(BigInteger, ForeignKey("colors.id"))

    build_date = Column(Date)
    engine_cc = Column(Integer)
    horsepower = Column(Integer)
    mileage_km = Column(Integer)

    # Локация
    location_country = Column(String(128))
    location_city = Column(String(128))
    location_note = Column(Text)

    # Цена до Владивостока
    price_to_vladivostok = Column(DECIMAL(12, 2))

    # Текстовые статусы (как было)
    status = Column(String(64))
    deal_status = Column(String(64))

    # Привязка к клиенту
    client_id = Column(BigInteger, ForeignKey("clients.id"))

    # ===== Расширенные поля (добавленные) =====
    vin = Column(String(32))
    drive = Column(String(8))  # FWD/RWD/AWD/4WD
    seats = Column(Integer)
    euro_class = Column(String(16))
    cons_mix_l100 = Column(DECIMAL(4, 1))  # расход смеш.

    pts_number = Column(String(64))
    market = Column(String(16))  # JP/KR/US/EU/CN/RU
    customs_decl_no = Column(String(64))
    sbkts_no = Column(String(64))

    length_mm = Column(Integer)
    width_mm = Column(Integer)
    height_mm = Column(Integer)
    wheelbase_mm = Column(Integer)
    ground_clearance_mm = Column(Integer)
    curb_weight_kg = Column(Integer)

    accel_0_100_s = Column(DECIMAL(4, 1))
    max_speed_kmh = Column(Integer)

    wheel_size = Column(String(32))
    tire_front = Column(String(32))
    tire_rear = Column(String(32))

    purchase_currency = Column(String(8))
    purchase_price = Column(DECIMAL(12, 2))
    other_costs = Column(DECIMAL(12, 2))
    price_customer = Column(DECIMAL(12, 2))
    responsible_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    lead_source = Column(String(64))
    priority = Column(String(16), default="normal")
    expected_arrival_date = Column(Date)
    next_action_date = Column(Date)
    next_action_note = Column(Text)
    blocked_reason = Column(Text)

    notes = Column(Text)

    # Этап сделки (воронка)
    deal_stage_id = Column(BigInteger, ForeignKey("deal_stages.id"))
    is_archived = Column(Boolean, nullable=False, default=False)
    archived_at = Column(DateTime)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # --- relationships ---
    brand = relationship("Brand")
    model = relationship("Model")
    trim  = relationship("Trim")
    body_type = relationship("BodyType")
    fuel_type = relationship("FuelType")
    transmission = relationship("Transmission")
    color = relationship("Color")
    client = relationship("Client")
    responsible_user = relationship("User", foreign_keys=[responsible_user_id])
    deals = relationship("Deal", back_populates="car")

    deal_stage = relationship("DealStage")
    stage_history = relationship("DealStageHistory", back_populates="car", cascade="all, delete-orphan")
    tasks = relationship("CarTask", back_populates="car", cascade="all, delete-orphan")
    comments = relationship("CarComment", back_populates="car", cascade="all, delete-orphan")

class CarMedia(Base):
    __tablename__ = "car_media"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    car_id = Column(BigInteger, ForeignKey("cars.id", ondelete="CASCADE"), nullable=False)
    media_type = Column(Enum("image", "video", name="media_type_enum"), nullable=False)
    file_path = Column(String(1024), nullable=False)
    original_name = Column(String(255))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class CarTask(Base):
    __tablename__ = "car_tasks"

    id = Column(MYSQL_BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    car_id = Column(MYSQL_BIGINT(unsigned=True), ForeignKey("cars.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    due_date = Column(Date)
    priority = Column(String(16), nullable=False, default="normal")
    is_done = Column(Boolean, nullable=False, default=False)
    done_at = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    car = relationship("Car", back_populates="tasks")


class CarComment(Base):
    __tablename__ = "car_comments"

    id = Column(MYSQL_BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    car_id = Column(MYSQL_BIGINT(unsigned=True), ForeignKey("cars.id", ondelete="CASCADE"), nullable=False, index=True)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    car = relationship("Car", back_populates="comments")


class DealTask(Base):
    __tablename__ = "deal_tasks"

    id = Column(MYSQL_BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    deal_id = Column(MYSQL_BIGINT(unsigned=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    due_date = Column(Date)
    priority = Column(String(16), nullable=False, default="normal")
    is_done = Column(Boolean, nullable=False, default=False)
    done_at = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    deal = relationship("Deal", back_populates="tasks")


class DealComment(Base):
    __tablename__ = "deal_comments"

    id = Column(MYSQL_BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    deal_id = Column(MYSQL_BIGINT(unsigned=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    deal = relationship("Deal", back_populates="comments")


class ChatRoomType(str, enum.Enum):
    general = "general"
    direct = "direct"
    car = "car"
    client = "client"


class ChatRoom(Base):
    __tablename__ = "chat_rooms"

    id = Column(MYSQL_BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    room_type = Column(Enum(ChatRoomType), nullable=False, default=ChatRoomType.general)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    created_by_user_id = Column(MYSQL_BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    car_id = Column(MYSQL_BIGINT(unsigned=True), ForeignKey("cars.id", ondelete="CASCADE"), nullable=True)
    client_id = Column(MYSQL_BIGINT(unsigned=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    created_by = relationship("User", foreign_keys=[created_by_user_id])
    car = relationship("Car", foreign_keys=[car_id])
    client = relationship("Client", foreign_keys=[client_id])
    members = relationship("ChatRoomMember", back_populates="room", cascade="all, delete-orphan")
    messages = relationship("ChatMessage", back_populates="room", cascade="all, delete-orphan")


class ChatRoomMember(Base):
    __tablename__ = "chat_room_members"
    __table_args__ = (UniqueConstraint("room_id", "user_id", name="uq_chat_room_member"),)

    id = Column(MYSQL_BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    room_id = Column(MYSQL_BIGINT(unsigned=True), ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(MYSQL_BIGINT(unsigned=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    last_read_message_id = Column(MYSQL_BIGINT(unsigned=True), nullable=True)
    is_muted = Column(Boolean, nullable=False, default=False)
    joined_at = Column(DateTime, server_default=func.now(), nullable=False)

    room = relationship("ChatRoom", back_populates="members")
    user = relationship("User", foreign_keys=[user_id])


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(MYSQL_BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    room_id = Column(MYSQL_BIGINT(unsigned=True), ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(MYSQL_BIGINT(unsigned=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    body = Column(Text, nullable=False)
    is_system = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    edited_at = Column(DateTime)

    room = relationship("ChatRoom", back_populates="messages")
    user = relationship("User", foreign_keys=[user_id])

# ===== Журнал действий =====
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    action = Column(String(64), nullable=False)    # e.g., 'create','update','delete','login'
    entity = Column(String(64), nullable=False)    # e.g., 'car','user','client','media'
    entity_id = Column(BigInteger)
    details = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

class WatchedCurrency(Base):
    __tablename__ = "watched_currencies"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(8), unique=True, nullable=False)

# ===== Справочник опций и связь авто—опции =====
class Option(Base):
    __tablename__ = "options"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)

class CarOption(Base):
    __tablename__ = "car_options"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    car_id = Column(BigInteger, ForeignKey("cars.id", ondelete="CASCADE"), nullable=False, index=True)
    option_id = Column(BigInteger, ForeignKey("options.id", ondelete="RESTRICT"), nullable=False, index=True)

    car = relationship("Car")
    option = relationship("Option")
