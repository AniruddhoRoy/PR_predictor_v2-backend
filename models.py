"""Small SQLAlchemy model set matching the diagrams in this repository."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String,
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
    prediction_results = relationship("PredictionResult", back_populates="user")


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
    duration = Column(Integer, nullable=False, default=1) ##! --> this defines the duration of the plan in days from now
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
    ended_at = Column(DateTime, nullable=False) ##! --> this defines the end time of the subscription related to the plan duration
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user = relationship("User", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")

class MLModel(Base):
    __tablename__ = "models"
    model_id = Column(String(36), primary_key=True, default=new_id)
    code = Column(String(80), unique=True, nullable=False)
    name = Column(String(150), nullable=False)
    version = Column(String(80), nullable=False, default="1.0")
    provider = Column(String(100), nullable=False, default="local")  ##! --> this defines the provider of the model (local llm or third pary api)
    description = Column(Text, nullable=True)
    credit_cost = Column(Integer, nullable=False, default=1)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    retired_at = Column(DateTime, nullable=True)
    predictions = relationship("Prediction", back_populates="model")
    plans = relationship("Plan", secondary=plan_model_access, back_populates="models")


class UsagePeriod(Base):
    __tablename__ = "usage_periods"
    usage_period_id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    time_stamp = Column(Date, nullable=False)
    credits_used = Column(Integer, nullable=False, default=0)
    user = relationship("User", back_populates="usage_periods") ## here map the user to the usage period
    predictions = relationship("Prediction", back_populates="usage_period") ## here map the usage period to the prediction made

class Prediction(Base):
    __tablename__ = "predictions"
    prediction_id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False, index=True)
    usage_period_id = Column(String(36), ForeignKey("usage_periods.usage_period_id"), nullable=False)
    model_id = Column(String(36), ForeignKey("models.model_id"), nullable=False)
    pr_url = Column(Text, nullable=False, index=True)  # request body "pr_url"
    status = Column(String(20), nullable=False, default="COMPLETED")  # COMPLETED / FAILED
    credits_cost = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    http_status = Column(Integer, nullable=True)  # upstream status (401/404/422/502/503/504 on failure)
    error_message = Column(Text, nullable=True)
    user = relationship("User", back_populates="predictions")
    usage_period = relationship("UsagePeriod", back_populates="predictions")
    model = relationship("MLModel", back_populates="predictions")
    result = relationship("PredictionResult", back_populates="prediction", uselist=False, cascade="all, delete-orphan")
 
 
class PredictionResult(Base):
    """Stores the successful /analyze response: the "features" (PR data) and the "analysis"."""
    __tablename__ = "prediction_results"
    result_id = Column(String(36), primary_key=True, default=new_id)
    prediction_id = Column(String(36), ForeignKey("predictions.prediction_id"), unique=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False, index=True)
 
    pr_url = Column(Text, nullable=False)
    repository = Column(String(255), nullable=False, index=True)   
    pr_number = Column(Integer, nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)                     
    author = Column(String(100), nullable=True)
    author_association = Column(String(50), nullable=True)        
    state = Column(String(20), nullable=True)                     
    merged = Column(Boolean, nullable=True)
    draft = Column(Boolean, nullable=True)
    mergeable = Column(Boolean, nullable=True)
    mergeable_state = Column(String(30), nullable=True)           
    pr_created_at = Column(DateTime(timezone=True), nullable=True)
    pr_updated_at = Column(DateTime(timezone=True), nullable=True)
    head_sha = Column(String(64), nullable=True)
    base_branch = Column(String(255), nullable=True)
    additions = Column(Integer, nullable=True)
    deletions = Column(Integer, nullable=True)
    changed_files = Column(Integer, nullable=True)
    commit_count = Column(Integer, nullable=True)
    comment_count = Column(Integer, nullable=True)
    review_comment_count = Column(Integer, nullable=True)
    review_count = Column(Integer, nullable=True)
    approvals = Column(Integer, nullable=True)
    changes_requested = Column(Integer, nullable=True)
 
    # ---- response["features"]: list fields (stored as JSON) ----
    labels = Column(JSON, nullable=True)
    files = Column(JSON, nullable=True)            
    comments = Column(JSON, nullable=True)
    reviews = Column(JSON, nullable=True)
    review_comments = Column(JSON, nullable=True)
    commits = Column(JSON, nullable=True)         
    checks = Column(JSON, nullable=True)
    statuses = Column(JSON, nullable=True)
    warnings = Column(JSON, nullable=True)
 
    # ---- response["analysis"] ----
    merge_probability = Column(Numeric(5, 2), nullable=True)      
    quality_score = Column(Numeric(5, 2), nullable=True)          
    quality = Column(String(30), nullable=True)                   
    confidence = Column(String(20), nullable=True)               
    summary = Column(Text, nullable=True)
    merge_reasoning = Column(Text, nullable=True)
    recommendations = Column(JSON, nullable=True)                 
    potential_improvements = Column(JSON, nullable=True)           
    limitations = Column(JSON, nullable=True)                     
 
    # ---- top level ----
    probability_note = Column(Text, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
 
    prediction = relationship("Prediction", back_populates="result")
    user = relationship("User", back_populates="prediction_results")
