from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime, timezone, timedelta
import os

TW = timezone(timedelta(hours=8))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///travel.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(TW))
    plans = relationship("TravelPlan", back_populates="owner", cascade="all, delete-orphan")


class TravelPlan(Base):
    __tablename__ = "travel_plans"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(100), default="旅行規劃")
    locked = Column(Boolean, default=False)
    rate_krw = Column(Float, default=45.5)
    rate_jpy = Column(Float, default=4.5)
    rate_usd = Column(Float, default=0.032)
    people = Column(JSON, default=[])
    tips = Column(JSON, default={})
    map_places = Column(JSON, default=[])
    shared_with = Column(JSON, default=[])
    share_code = Column(String(20), unique=True, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(TW))
    updated_at = Column(DateTime, default=lambda: datetime.now(TW), onupdate=lambda: datetime.now(TW))

    owner = relationship("User", back_populates="plans")
    flights = relationship("Flight", back_populates="plan", cascade="all, delete-orphan")
    hotels = relationship("Hotel", back_populates="plan", cascade="all, delete-orphan")
    days = relationship("Day", back_populates="plan", cascade="all, delete-orphan")
    shopping = relationship("ShoppingItem", back_populates="plan", cascade="all, delete-orphan")
    fixed_expenses = relationship("FixedExpense", back_populates="plan", cascade="all, delete-orphan")
    other_expenses = relationship("OtherExpense", back_populates="plan", cascade="all, delete-orphan")


class Flight(Base):
    __tablename__ = "flights"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("travel_plans.id"), nullable=False)
    fr = Column(String(50), default="")
    to = Column(String(50), default="")
    date = Column(String(20), default="")
    time = Column(String(30), default="")
    tag = Column(String(20), default="")
    price = Column(Integer, default=0)
    order = Column(Integer, default=0)
    plan = relationship("TravelPlan", back_populates="flights")


class Hotel(Base):
    __tablename__ = "hotels"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("travel_plans.id"), nullable=False)
    name = Column(String(100), default="")
    checkin = Column(String(20), default="")
    checkout = Column(String(20), default="")
    nights = Column(Integer, default=0)
    price = Column(Integer, default=0)
    order = Column(Integer, default=0)
    plan = relationship("TravelPlan", back_populates="hotels")


class Day(Base):
    __tablename__ = "days"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("travel_plans.id"), nullable=False)
    date = Column(String(20), default="")
    label = Column(String(50), default="")
    order = Column(Integer, default=0)
    plan = relationship("TravelPlan", back_populates="days")
    items = relationship("DayItem", back_populates="day", cascade="all, delete-orphan")


class DayItem(Base):
    __tablename__ = "day_items"
    id = Column(Integer, primary_key=True, index=True)
    day_id = Column(Integer, ForeignKey("days.id"), nullable=False)
    time = Column(String(20), default="")
    title = Column(String(100), default="")
    note = Column(String(200), default="")
    metro = Column(String(100), default="")
    map_query = Column(String(200), default="")
    order = Column(Integer, default=0)
    day = relationship("Day", back_populates="items")


class ShoppingItem(Base):
    __tablename__ = "shopping"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("travel_plans.id"), nullable=False)
    name = Column(String(100), default="")
    store = Column(String(100), default="")
    kr = Column(Integer, default=0)
    tw = Column(Integer, default=0)
    bought = Column(Boolean, default=False)
    split_with = Column(JSON, default=[])
    order = Column(Integer, default=0)
    plan = relationship("TravelPlan", back_populates="shopping")


class FixedExpense(Base):
    __tablename__ = "fixed_expenses"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("travel_plans.id"), nullable=False)
    name = Column(String(100), default="")
    note = Column(String(200), default="")
    cur = Column(String(10), default="TWD")
    amt = Column(Float, default=0)
    paid_by = Column(String(50), default="")
    split_with = Column(JSON, default=[])
    order = Column(Integer, default=0)
    plan = relationship("TravelPlan", back_populates="fixed_expenses")


class OtherExpense(Base):
    __tablename__ = "other_expenses"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("travel_plans.id"), nullable=False)
    name = Column(String(100), default="")
    note = Column(String(200), default="")
    cur = Column(String(10), default="TWD")
    amt = Column(Float, default=0)
    paid_by = Column(String(50), default="")
    split_with = Column(JSON, default=[])
    order = Column(Integer, default=0)
    plan = relationship("TravelPlan", back_populates="other_expenses")


def init_db():
    Base.metadata.create_all(bind=engine)
    # Add missing columns for existing databases
    from sqlalchemy import text
    with engine.connect() as conn:
        for col, typ in [
            ("shared_with", "JSON"),
            ("share_code", "VARCHAR(20)")
        ]:
            try:
                conn.execute(text(f"ALTER TABLE travel_plans ADD COLUMN {col} {typ}"))
                conn.commit()
            except Exception:
                pass  # Column already exists


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
