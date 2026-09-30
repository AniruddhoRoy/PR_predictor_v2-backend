from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    Text,
    DateTime,
    Date,
    DECIMAL,
    ForeignKey,
    UniqueConstraint
)

from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import CHAR

from datetime import datetime
import uuid

from database import Base


# ---------------- USERS ----------------

class User(Base):

    __tablename__ = "users"

    user_id = Column(
        CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    username = Column(
        String(80),
        unique=True,
        nullable=False
    )

    email = Column(
        String(255),
        unique=True,
        nullable=False
    )

    password_hash = Column(
        String(255),
        nullable=False
    )

    full_name = Column(
        String(150),
        nullable=False
    )

    role = Column(
        String(50),
        nullable=False
    )

    github_profile_url = Column(
        Text
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


    settings = relationship(
        "UserSetting",
        back_populates="user",
        uselist=False
    )

    predictions = relationship(
        "Prediction",
        back_populates="user"
    )


# ---------------- USER SETTINGS ----------------

class UserSetting(Base):

    __tablename__ = "user_settings"


    user_id = Column(
        CHAR(36),
        ForeignKey("users.user_id"),
        primary_key=True
    )

    theme_mode = Column(
        String(10),
        default="LIGHT"
    )

    notifications_enabled = Column(
        Boolean,
        default=True
    )

    default_prediction_type = Column(
        String(30)
    )

    default_input_mode = Column(
        String(30)
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow
    )


    user = relationship(
        "User",
        back_populates="settings"
    )


# ---------------- PLANS ----------------

class Plan(Base):

    __tablename__ = "plans"


    plan_id = Column(
        CHAR(36),
        primary_key=True,
        default=lambda:str(uuid.uuid4())
    )


    code = Column(
        String(80),
        unique=True
    )


    name = Column(
        String(150)
    )


    monthly_prediction_limit = Column(
        Integer,
        nullable=True
    )


    description = Column(Text)


    active = Column(
        Boolean,
        default=True
    )



# ---------------- MODELS ----------------

class MLModel(Base):

    __tablename__ = "models"


    model_id = Column(
        CHAR(36),
        primary_key=True,
        default=lambda:str(uuid.uuid4())
    )


    code = Column(
        String(80),
        unique=True
    )


    name = Column(
        String(150)
    )


    task_type = Column(
        String(30)
    )


    version = Column(
        String(80)
    )


    provider = Column(
        String(100)
    )


    description = Column(Text)


    active = Column(
        Boolean,
        default=True
    )


    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


    retired_at = Column(
        DateTime,
        nullable=True
    )


# ---------------- REPOSITORIES ----------------

class Repository(Base):

    __tablename__="repositories"


    repository_id = Column(
        CHAR(36),
        primary_key=True,
        default=lambda:str(uuid.uuid4())
    )


    provider = Column(
        String(50)
    )


    owner = Column(
        String(100)
    )


    name = Column(
        String(150)
    )


    canonical_url = Column(
        Text
    )


    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


    pull_requests = relationship(
        "PullRequest",
        back_populates="repository"
    )



# ---------------- PULL REQUESTS ----------------

class PullRequest(Base):

    __tablename__="pull_requests"


    pull_request_id = Column(
        CHAR(36),
        primary_key=True,
        default=lambda:str(uuid.uuid4())
    )


    repository_id = Column(
        CHAR(36),
        ForeignKey(
            "repositories.repository_id"
        )
    )


    number = Column(
        Integer
    )


    url = Column(
        Text,
        unique=True
    )


    title = Column(Text)


    state = Column(
        String(30)
    )


    author_login = Column(
        String(100)
    )


    fetched_at = Column(
        DateTime,
        default=datetime.utcnow
    )


    repository = relationship(
        "Repository",
        back_populates="pull_requests"
    )