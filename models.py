"""Simple models for users, plans, credit usage, and hosted PR analysis."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String,
    JSON, Table, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


plan_model_access = Table(
    "plan_model_access",
    Base.metadata,
    Column("plan_id", String(36), ForeignKey("plans.plan_id"), primary_key=True),
    Column("model_id", String(36), ForeignKey("models.model_id"), primary_key=True),
)


def new_id():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    user_id = Column(String(36), primary_key=True, default=new_id)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    #! Authorization stays deliberately small for this project: USER or ADMIN.
    role = Column(String(20), nullable=False, default="USER")
    github_profile_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    settings = relationship("UserSetting", back_populates="user", uselist=False, cascade="all, delete-orphan")
    #! uselist = False means that the relationship will return a single object, not a list of objects.
    #! back_populates="user" makes the relationship two-way.
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    usage_periods = relationship("UsagePeriod", back_populates="user", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="user", cascade="all, delete-orphan")


class UserSetting(Base):
    __tablename__ = "user_settings"
    user_id = Column(String(36), ForeignKey("users.user_id"), primary_key=True)
    theme_mode = Column(String(10), nullable=False, default="LIGHT")
    notifications_enabled = Column(Boolean, nullable=False, default=True)
    default_prediction_type = Column(String(30), nullable=False, default="BOTH")
    default_input_mode = Column(String(30), nullable=False, default="GITHUB_URL")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    user = relationship("User", back_populates="settings")



class Plan(Base):
    __tablename__ = "plans"
    plan_id = Column(String(36), primary_key=True, default=new_id)
    code = Column(String(80), unique=True, nullable=False)
    name = Column(String(150), nullable=False)
    credits = Column(Integer, nullable=False, default=5)
    duration = Column(Integer, nullable=False, default=1)  # Days from subscription start.
    description = Column(Text, nullable=False, default="")
    active = Column(Boolean, nullable=False, default=True)
    subscriptions = relationship("Subscription", back_populates="plan")
    models = relationship("MLModel", secondary=plan_model_access, back_populates="plans")


class Subscription(Base):
    __tablename__ = "subscriptions"
    subscription_id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    plan_id = Column(String(36), ForeignKey("plans.plan_id"), nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE")
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user = relationship("User", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")

class MLModel(Base):
    __tablename__ = "models"
    model_id = Column(String(36), primary_key=True, default=new_id)
    code = Column(String(80), unique=True, nullable=False)
    name = Column(String(150), nullable=False)
    version = Column(String(80), nullable=False, default="1.0")
    provider = Column(String(100), nullable=False, default="local")
    description = Column(Text, nullable=True)
    credit_cost = Column(Integer, nullable=False, default=1)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    retired_at = Column(DateTime, nullable=True)
    predictions = relationship("Prediction", back_populates="model")
    plans = relationship("Plan", secondary=plan_model_access, back_populates="models")


class UsagePeriod(Base):
    __tablename__ = "usage_periods"
    __table_args__ = (UniqueConstraint("user_id", "time_stamp", name="uq_usage_user_time"),)
    usage_period_id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    time_stamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    credits_used = Column(Integer, nullable=False, default=0)
    user = relationship("User", back_populates="usage_periods")
    predictions = relationship("Prediction", back_populates="usage_period")


class Prediction(Base):
    __tablename__ = "predictions"
    prediction_id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False, index=True)
    usage_period_id = Column(String(36), ForeignKey("usage_periods.usage_period_id"), nullable=False)
    model_id = Column(String(36), ForeignKey("models.model_id"), nullable=False)
    pr_url = Column(Text, nullable=True)  # Older manual predictions may have no URL.
    title = Column(Text, nullable=False, default="Pull request")
    prediction_type = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="COMPLETED")
    model_version = Column(String(80), nullable=False)
    credits_cost = Column(Integer, nullable=False, default=1)
    inference_key = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    user = relationship("User", back_populates="predictions")
    usage_period = relationship("UsagePeriod", back_populates="predictions")
    model = relationship("MLModel", back_populates="predictions")
    result = relationship("PredictionResult", back_populates="prediction", uselist=False, cascade="all, delete-orphan")


class PredictionResult(Base):
    __tablename__ = "prediction_results"
    result_id = Column(String(36), primary_key=True, default=new_id)
    prediction_id = Column(String(36), ForeignKey("predictions.prediction_id"), unique=True, nullable=False)
    merge_probability = Column(Numeric(5, 2), nullable=True)
    quality_score = Column(Numeric(5, 2), nullable=True)
    quality_label = Column(String(30), nullable=True)
    recommendation = Column(Text, nullable=False)
    analysis_response = Column(JSON, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    prediction = relationship("Prediction", back_populates="result")
