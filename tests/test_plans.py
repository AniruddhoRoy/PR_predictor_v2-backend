import os
import unittest
from copy import deepcopy
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite://'
from sqlalchemy import create_engine, text
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

    def tearDown(self):
        backend.app.dependency_overrides.clear()
        self.engine.dispose()

    def test_admin_changes_survive_restart(self):
        plans = self.client.get('/admin/api/plans', headers=self.admin).json()
        plus = next(p for p in plans if p['code'] == 'PLUS')
        response = self.client.patch('/admin/api/plans/' + plus['planId'], headers=self.admin, json={'credits': 0, 'duration': 7, 'modelCodes': ['model-4']})
        self.assertEqual(response.status_code, 200)
        backend.seed_database()
        with self.sessions() as db:
            plan = db.query(Plan).filter_by(code='PLUS').one()
            self.assertEqual(plan.credits, 0)
            self.assertEqual([m.code for m in plan.models], ['model-4'])

    def test_access_cost_and_failure(self):
        body = {'pullRequestUrl': 'https://github.com/owner/repo/pull/12', 'predictionType': 'BOTH', 'modelId': 'model-4'}
        self.assertEqual(self.client.post('/predict', headers=self.headers, json=body).status_code, 403)
        body['modelId'] = 'model-1'
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
        self.assertEqual(data['inferenceKey'], 'gemini-api')
        self.assertEqual(data['analysis'], ANALYSIS['analysis'])
        self.assertEqual(data['features'], ANALYSIS['features'])
        self.assertEqual(data['probabilityNote'], ANALYSIS['probability_note'])
        with self.sessions() as db:
            self.assertEqual(db.query(PredictionResult).one().analysis_response, ANALYSIS)
        self.assertEqual(self.client.get('/predictions/' + data['predictionId'], headers=self.headers).json(), data)
        dashboard = self.client.get('/dashboard', headers=self.headers).json()
        self.assertEqual(dashboard['totalPredictions'], 1)
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
        for prediction_type in ('BOTH', 'PR_QUALITY', 'MERGE_PROBABILITY'):
            with self.subTest(prediction_type=prediction_type), patch.object(backend, 'analyze_pr', return_value=response_body):
                body = {'pullRequestUrl': ANALYSIS['pr_url'], 'predictionType': prediction_type}
                for route, headers in [('/predict-dev', {}), ('/predict', self.headers)]:
                    response = self.client.post(route, json=body, headers=headers)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json(), response_body)
        with self.sessions() as db:
            for saved in db.query(PredictionResult).all():
                self.assertEqual(saved.analysis_response, response_body)
        self.assertEqual(self.client.get('/active-plan', headers=self.headers).json()['creditsUsed'], 3)
        self.assertEqual(len(self.client.get('/history', headers=self.headers).json()), 3)
        with patch.object(backend, 'analyze_pr', return_value=ANALYSIS):
            self.assertEqual(self.client.post('/predict-dev', json=ANALYSIS['pr_url']).status_code, 200)
        self.assertEqual(self.client.post('/predict', json=ANALYSIS['pr_url']).status_code, 401)

    def test_failed_analysis_does_not_save_or_charge(self):
        for code in (401, 404, 422, 502, 503, 504):
            with self.subTest(code=code), patch.object(backend, 'analyze_pr', side_effect=HTTPException(code, 'Service failed')):
                for route, headers in [('/predict-dev', {}), ('/predict', self.headers)]:
                    response = self.client.post(route, json=ANALYSIS['pr_url'], headers=headers)
                    self.assertEqual(response.status_code, code)
        self.assertEqual(self.client.get('/active-plan', headers=self.headers).json()['creditsUsed'], 0)
        self.assertEqual(self.client.get('/history', headers=self.headers).json(), [])
        with self.sessions() as db:
            self.assertEqual(db.query(PredictionResult).count(), 0)
            self.assertEqual(db.query(Prediction).count(), 0)

    def test_url_aliases_and_bad_inputs(self):
        with patch.object(backend, 'analyze_pr', return_value=ANALYSIS):
            for field in ('pullRequestUrl', 'pr_url', 'pull_request_url'):
                self.assertEqual(self.client.post('/predict-dev', json={field: ANALYSIS['pr_url']}).status_code, 200)
        with patch.object(backend, 'analyze_pr') as service:
            for body in ('', ' ', {}, {'features': {}}, {'pr_url': None}, {'pr_url': ANALYSIS['pr_url'], 'unexpected': True}):
                for route, headers in [('/predict-dev', {}), ('/predict', self.headers)]:
                    self.assertEqual(self.client.post(route, headers=headers, json=body).status_code, 422)
            service.assert_not_called()

    def test_history_search_uses_saved_url_and_title(self):
        with patch.object(backend, 'analyze_pr', return_value=ANALYSIS):
            self.client.post('/predict', json=ANALYSIS['pr_url'], headers=self.headers)
        for search in ('login', 'owner/repo'):
            history = self.client.get('/history', params={'search': search}, headers=self.headers).json()
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]['pr_url'], ANALYSIS['pr_url'])
        self.assertEqual(self.client.get('/history?search=missing', headers=self.headers).json(), [])

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
