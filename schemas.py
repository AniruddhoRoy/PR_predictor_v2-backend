"""Request models kept separate so app.py stays readable."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=4, max_length=128)
    full_name: str = Field(min_length=1, max_length=150, alias="fullName")
    github_profile_url: Optional[str] = Field(default=None, alias="githubProfileUrl")
    model_config = ConfigDict(populate_by_name=True)


class LoginRequest(BaseModel):
    username: str
    password: str


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, alias="fullName")
    email: Optional[str] = None
    github_profile_url: Optional[str] = Field(default=None, alias="githubProfileUrl")
    model_config = ConfigDict(populate_by_name=True)


class SettingsUpdate(BaseModel):
    theme_mode: Optional[str] = Field(default=None, alias="themeMode")
    notifications_enabled: Optional[bool] = Field(default=None, alias="notificationsEnabled")
    default_prediction_type: Optional[str] = Field(default=None, alias="defaultPredictionType")
    default_input_mode: Optional[str] = Field(default=None, alias="defaultInputMode")
    model_config = ConfigDict(populate_by_name=True)


class SubscriptionUpdate(BaseModel):
    plan_code: str = Field(alias="planCode")
    model_config = ConfigDict(populate_by_name=True)


class PredictionRequest(BaseModel):
    input_type: str = Field(alias="inputType")
    prediction_type: str = Field(alias="predictionType")
    model_id: Optional[str] = Field(default=None, alias="modelId")
    pull_request_url: Optional[str] = Field(default=None, alias="pullRequestUrl")
    features: Optional[Dict[str, Any]] = None
    model_config = ConfigDict(populate_by_name=True)
