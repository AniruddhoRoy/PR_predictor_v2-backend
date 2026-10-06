import os
import io
import json
import unittest
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite://'
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
import app as backend
import github_api
from auth import verify_password
from database import Base
from models import Plan, User
from prediction_engine import predict, _row


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
        response = self.client.patch('/admin/api/plans/' + plus['planId'], headers=self.admin, json={'monthlyCredits': 0, 'modelCodes': ['model-4'], 'parentPlanCode': None})
        self.assertEqual(response.status_code, 200)
        backend.seed_database()
        with self.sessions() as db:
            plan = db.query(Plan).filter_by(code='PLUS').one()
            self.assertEqual(plan.monthly_credits, 0)
            self.assertEqual([m.code for m in plan.models], ['model-4'])

    def test_access_cost_and_failure(self):
        body = {'pullRequestUrl': 'https://github.com/owner/repo/pull/12', 'predictionType': 'BOTH', 'modelId': 'model-4'}
        self.assertEqual(self.client.post('/predict', headers=self.headers, json=body).status_code, 403)
        body['modelId'] = 'model-1'
        model = self.client.get('/models', headers=self.headers).json()[0]
        self.client.patch('/admin/api/models/' + model['modelId'], headers=self.admin, json={'creditCost': 3})
        github_data = ({'owner': {'login': 'owner'}, 'name': 'repo', 'html_url': 'https://github.com/owner/repo'},
                       {'number': 12, 'html_url': body['pullRequestUrl'], 'title': 'Fix login', 'state': 'open'},
                       {'total_lines_added': 10})
        with patch.object(backend, 'get_pull_request', return_value=github_data), patch.object(backend, 'run_model_prediction', side_effect=RuntimeError('unavailable')):
            self.assertEqual(self.client.post('/predict', headers=self.headers, json=body).status_code, 503)
        self.assertEqual(self.client.get('/active-plan', headers=self.headers).json()['creditsUsed'], 0)
        with patch.object(backend, 'get_pull_request', return_value=github_data), patch.object(backend, 'run_model_prediction', return_value=(80, 80, [])):
            result = self.client.post('/predict', headers=self.headers, json=body)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['creditsCost'], 3)
            self.assertEqual(self.client.post('/predict', headers=self.headers, json=body).status_code, 429)
        self.assertEqual(self.client.get('/active-plan', headers=self.headers).json()['creditsRemaining'], 2)
        self.client.post('/subscription', headers=self.headers, json={'planCode': 'ULTRA'})
        plan = self.client.get('/active-plan', headers=self.headers).json()
        self.assertEqual(len(plan['models']), 6)
        self.assertEqual(plan['creditsUsed'], 3)

    def test_notebook_models(self):
        self.assertEqual(_row({'additions': 12})['total_lines_added'], 12)
        for key in ('model-1', 'model-2', 'model-3', 'model-4', 'model-5', 'model-6'):
            with self.subTest(model=key):
                score, _, _ = predict({'additions': 12, 'changedFiles': 2, 'language': 'Python'}, key)
                self.assertGreaterEqual(score, 0)
                self.assertLessEqual(score, 100)
        with self.assertRaises(ValueError):
            predict({'additions': 12}, 'missing-model')

    def test_github_features(self):
        responses = [
            {'title': 'Fix login', 'body': 'Add regression test', 'additions': 12,
             'deletions': 3, 'changed_files': 2, 'commits': 1},
            {'stargazers_count': 10, 'forks_count': 4, 'language': 'Python'},
            [{'status': 'added'}, {'status': 'modified'}],
        ]
        with patch.object(github_api, 'urlopen', side_effect=[io.BytesIO(json.dumps(item).encode()) for item in responses]):
            _, _, features = github_api.get_pull_request('https://github.com/owner/repo/pull/12')
        self.assertEqual(features['total_lines_added'], 12)
        self.assertEqual(features['files_added'], 1)
        self.assertEqual(features['title_word_count'], 2)


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
