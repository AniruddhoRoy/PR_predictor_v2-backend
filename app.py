"""Simple PR prediction backend.

The service intentionally keeps the workflow synchronous and understandable:
request -> validate -> calculate demo scores -> persist -> return result.
"""

import hashlib
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_
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
    SettingsUpdate, SubscriptionUpdate,
)


app = FastAPI(title="PR Predictor API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ADMIN_DIR = Path(__file__).parent / "admin"

bearer = HTTPBearer(auto_error=False)
GITHUB_PR_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$", re.I)
ALLOWED_PREDICTION_TYPES = {"MERGE_PROBABILITY", "PR_QUALITY", "BOTH"}


@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    seed_database()


def seed_database():
    db = SessionLocal()
    try:
        if not db.query(Plan).filter_by(code="FREE").first():
            db.add(Plan(code="FREE", name="Free", monthly_prediction_limit=5, description="5 predictions each month"))
        if not db.query(Plan).filter_by(code="PREMIUM").first():
            db.add(Plan(code="PREMIUM", name="Premium", monthly_prediction_limit=None, description="Unlimited predictions for the demo"))
        if not db.query(MLModel).filter_by(code="merge-probability-v1").first():
            db.add(MLModel(code="merge-probability-v1", name="PR Predictor Demo", task_type="BOTH", version="1.0", provider="local", description="A deterministic demo model based on submitted features."))
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


def _token_response(user: User) -> dict:
    return {"accessToken": create_token(user.user_id, user.role), "tokenType": "bearer", "user": _public_user(user)}


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


@app.patch("/profile")
def update_profile(data: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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


@app.get("/models")
def models(prediction_type: Optional[str] = Query(default=None, alias="predictionType"), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(MLModel).filter_by(active=True)
    if prediction_type:
        prediction_type = prediction_type.upper()
        query = query.filter(or_(MLModel.task_type == "BOTH", MLModel.task_type == prediction_type))
    return [_model_dict(item) for item in query.order_by(MLModel.name).all()]


def _model_dict(model: MLModel) -> dict:
    return {"modelId": model.model_id, "code": model.code, "name": model.name, "taskType": model.task_type, "version": model.version, "provider": model.provider, "description": model.description}


@app.get("/subscription")
def get_subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    subscription = _active_subscription(db, user)
    return _subscription_dict(subscription)


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
    return {"subscriptionId": subscription.subscription_id, "status": subscription.status, "startedAt": subscription.started_at.isoformat(), "plan": {"code": subscription.plan.code, "name": subscription.plan.name, "monthlyPredictionLimit": subscription.plan.monthly_prediction_limit, "description": subscription.plan.description}}


@app.post("/predict")
def predict(body: Any = Body(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    request_data = _prediction_request(body)
    input_type = request_data.input_type.upper()
    prediction_type = request_data.prediction_type.upper()
    if input_type not in {"GITHUB_URL", "MANUAL_FEATURES"}:
        raise HTTPException(status_code=400, detail="inputType must be GITHUB_URL or MANUAL_FEATURES")
    if prediction_type not in ALLOWED_PREDICTION_TYPES:
        raise HTTPException(status_code=400, detail="predictionType must be MERGE_PROBABILITY, PR_QUALITY, or BOTH")
    subscription = _active_subscription(db, user)
    usage = _get_usage(db, user, subscription.plan.monthly_prediction_limit)
    if usage.limit_snapshot is not None and usage.predictions_used >= usage.limit_snapshot:
        raise HTTPException(status_code=429, detail="Monthly prediction limit reached")
    model = _choose_model(db, request_data.model_id, prediction_type)
    parsed_url = None
    features: dict[str, Any]
    raw_feature_text = None
    if input_type == "GITHUB_URL":
        if not request_data.pull_request_url:
            raise HTTPException(status_code=400, detail="pullRequestUrl is required for GITHUB_URL")
        parsed_url = GITHUB_PR_RE.match(request_data.pull_request_url.strip())
        if not parsed_url:
            raise HTTPException(status_code=400, detail="Use a GitHub pull request URL such as https://github.com/owner/repo/pull/12")
        features = {"changedFiles": 4 + int(parsed_url.group(3)) % 18, "additions": 20 + int(parsed_url.group(3)) * 3 % 160, "deletions": 5 + int(parsed_url.group(3)) * 2 % 80, "testsAdded": int(parsed_url.group(3)) % 2 == 0}
    else:
        features = request_data.features or {}
        if not features:
            raise HTTPException(status_code=400, detail="features must contain at least one value for MANUAL_FEATURES")
        raw_feature_text = ", ".join(f"{key}={value}" for key, value in features.items())
    merge_score, quality_score, factors = _calculate_scores(features, request_data.pull_request_url or raw_feature_text or "")
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
    prediction = Prediction(user_id=user.user_id, usage_period_id=usage.usage_period_id, model_id=model.model_id, pull_request_id=pull_request.pull_request_id if pull_request else None, prediction_type=prediction_type, status="COMPLETED", model_version=model.version, completed_at=datetime.utcnow())
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
    usage.predictions_used += 1
    db.commit()
    db.refresh(prediction)
    return _prediction_dict(prediction)


def _prediction_request(body: Any) -> PredictionRequest:
    if isinstance(body, str):
        return PredictionRequest(inputType="GITHUB_URL", predictionType="BOTH", pullRequestUrl=body)
    try:
        return PredictionRequest.model_validate(body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Prediction body does not match the documented format") from exc


def _choose_model(db: Session, model_id: Optional[str], prediction_type: str) -> MLModel:
    query = db.query(MLModel).filter(MLModel.active.is_(True), or_(MLModel.task_type == "BOTH", MLModel.task_type == prediction_type))
    model = query.filter(or_(MLModel.model_id == model_id, MLModel.code == model_id)).first() if model_id else query.order_by(MLModel.created_at).first()
    if not model:
        raise HTTPException(status_code=404, detail="Prediction model not found")
    return model


def _get_usage(db: Session, user: User, limit: Optional[int]) -> UsagePeriod:
    today = date.today()
    period_start = today.replace(day=1)
    next_month = date(today.year + (1 if today.month == 12 else 0), 1 if today.month == 12 else today.month + 1, 1)
    usage = db.query(UsagePeriod).filter_by(user_id=user.user_id, period_start=period_start).first()
    if not usage:
        usage = UsagePeriod(user_id=user.user_id, period_start=period_start, period_end=next_month - timedelta(days=1), limit_snapshot=limit, predictions_used=0)
        db.add(usage)
        db.flush()
    return usage


def _feature_row(prediction_id: str, name: str, value: Any, source: str) -> PredictionFeature:
    if isinstance(value, bool):
        return PredictionFeature(prediction_id=prediction_id, feature_name=name, value_type="BOOLEAN", value_boolean=value, source=source)
    if isinstance(value, (int, float)):
        return PredictionFeature(prediction_id=prediction_id, feature_name=name, value_type="NUMBER", value_number=float(value), source=source)
    return PredictionFeature(prediction_id=prediction_id, feature_name=name, value_type="TEXT", value_text=str(value), source=source)


def _calculate_scores(features: dict[str, Any], seed: str) -> tuple[float, float, list[dict]]:
    def number(*names):
        for name in names:
            try:
                return float(features.get(name, 0) or 0)
            except (TypeError, ValueError):
                pass
        return 0.0
    changed = number("changedFiles", "changed_files")
    additions = number("additions", "linesAdded", "lines_added")
    deletions = number("deletions", "linesDeleted", "lines_deleted")
    tests = features.get("testsAdded", features.get("tests_added", False))
    tests_bonus = 8 if str(tests).lower() in {"true", "1", "yes"} else 0
    digest = int(hashlib.sha256(seed.encode()).hexdigest()[:4], 16)
    merge_score = max(5.0, min(98.0, 74.0 - changed * 0.8 - additions * 0.05 - deletions * 0.03 + tests_bonus + (digest % 11 - 5)))
    quality_score = max(5.0, min(98.0, 80.0 - changed * 0.7 - additions * 0.04 - deletions * 0.02 + tests_bonus))
    factors = [
        {"factor_name": "Change size", "description": f"{int(changed)} changed files and {int(additions + deletions)} line changes were considered.", "impact": "NEGATIVE" if changed > 12 else "POSITIVE"},
        {"factor_name": "Test coverage", "description": "Tests were included in the submitted features." if tests_bonus else "No added tests were reported in the submitted features.", "impact": "POSITIVE" if tests_bonus else "NEGATIVE"},
        {"factor_name": "Deletion balance", "description": f"The pull request reports {int(deletions)} deleted lines.", "impact": "POSITIVE" if deletions < additions else "NEUTRAL"},
    ]
    return round(merge_score, 2), round(quality_score, 2), factors


def _quality_label(score: float) -> str:
    return "Excellent" if score >= 80 else "Good" if score >= 65 else "Needs review" if score >= 50 else "Risky"


def _recommendation(merge_score: float, quality_score: float) -> str:
    if merge_score >= 75 and quality_score >= 70:
        return "Looks ready for review. Keep the existing tests and ask a reviewer to verify the edge cases."
    if merge_score >= 55:
        return "Review the change size and test coverage before merging."
    return "Add tests and split the change into smaller parts before merging."


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
    usage = _get_usage(db, user, subscription.plan.monthly_prediction_limit)
    total = db.query(Prediction).filter_by(user_id=user.user_id).count()
    average = db.query(func.avg(PredictionResult.merge_probability)).join(Prediction).filter(Prediction.user_id == user.user_id).scalar()
    recent = db.query(Prediction).filter_by(user_id=user.user_id).order_by(Prediction.created_at.desc()).limit(5).all()
    return {"totalPredictions": total, "averageMergeProbability": round(float(average), 2) if average is not None else None, "usage": {"used": usage.predictions_used, "limit": usage.limit_snapshot}, "subscription": _subscription_dict(subscription), "recentPredictions": [_prediction_dict(item) for item in recent]}


@app.get("/admin/api/stats")
def admin_stats(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"users": db.query(User).count(), "predictions": db.query(Prediction).count(), "models": db.query(MLModel).filter_by(active=True).count(), "plans": db.query(Plan).filter_by(active=True).count()}


@app.get("/admin/api/users")
def admin_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_public_user(user) for user in db.query(User).order_by(User.created_at.desc()).all()]


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
