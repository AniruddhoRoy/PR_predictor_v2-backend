"""Reproduce EDA_MY.ipynb cells 43-51 and export each fitted pipeline."""
import hashlib
import json
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, RobustScaler
from sklearn.tree import DecisionTreeClassifier

from prediction_engine import NUMERIC_FEATURES, CATEGORICAL_FEATURES, ARTIFACT_DIR, ARTIFACTS


def train():
    source = Path(__file__).parent / 'models(notebook)' / 'final_df.csv'
    df = pd.read_csv(source).drop(columns=['id', 'body_char_count', 'body_is_empty'])
    df = df.drop_duplicates().dropna()
    X = df.drop(columns=['label'])
    y = df['label']
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.33, random_state=42)
    preprocessing = ColumnTransformer([
        ('num', Pipeline([('imputer', SimpleImputer(strategy='median')), ('scaler', RobustScaler())]), NUMERIC_FEATURES),
        ('cat', Pipeline([('imputer', SimpleImputer(strategy='most_frequent')),
                          ('encoder', OneHotEncoder(handle_unknown='ignore', drop='first', sparse_output=False))]), CATEGORICAL_FEATURES),
    ])
    classifiers = {
        'logistic-regression': LogisticRegression(max_iter=1000, class_weight='balanced', random_state=42),
        'random-forest': RandomForestClassifier(n_estimators=100, class_weight='balanced', random_state=42, n_jobs=-1),
        'knn': KNeighborsClassifier(n_neighbors=5),
        'decision-tree': DecisionTreeClassifier(max_depth=10, class_weight='balanced', random_state=42),
        'sgd-classifier': SGDClassifier(loss='log_loss', class_weight='balanced', max_iter=2000, random_state=42),
    }
    ARTIFACT_DIR.mkdir(exist_ok=True)
    report = {'source': 'models(notebook)/EDA_MY.ipynb', 'datasetSha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'sklearnVersion': sklearn.__version__, 'trainingRows': len(X_train), 'testRows': len(X_test),
              'features': list(X.columns), 'label': {'0': 'not merged', '1': 'merged'}, 'models': {}}
    for key, clf in classifiers.items():
        # Each saved pipeline owns its fitted preprocessing; it is not shared with later fits.
        pipeline = Pipeline([('preprocessor', clone(preprocessing)), ('model', clf)])
        pipeline.fit(X_train, y_train)
        predicted = pipeline.predict(X_test)
        artifact = ARTIFACT_DIR / f'{key}.joblib'
        joblib.dump(pipeline, artifact, compress=3)
        report['models'][key] = {'name': ARTIFACTS[key], 'version': 'notebook-v1',
                                 'accuracy': accuracy_score(y_test, predicted),
                                 'classificationReport': classification_report(y_test, predicted, output_dict=True),
                                 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}
        print(key, round(report['models'][key]['accuracy'], 4), flush=True)
    (ARTIFACT_DIR / 'training_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    train()
