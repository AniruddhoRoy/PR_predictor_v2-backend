"""Run all API routes against an isolated database; write a local audit report.

Run: python tests/audit_api.py
No application data is changed and no external requests are made.
"""

import io
import json
import os
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['ADMIN_PASSWORD'] = 'audit-admin-password'
os.environ['PR_ANALYZER_TOKEN'] = 'audit-only-token'

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import analysis_api
import app as backend
from database import Base
from test_plans import ANALYSIS


checks = []
coverage = Counter()
routes = [route for route in backend.app.routes if getattr(route, 'include_in_schema', False)]


def record(name, passed, evidence):
    checks.append({'name': name, 'passed': passed, 'evidence': evidence})
    if not passed:
        print('FAIL:', name, '-', evidence, flush=True)


def request(client, name, method, path, expected=200, headers=None, body=None):
    kwargs = {'headers': headers or {}}
    if body is not None:
        kwargs['json'] = body
    response = client.request(method, path, **kwargs)
    for route in routes:
        if method in route.methods and route.path_regex.fullmatch(path.split('?')[0]):
            coverage[(method, route.path)] += 1
    expected = (expected,) if isinstance(expected, int) else expected
    evidence = f'{method} {path}: expected {expected}, got {response.status_code}'
    if response.status_code not in expected:
        # Do not write login tokens or successful registration bodies to the report.
        evidence += '; response=' + (response.text[:250] if response.status_code >= 400 else '[successful response]')
        if body is not None:
            safe_body = {key: ('[redacted]' if 'password' in key.lower() else value) for key, value in body.items()}
            evidence += '; input=' + json.dumps(safe_body)
    record(name, response.status_code in expected, evidence)
    return response


