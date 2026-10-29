"""Request models kept separate so app.py stays readable."""
"""
! This file defines Pydantic request models for a FastAPI application.
! The purpose is:
! To validate incoming API request data and convert JSON data from the frontend into Python objects.

"""

from typing import Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=4, max_length=128)
    full_name: str = Field(min_length=1, max_length=150, alias="fullName")
    github_profile_url: Optional[str] = Field(default=None, alias="githubProfileUrl")
    model_config = ConfigDict(populate_by_name=True) #! this is to allow the model to be populated by name (accept both alias and field name from the frontend)


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128, alias="currentPassword")
    new_password: str = Field(min_length=4, max_length=128, alias="newPassword")
    model_config = ConfigDict(populate_by_name=True)


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, alias="fullName")
    email: Optional[str] = None #! this is equivalent to upper one
    github_profile_url: Optional[str] = Field(default=None, alias="githubProfileUrl")
    model_config = ConfigDict(populate_by_name=True)

    @field_validator("email")
    @classmethod
    def email_not_null(cls, value):
        if value is None:
            raise ValueError("email cannot be null")
        return value


class SettingsUpdate(BaseModel):
    theme_mode: Optional[str] = Field(default=None, alias="themeMode")
    notifications_enabled: Optional[bool] = Field(default=None, alias="notificationsEnabled")
    default_prediction_type: Optional[str] = Field(default=None, alias="defaultPredictionType")
    default_input_mode: Optional[str] = Field(default=None, alias="defaultInputMode")
    model_config = ConfigDict(populate_by_name=True)

    @field_validator("notifications_enabled")
    @classmethod
    def notifications_not_null(cls, value):
        if value is None:
            raise ValueError("notificationsEnabled cannot be null")
        return value


class SubscriptionUpdate(BaseModel):
    plan_code: str = Field(alias="planCode")
    model_config = ConfigDict(populate_by_name=True)


class PredictionRequest(BaseModel):
    pull_request_url: str = Field(min_length=1, alias="pullRequestUrl", validation_alias=AliasChoices("pullRequestUrl", "pr_url", "pull_request_url"))
    # prediction_type: str = Field(default="BOTH", alias="predictionType")
    model_id: str = Field(min_length=1, alias="modelId")
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ModelCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=1, max_length=150)
    version: str = Field(min_length=1, max_length=80)
    provider: str = "local"
    description: Optional[str] = None
    credit_cost: int = Field(default=1, ge=1, le=100000, alias="creditCost")
    active: bool = True
    model_config = ConfigDict(populate_by_name=True)


class ModelUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=2, max_length=80)
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    version: Optional[str] = Field(default=None, min_length=1, max_length=80)
    provider: Optional[str] = None
    description: Optional[str] = None
    credit_cost: Optional[int] = Field(default=None, ge=1, le=100000, alias="creditCost")
    active: Optional[bool] = None
    model_config = ConfigDict(populate_by_name=True)


class PlanCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=1, max_length=150)
    credits: int = Field(default=5, ge=0, le=1000000000)
    duration: int = Field(default=1, ge=1, le=36500)
    model_codes: list[str] = Field(default_factory=list, alias="modelCodes")
    description: Optional[str] = None
    active: bool = True
    model_config = ConfigDict(populate_by_name=True)


class PlanUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=2, max_length=80)
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    credits: Optional[int] = Field(default=None, ge=0, le=1000000000)
    duration: Optional[int] = Field(default=None, ge=1, le=36500)
    model_codes: Optional[list[str]] = Field(default=None, alias="modelCodes")
    description: Optional[str] = None
    active: Optional[bool] = None
    model_config = ConfigDict(populate_by_name=True)
