"""Small SQLAlchemy model set matching the diagrams in this repository."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String,
    Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


def new_id():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    user_id = Column(String(36), primary_key=True, default=new_id)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    # Authorization stays deliberately small for this project: USER or ADMIN.
    role = Column(String(20), nullable=False, default="USER")
    github_profile_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    settings = relationship("UserSetting", back_populates="user", uselist=False, cascade="all, delete-orphan")
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
    monthly_prediction_limit = Column(Integer, nullable=True)
    description = Column(Text, nullable=False, default="")
    active = Column(Boolean, nullable=False, default=True)
    subscriptions = relationship("Subscription", back_populates="plan")


class Subscription(Base):
    __tablename__ = "subscriptions"
    subscription_id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    plan_id = Column(String(36), ForeignKey("plans.plan_id"), nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE")
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    provider_reference = Column(String(150), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user = relationship("User", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")


class MLModel(Base):
    __tablename__ = "models"
    model_id = Column(String(36), primary_key=True, default=new_id)
    code = Column(String(80), unique=True, nullable=False)
    name = Column(String(150), nullable=False)
    task_type = Column(String(30), nullable=False, default="BOTH")
    version = Column(String(80), nullable=False, default="1.0")
    provider = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    retired_at = Column(DateTime, nullable=True)
    predictions = relationship("Prediction", back_populates="model")


class UsagePeriod(Base):
    __tablename__ = "usage_periods"
    __table_args__ = (UniqueConstraint("user_id", "period_start", name="uq_usage_user_period"),)
    usage_period_id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    predictions_used = Column(Integer, nullable=False, default=0)
    limit_snapshot = Column(Integer, nullable=True)
    user = relationship("User", back_populates="usage_periods")
    predictions = relationship("Prediction", back_populates="usage_period")


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("provider", "owner", "name", name="uq_repository_name"),)
    repository_id = Column(String(36), primary_key=True, default=new_id)
    provider = Column(String(50), nullable=False, default="github")
    owner = Column(String(100), nullable=False)
    name = Column(String(150), nullable=False)
    canonical_url = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    pull_requests = relationship("PullRequest", back_populates="repository")


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (UniqueConstraint("repository_id", "number", name="uq_pull_request_number"),)
    pull_request_id = Column(String(36), primary_key=True, default=new_id)
    repository_id = Column(String(36), ForeignKey("repositories.repository_id"), nullable=False)
    number = Column(Integer, nullable=False)
    url = Column(Text, unique=True, nullable=False)
    title = Column(Text, nullable=False, default="Pull request")
    state = Column(String(30), nullable=False, default="OPEN")
    author_login = Column(String(100), nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    repository = relationship("Repository", back_populates="pull_requests")
    predictions = relationship("Prediction", back_populates="pull_request")


class Prediction(Base):
    __tablename__ = "predictions"
    prediction_id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False, index=True)
    usage_period_id = Column(String(36), ForeignKey("usage_periods.usage_period_id"), nullable=False)
    model_id = Column(String(36), ForeignKey("models.model_id"), nullable=False)
    pull_request_id = Column(String(36), ForeignKey("pull_requests.pull_request_id"), nullable=True)
    prediction_type = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="COMPLETED")
    model_version = Column(String(80), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    user = relationship("User", back_populates="predictions")
    usage_period = relationship("UsagePeriod", back_populates="predictions")
    model = relationship("MLModel", back_populates="predictions")
    pull_request = relationship("PullRequest", back_populates="predictions")
    input = relationship("PredictionInput", back_populates="prediction", uselist=False, cascade="all, delete-orphan")
    features = relationship("PredictionFeature", back_populates="prediction", cascade="all, delete-orphan")
    result = relationship("PredictionResult", back_populates="prediction", uselist=False, cascade="all, delete-orphan")


class PredictionInput(Base):
    __tablename__ = "prediction_inputs"
    prediction_id = Column(String(36), ForeignKey("predictions.prediction_id"), primary_key=True)
    input_mode = Column(String(30), nullable=False)
    github_url = Column(Text, nullable=True)
    raw_feature_text = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    prediction = relationship("Prediction", back_populates="input")


class PredictionFeature(Base):
    __tablename__ = "prediction_features"
    feature_id = Column(String(36), primary_key=True, default=new_id)
    prediction_id = Column(String(36), ForeignKey("predictions.prediction_id"), nullable=False)
    feature_name = Column(String(100), nullable=False)
    value_type = Column(String(20), nullable=False)
    value_text = Column(Text, nullable=True)
    value_number = Column(Numeric(12, 2), nullable=True)
    value_boolean = Column(Boolean, nullable=True)
    source = Column(String(30), nullable=False, default="USER")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    prediction = relationship("Prediction", back_populates="features")


class PredictionResult(Base):
    __tablename__ = "prediction_results"
    result_id = Column(String(36), primary_key=True, default=new_id)
    prediction_id = Column(String(36), ForeignKey("predictions.prediction_id"), unique=True, nullable=False)
    merge_probability = Column(Numeric(5, 2), nullable=True)
    quality_score = Column(Numeric(5, 2), nullable=True)
    quality_label = Column(String(30), nullable=True)
    recommendation = Column(Text, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    prediction = relationship("Prediction", back_populates="result")
    factors = relationship("PredictionFactor", back_populates="result", cascade="all, delete-orphan", order_by="PredictionFactor.display_order")


class PredictionFactor(Base):
    __tablename__ = "prediction_factors"
    factor_id = Column(String(36), primary_key=True, default=new_id)
    result_id = Column(String(36), ForeignKey("prediction_results.result_id"), nullable=False)
    factor_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    impact = Column(String(20), nullable=False)
    display_order = Column(Integer, nullable=False, default=0)
    result = relationship("PredictionResult", back_populates="factors")
