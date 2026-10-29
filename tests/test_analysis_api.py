import io
import json
import os
import unittest
from copy import deepcopy
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from fastapi import HTTPException
import analysis_api
from test_plans import ANALYSIS


class AnalysisApiTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'PR_ANALYZER_TOKEN': 'test-only-token'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_posts_only_url_with_server_token(self):
        response_body = deepcopy(ANALYSIS)
        response_body['pr_url'] += '/'
        response_body['service_metadata'] = {'extra': [1, None, False]}
        with patch.object(analysis_api, 'urlopen', return_value=io.BytesIO(json.dumps(response_body).encode())) as send:
            result = analysis_api.analyze_pr(ANALYSIS['pr_url'])
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, analysis_api.ANALYZE_URL)
        self.assertEqual(request.method, 'POST')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-only-token')
        self.assertEqual(json.loads(request.data), {'pr_url': ANALYSIS['pr_url']})
        self.assertEqual(result, response_body)

    def test_missing_token_and_bad_url_do_not_make_requests(self):
        with patch.object(analysis_api, 'urlopen') as send:
            with patch.dict(os.environ, {'PR_ANALYZER_TOKEN': ''}):
                with self.assertRaises(HTTPException) as caught:
                    analysis_api.analyze_pr(ANALYSIS['pr_url'])
                self.assertEqual(caught.exception.status_code, 503)
            for url in ('http://localhost/pr/1', 'https://github.com/owner/../pull/12', 'https://github.com/owner/repo', ''):
                with self.subTest(url=url), self.assertRaises(HTTPException) as caught:
                    analysis_api.analyze_pr(url)
                self.assertEqual(caught.exception.status_code, 422)
            send.assert_not_called()

    def test_service_error_codes_and_safe_messages(self):
        for code in (401, 404, 422, 502, 503, 504, 500):
            error = HTTPError(analysis_api.ANALYZE_URL, code, 'failure', {}, io.BytesIO(b'sensitive upstream body'))
            with self.subTest(code=code), patch.object(analysis_api, 'urlopen', side_effect=error):
                with self.assertRaises(HTTPException) as caught:
                    analysis_api.analyze_pr(ANALYSIS['pr_url'])
                self.assertEqual(caught.exception.status_code, code if code in analysis_api.ERRORS else 502)
                self.assertNotIn('sensitive', caught.exception.detail)
                self.assertNotIn('test-only-token', caught.exception.detail)

    def test_timeout_and_connection_errors(self):
        for error, code in [(TimeoutError(), 504), (URLError(TimeoutError()), 504), (URLError('offline'), 502)]:
            with self.subTest(error=error), patch.object(analysis_api, 'urlopen', side_effect=error):
                with self.assertRaises(HTTPException) as caught:
                    analysis_api.analyze_pr(ANALYSIS['pr_url'])
                self.assertEqual(caught.exception.status_code, code)

    def test_invalid_responses_are_rejected(self):
        bodies = [b'', b'<html>Error</html>', b'{}', b'[]']
        for value in (-1, 101, '95', None, True, float('nan')):
            result = deepcopy(ANALYSIS)
            result['analysis']['quality_score'] = value
            bodies.append(json.dumps(result).encode())
        wrong_pr = deepcopy(ANALYSIS)
        wrong_pr['pr_url'] = 'https://github.com/other/repo/pull/1'
        bodies.append(json.dumps(wrong_pr).encode())
        for body in bodies:
            with self.subTest(body=body), patch.object(analysis_api, 'urlopen', return_value=io.BytesIO(body)):
                with self.assertRaises(HTTPException) as caught:
                    analysis_api.analyze_pr(ANALYSIS['pr_url'])
                self.assertEqual(caught.exception.status_code, 502)


if __name__ == '__main__':
    unittest.main()