def run():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine)
    backend.engine = engine
    backend.SessionLocal = sessions

    def database():
        with sessions() as session:
            yield session

    backend.app.dependency_overrides[backend.get_db] = database
    # The HTTP adapter is mocked, so real URL validation and result mapping still run.
    with patch.object(analysis_api, 'urlopen', side_effect=lambda *a, **kw: io.BytesIO(json.dumps(ANALYSIS).encode())):
        with TestClient(backend.app, raise_server_exceptions=False) as client:
            for path in ('/', '/health', '/docs', '/redoc', '/openapi.json', '/admin/', '/admin/admin.js', '/admin/admin.css'):
                request(client, 'public ' + path, 'GET', path)

            user_body = {'username': 'audit-user', 'email': 'audit@example.com', 'password': '1234', 'fullName': 'Audit User'}
            user = request(client, 'register', 'POST', '/register', 201, body=user_body).json()
            user_headers = {'Authorization': 'Bearer ' + user['accessToken']}
            user_id = user['user']['userId']
            admin = request(client, 'admin login', 'POST', '/login', body={'username': 'admin', 'password': 'audit-admin-password'}).json()
            admin_headers = {'Authorization': 'Bearer ' + admin['accessToken']}

            # Every protected route must reject missing and malformed credentials.
            public = {'/', '/health', '/register', '/login', '/predict-dev'}
            for route in routes:
                if route.path in public:
                    continue
                path = route.path
                for parameter in route.param_convertors:
                    path = path.replace('{' + parameter + '}', 'missing')
                for method in sorted(route.methods):
                    request(client, 'missing auth ' + method + ' ' + path, method, path, 401, body={} if method in {'POST', 'PATCH'} else None)
                    request(client, 'invalid auth ' + method + ' ' + path, method, path, 401,
                            headers={'Authorization': 'Bearer invalid'}, body={} if method in {'POST', 'PATCH'} else None)
                    if path.startswith('/admin/api/'):
                        request(client, 'admin authorization ' + method + ' ' + path, method, path, 403,
                                headers=user_headers, body={} if method in {'POST', 'PATCH'} else None)

            request(client, 'duplicate registration', 'POST', '/register', 409, body=user_body)
            request(client, 'invalid registration', 'POST', '/register', 422, body={})
            request(client, 'wrong password', 'POST', '/login', 401, body={'username': 'audit-user', 'password': 'wrong'})
            request(client, 'email login', 'POST', '/login', body={'username': 'AUDIT@EXAMPLE.COM', 'password': '1234'})
            for path in ('/me', '/profile', '/settings', '/models', '/subscription', '/active-plan', '/plan', '/plans', '/dashboard', '/history', '/predictions'):
                request(client, 'user read ' + path, 'GET', path, headers=user_headers)
            for path in ('/admin/api/stats', '/admin/api/plans', '/admin/api/models', '/admin/api/users', '/admin/api/predictions'):
                request(client, 'admin read ' + path, 'GET', path, headers=admin_headers)

            request(client, 'profile update', 'PATCH', '/profile', headers=user_headers,
                    body={'fullName': 'Updated User', 'email': 'updated@example.com', 'githubProfileUrl': 'https://github.com/example'})
            request(client, 'duplicate profile email', 'PATCH', '/profile', 409, user_headers, {'email': 'admin@example.com'})
            request(client, 'clear optional profile URL', 'PATCH', '/profile', headers=user_headers, body={'githubProfileUrl': None})
            request(client, 'settings update', 'PATCH', '/settings', headers=user_headers,
                    body={'themeMode': 'DARK', 'notificationsEnabled': False, 'defaultPredictionType': 'PR_QUALITY', 'defaultInputMode': 'GITHUB_URL'})
            request(client, 'invalid settings enum', 'PATCH', '/settings', 400, user_headers, {'themeMode': 'BLUE'})
            request(client, 'invalid model filter', 'GET', '/models?predictionType=INVALID', 400, user_headers)

            model_body = {'code': 'audit-model', 'name': 'Audit Model', 'version': '1.0', 'creditCost': 2}
            model = request(client, 'create model', 'POST', '/admin/api/models', 201, admin_headers, model_body).json()
            model_path = '/admin/api/models/' + model['modelId']
            request(client, 'duplicate model', 'POST', '/admin/api/models', 409, admin_headers, model_body)
            request(client, 'update model', 'PATCH', model_path, headers=admin_headers, body={'name': 'Updated Model', 'creditCost': 1})
            request(client, 'null model cost', 'PATCH', model_path, 422, admin_headers, {'creditCost': None})
            request(client, 'invalid model cost', 'PATCH', model_path, 422, admin_headers, {'creditCost': 0})
            request(client, 'missing model update', 'PATCH', '/admin/api/models/missing', 404, admin_headers, {'name': 'Missing'})
            request(client, 'missing model delete', 'DELETE', '/admin/api/models/missing', 404, admin_headers)

            plan_body = {'code': 'AUDIT', 'name': 'Audit Plan', 'credits': 8, 'duration': 7, 'modelCodes': ['audit-model']}
            plan = request(client, 'create plan', 'POST', '/admin/api/plans', 201, admin_headers, plan_body).json()
            plan_path = '/admin/api/plans/' + plan['planId']
            request(client, 'duplicate plan', 'POST', '/admin/api/plans', 409, admin_headers, plan_body)
            request(client, 'update plan', 'PATCH', plan_path, headers=admin_headers, body={'credits': 9, 'duration': 10})
            request(client, 'null plan duration', 'PATCH', plan_path, 422, admin_headers, {'duration': None})
            request(client, 'invalid plan duration', 'PATCH', plan_path, 422, admin_headers, {'duration': 0})
            request(client, 'missing plan model', 'PATCH', plan_path, 404, admin_headers, {'modelCodes': ['missing']})
            request(client, 'missing plan update', 'PATCH', '/admin/api/plans/missing', 404, admin_headers, {'credits': 10})
            request(client, 'missing plan delete', 'DELETE', '/admin/api/plans/missing', 404, admin_headers)

            free_model = request(client, 'available model', 'GET', '/models', headers=user_headers).json()[0]
            body = {'pr_url': ANALYSIS['pr_url'], 'modelId': free_model['modelId']}
            request(client, 'prediction disallowed model', 'POST', '/predict', 403, user_headers, {**body, 'modelId': model['modelId']})
            request(client, 'prediction missing model', 'POST', '/predict', 404, user_headers, {**body, 'modelId': 'missing'})
            request(client, 'prediction bad URL', 'POST', '/predict', 422, user_headers, {**body, 'pr_url': 'bad'})
            request(client, 'public prediction', 'POST', '/predict-dev', body=body)
            request(client, 'saved prediction', 'POST', '/predict', headers=user_headers, body=body)
            history = request(client, 'list predictions', 'GET', '/predictions', headers=user_headers).json()
            detail_path = '/predictions/' + history[0]['predictionId']
            detail = request(client, 'prediction detail', 'GET', detail_path, headers=user_headers).json()
            record('history/detail match', detail == history[0], 'List record equals detail response')
            request(client, 'other user prediction denied', 'GET', detail_path, 404, admin_headers)
            request(client, 'missing prediction', 'GET', '/predictions/missing', 404, user_headers)
            request(client, 'history invalid limit', 'GET', '/predictions?limit=0', 422, user_headers)
            searched = request(client, 'history title search', 'GET', '/predictions?search=login', headers=user_headers).json()
            record('title search matches result', len(searched) == 1, f'Matching predictions: {len(searched)}')

            request(client, 'switch plan', 'POST', '/subscription', headers=user_headers, body={'planCode': 'AUDIT'})
            request(client, 'missing subscription plan', 'POST', '/subscription', 404, user_headers, {'planCode': 'MISSING'})
            active = request(client, 'credit carryover', 'GET', '/active-plan', headers=user_headers).json()
            record('credits retained across switch', active['creditsUsed'] == 1, f"creditsUsed={active['creditsUsed']}")
            request(client, 'deactivate model', 'DELETE', model_path, headers=admin_headers)
            request(client, 'inactive model cannot predict', 'POST', '/predict', 404, user_headers, {**body, 'modelId': model['modelId']})
            request(client, 'reactivate model', 'PATCH', model_path, headers=admin_headers, body={'active': True})
            request(client, 'deactivate plan', 'DELETE', plan_path, headers=admin_headers)
            request(client, 'inactive plan cannot subscribe', 'POST', '/subscription', 404, user_headers, {'planCode': 'AUDIT'})
            active = request(client, 'inactive plan fallback', 'GET', '/active-plan', headers=user_headers).json()
            record('inactive plan falls back to FREE', active['code'] == 'FREE', f"code={active['code']}")
            request(client, 'reactivate plan', 'PATCH', plan_path, headers=admin_headers, body={'active': True})
            plans = client.get('/plans', headers=user_headers).json()
            free = next(p for p in plans if p['code'] == 'FREE')
            free_path = '/admin/api/plans/' + free['planId']
            request(client, 'FREE delete protected', 'DELETE', free_path, 400, admin_headers)
            request(client, 'FREE deactivate protected', 'PATCH', free_path, 400, admin_headers, {'active': False})

            role_path = '/admin/api/users/' + user_id + '/role'
            request(client, 'promote user', 'PATCH', role_path, headers=admin_headers, body={'role': 'ADMIN'})
            request(client, 'changed role takes effect', 'GET', '/admin/api/stats', headers=user_headers)
            request(client, 'demote user', 'PATCH', role_path, headers=admin_headers, body={'role': 'USER'})
            request(client, 'demoted user denied', 'GET', '/admin/api/stats', 403, user_headers)
            request(client, 'invalid role', 'PATCH', role_path, 400, admin_headers, {'role': 'OWNER'})
            request(client, 'missing role target', 'PATCH', '/admin/api/users/missing/role', 404, admin_headers, {'role': 'USER'})
            request(client, 'change password', 'POST', '/change-password', headers=user_headers, body={'currentPassword': '1234', 'newPassword': '5678'})
            request(client, 'old password rejected', 'POST', '/login', 401, body={'username': 'audit-user', 'password': '1234'})
            request(client, 'new password accepted', 'POST', '/login', body={'username': 'audit-user', 'password': '5678'})

            # Invalid input probes: each should be rejected cleanly, not crash or save blanks.
            request(client, 'null profile email rejected', 'PATCH', '/profile', (400, 422), user_headers, {'email': None})
            request(client, 'null notifications rejected', 'PATCH', '/settings', (400, 422), user_headers, {'notificationsEnabled': None})
            request(client, 'blank profile name rejected', 'PATCH', '/profile', (400, 422), user_headers, {'fullName': '   '})
            request(client, 'oversized profile name rejected', 'PATCH', '/profile', (400, 422), user_headers, {'fullName': 'x' * 151})
            request(client, 'blank profile email rejected', 'PATCH', '/profile', (400, 422), user_headers, {'email': '   '})
            request(client, 'blank account rejected', 'POST', '/register', (400, 422), body={**user_body, 'username': '   ', 'email': 'blank-audit@example.com', 'fullName': ' '})
            request(client, 'blank plan create rejected', 'POST', '/admin/api/plans', (400, 422), admin_headers, {**plan_body, 'code': '  '})
            blank_plan = next((p for p in client.get('/admin/api/plans', headers=admin_headers).json() if p['code'] == ''), None)
            if blank_plan:
                # Rename it so the next check is not masked by a duplicate code error.
                client.patch('/admin/api/plans/' + blank_plan['planId'], headers=admin_headers, json={'code': 'BLANK-AUDIT'})
            request(client, 'blank plan update rejected', 'PATCH', plan_path, (400, 422), admin_headers, {'code': '  '})

            invalid_result = deepcopy(ANALYSIS)
            invalid_result['features']['merged'] = 'not-a-boolean'
            with patch.object(analysis_api, 'urlopen', side_effect=lambda *a, **kw: io.BytesIO(json.dumps(invalid_result).encode())):
                request(client, 'invalid analyzer Boolean handled', 'POST', '/predict', 502, user_headers, body)

            # A legitimate service timestamp must represent the same instant in saved history.
            dated_result = deepcopy(ANALYSIS)
            dated_result['features']['created_at'] = '2026-10-01T12:00:00+06:00'
            with patch.object(analysis_api, 'urlopen', side_effect=lambda *a, **kw: io.BytesIO(json.dumps(dated_result).encode())):
                request(client, 'offset timestamp prediction', 'POST', '/predict', headers=user_headers, body=body)
            latest = client.get('/predictions', headers=user_headers).json()[0]
            actual = latest['features'].get('created_at')
            record('PR timestamp keeps its instant', actual in ('2026-10-01T06:00:00', '2026-10-01T06:00:00+00:00', '2026-10-01T12:00:00+06:00'),
                   f'Analyzer created_at=2026-10-01T12:00:00+06:00; saved history created_at={actual}')

            admin_history = client.get('/admin/api/predictions', headers=admin_headers).json()
            js = (ROOT / 'admin/admin.js').read_text()
            html = (ROOT / 'admin/index.html').read_text()
            uses_removed_type = 'item.predictionType' in js or '<th>Type</th>' in html
            record('admin prediction table matches API', not uses_removed_type,
                   'Admin table still references predictionType' if uses_removed_type else 'Admin table uses User, Status, and Created; no removed field references')

    backend.app.dependency_overrides.clear()
    engine.dispose()


