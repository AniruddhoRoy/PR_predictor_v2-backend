"""Simple PR prediction backend.

The service intentionally keeps the workflow synchronous and understandable:
request -> call the hosted analyzer -> save result and charge credits.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, inspect, or_, text
from sqlalchemy.orm import Session

from auth import create_token, hash_password, read_token, verify_password
from database import Base, SessionLocal, engine, get_db
from models import (
    MLModel, Plan, Prediction, PredictionResult, Subscription, UsagePeriod, User, UserSetting,
)
from schemas import (
    ChangePasswordRequest, LoginRequest, PredictionRequest, ProfileUpdate, RegisterRequest,
    SettingsUpdate, SubscriptionUpdate, ModelCreate, ModelUpdate, PlanCreate, PlanUpdate,
)
from analysis_api import analyze_pr


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
ALLOWED_PREDICTION_TYPES = {"MERGE_PROBABILITY", "PR_QUALITY", "BOTH"}


@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    migrate_schema()
    seed_database()

# ! ############################################ Ignore it [Start] #############################################################

def migrate_schema():
    """Add the few new columns when an older local SQLite database is reused."""
    additions = {
        "plans": {"monthly_credits": "INTEGER DEFAULT 5", "parent_plan_id": "VARCHAR(36)"},
        "models": {"credit_cost": "INTEGER DEFAULT 1", "artifact_key": "VARCHAR(80)"},
        "usage_periods": {"credits_used": "INTEGER DEFAULT 0", "credit_limit_snapshot": "INTEGER DEFAULT 5"},
        "predictions": {"credits_cost": "INTEGER DEFAULT 1", "inference_key": "VARCHAR(80)"},
        "prediction_results": {"analysis_response": "JSON"},
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
        models = []
        for number in range(1, 7):
            code = f"model-{number}"
            model = db.query(MLModel).filter_by(code=code).first()
            if not model:
                model = MLModel(code=code, name=f"Model {number}", task_type="BOTH", version="1.0",
                                provider="gemini-api", credit_cost=1, description="Hosted Gemini PR analysis.")
                db.add(model)
            elif model.provider == "notebook":
                # Keep existing plan assignments and prices when retiring local inference.
                model.provider = "gemini-api"
                model.artifact_key = None
                model.description = "Hosted Gemini PR analysis."
                if model.name.startswith(f"Model {number} - "):
                    model.name = f"Model {number}"
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
                if plan.credits is None:
                    plan.credits = credits
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

# ! ############################################ Ignore it [End] #############################################################
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
        _start_subscription(db, user, free)
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


@app.post("/change-password")
def change_password(data: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "Password changed successfully"}


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
    allowed = {"theme_mode": {"LIGHT", "DARK"}, "default_prediction_type": ALLOWED_PREDICTION_TYPES, "default_input_mode": {"GITHUB_URL"}}
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
    return {"themeMode": settings.theme_mode, "notificationsEnabled": settings.notifications_enabled, "defaultPredictionType": settings.default_prediction_type, "defaultInputMode": "GITHUB_URL"}


#! prediction_type: Optional[str] = Query(default=None, alias="predictionType") query parameter
@app.get("/models")
def models(prediction_type: Optional[str] = Query(default=None, alias="predictionType"), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    plan = _active_subscription(db, user).plan
    allowed_ids = {item.model_id for item in plan.models}
    query = db.query(MLModel).filter(MLModel.active.is_(True), MLModel.model_id.in_(allowed_ids))
    if prediction_type:
        prediction_type = prediction_type.upper()
        if prediction_type not in ALLOWED_PREDICTION_TYPES:
            raise HTTPException(400, "Invalid predictionType")
    return [_model_dict(item) for item in query.order_by(MLModel.name).all()]


def _model_dict(model: MLModel) -> dict:
    return {"modelId": model.model_id, "code": model.code, "name": model.name, "version": model.version, "provider": model.provider, "description": model.description, "creditCost": model.credit_cost}


@app.get("/subscription")
def get_subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    subscription = _active_subscription(db, user)
    return _subscription_dict(subscription)


@app.get("/active-plan")
@app.get("/plan")
def active_plan(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    subscription = _active_subscription(db, user)
    plan = subscription.plan
    usage = _get_usage(db, subscription)
    result = _plan_dict(plan)
    result.update(creditsUsed=usage.credits_used, creditsRemaining=max(0, plan.credits - usage.credits_used))
    return result


@app.get("/plans")
def available_plans(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_plan_dict(plan) for plan in db.query(Plan).filter_by(active=True).order_by(Plan.credits).all()]


@app.post("/subscription")
def change_subscription(data: SubscriptionUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = db.query(Plan).filter_by(code=data.plan_code.upper(), active=True).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    old = _active_subscription(db, user)
    if old.plan_id == plan.plan_id:
        return _subscription_dict(old)
    credits_used = _get_usage(db, old).credits_used
    old.status = "CANCELLED"
    old.ended_at = datetime.utcnow()
    subscription = _start_subscription(db, user, plan, credits_used)
    db.commit()
    return _subscription_dict(subscription)


def _start_subscription(db: Session, user: User, plan: Plan, credits_used: int = 0) -> Subscription:
    now = datetime.utcnow()
    subscription = Subscription(user_id=user.user_id, plan=plan, status="ACTIVE",
                                started_at=now, ended_at=now + timedelta(days=plan.duration))
    db.add(subscription)
    db.add(UsagePeriod(user_id=user.user_id, time_stamp=now, credits_used=credits_used))
    db.flush()
    return subscription


def _active_subscription(db: Session, user: User) -> Subscription:
    subscription = db.query(Subscription).filter_by(user_id=user.user_id, status="ACTIVE").order_by(Subscription.started_at.desc()).first()
    if subscription and subscription.ended_at > datetime.utcnow() and subscription.plan.active:
        return subscription
    if subscription:
        subscription.status = "EXPIRED"
    plan = db.query(Plan).filter_by(code="FREE", active=True).first()
    if not plan:
        raise HTTPException(404, "The FREE plan is unavailable")
    subscription = _start_subscription(db, user, plan)
    db.commit()
    return subscription


def _subscription_dict(subscription: Subscription) -> dict:
    return {"subscriptionId": subscription.subscription_id, "status": subscription.status,
            "startedAt": subscription.started_at.isoformat(), "endedAt": subscription.ended_at.isoformat(),
            "plan": _plan_dict(subscription.plan)}


def _plan_dict(plan: Plan) -> dict:
    return {"planId": plan.plan_id, "code": plan.code, "name": plan.name,
            "credits": plan.credits, "duration": plan.duration, "description": plan.description,
            "models": [_model_dict(model) for model in sorted(plan.models, key=lambda item: item.name.lower())]}


def _prediction_request(body: PredictionRequest | str) -> PredictionRequest:
    if isinstance(body, str) and not body.strip():
        raise HTTPException(422, "A GitHub pull request URL is required")
    data = PredictionRequest(pullRequestUrl=body) if isinstance(body, str) else body
    data.prediction_type = data.prediction_type.upper()
    if data.prediction_type not in ALLOWED_PREDICTION_TYPES:
        raise HTTPException(400, "predictionType must be MERGE_PROBABILITY, PR_QUALITY, or BOTH")
    return data


def _analysis_fields(response: dict, prediction_type: str) -> dict:
    """Map analyzer fields for database storage and history records."""
    features, analysis = response["features"], response["analysis"]
    owner, name, _, number = response["pr_url"].rstrip("/").split("/")[3:]
    return {
        "repository": {"owner": owner, "name": name, "url": f"https://github.com/{owner}/{name}"},
        "pullRequest": {"number": int(number), "url": response["pr_url"],
                        "title": features.get("title") or f"Pull request #{number}",
                        "state": "MERGED" if features.get("merged") else (features.get("state") or "open").upper(),
                        "authorLogin": features.get("author")},
        "features": features,
        "mergeProbability": None if prediction_type == "PR_QUALITY" else analysis["merge_probability"],
        "qualityScore": None if prediction_type == "MERGE_PROBABILITY" else analysis["quality_score"],
        "qualityLabel": analysis["quality"],
        "recommendation": analysis["summary"],
        "analysis": analysis,
        "probabilityNote": response.get("probability_note"),
    }


@app.post("/predict-dev")
def predict_dev(body: PredictionRequest | str = Body(...)):
    """Call the same service without login, credit charging, or saved history."""
    data = _prediction_request(body)
    return analyze_pr(data.pull_request_url)


@app.post("/predict")
def predict(body: PredictionRequest | str = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    request_data = _prediction_request(body)
    prediction_type = request_data.prediction_type
    subscription = _active_subscription(db, user)
    plan = subscription.plan
    model = _choose_model(db, request_data.model_id, plan)
    usage = _get_usage(db, subscription)
    if usage.credits_used + model.credit_cost > plan.credits:
        raise HTTPException(status_code=429, detail="Not enough credits for this model")
    # Release the database write lock while the external service is working.
    db.commit()
    response = analyze_pr(request_data.pull_request_url)
    fields = _analysis_fields(response, prediction_type)
    # The plan may have expired or changed while the analyzer was running.
    if not db.query(Subscription).filter(Subscription.subscription_id == subscription.subscription_id,
                                        Subscription.status == "ACTIVE", Subscription.ended_at > datetime.utcnow()).first():
        raise HTTPException(409, "Your subscription changed or expired; try again")
    prediction = Prediction(user_id=user.user_id, usage_period_id=usage.usage_period_id, model_id=model.model_id,
                            pr_url=response["pr_url"], title=fields["pullRequest"]["title"], prediction_type=prediction_type,
                            status="COMPLETED", model_version=model.version, credits_cost=model.credit_cost,
                            inference_key="gemini-api", completed_at=datetime.utcnow())
    db.add(prediction)
    db.flush()
    db.add(PredictionResult(prediction_id=prediction.prediction_id, merge_probability=fields["mergeProbability"],
                           quality_score=fields["qualityScore"], quality_label=fields["qualityLabel"],
                           recommendation=fields["recommendation"], analysis_response=response))
    # Reserve credits atomically so simultaneous requests cannot overspend.
    charged = db.query(UsagePeriod).filter(
        UsagePeriod.usage_period_id == usage.usage_period_id,
        UsagePeriod.credits_used + model.credit_cost <= plan.credits,
    ).update({UsagePeriod.credits_used: UsagePeriod.credits_used + model.credit_cost}, synchronize_session=False)
    if not charged:
        db.rollback()
        raise HTTPException(status_code=429, detail="Not enough credits for this model")
    db.commit()
    return response


def _choose_model(db: Session, model_id: Optional[str], plan: Plan) -> MLModel:
    allowed = plan.models
    allowed_ids = {item.model_id for item in allowed}
    query = db.query(MLModel).filter(MLModel.active.is_(True), MLModel.model_id.in_(allowed_ids))
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
        raise HTTPException(status_code=404, detail="Your active plan has no active model")
    return model


def _get_usage(db: Session, subscription: Subscription) -> UsagePeriod:
    usage = db.query(UsagePeriod).filter_by(user_id=subscription.user_id, time_stamp=subscription.started_at).first()
    if not usage:
        usage = UsagePeriod(user_id=subscription.user_id, time_stamp=subscription.started_at, credits_used=0)
        db.add(usage)
        db.flush()
    return usage


@app.get("/history")
@app.get("/predictions")
def history(search: Optional[str] = None, limit: int = Query(default=20, ge=1, le=100), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Prediction).filter(Prediction.user_id == user.user_id).order_by(Prediction.created_at.desc())
    if search:
        query = query.filter(or_(Prediction.pr_url.ilike(f"%{search}%"), Prediction.title.ilike(f"%{search}%")))
    return [_prediction_dict(item) for item in query.limit(limit).all()]


@app.get("/predictions/{prediction_id}")
def prediction_detail(prediction_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    prediction = db.query(Prediction).filter_by(prediction_id=prediction_id, user_id=user.user_id).first()
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return _prediction_dict(prediction)


def _prediction_dict(prediction: Prediction) -> dict:
    result = prediction.result
    data = {
        "predictionId": prediction.prediction_id,
        "status": prediction.status,
        "predictionType": prediction.prediction_type,
        "createdAt": prediction.created_at.isoformat() if prediction.created_at else None,
        "completedAt": prediction.completed_at.isoformat() if prediction.completed_at else None,
        "modelVersion": prediction.model_version,
        "creditsCost": prediction.credits_cost,
        "inferenceKey": prediction.inference_key,
        "model": _model_dict(prediction.model) if prediction.model else None,
        "pr_url": prediction.pr_url,
        "title": prediction.title,
        "features": {},
        "mergeProbability": float(result.merge_probability) if result and result.merge_probability is not None else None,
        "qualityScore": float(result.quality_score) if result and result.quality_score is not None else None,
        "qualityLabel": result.quality_label if result else None,
        "recommendation": result.recommendation if result else None,
    }
    if result and result.analysis_response:
        data.update(_analysis_fields(result.analysis_response, prediction.prediction_type))
    return data


@app.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    subscription = _active_subscription(db, user)
    usage = _get_usage(db, subscription)
    total = db.query(Prediction).filter_by(user_id=user.user_id).count()
    average = db.query(func.avg(PredictionResult.merge_probability)).join(Prediction).filter(Prediction.user_id == user.user_id).scalar()
    recent = db.query(Prediction).filter_by(user_id=user.user_id).order_by(Prediction.created_at.desc()).limit(5).all()
    return {"totalPredictions": total, "averageMergeProbability": round(float(average), 2) if average is not None else None, "usage": {"predictionsUsed": db.query(Prediction).filter_by(usage_period_id=usage.usage_period_id).count(), "creditsUsed": usage.credits_used, "creditLimit": subscription.plan.credits, "creditsRemaining": max(0, subscription.plan.credits - usage.credits_used)}, "subscription": _subscription_dict(subscription), "recentPredictions": [_prediction_dict(item) for item in recent]}


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


def _admin_plan_dict(plan: Plan) -> dict:
    return {**_plan_dict(plan), "active": plan.active}


@app.get("/admin/api/plans")
def admin_plans(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_admin_plan_dict(plan) for plan in db.query(Plan).order_by(Plan.credits).all()]


@app.post("/admin/api/plans", status_code=status.HTTP_201_CREATED)
def admin_create_plan(data: PlanCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    code = data.code.strip().upper()
    if db.query(Plan).filter_by(code=code).first():
        raise HTTPException(status_code=409, detail="Plan code is already in use")
    plan = Plan(code=code, name=data.name.strip(), credits=data.credits, duration=data.duration,
                description=(data.description or "").strip(), active=data.active,
                models=_models_for_plan(db, data.model_codes))
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
    if any(value is None for key, value in values.items() if key not in {"description", "model_codes"}):
        raise HTTPException(422, "Required fields cannot be null")
    if "code" in values:
        values["code"] = values["code"].strip().upper()
        if plan.code == "FREE" and values["code"] != "FREE":
            raise HTTPException(400, "The FREE plan cannot be renamed")
        if db.query(Plan).filter(Plan.code == values["code"], Plan.plan_id != plan_id).first():
            raise HTTPException(status_code=409, detail="Plan code is already in use")
    if "name" in values:
        values["name"] = values["name"].strip()
        if not values["name"]:
            raise HTTPException(status_code=400, detail="Plan name cannot be blank")
    if "model_codes" in values:
        plan.models = _models_for_plan(db, values.pop("model_codes") or [])
    if plan.code == "FREE" and values.get("active") is False:
        raise HTTPException(400, "The FREE plan cannot be deactivated")
    if values.get("description") is None and "description" in values:
        values["description"] = ""
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
    model = MLModel(code=code, name=name, version=version, provider=data.provider, description=data.description, credit_cost=data.credit_cost, active=data.active)
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
    if any(value is None for key, value in values.items() if key not in {"description", "model_codes"}):
        raise HTTPException(422, "Required fields cannot be null")
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
