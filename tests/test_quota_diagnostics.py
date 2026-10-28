import io
import json
import unittest
import urllib.error
from unittest.mock import patch
import take_screenshot as app


class QuotaDiagnosticsTests(unittest.TestCase):
    def payload(self):
        return {'error': {'status': 'RESOURCE_EXHAUSTED', 'message': 'SECRET account private text', 'details': [
            {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{
                'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests',
                'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaValue': '20',
                'subject': 'projects/123456', 'description': 'SECRET', 'quotaDimensions': {'project': 'SECRET'}}]},
            {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '42s'}]}}

    def test_quota_identifiers_and_retry_delay_without_private_text(self):
        result = app.quota_diagnostics(json.dumps(self.payload()))
        self.assertEqual(result['violations'][0]['quotaValue'], '20')
        self.assertIn('PerDay', result['violations'][0]['quotaId'])
        self.assertEqual(result['retry_delay'], '42s')
        for secret in ('SECRET', '123456', 'subject', 'description', 'quotaDimensions', 'message'):
            self.assertNotIn(secret, json.dumps(result))

    def test_malformed_response_cannot_expose_raw_error(self):
        for raw in ('SECRET', '[]', '{"error":null}'):
            self.assertNotIn('SECRET', json.dumps(app.quota_diagnostics(raw)))

    def test_429_still_stops_once_and_emits_only_safe_details(self):
        exc = urllib.error.HTTPError('https://example.test/', 429, 'SECRET', {}, io.BytesIO(json.dumps(self.payload()).encode()))
        with patch.object(app.urllib.request, 'urlopen', side_effect=exc) as request, patch('builtins.print') as output:
            with self.assertRaises(app.GeminiAPIError):
                app.gemini_request('models/gemini-3.6-flash:generateContent', 'SECRET', {})
            self.assertEqual(request.call_count, 1)
            self.assertNotIn('SECRET', str(output.call_args))
            self.assertIn('PerDay', str(output.call_args))
