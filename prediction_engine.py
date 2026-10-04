"""Small adapter around the classifiers built in models(notebook)/EDA_MY.ipynb."""

from functools import lru_cache
from pathlib import Path


DATA_FILE = Path(__file__).parent / "models(notebook)" / "final_df.csv"
MODEL_DIR = Path(__file__).parent / "trained_models"
NUMERIC = [
    "title_word_count", "body_word_count", "total_lines_added",
    "total_lines_deleted", "total_lines_changed", "total_files_touched",
    "files_added", "files_modified", "files_deleted", "total_commits",
    "stars", "forks",
]
CATEGORICAL = ["agent", "task_type", "language"]
MODEL_NAMES = {
    "model-1": "logistic-regression",
    "model-2": "random-forest",
    "model-3": "knn",
    "model-4": "decision-tree",
    "model-5": "sgd-classifier",
    "model-6": "extra-trees",
    "logistic-regression": "logistic-regression",
    "random-forest": "random-forest",
    "knn": "knn",
    "decision-tree": "decision-tree",
    "sgd-classifier": "sgd-classifier",
    "extra-trees": "extra-trees",
}


def _number(values, *names):
    for name in names:
        try:
            if name in values:
                return float(values[name] or 0)
        except (TypeError, ValueError):
            pass
    return 0.0


def _row(values):
    """Translate API feature names to the notebook's column names."""
    row = {
        "title_word_count": _number(values, "title_word_count", "titleWordCount"),
        "body_word_count": _number(values, "body_word_count", "bodyWordCount"),
        "total_lines_added": _number(values, "total_lines_added", "totalLinesAdded", "additions"),
        "total_lines_deleted": _number(values, "total_lines_deleted", "totalLinesDeleted", "deletions"),
        "total_lines_changed": _number(values, "total_lines_changed", "totalLinesChanged"),
        "total_files_touched": _number(values, "total_files_touched", "totalFilesTouched", "changedFiles"),
        "files_added": _number(values, "files_added", "filesAdded"),
        "files_modified": _number(values, "files_modified", "filesModified"),
        "files_deleted": _number(values, "files_deleted", "filesDeleted"),
        "total_commits": _number(values, "total_commits", "totalCommits"),
        "stars": _number(values, "stars"),
        "forks": _number(values, "forks"),
        "agent": str(values.get("agent", "unknown")),
        "task_type": str(values.get("task_type", values.get("taskType", "unknown"))),
        "language": str(values.get("language", "unknown")),
    }
    if not row["total_lines_changed"]:
        row["total_lines_changed"] = row["total_lines_added"] + row["total_lines_deleted"]
    return row


def _classifier(name):
    from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression, SGDClassifier
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.tree import DecisionTreeClassifier

    if name == "random-forest":
        return RandomForestClassifier(n_estimators=100, class_weight="balanced", random_state=42, n_jobs=-1)
    if name == "knn":
        return KNeighborsClassifier(n_neighbors=5)
    if name == "decision-tree":
        return DecisionTreeClassifier(max_depth=10, class_weight="balanced", random_state=42)
    if name == "sgd-classifier":
        return SGDClassifier(loss="log_loss", class_weight="balanced", max_iter=2000, random_state=42)
    if name == "extra-trees":
        return ExtraTreesClassifier(n_estimators=80, class_weight="balanced", random_state=42, n_jobs=-1)
    return LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)


@lru_cache(maxsize=8)
def _pipeline(model_name):
    """Load a saved notebook model, or fit that same pipeline from its CSV."""
    import joblib
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, RobustScaler

    saved = MODEL_DIR / f"{model_name}.joblib"
    if saved.exists():
        return joblib.load(saved)
    if not DATA_FILE.exists():
        raise FileNotFoundError(DATA_FILE)
    frame = pd.read_csv(DATA_FILE).drop(columns=["id", "body_char_count", "body_is_empty"], errors="ignore")
    frame = frame.drop_duplicates().dropna()
    numeric = Pipeline([( "inputer", SimpleImputer(strategy="median")), ("scaler", RobustScaler())])
    categorical = Pipeline([( "inputer", SimpleImputer(strategy="most_frequent")), ("encoder", OneHotEncoder(handle_unknown="ignore", drop="first", sparse_output=False))])
    preprocessor = ColumnTransformer([("num", numeric, NUMERIC), ("cat", categorical, CATEGORICAL)])
    pipeline = Pipeline([("preprocessor", preprocessor), ("model", _classifier(model_name))])
    x_train, _, y_train, _ = train_test_split(frame[NUMERIC + CATEGORICAL], frame["label"], test_size=0.33, random_state=42)
    pipeline.fit(x_train, y_train)
    return pipeline


def predict(features, model_key="model-1"):
    # The public prediction helper can be called with a PR URL directly.
    if isinstance(features, str):
        from github_api import get_pull_request
        features = get_pull_request(features)[2]
    row = _row(features)
    model_name = MODEL_NAMES.get((model_key or "model-1").lower())
    if not model_name:
        raise ValueError("Unknown notebook model")
    import pandas as pd
    pipeline = _pipeline(model_name)
    values = pipeline.predict_proba(pd.DataFrame([row]))[0]
    classes = list(pipeline.classes_)
    score = float(values[classes.index(1)]) * 100
    score = round(max(0.0, min(100.0, score)), 2)
    factors = [
        {"factor_name": "Change size", "description": f"{int(row['total_files_touched'])} files and {int(row['total_lines_changed'])} changed lines were considered.", "impact": "NEGATIVE" if row["total_files_touched"] > 12 else "POSITIVE"},
        {"factor_name": "Repository context", "description": f"The notebook model used {row['language']} and {row['task_type']} as categorical features.", "impact": "NEUTRAL"},
    ]
    return score, score, factors