def report():
    failures = [c for c in checks if not c['passed']]
    missing = [(method, route.path) for route in routes for method in route.methods if (method, route.path) not in coverage]
    lines = ['# API audit — 2026-10-30', '',
             'Tested locally with FastAPI TestClient, a fresh SQLite database, and simulated analyzer HTTP responses. '
             'No real users, local project database, or external analyzer credits were changed. '
             'The real HTTP adapter validation and prediction storage code were exercised. Live hosting and MySQL were not tested.', '',
             f'Extended audit: {len(checks) - len(failures)}/{len(checks)} checks passed; {len(failures)} failed.',
             f'Application route coverage: {len(coverage)} method/path combinations; untested routes: {missing or "none"}.', '',
             'Reproduce: `python tests/audit_api.py` (requires the project dependencies and httpx). Run the separate unit suite with `python -m unittest discover -s tests`.', '',
             '## Confirmed failing checks', '']
    if not failures:
        lines.extend(['None. All seven original findings are resolved.', ''])
    for check in failures:
        lines.extend([f'### {check["name"]}', '', check['evidence'], ''])
    lines.extend(['## Route coverage', '', '| Method | Path | Checks |', '| --- | --- | --- |'])
    for (method, path), count in sorted(coverage.items()):
        lines.append(f'| {method} | `{path}` | {count} |')
    lines.extend(['', '## Full check results', '', '| Check | Result | Evidence |', '| --- | --- | --- |'])
    for check in checks:
        lines.append(f'| {check["name"]} | {"PASS" if check["passed"] else "FAIL"} | {check["evidence"].replace(chr(10), " ").replace("|", "/")} |')
    (ROOT / 'api_audit_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Audit: {len(checks)} checks; {len(failures)} failed; {len(coverage)} API routes covered; {len(missing)} missing', flush=True)
    return bool(failures or missing)


if __name__ == '__main__':
    run()
    sys.exit(report())
