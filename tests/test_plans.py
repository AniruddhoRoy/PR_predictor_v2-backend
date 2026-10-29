import os
import json
import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite://'
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
import app as backend
from fastapi import HTTPException
from auth import verify_password
from database import Base
from models import Plan, User, Prediction, PredictionResult, Subscription, UsagePeriod


ANALYSIS = {
    "pr_url": "https://github.com/owner/repo/pull/12",
    "features": {"repository": "owner/repo", "number": 12, "title": "Fix login",
                 "state": "open", "author": "tester", "merged": False,
                 "files": [{"filename": "app.py", "patch": "+fix"}], "warnings": []},
    "analysis": {"merge_probability": 95, "quality_score": 92, "quality": "excellent",
                 "confidence": "high", "summary": "Fixes login.", "merge_reasoning": "Small tested fix.",
                 "recommendations": {"excellent": ["Tests included"], "good": [], "bad": [], "worst": []},
                 "potential_improvements": [], "limitations": ["No CI results"]},
    "probability_note": "AI estimate, not a calibrated probability or a guarantee.",
}


class CreditPlansTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        self.sessions = sessionmaker(bind=self.engine)
        backend.engine = self.engine
        backend.SessionLocal = self.sessions
        Base.metadata.create_all(self.engine)
        backend.seed_database()
        def db():
            with self.sessions() as session:
                yield session
        backend.app.dependency_overrides[backend.get_db] = db
        self.client = TestClient(backend.app)
        user = self.client.post('/register', json={'username': 'tester', 'email': 'test@example.com', 'password': '1234', 'fullName': 'Tester'}).json()
        self.headers = {'Authorization': 'Bearer ' + user['accessToken']}
        admin = self.client.post('/login', json={'username': 'admin', 'password': '1234'}).json()
        self.admin = {'Authorization': 'Bearer ' + admin['accessToken']}
        self.model_id = self.client.get('/models', headers=self.headers).json()[0]['modelId']
        self.body = {'pr_url': ANALYSIS['pr_url'], 'modelId': self.model_id}

    def tearDown(self):
        backend.app.dependency_overrides.clear()
        self.engine.dispose()

    def test_profile_email_null_is_rejected(self):
        before = self.client.get('/profile', headers=self.headers).json()
        response = self.client.patch('/profile', headers=self.headers, json={'email': None})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get('/profile', headers=self.headers).json(), before)
        self.assertEqual(self.client.patch('/profile', headers=self.headers, json={}).status_code, 200)
        self.assertEqual(self.client.patch('/profile', headers=self.headers, json={'githubProfileUrl': None}).status_code, 200)

    def test_admin_changes_survive_restart(self):
        plans = self.client.get('/admin/api/plans', headers=self.admin).json()
        plus = next(p for p in plans if p['code'] == 'PLUS')
        response = self.client.patch('/admin/api/plans/' + plus['planId'], headers=self.admin, json={'credits': 0, 'duration': 7, 'modelCodes': ['model-4']})
        self.assertEqual(response.status_code, 200)
        backend.seed_database()
        with self.sessions() as db:
            plan = db.query(Plan).filter_by(code='PLUS').one()
            self.assertEqual(plan.credits, 0)
            self.assertEqual(plan.duration, 7)
            self.assertEqual([m.code for m in plan.models], ['model-4'])

    def test_subscription_duration_expiry_and_same_plan(self):
        subscription = self.client.get('/subscription', headers=self.headers).json()
        self.assertEqual(datetime.fromisoformat(subscription['endedAt']) - datetime.fromisoformat(subscription['startedAt']), timedelta(days=1))
        with patch.object(backend, 'analyze_pr', return_value=ANALYSIS):
            self.client.post('/predict', json=self.body, headers=self.headers)
        same = self.client.post('/subscription', headers=self.headers, json={'planCode': 'FREE'}).json()
        self.assertEqual(same['subscriptionId'], subscription['subscriptionId'])
        self.assertEqual(self.client.get('/active-plan', headers=self.headers).json()['creditsUsed'], 1)
        with self.sessions() as db:
            saved = db.get(Subscription, subscription['subscriptionId'])
            saved.started_at -= timedelta(days=1)
            saved.ended_at = datetime.utcnow() - timedelta(seconds=1)
            db.query(UsagePeriod).one().time_stamp = saved.started_at.date()
            db.commit()
        renewed = self.client.get('/subscription', headers=self.headers).json()
        self.assertNotEqual(renewed['subscriptionId'], subscription['subscriptionId'])
        self.assertEqual(self.client.get('/active-plan', headers=self.headers).json()['creditsUsed'], 0)
        self.assertEqual(len(self.client.get('/history', headers=self.headers).json()), 1)
        with self.sessions() as db:
            self.assertEqual(db.get(Subscription, subscription['subscriptionId']).status, 'EXPIRED')

    def test_expiry_during_analysis_does_not_charge(self):
        subscription = self.client.get('/subscription', headers=self.headers).json()
        def analyze(url):
            with self.sessions() as db:
                saved = db.get(Subscription, subscription['subscriptionId'])
                saved.ended_at = datetime.utcnow() - timedelta(seconds=1)
                db.commit()
            return ANALYSIS
        with patch.object(backend, 'analyze_pr', side_effect=analyze):
            response = self.client.post('/predict', json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 409)
        with self.sessions() as db:
            self.assertEqual(db.query(Prediction).count(), 0)
            self.assertEqual(db.query(UsagePeriod).one().credits_used, 0)

    def test_admin_plan_and_model_fields(self):
        model = self.client.post('/admin/api/models', headers=self.admin, json={
            'code': 'custom-model', 'name': 'Custom', 'version': '1.0', 'creditCost': 2,
        })
        self.assertEqual(model.status_code, 201)
        self.assertNotIn('taskType', model.json())
        self.assertNotIn('artifactKey', model.json())
        plan = self.client.post('/admin/api/plans', headers=self.admin, json={
            'code': 'CUSTOM', 'name': 'Custom', 'credits': 10, 'duration': 7, 'modelCodes': ['custom-model'],
        })
        self.assertEqual(plan.status_code, 201)
        self.assertEqual(plan.json()['duration'], 7)
        self.assertEqual([m['code'] for m in plan.json()['models']], ['custom-model'])
        subscription = self.client.post('/subscription', headers=self.headers, json={'planCode': 'CUSTOM'}).json()
        self.assertEqual(datetime.fromisoformat(subscription['endedAt']) - datetime.fromisoformat(subscription['startedAt']), timedelta(days=7))
        free = next(p for p in self.client.get('/plans', headers=self.headers).json() if p['code'] == 'FREE')
        for payload, code in [({'duration': 0}, 422), ({'duration': None}, 422), ({'credits': -1}, 422), ({'active': False}, 400), ({'code': 'OTHER'}, 400)]:
            self.assertEqual(self.client.patch('/admin/api/plans/' + free['planId'], headers=self.admin, json=payload).status_code, code)

    def test_legacy_migration_preserves_data_and_is_repeatable(self):
        with patch.object(backend, 'analyze_pr', return_value=ANALYSIS):
            self.client.post('/predict', json=self.body, headers=self.headers)
        with self.engine.begin() as connection:
            connection.execute(text('ALTER TABLE predictions DROP COLUMN http_status'))
            connection.execute(text('ALTER TABLE prediction_results RENAME TO old_results'))
            connection.execute(text('CREATE TABLE prediction_results (result_id VARCHAR(36) PRIMARY KEY, prediction_id VARCHAR(36), analysis_response JSON, generated_at DATETIME)'))
            connection.execute(text('INSERT INTO prediction_results SELECT result_id, prediction_id, :response, generated_at FROM old_results'), {'response': json.dumps(ANALYSIS)})
            connection.execute(text('DROP TABLE old_results'))
        backend.migrate_schema()
        backend.seed_database()
        backend.migrate_schema()
        backend.seed_database()
        with self.sessions() as db:
            self.assertEqual(db.query(User).count(), 2)
            result = db.query(PredictionResult).one()
            self.assertEqual(result.summary, ANALYSIS['analysis']['summary'])
            self.assertEqual(result.files, ANALYSIS['features']['files'])
            self.assertEqual(result.user_id, db.query(Prediction).one().user_id)
            self.assertEqual(db.query(Prediction).one().pr_url, ANALYSIS['pr_url'])
            self.assertEqual(db.query(Plan).filter_by(code='FREE').one().credits, 5)
        self.assertEqual(self.client.get('/active-plan', headers=self.headers).json()['creditsUsed'], 1)
        self.assertEqual(len(self.client.get('/history', headers=self.headers).json()), 1)
        with patch.object(backend, 'analyze_pr', return_value=ANALYSIS):
            self.assertEqual(self.client.post('/predict', json=self.body, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get('/active-plan', headers=self.headers).json()['creditsUsed'], 2)

    def test_migration_failure_rolls_back_schema_and_data(self):
        with self.engine.begin() as connection:
            connection.execute(text('ALTER TABLE predictions DROP COLUMN http_status'))
        def fail_on_drop(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith('DROP TABLE'):
                raise RuntimeError('Simulated migration failure')
        event.listen(self.engine, 'before_cursor_execute', fail_on_drop)
        try:
            with self.assertRaisesRegex(RuntimeError, 'Simulated migration failure'):
                backend.migrate_schema()
        finally:
            event.remove(self.engine, 'before_cursor_execute', fail_on_drop)
        self.assertNotIn('http_status', {column['name'] for column in inspect(self.engine).get_columns('predictions')})
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(text('SELECT COUNT(*) FROM users')).scalar(), 2)

    def test_access_cost_and_failure(self):
        other = next(m for m in self.client.get('/admin/api/models', headers=self.admin).json() if m['code'] == 'model-4')
        body = {'pullRequestUrl': ANALYSIS['pr_url'], 'modelId': other['modelId']}
        self.assertEqual(self.client.post('/predict', headers=self.headers, json=body).status_code, 403)
        body['modelId'] = self.model_id
        model = self.client.get('/models', headers=self.headers).json()[0]
        self.client.patch('/admin/api/models/' + model['modelId'], headers=self.admin, json={'creditCost': 3})
        with patch.object(backend, 'analyze_pr', side_effect=HTTPException(503, 'Service unavailable')):
            self.assertEqual(self.client.post('/predict', headers=self.headers, json=body).status_code, 503)
        self.assertEqual(self.client.get('/active-plan', headers=self.headers).json()['creditsUsed'], 0)
        with patch.object(backend, 'analyze_pr', return_value=ANALYSIS) as service:
            result = self.client.post('/predict', headers=self.headers, json=body)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json(), ANALYSIS)
            self.assertEqual(self.client.post('/predict', headers=self.headers, json=body).status_code, 429)
            service.assert_called_once_with(body['pullRequestUrl'])
        data = self.client.get('/history', headers=self.headers).json()[0]
        self.assertEqual(data['creditsCost'], 3)
        self.assertEqual(data['mergeProbability'], 95)
        self.assertEqual(data['qualityScore'], 92)
        self.assertEqual(data['httpStatus'], 200)
        self.assertEqual(data['analysis'], ANALYSIS['analysis'])
        for key, value in ANALYSIS['features'].items():
            self.assertEqual(data['features'][key], value)
        self.assertEqual(data['probabilityNote'], ANALYSIS['probability_note'])
        with self.sessions() as db:
            self.assertEqual(db.query(PredictionResult).one().summary, ANALYSIS['analysis']['summary'])
        self.assertEqual(self.client.get('/predictions/' + data['predictionId'], headers=self.headers).json(), data)
        dashboard = self.client.get('/dashboard', headers=self.headers).json()
        self.assertEqual(dashboard['totalPredictions'], 2)
        self.assertEqual(dashboard['averageMergeProbability'], 95)
        self.assertEqual(self.client.get('/active-plan', headers=self.headers).json()['creditsRemaining'], 2)
        self.client.post('/subscription', headers=self.headers, json={'planCode': 'ULTRA'})
        plan = self.client.get('/active-plan', headers=self.headers).json()
        self.assertEqual(len(plan['models']), 6)
        self.assertEqual(plan['creditsUsed'], 3)

    def test_prediction_routes_return_entire_analyzer_response(self):
        response_body = deepcopy(ANALYSIS)
        response_body['pr_url'] += '/'
        response_body['service_metadata'] = {'version': 'new', 'optional': None}
        response_body['features']['extra_details'] = [{'enabled': False}]
        response_body['analysis']['extra_scores'] = {'future_score': 88}
        with patch.object(backend, 'analyze_pr', return_value=response_body):
            for route, headers in [('/predict-dev', {}), ('/predict', self.headers)]:
                response = self.client.post(route, json=self.body, headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), response_body)
        with self.sessions() as db:
            saved = db.query(PredictionResult).one()
            self.assertEqual(saved.files, response_body['features']['files'])
            self.assertEqual(saved.pr_url, response_body['pr_url'])
        self.assertEqual(self.client.get('/active-plan', headers=self.headers).json()['creditsUsed'], 1)
        self.assertEqual(len(self.client.get('/history', headers=self.headers).json()), 1)
        self.assertEqual(self.client.post('/predict', json=self.body).status_code, 401)

    def test_failed_analysis_saves_error_without_result_or_charge(self):
        for code in (401, 404, 422, 502, 503, 504):
            with self.subTest(code=code), patch.object(backend, 'analyze_pr', side_effect=HTTPException(code, 'Service failed')):
                for route, headers in [('/predict-dev', {}), ('/predict', self.headers)]:
                    response = self.client.post(route, json=self.body, headers=headers)
                    self.assertEqual(response.status_code, code)
        self.assertEqual(self.client.get('/active-plan', headers=self.headers).json()['creditsUsed'], 0)
        history = self.client.get('/predictions', headers=self.headers).json()
        self.assertEqual(len(history), 6)
        for item in history:
            self.assertEqual(item['status'], 'FAILED')
            self.assertEqual(item['creditsCost'], 0)
            self.assertEqual(item['features'], {})
            self.assertEqual(item['analysis'], {})
            self.assertEqual(item['errorMessage'], 'Service failed')
            detail = self.client.get('/predictions/' + item['predictionId'], headers=self.headers)
            self.assertEqual(detail.json(), item)
        with self.sessions() as db:
            self.assertEqual(db.query(PredictionResult).count(), 0)
            self.assertEqual(db.query(Prediction).count(), 6)

    def test_url_aliases_and_bad_inputs(self):
        with patch.object(backend, 'analyze_pr', return_value=ANALYSIS):
            for field in ('pullRequestUrl', 'pr_url', 'pull_request_url'):
                self.assertEqual(self.client.post('/predict-dev', json={field: ANALYSIS['pr_url'], 'modelId': self.model_id}).status_code, 200)
        with patch.object(backend, 'analyze_pr') as service:
            for body in ('', ANALYSIS['pr_url'], {}, {'pr_url': ANALYSIS['pr_url']}, {**self.body, 'modelId': None}, {**self.body, 'pr_url': 'bad'}, {**self.body, 'predictionType': 'BOTH'}, {**self.body, 'unexpected': True}):
                for route, headers in [('/predict-dev', {}), ('/predict', self.headers)]:
                    self.assertEqual(self.client.post(route, headers=headers, json=body).status_code, 422)
            service.assert_not_called()

    def test_history_search_uses_saved_url_and_title(self):
        with patch.object(backend, 'analyze_pr', return_value=ANALYSIS):
            self.client.post('/predict', json=self.body, headers=self.headers)
        for search in ('login', 'owner/repo'):
            history = self.client.get('/history', params={'search': search}, headers=self.headers).json()
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]['pr_url'], ANALYSIS['pr_url'])
        self.assertEqual(self.client.get('/history?search=missing', headers=self.headers).json(), [])

    def test_prediction_ownership_and_limits(self):
        with patch.object(backend, 'analyze_pr', return_value=ANALYSIS):
            self.client.post('/predict', json=self.body, headers=self.headers)
        prediction = self.client.get('/predictions', headers=self.headers).json()[0]
        self.assertEqual(self.client.get('/predictions', headers=self.admin).json(), [])
        self.assertEqual(self.client.get('/predictions/' + prediction['predictionId'], headers=self.admin).status_code, 404)
        self.assertEqual(self.client.get('/predictions/missing', headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get('/predictions?limit=0', headers=self.headers).status_code, 422)
        self.assertEqual(self.client.get('/predictions').status_code, 401)

    def test_result_columns_and_timestamps(self):
        response = deepcopy(ANALYSIS)
        response['features'].update(created_at='2026-10-01T01:02:03Z', updated_at='2026-10-02T01:02:03+00:00',
                                    draft=False, mergeable=None, additions=0, labels=['fix'],
                                    comments=[{'body': 'Looks good'}], reviews=[], statuses=[])
        with patch.object(backend, 'analyze_pr', return_value=response):
            self.assertEqual(self.client.post('/predict', json=self.body, headers=self.headers).status_code, 200)
        with self.sessions() as db:
            result = db.query(PredictionResult).one()
            self.assertEqual(result.pr_created_at, datetime(2026, 10, 1, 1, 2, 3))
            self.assertEqual(result.pr_number, 12)
            self.assertEqual(result.repository, 'owner/repo')
            self.assertEqual(result.comments, response['features']['comments'])
            self.assertFalse(result.draft)
            self.assertEqual(result.additions, 0)
            self.assertIsNone(result.mergeable)
        item = self.client.get('/predictions', headers=self.headers).json()[0]
        self.assertEqual(item['features']['created_at'], '2026-10-01T01:02:03')
        self.assertEqual(item['analysis']['recommendations'], response['analysis']['recommendations'])
        with self.sessions() as db:
            self.assertEqual(db.query(UsagePeriod).count(), 1)
        response['features']['created_at'] = 'invalid timestamp'
        with patch.object(backend, 'analyze_pr', return_value=response):
            self.assertEqual(self.client.post('/predict', json=self.body, headers=self.headers).status_code, 502)
        self.assertEqual(self.client.get('/active-plan', headers=self.headers).json()['creditsUsed'], 1)

    def test_change_password_for_user_and_admin(self):
        for username, headers in [('tester', self.headers), ('admin', self.admin)]:
            with self.subTest(username=username):
                response = self.client.post('/change-password', headers=headers, json={'currentPassword': '1234', 'newPassword': 'newpass5678'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {'message': 'Password changed successfully'})
                self.assertEqual(self.client.post('/login', json={'username': username, 'password': '1234'}).status_code, 401)
                self.assertEqual(self.client.post('/login', json={'username': username, 'password': 'newpass5678'}).status_code, 200)
                self.assertEqual(self.client.get('/me', headers=headers).status_code, 200)
                with self.sessions() as db:
                    user = db.query(User).filter_by(username=username).one()
                    self.assertNotEqual(user.password_hash, 'newpass5678')
                    self.assertTrue(verify_password('newpass5678', user.password_hash))

    def test_change_password_rejects_wrong_current_password(self):
        response = self.client.post('/change-password', headers=self.headers, json={'currentPassword': 'wrong', 'newPassword': 'newpass5678'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'detail': 'Current password is incorrect'})
        self.assertEqual(self.client.post('/login', json={'username': 'tester', 'password': '1234'}).status_code, 200)

    def test_change_password_requires_authentication(self):
        for headers in ({}, {'Authorization': 'Bearer invalid'}):
            with self.subTest(headers=headers):
                response = self.client.post('/change-password', headers=headers, json={'currentPassword': '1234', 'newPassword': 'newpass5678'})
                self.assertEqual(response.status_code, 401)

    def test_change_password_validates_fields(self):
        bodies = [{}, {'currentPassword': '1234'}, {'newPassword': 'newpass5678'}]
        bodies += [{'currentPassword': value, 'newPassword': 'newpass5678'} for value in ('', None, 1234, 'x' * 129)]
        bodies += [{'currentPassword': '1234', 'newPassword': value} for value in ('', 'abc', None, 1234, 'x' * 129)]
        for body in bodies:
            with self.subTest(body=body):
                self.assertEqual(self.client.post('/change-password', headers=self.headers, json=body).status_code, 422)
        self.assertEqual(self.client.post('/login', json={'username': 'tester', 'password': '1234'}).status_code, 200)

    def test_change_password_only_updates_signed_in_account(self):
        admin_id = self.client.get('/me', headers=self.admin).json()['userId']
        response = self.client.post('/change-password', headers=self.headers, json={'current_password': '1234', 'new_password': ' new pass ', 'userId': admin_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post('/login', json={'username': 'tester', 'password': ' new pass '}).status_code, 200)
        self.assertEqual(self.client.post('/login', json={'username': 'tester', 'password': 'new pass'}).status_code, 401)
        self.assertEqual(self.client.post('/login', json={'username': 'admin', 'password': '1234'}).status_code, 200)


if __name__ == '__main__':
    unittest.main()
