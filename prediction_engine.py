"""Inference using the notebook pipelines, plus real GitHub feature retrieval."""
import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import joblib
import numpy as np
import pandas as pd
from fastapi import HTTPException

ARTIFACT_DIR = Path(__file__).parent / 'trained_models'
ARTIFACTS = {'logistic-regression': 'Logistic Regression', 'random-forest': 'Random Forest',
             'knn': 'KNN', 'decision-tree': 'Decision Tree', 'sgd-classifier': 'SGD Classifier'}
NUMERIC_FEATURES = ['title_word_count', 'body_word_count', 'total_lines_added', 'total_lines_deleted',
                    'total_lines_changed', 'total_files_touched', 'files_added', 'files_modified',
                    'files_deleted', 'total_commits', 'stars', 'forks']
CATEGORICAL_FEATURES = ['agent', 'task_type', 'language']
ALIASES = {'changedFiles': 'total_files_touched', 'additions': 'total_lines_added',
           'deletions': 'total_lines_deleted', 'commits': 'total_commits', 'taskType': 'task_type'}
PR_URL = re.compile(r'^https://github\.com/([\w.-]+)/([\w.-]+)/pull/([1-9]\d*)/?$', re.I)


def normalize_features(values):
    result = {}
    for supplied, value in values.items():
        name = ALIASES.get(supplied, supplied)
        if name not in NUMERIC_FEATURES + CATEGORICAL_FEATURES:
            # Historical UI used this field for the old demo; it is not a trained input.
            if name == 'testsAdded':
                continue
            raise HTTPException(422, f'Unknown feature: {supplied}')
        if value is None:
            continue
        if name in NUMERIC_FEATURES:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1e9:
                raise HTTPException(422, f'{supplied} must be a finite non-negative number no greater than 1000000000')
        elif not isinstance(value, str) or not value.strip() or len(value) > 100:
            raise HTTPException(422, f'{supplied} must be a non-empty string of at most 100 characters')
        result[name] = value
    if not result:
        raise HTTPException(422, 'Supply at least one recognized model feature')
    if 'total_lines_changed' not in result and all(k in result for k in ('total_lines_added', 'total_lines_deleted')):
        result['total_lines_changed'] = result['total_lines_added'] + result['total_lines_deleted']
    return result


def artifact_ready(key):
    return key in ARTIFACTS and (ARTIFACT_DIR / f'{key}.joblib').is_file()


@lru_cache(maxsize=10)
def _load_pipeline(key, modified):
    # Only locally exported, allowlisted artifacts can be selected by the web admin.
    return joblib.load(ARTIFACT_DIR / f'{key}.joblib')


def infer(key, features):
    if not artifact_ready(key):
        raise HTTPException(503, 'Trained model unavailable. Run python train_models.py first.')
    path = ARTIFACT_DIR / f'{key}.joblib'
    try:
        pipeline = _load_pipeline(key, path.stat().st_mtime_ns)
        row = pd.DataFrame([{name: features.get(name, np.nan) for name in NUMERIC_FEATURES + CATEGORICAL_FEATURES}])
        positive_index = list(pipeline.classes_).index(1)
        probability = float(pipeline.predict_proba(row)[0][positive_index]) * 100
    except Exception as exc:
        raise HTTPException(503, 'Trained model could not run. Re-export it with the installed dependencies.') from exc
    if not math.isfinite(probability):
        raise HTTPException(503, 'Trained model produced an invalid probability')
    # The notebook has no quality target: retain a simple, explicitly labelled rule score.
    changed = features.get('total_files_touched', 0)
    lines = features.get('total_lines_changed', 0)
    quality = round(max(5, min(95, 85 - changed * .7 - lines * .02)), 2)
    missing = [name for name in NUMERIC_FEATURES + CATEGORICAL_FEATURES if name not in features]
    factors = [dict(factor_name='Inference', description=f'Merge likelihood from the trained {ARTIFACTS[key]} pipeline. Quality uses change-size rules, not a trained quality model.', impact='NEUTRAL'),
               dict(factor_name='Feature coverage', description='Missing inputs imputed by the training pipeline: ' + (', '.join(missing) or 'none') + '. These notes are not model feature attributions.', impact='NEUTRAL')]
    return round(probability, 2), quality, factors


def github_get(path):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'university-pr-predictor'}
    if os.getenv('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    try:
        with urlopen(Request('https://api.github.com' + path, headers=headers), timeout=15) as response:
            return json.load(response)
    except HTTPError as exc:
        message = 'GitHub pull request not found or inaccessible' if exc.code == 404 else 'GitHub request failed or rate limit reached'
        raise HTTPException(502, message) from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(502, 'Unable to retrieve GitHub pull request data') from exc


def github_features(url, overrides=None):
    match = PR_URL.fullmatch(url.strip())
    if not match:
        raise HTTPException(422, 'Use https://github.com/owner/repo/pull/123')
    owner, repo, number = match.groups()
    if owner in {'.', '..'} or repo in {'.', '..'}:
        raise HTTPException(422, 'Invalid GitHub repository')
    base = f'/repos/{owner}/{repo}'
    pr = github_get(f'{base}/pulls/{number}')
    repository = github_get(base)
    files = []
    for page in range(1, 31):
        batch = github_get(f'{base}/pulls/{number}/files?per_page=100&page={page}')
        files.extend(batch)
        if len(batch) < 100:
            break
    if len(files) != pr['changed_files']:
        raise HTTPException(422, 'GitHub returned an incomplete file list; submit manual features for this PR')
    features = {'title_word_count': len((pr.get('title') or '').split()),
                'body_word_count': len((pr.get('body') or '').split()),
                'total_lines_added': pr['additions'], 'total_lines_deleted': pr['deletions'],
                'total_lines_changed': pr['additions'] + pr['deletions'],
                'total_files_touched': pr['changed_files'], 'total_commits': pr['commits'],
                'files_added': sum(f['status'] == 'added' for f in files),
                'files_modified': sum(f['status'] not in ('added', 'removed') for f in files),
                'files_deleted': sum(f['status'] == 'removed' for f in files),
                'stars': repository['stargazers_count'], 'forks': repository['forks_count']}
    if repository.get('language'):
        features['language'] = repository['language']
    # Agent identity and the notebook's LLM-assigned task type are not GitHub fields.
    if overrides:
        if set(overrides) - {'agent', 'task_type', 'taskType'}:
            raise HTTPException(422, 'GitHub mode only accepts agent and task_type overrides')
        features.update(normalize_features(overrides))
    meta = {'owner': owner.lower(), 'name': repo.lower(), 'number': int(number),
            'url': f'https://github.com/{owner.lower()}/{repo.lower()}/pull/{int(number)}',
            'title': pr['title'], 'state': 'MERGED' if pr.get('merged') else pr['state'].upper(),
            'author_login': pr['user']['login']}
    return features, meta
