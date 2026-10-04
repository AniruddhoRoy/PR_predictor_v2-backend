"""Request models kept separate so app.py stays readable."""
"""
! This file defines Pydantic request models for a FastAPI application.
! The purpose is:
! To validate incoming API request data and convert JSON data from the frontend into Python objects.

"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, alias="fullName")
    email: Optional[str] = None #! this is equivalent to upper one
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


class ModelCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=1, max_length=150)
    task_type: str = Field(alias="taskType")
    version: str = Field(min_length=1, max_length=80)
    provider: Optional[str] = None
    description: Optional[str] = None
    credit_cost: int = Field(default=1, ge=1, le=100000, alias="creditCost")
    artifact_key: Optional[str] = Field(default=None, alias="artifactKey")
    active: bool = True
    model_config = ConfigDict(populate_by_name=True)


class ModelUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=2, max_length=80)
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    task_type: Optional[str] = Field(default=None, alias="taskType")
    version: Optional[str] = Field(default=None, min_length=1, max_length=80)
    provider: Optional[str] = None
    description: Optional[str] = None
    credit_cost: Optional[int] = Field(default=None, ge=1, le=100000, alias="creditCost")
    artifact_key: Optional[str] = Field(default=None, alias="artifactKey")
    active: Optional[bool] = None
    model_config = ConfigDict(populate_by_name=True)


class PlanCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=1, max_length=150)
    monthly_credits: int = Field(alias="monthlyCredits", ge=0, le=1000000000)
    parent_plan_code: Optional[str] = Field(default=None, alias="parentPlanCode")
    model_codes: list[str] = Field(default_factory=list, alias="modelCodes")
    description: Optional[str] = None
    active: bool = True
    model_config = ConfigDict(populate_by_name=True)


class PlanUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=2, max_length=80)
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    monthly_credits: Optional[int] = Field(default=None, ge=0, le=1000000000, alias="monthlyCredits")
    parent_plan_code: Optional[str] = Field(default=None, alias="parentPlanCode")
    model_codes: Optional[list[str]] = Field(default=None, alias="modelCodes")
    description: Optional[str] = None
    active: Optional[bool] = None
    model_config = ConfigDict(populate_by_name=True)
