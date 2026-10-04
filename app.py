"""Simple PR prediction backend.

The service intentionally keeps the workflow synchronous and understandable:
request -> validate -> run notebook model -> persist -> return result.
"""

import os
import re
import json
from urllib.request import Request, urlopen
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, inspect, or_, text
from sqlalchemy.orm import Session

from auth import create_token, hash_password, read_token, verify_password
from database import Base, SessionLocal, engine, get_db
from models import (
    MLModel, Plan, Prediction, PredictionFactor, PredictionFeature,
    PredictionInput, PredictionResult, PullRequest, Repository, Subscription,
    UsagePeriod, User, UserSetting,
)
from schemas import (
    LoginRequest, PredictionRequest, ProfileUpdate, RegisterRequest,
    SettingsUpdate, SubscriptionUpdate, ModelCreate, ModelUpdate, PlanCreate, PlanUpdate,
)
from prediction_engine import predict as run_model_prediction


app = FastAPI(title="PR Predictor API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ADMIN_DIR = Path(__file__).parent / "admin"

# ! problem
bearer = HTTPBearer(auto_error=False)
GITHUB_PR_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$", re.I)
ALLOWED_PREDICTION_TYPES = {"MERGE_PROBABILITY", "PR_QUALITY", "BOTH"}


@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    migrate_schema()
    seed_database()


def migrate_schema():
    """Add the few new columns when an older local SQLite database is reused."""
    additions = {
        "plans": {"monthly_credits": "INTEGER DEFAULT 5", "parent_plan_id": "VARCHAR(36)"},
        "models": {"credit_cost": "INTEGER DEFAULT 1", "artifact_key": "VARCHAR(80)"},
        "usage_periods": {"credits_used": "INTEGER DEFAULT 0", "credit_limit_snapshot": "INTEGER DEFAULT 5"},
        "predictions": {"credits_cost": "INTEGER DEFAULT 1", "inference_key": "VARCHAR(80)"},
    }
    existing = inspect(engine)
    with engine.begin() as connection:
        for table, columns in additions.items():
            names = {item["name"] for item in existing.get_columns(table)}
            for name, definition in columns.items():
                if name not in names:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
                    if name == "monthly_credits":
                        connection.execute(text("UPDATE plans SET monthly_credits = COALESCE(monthly_prediction_limit, 5)"))
                    elif name == "credits_used":
                        connection.execute(text("UPDATE usage_periods SET credits_used = predictions_used"))


def seed_database():
    db = SessionLocal()
    try:
        model_data = [
            ("model-1", "Model 1 - Logistic Regression", "logistic-regression"),
            ("model-2", "Model 2 - Random Forest", "random-forest"),
            ("model-3", "Model 3 - KNN", "knn"),
            ("model-4", "Model 4 - Decision Tree", "decision-tree"),
            ("model-5", "Model 5 - SGD Classifier", "sgd-classifier"),
            ("model-6", "Model 6 - Extra Trees", "extra-trees"),
        ]
        models = []
        for code, name, artifact in model_data:
            model = db.query(MLModel).filter_by(code=code).first()
            if not model:
                model = MLModel(code=code, name=name, task_type="BOTH", version="1.0", provider="notebook", artifact_key=artifact, credit_cost=1, description="Classifier trained from models(notebook)/final_df.csv.")
                db.add(model)
            else:
                model.artifact_key = model.artifact_key or artifact
                model.credit_cost = model.credit_cost or 1
            models.append(model)
        db.flush()
        plans = {}
        new_plans = set()
        for code, name, credits in [("FREE", "Free", 5), ("PLUS", "Plus", 30), ("PRO", "Pro", 100), ("ULTRA", "Ultra", 300)]:
            plan = db.query(Plan).filter_by(code=code).first()
            if not plan:
                plan = Plan(code=code, name=name, monthly_credits=credits, monthly_prediction_limit=credits, description=f"{credits} credits each month")
                db.add(plan)
                new_plans.add(code)
            else:
                if plan.monthly_credits is None:
                    plan.monthly_credits = credits
            plans[code] = plan
        db.flush()
        for code in new_plans:
            plan = plans[code]
            if code == "FREE":
                plan.models = models[:1]
            elif code == "PLUS":
                plan.models = models[:3]
            elif code == "PRO":
                plan.parent = plans["PLUS"]
                plan.models = models[3:]
            elif code == "ULTRA":
                plan.parent = plans["PRO"]
        # Keep the old demo plan usable for existing accounts.
        old = db.query(Plan).filter_by(code="PREMIUM").first()
        if old and old.monthly_credits is None:
            old.monthly_credits = 100
        admin = db.query(User).filter_by(username="admin").first()
        if not admin:
            admin = User(username="admin", email="admin@example.com", full_name="Project Admin", role="ADMIN", password_hash=hash_password(os.getenv("ADMIN_PASSWORD", "1234")))
            db.add(admin)
            db.flush()
            db.add(UserSetting(user_id=admin.user_id))
        db.commit()
    finally:
        db.close()


@app.get("/")
def home():
    return {"message": "PR Predictor API is running", "docs": "/docs", "admin": "/admin/"}


@app.get("/health")
def health():
    return {"status": "ok"}


#! this is a helper function to return a public user representation
def _public_user(user: User) -> dict:
    return {
        "userId": user.user_id,
        "username": user.username,
        "email": user.email,
        "fullName": user.full_name,
        "role": user.role,
        "githubProfileUrl": user.github_profile_url,
        "createdAt": user.created_at.isoformat() if user.created_at else None,
    }

#! this is a helper function to return a token response
def _token_response(user: User) -> dict:
    return {"accessToken": create_token(user.user_id, user.role), "tokenType": "bearer", "user": _public_user(user)}


#! db: Session = Depends(get_db) ,  This is FastAPI's dependency injection. It tells FastAPI: "before running this endpoint, call get_db() and hand me the result as db."

@app.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    username = data.username.strip().lower()
    email = data.email.strip().lower()
    if db.query(User).filter(or_(User.username == username, User.email == email)).first():
        raise HTTPException(status_code=409, detail="Username or email is already registered")
    user = User(username=username, email=email, full_name=data.full_name.strip(), password_hash=hash_password(data.password), role="USER", github_profile_url=data.github_profile_url)
    db.add(user)
    db.flush()
    db.add(UserSetting(user_id=user.user_id))
    free = db.query(Plan).filter_by(code="FREE", active=True).first()
    if free:
        db.add(Subscription(user_id=user.user_id, plan_id=free.plan_id, status="ACTIVE"))
    db.commit()
    db.refresh(user)
    return _token_response(user)


@app.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    identifier = data.username.strip().lower()
    user = db.query(User).filter(or_(User.username == identifier, User.email == identifier)).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return _token_response(user)


def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Bearer token required")
    try:
        payload = read_token(credentials.credentials)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter_by(user_id=payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role.upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@app.get("/me")
def me(user: User = Depends(get_current_user)):
    return _public_user(user)


@app.get("/profile")
def get_profile(user: User = Depends(get_current_user)):
    return _public_user(user)



#! Depends tells FastAPI: "don't expect this value from the client; get it by calling this function for me."

#! Without Depends, FastAPI assumes a parameter comes from the request itself (body, query string, path). With Depends(some_function), FastAPI runs some_function first and passes its return value in as the parameter.
@app.patch("/profile")
def update_profile(data: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
#! values = data.model_dump(exclude_unset=True, by_alias=False)
model_dump() converts the Pydantic model into a plain dict.
exclude_unset=True leaves out any field the client didn't include in the JSON. This is what lets you tell "field not sent" (ignore it) from "field sent as null" (clear it).
by_alias=False uses the Python field names (github_profile_url) instead of any aliases (such as camelCase githubProfileUrl) the model defines for the JSON.
#? So if the client sends {"full_name": "Ali"}, values is just {"full_name": "Ali"}.
    """
    values = data.model_dump(exclude_unset=True, by_alias=False)
    if "email" in values:
        email = values["email"].strip().lower()
        duplicate = db.query(User).filter(User.email == email, User.user_id != user.user_id).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Email is already registered")
        user.email = email
    if values.get("full_name") is not None:
        user.full_name = values["full_name"].strip()
    if "github_profile_url" in values:
        user.github_profile_url = values["github_profile_url"]
    db.commit()
    db.refresh(user)
    return _public_user(user)


@app.get("/settings")
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    settings = _ensure_settings(db, user)
    return _settings_dict(settings)


@app.patch("/settings")
def update_settings(data: SettingsUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    settings = _ensure_settings(db, user)
    values = data.model_dump(exclude_unset=True, by_alias=False)
    allowed = {"theme_mode": {"LIGHT", "DARK"}, "default_prediction_type": ALLOWED_PREDICTION_TYPES, "default_input_mode": {"GITHUB_URL", "MANUAL_FEATURES"}}
    for key, value in values.items():
        if key in allowed and value not in allowed[key]:
            raise HTTPException(status_code=400, detail=f"Invalid {key}")
        setattr(settings, key, value)
    db.commit()
    return _settings_dict(settings)


def _ensure_settings(db: Session, user: User) -> UserSetting:
    settings = db.query(UserSetting).filter_by(user_id=user.user_id).first()
    if not settings:
        settings = UserSetting(user_id=user.user_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _settings_dict(settings: UserSetting) -> dict:
    return {"themeMode": settings.theme_mode, "notificationsEnabled": settings.notifications_enabled, "defaultPredictionType": settings.default_prediction_type, "defaultInputMode": settings.default_input_mode}


#! prediction_type: Optional[str] = Query(default=None, alias="predictionType") query parameter
@app.get("/models")
def models(prediction_type: Optional[str] = Query(default=None, alias="predictionType"), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    plan = _active_subscription(db, user).plan
    allowed_ids = {item.model_id for item in _resolved_plan_models(plan)}
    query = db.query(MLModel).filter(MLModel.active.is_(True), MLModel.model_id.in_(allowed_ids))
    if prediction_type:
        prediction_type = prediction_type.upper()
        query = query.filter(or_(MLModel.task_type == "BOTH", MLModel.task_type == prediction_type))
    return [_model_dict(item) for item in query.order_by(MLModel.name).all()]


def _model_dict(model: MLModel) -> dict:
    return {"modelId": model.model_id, "code": model.code, "name": model.name, "taskType": model.task_type, "version": model.version, "provider": model.provider, "description": model.description, "creditCost": model.credit_cost, "artifactKey": model.artifact_key}


@app.get("/subscription")
def get_subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    subscription = _active_subscription(db, user)
    return _subscription_dict(subscription)


@app.get("/active-plan")
@app.get("/plan")
def active_plan(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = _active_subscription(db, user).plan
    usage = _get_usage(db, user, plan.monthly_credits)
    result = _plan_dict(plan)
    result.update(creditsUsed=usage.credits_used, creditsRemaining=max(0, plan.monthly_credits - usage.credits_used))
    return result


@app.get("/plans")
def available_plans(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_plan_dict(plan) for plan in db.query(Plan).filter_by(active=True).order_by(Plan.monthly_credits).all()]


@app.post("/subscription")
def change_subscription(data: SubscriptionUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = db.query(Plan).filter_by(code=data.plan_code.upper(), active=True).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    for old in db.query(Subscription).filter_by(user_id=user.user_id, status="ACTIVE").all():
        old.status = "CANCELLED"
        old.ended_at = datetime.utcnow()
    subscription = Subscription(user_id=user.user_id, plan_id=plan.plan_id, status="ACTIVE")
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return _subscription_dict(subscription)


def _active_subscription(db: Session, user: User) -> Subscription:
    subscription = db.query(Subscription).filter_by(user_id=user.user_id, status="ACTIVE").order_by(Subscription.started_at.desc()).first()
    if not subscription:
        plan = db.query(Plan).filter_by(code="FREE").first()
        subscription = Subscription(user_id=user.user_id, plan_id=plan.plan_id, status="ACTIVE")
        db.add(subscription)
        db.commit()
        db.refresh(subscription)
    return subscription


def _subscription_dict(subscription: Subscription) -> dict:
    return {"subscriptionId": subscription.subscription_id, "status": subscription.status, "startedAt": subscription.started_at.isoformat(), "plan": _plan_dict(subscription.plan)}


def _resolved_plan_models(plan: Plan) -> list[MLModel]:
    found = {}
    seen = set()
    while plan:
        if plan.plan_id in seen:
            raise HTTPException(status_code=409, detail="Plan inheritance contains a cycle")
        seen.add(plan.plan_id)
        for model in plan.models:
            found[model.model_id] = model
        plan = plan.parent
    return sorted(found.values(), key=lambda item: item.name.lower())


def _plan_dict(plan: Plan) -> dict:
    return {"planId": plan.plan_id, "code": plan.code, "name": plan.name,
            "monthlyCredits": plan.monthly_credits, "description": plan.description,
            "parentPlanCode": plan.parent.code if plan.parent else None,
            "models": [_model_dict(model) for model in _resolved_plan_models(plan)]}



#### todo Pediction Happends Here (Start)

@app.post("/predict")
def predict(body: PredictionRequest | str = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    request_data = _prediction_request(body)
    input_type = request_data.input_type.upper()
    prediction_type = request_data.prediction_type.upper()
    if input_type not in {"GITHUB_URL", "MANUAL_FEATURES"}:
        raise HTTPException(status_code=400, detail="inputType must be GITHUB_URL or MANUAL_FEATURES")
    if prediction_type not in ALLOWED_PREDICTION_TYPES:
        raise HTTPException(status_code=400, detail="predictionType must be MERGE_PROBABILITY, PR_QUALITY, or BOTH")
    subscription = _active_subscription(db, user)
    plan = subscription.plan
    model = _choose_model(db, request_data.model_id, prediction_type, plan)
    usage = _get_usage(db, user, plan.monthly_credits)
    if usage.credits_used + model.credit_cost > plan.monthly_credits:
        raise HTTPException(status_code=429, detail="Not enough credits for this model")
    parsed_url = None
    features: dict[str, Any]
    raw_feature_text = None
    if input_type == "GITHUB_URL":
        if not request_data.pull_request_url:
            raise HTTPException(status_code=400, detail="pullRequestUrl is required for GITHUB_URL")
        parsed_url = GITHUB_PR_RE.match(request_data.pull_request_url.strip())
        if not parsed_url:
            raise HTTPException(status_code=400, detail="Use a GitHub pull request URL such as https://github.com/owner/repo/pull/12")
        owner, repo_name, number = parsed_url.groups()
        features = _github_features(owner, repo_name, number)
    else:
        features = request_data.features or {}
        if not features:
            raise HTTPException(status_code=400, detail="features must contain at least one value for MANUAL_FEATURES")
        raw_feature_text = ", ".join(f"{key}={value}" for key, value in features.items())
    try:
        merge_score, quality_score, factors = run_model_prediction(features, model.artifact_key or model.code)
    except Exception as error:
        db.rollback()
        raise HTTPException(status_code=503, detail="Notebook model is unavailable; no credits were charged") from error
    repository = pull_request = None
    if parsed_url:
        owner, repo_name, number = parsed_url.groups()
        repository = db.query(Repository).filter_by(provider="github", owner=owner, name=repo_name).first()
        if not repository:
            repository = Repository(provider="github", owner=owner, name=repo_name, canonical_url=f"https://github.com/{owner}/{repo_name}")
            db.add(repository)
            db.flush()
        pull_request = db.query(PullRequest).filter_by(url=request_data.pull_request_url.strip()).first()
        if not pull_request:
            pull_request = PullRequest(repository_id=repository.repository_id, number=int(number), url=request_data.pull_request_url.strip(), title=f"Pull request #{number}", author_login=owner)
            db.add(pull_request)
            db.flush()
    prediction = Prediction(user_id=user.user_id, usage_period_id=usage.usage_period_id, model_id=model.model_id, pull_request_id=pull_request.pull_request_id if pull_request else None, prediction_type=prediction_type, status="COMPLETED", model_version=model.version, credits_cost=model.credit_cost, inference_key=model.artifact_key or model.code, completed_at=datetime.utcnow())
    db.add(prediction)
    db.flush()
    db.add(PredictionInput(prediction_id=prediction.prediction_id, input_mode=input_type, github_url=request_data.pull_request_url if input_type == "GITHUB_URL" else None, raw_feature_text=raw_feature_text))
    for name, value in features.items():
        db.add(_feature_row(prediction.prediction_id, name, value, "GITHUB" if input_type == "GITHUB_URL" else "USER"))
    show_merge = None if prediction_type == "PR_QUALITY" else merge_score
    show_quality = None if prediction_type == "MERGE_PROBABILITY" else quality_score
    label = _quality_label(quality_score)
    result = PredictionResult(prediction_id=prediction.prediction_id, merge_probability=show_merge, quality_score=show_quality, quality_label=label, recommendation=_recommendation(merge_score, quality_score))
    db.add(result)
    db.flush()
    for index, factor in enumerate(factors):
        db.add(PredictionFactor(result_id=result.result_id, display_order=index, **factor))
    # Reserve credits atomically so simultaneous requests cannot overspend.
    charged = db.query(UsagePeriod).filter(
        UsagePeriod.usage_period_id == usage.usage_period_id,
        UsagePeriod.credits_used + model.credit_cost <= plan.monthly_credits,
    ).update({UsagePeriod.predictions_used: UsagePeriod.predictions_used + 1,
              UsagePeriod.credits_used: UsagePeriod.credits_used + model.credit_cost,
              UsagePeriod.credit_limit_snapshot: plan.monthly_credits}, synchronize_session=False)
    if not charged:
        db.rollback()
        raise HTTPException(status_code=429, detail="Not enough credits for this model")
    db.commit()
    db.refresh(prediction)
    return _prediction_dict(prediction)


def _prediction_request(body: Any) -> PredictionRequest:
    if isinstance(body, PredictionRequest):
        return body
    if isinstance(body, str):
        return PredictionRequest(inputType="GITHUB_URL", predictionType="BOTH", pullRequestUrl=body)
    try:
        return PredictionRequest.model_validate(body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Prediction body does not match the documented format") from exc


def _choose_model(db: Session, model_id: Optional[str], prediction_type: str, plan: Plan) -> MLModel:
    allowed = _resolved_plan_models(plan)
    allowed_ids = {item.model_id for item in allowed}
    query = db.query(MLModel).filter(MLModel.active.is_(True), MLModel.model_id.in_(allowed_ids), or_(MLModel.task_type == "BOTH", MLModel.task_type == prediction_type))
    if model_id:
        key = model_id.strip().lower()
        model = query.filter(or_(MLModel.model_id == model_id, MLModel.code == key)).first()
        if model:
            return model
        if db.query(MLModel).filter(MLModel.active.is_(True), or_(MLModel.model_id == model_id, MLModel.code == key)).first():
            raise HTTPException(status_code=403, detail="Your active plan does not include this model")
        raise HTTPException(status_code=404, detail="Prediction model not found")
    model = query.order_by(MLModel.created_at).first()
    if not model:
        raise HTTPException(status_code=404, detail="Your active plan has no model for this prediction type")
    return model


def _get_usage(db: Session, user: User, credit_limit: int) -> UsagePeriod:
    today = date.today()
    period_start = today.replace(day=1)
    next_month = date(today.year + (1 if today.month == 12 else 0), 1 if today.month == 12 else today.month + 1, 1)
    usage = db.query(UsagePeriod).filter_by(user_id=user.user_id, period_start=period_start).first()
    if not usage:
        usage = UsagePeriod(user_id=user.user_id, period_start=period_start, period_end=next_month - timedelta(days=1), limit_snapshot=credit_limit, predictions_used=0, credits_used=0, credit_limit_snapshot=credit_limit)
        db.add(usage)
        db.flush()
    usage.credits_used = usage.credits_used or 0
    return usage


def _feature_row(prediction_id: str, name: str, value: Any, source: str) -> PredictionFeature:
    if isinstance(value, bool):
        return PredictionFeature(prediction_id=prediction_id, feature_name=name, value_type="BOOLEAN", value_boolean=value, source=source)
    if isinstance(value, (int, float)):
        return PredictionFeature(prediction_id=prediction_id, feature_name=name, value_type="NUMBER", value_number=float(value), source=source)
    return PredictionFeature(prediction_id=prediction_id, feature_name=name, value_type="TEXT", value_text=str(value), source=source)


def _github_features(owner, repo, number):
    """Read actual PR features instead of inventing them from its number."""
    def fetch(path):
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "PR-Predictor"}
        if os.getenv("GITHUB_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
        try:
            with urlopen(Request("https://api.github.com" + path, headers=headers), timeout=20) as response:
                return json.load(response)
        except Exception as error:
            raise HTTPException(status_code=502, detail="Cannot read GitHub PR; check the URL or GITHUB_TOKEN") from error

    path = f"/repos/{owner}/{repo}"
    pr = fetch(f"{path}/pulls/{number}")
    repository = fetch(path)
    files = []
    for page in range(1, 31):
        batch = fetch(f"{path}/pulls/{number}/files?per_page=100&page={page}")
        files.extend(batch)
        if len(batch) < 100:
            break
    return {
        "title_word_count": len((pr.get("title") or "").split()),
        "body_word_count": len((pr.get("body") or "").split()),
        "total_lines_added": pr["additions"], "total_lines_deleted": pr["deletions"],
        "total_files_touched": pr["changed_files"], "total_commits": pr["commits"],
        "files_added": sum(file["status"] == "added" for file in files),
        "files_modified": sum(file["status"] == "modified" for file in files),
        "files_deleted": sum(file["status"] == "removed" for file in files),
        "stars": repository["stargazers_count"], "forks": repository["forks_count"],
        "language": repository.get("language") or "unknown",
        "agent": "unknown", "task_type": "unknown",
    }


def _quality_label(score: float) -> str:
    return "Excellent" if score >= 80 else "Good" if score >= 65 else "Needs review" if score >= 50 else "Risky"


def _recommendation(merge_score: float, quality_score: float) -> str:
    if merge_score >= 75 and quality_score >= 70:
        return "Looks ready for review. Keep the existing tests and ask a reviewer to verify the edge cases."
    if merge_score >= 55:
        return "Review the change size and test coverage before merging."
    return "Add tests and split the change into smaller parts before merging."


#### todo Pediction Happends Here (End)

@app.get("/history")
@app.get("/predictions")
def history(search: Optional[str] = None, limit: int = Query(default=20, ge=1, le=100), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Prediction).filter(Prediction.user_id == user.user_id).order_by(Prediction.created_at.desc())
    if search:
        query = query.outerjoin(PullRequest).filter(or_(PullRequest.url.ilike(f"%{search}%"), PullRequest.title.ilike(f"%{search}%")))
    return [_prediction_dict(item) for item in query.limit(limit).all()]


@app.get("/predictions/{prediction_id}")
def prediction_detail(prediction_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    prediction = db.query(Prediction).filter_by(prediction_id=prediction_id, user_id=user.user_id).first()
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return _prediction_dict(prediction)


def _prediction_dict(prediction: Prediction) -> dict:
    result = prediction.result
    pr = prediction.pull_request
    repository = pr.repository if pr else None
    return {
        "predictionId": prediction.prediction_id,
        "status": prediction.status,
        "predictionType": prediction.prediction_type,
        "createdAt": prediction.created_at.isoformat() if prediction.created_at else None,
        "completedAt": prediction.completed_at.isoformat() if prediction.completed_at else None,
        "modelVersion": prediction.model_version,
        "creditsCost": prediction.credits_cost,
        "inferenceKey": prediction.inference_key,
        "model": _model_dict(prediction.model) if prediction.model else None,
        "repository": {"owner": repository.owner, "name": repository.name, "url": repository.canonical_url} if repository else None,
        "pullRequest": {"number": pr.number, "url": pr.url, "title": pr.title, "state": pr.state, "authorLogin": pr.author_login} if pr else None,
        "mergeProbability": float(result.merge_probability) if result and result.merge_probability is not None else None,
        "qualityScore": float(result.quality_score) if result and result.quality_score is not None else None,
        "qualityLabel": result.quality_label if result else None,
        "recommendation": result.recommendation if result else None,
        "factors": [{"name": factor.factor_name, "description": factor.description, "impact": factor.impact, "order": factor.display_order} for factor in (result.factors if result else [])],
    }


@app.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    subscription = _active_subscription(db, user)
    usage = _get_usage(db, user, subscription.plan.monthly_credits)
    total = db.query(Prediction).filter_by(user_id=user.user_id).count()
    average = db.query(func.avg(PredictionResult.merge_probability)).join(Prediction).filter(Prediction.user_id == user.user_id).scalar()
    recent = db.query(Prediction).filter_by(user_id=user.user_id).order_by(Prediction.created_at.desc()).limit(5).all()
    return {"totalPredictions": total, "averageMergeProbability": round(float(average), 2) if average is not None else None, "usage": {"predictionsUsed": usage.predictions_used, "creditsUsed": usage.credits_used, "creditLimit": subscription.plan.monthly_credits, "creditsRemaining": max(0, subscription.plan.monthly_credits - usage.credits_used)}, "subscription": _subscription_dict(subscription), "recentPredictions": [_prediction_dict(item) for item in recent]}


@app.get("/admin/api/stats")
def admin_stats(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"users": db.query(User).count(), "predictions": db.query(Prediction).count(), "models": db.query(MLModel).filter_by(active=True).count(), "plans": db.query(Plan).filter_by(active=True).count()}


def _models_for_plan(db: Session, codes: list[str]) -> list[MLModel]:
    result = []
    seen = set()
    for code in codes:
        model = db.query(MLModel).filter_by(code=code.strip().lower()).first()
        if not model:
            raise HTTPException(status_code=404, detail=f"Model not found: {code}")
        if model.model_id not in seen:
            result.append(model)
            seen.add(model.model_id)
    return result


def _check_plan_parent(plan: Plan, parent: Optional[Plan]) -> None:
    seen = set()
    while parent:
        if parent.plan_id == plan.plan_id:
            raise HTTPException(status_code=400, detail="A plan cannot inherit from itself")
        if parent.plan_id in seen:
            raise HTTPException(status_code=409, detail="Plan inheritance contains a cycle")
        seen.add(parent.plan_id)
        parent = parent.parent


def _admin_plan_dict(plan: Plan) -> dict:
    return {"planId": plan.plan_id, "code": plan.code, "name": plan.name,
            "monthlyCredits": plan.monthly_credits, "description": plan.description,
            "active": plan.active, "parentPlanCode": plan.parent.code if plan.parent else None,
            "directModels": [_model_dict(model) for model in plan.models],
            "models": [_model_dict(model) for model in _resolved_plan_models(plan)]}


@app.get("/admin/api/plans")
def admin_plans(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_admin_plan_dict(plan) for plan in db.query(Plan).order_by(Plan.monthly_credits).all()]


@app.post("/admin/api/plans", status_code=status.HTTP_201_CREATED)
def admin_create_plan(data: PlanCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    code = data.code.strip().upper()
    if db.query(Plan).filter_by(code=code).first():
        raise HTTPException(status_code=409, detail="Plan code is already in use")
    parent = db.query(Plan).filter_by(code=data.parent_plan_code.strip().upper()).first() if data.parent_plan_code else None
    if data.parent_plan_code and not parent:
        raise HTTPException(status_code=404, detail="Parent plan not found")
    plan = Plan(code=code, name=data.name.strip(), monthly_credits=data.monthly_credits,
                monthly_prediction_limit=data.monthly_credits, description=(data.description or "").strip(),
                active=data.active, parent=parent, models=_models_for_plan(db, data.model_codes))
    if not plan.name:
        raise HTTPException(status_code=400, detail="Plan name cannot be blank")
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return _admin_plan_dict(plan)


@app.patch("/admin/api/plans/{plan_id}")
def admin_update_plan(plan_id: str, data: PlanUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    plan = db.query(Plan).filter_by(plan_id=plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    values = data.model_dump(exclude_unset=True, by_alias=False)
    if "code" in values:
        values["code"] = values["code"].strip().upper()
        if db.query(Plan).filter(Plan.code == values["code"], Plan.plan_id != plan_id).first():
            raise HTTPException(status_code=409, detail="Plan code is already in use")
    if "name" in values:
        values["name"] = values["name"].strip()
        if not values["name"]:
            raise HTTPException(status_code=400, detail="Plan name cannot be blank")
    if "parent_plan_code" in values:
        parent = db.query(Plan).filter_by(code=values["parent_plan_code"].strip().upper()).first() if values["parent_plan_code"] else None
        if values["parent_plan_code"] and not parent:
            raise HTTPException(status_code=404, detail="Parent plan not found")
        _check_plan_parent(plan, parent)
        plan.parent = parent
        values.pop("parent_plan_code")
    if "model_codes" in values:
        plan.models = _models_for_plan(db, values.pop("model_codes") or [])
    if "monthly_credits" in values:
        plan.monthly_prediction_limit = values["monthly_credits"]
    for key, value in values.items():
        setattr(plan, key, value)
    db.commit()
    db.refresh(plan)
    return _admin_plan_dict(plan)


@app.delete("/admin/api/plans/{plan_id}")
def admin_delete_plan(plan_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    plan = db.query(Plan).filter_by(plan_id=plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan.code == "FREE":
        raise HTTPException(status_code=400, detail="The FREE plan cannot be deleted")
    plan.active = False
    db.commit()
    db.refresh(plan)
    return {"message": "Plan deactivated", "plan": _admin_plan_dict(plan)}


@app.get("/admin/api/users")
def admin_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_public_user(user) for user in db.query(User).order_by(User.created_at.desc()).all()]


def _validate_model_task_type(task_type: str) -> str:
    task_type = task_type.upper().strip()
    if task_type not in ALLOWED_PREDICTION_TYPES:
        raise HTTPException(status_code=400, detail="taskType must be MERGE_PROBABILITY, PR_QUALITY, or BOTH")
    return task_type


def _admin_model_dict(model: MLModel) -> dict:
    item = _model_dict(model)
    item.update({
        "active": model.active,
        "createdAt": model.created_at.isoformat() if model.created_at else None,
        "retiredAt": model.retired_at.isoformat() if model.retired_at else None,
    })
    return item


@app.get("/admin/api/models")
def admin_models(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(MLModel).order_by(MLModel.active.desc(), MLModel.name)
    return [_admin_model_dict(model) for model in query.all()]


@app.post("/admin/api/models", status_code=status.HTTP_201_CREATED)
def admin_create_model(data: ModelCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    code = data.code.strip().lower()
    name = data.name.strip()
    version = data.version.strip()
    if not code or not name or not version:
        raise HTTPException(status_code=400, detail="Model code, name, and version cannot be blank")
    if db.query(MLModel).filter_by(code=code).first():
        raise HTTPException(status_code=409, detail="Model code is already in use")
    model = MLModel(code=code, name=name, task_type=_validate_model_task_type(data.task_type), version=version, provider=data.provider, description=data.description, credit_cost=data.credit_cost, artifact_key=data.artifact_key or code, active=data.active)
    if not model.active:
        model.retired_at = datetime.utcnow()
    db.add(model)
    db.commit()
    db.refresh(model)
    return _admin_model_dict(model)


@app.patch("/admin/api/models/{model_id}")
def admin_update_model(model_id: str, data: ModelUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    model = db.query(MLModel).filter_by(model_id=model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    values = data.model_dump(exclude_unset=True, by_alias=False)
    if "code" in values:
        code = values["code"].strip().lower()
        if not code:
            raise HTTPException(status_code=400, detail="Model code cannot be blank")
        duplicate = db.query(MLModel).filter(MLModel.code == code, MLModel.model_id != model_id).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Model code is already in use")
        values["code"] = code
    if "name" in values:
        values["name"] = values["name"].strip()
        if not values["name"]:
            raise HTTPException(status_code=400, detail="Model name cannot be blank")
    if "version" in values:
        values["version"] = values["version"].strip()
        if not values["version"]:
            raise HTTPException(status_code=400, detail="Model version cannot be blank")
    if "task_type" in values:
        values["task_type"] = _validate_model_task_type(values["task_type"])
    if "artifact_key" in values and values["artifact_key"]:
        values["artifact_key"] = values["artifact_key"].strip().lower()
    for key, value in values.items():
        setattr(model, key, value)
    if data.active is False:
        model.retired_at = model.retired_at or datetime.utcnow()
    elif data.active is True:
        model.retired_at = None
    db.commit()
    db.refresh(model)
    return _admin_model_dict(model)


@app.delete("/admin/api/models/{model_id}")
def admin_delete_model(model_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    model = db.query(MLModel).filter_by(model_id=model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    model.active = False
    model.retired_at = model.retired_at or datetime.utcnow()
    db.commit()
    db.refresh(model)
    return {"message": "Model deactivated", "model": _admin_model_dict(model)}


@app.patch("/admin/api/users/{user_id}/role")
def admin_change_role(user_id: str, body: dict, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    role = str(body.get("role", "")).upper()
    if role not in {"USER", "ADMIN"}:
        raise HTTPException(status_code=400, detail="role must be USER or ADMIN")
    user = db.query(User).filter_by(user_id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = role
    db.commit()
    return _public_user(user)


@app.get("/admin/api/predictions")
def admin_predictions(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(Prediction).order_by(Prediction.created_at.desc()).limit(100).all()
    return [{"predictionId": p.prediction_id, "username": p.user.username if p.user else None, "status": p.status, "predictionType": p.prediction_type, "createdAt": p.created_at.isoformat() if p.created_at else None} for p in query]

if ADMIN_DIR.exists():
    app.mount("/admin", StaticFiles(directory=ADMIN_DIR, html=True), name="admin")
