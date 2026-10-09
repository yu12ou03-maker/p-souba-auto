import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import take_screenshot as app
from test_souba import fixture


def response(rows, finish='STOP'):
    return {'candidates': [{'finishReason': finish, 'content': {'parts': [{'text': json.dumps({'rows': rows})}]}}]}


class GeminiTests(unittest.TestCase):
    def setUp(self):
        self.refs = [{'rank': 1, 'name': 'テスト1'}, {'rank': 2, 'name': 'テスト2'}]
        self.rows = [{'rank': 1, 'name': 'テスト1', 'price': 123456, 'change': -1234}, {'rank': 2, 'name': 'テスト2', 'price': 234567, 'change': 0}]

    def test_structured_output(self):
        rows = app.parse_gemini(response(self.rows), self.refs)
        self.assertEqual(rows[0], app.Row(1, 'テスト1', 123456, -1234))
        self.assertEqual(rows[1].change, 0)

    def test_reject_missing_null_wrong_name_rank_and_type(self):
        bad = [self.rows[:1], list(reversed(self.rows))]
        for key, value in [('price', None), ('change', '0'), ('name', '架空機種'), ('rank', True), ('price', 0), ('change', 200000000)]:
            rows = [dict(r) for r in self.rows]; rows[0][key] = value; bad.append(rows)
        for rows in bad:
            with self.subTest(rows=rows), self.assertRaises(app.DataError):
                app.parse_gemini(response(rows), self.refs)
        with self.assertRaises(app.DataError):
            app.parse_gemini(response(self.rows, 'MAX_TOKENS'), self.refs)
        with self.assertRaises(app.DataError):
            app.parse_gemini({'candidates': []}, self.refs)

    def test_two_reads_must_agree(self):
        images = {'パチンコ': [(Path('unused.png'), self.refs)], 'パチスロ': []}
        first = app.parse_gemini(response(self.rows), self.refs)
        second = [app.Row(1, 'テスト1', 999999, -1234), first[1]]
        with patch.object(app, 'analyze_chunk', side_effect=[first, second]), patch.object(app.time, 'sleep'), patch.object(app, 'publish') as send:
            with self.assertRaises(app.DataError):
                app.analyze_images(images, 'synthetic-key', 'gemini-2.5-flash')
            send.assert_not_called()

    def test_incomplete_snapshot_rejected(self):
        with patch.object(app.time, 'monotonic'):
            page = type('Page', (), {'content': lambda self: fixture(count=10)})()
            with self.assertRaises(app.DataError):
                app.ranking_snapshot(page, 'パチンコ')

    def test_valid_snapshot_uses_only_rank_name(self):
        page = type('Page', (), {'content': lambda self: fixture(count=100)})()
        _, _, _, refs = app.ranking_snapshot(page, 'パチンコ')
        self.assertEqual(len(refs), 100)
        self.assertEqual(set(refs[0]), {'rank', 'name'})

    def test_quota_error_stops_without_retry(self):
        error = app.urllib.error.HTTPError('https://generativelanguage.googleapis.com', 429, 'quota', {}, None)
        with patch.object(app.urllib.request, 'urlopen', side_effect=error) as request:
            with self.assertRaises(app.DataError):
                app.gemini_request('models', 'synthetic-key')
            request.assert_called_once()

    def test_invalid_model_override_rejected(self):
        with patch.dict(app.os.environ, {'GEMINI_MODEL': '../../secret'}), self.assertRaises(app.DataError):
            app.select_model('synthetic-key')

    def test_image_payload_and_verification_direction(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / 'image.png'; image.write_bytes(b'synthetic-image')
            with patch.object(app, 'gemini_request', return_value=response(self.rows)) as request:
                app.analyze_chunk(image, self.refs, 'synthetic-key', 'gemini-2.5-flash', verify=True)
                payload = request.call_args.args[2]
                self.assertEqual(payload['contents'][0]['parts'][1]['inlineData']['mimeType'], 'image/png')
                self.assertIn('下から', payload['contents'][0]['parts'][0]['text'])


class ModelSelectionTests(unittest.TestCase):
    def setUp(self):
        printer = patch('builtins.print'); printer.start(); self.addCleanup(printer.stop)

    def test_original_model_preferred_when_available(self):
        models = {'models': [{'name': 'models/' + name, 'supportedGenerationMethods': ['generateContent']} for name in ('gemini-2.5-flash', 'gemini-3.6-flash')]}
        with patch.dict(app.os.environ, {'GEMINI_MODEL': ''}), patch.object(app, 'gemini_request', return_value=models):
            self.assertEqual(app.select_model('synthetic-key'), 'gemini-3.6-flash')

    def test_override_must_be_in_available_models(self):
        with patch.dict(app.os.environ, {'GEMINI_MODEL': 'gemini-unavailable'}), patch.object(app, 'gemini_request', return_value={'models': []}), self.assertRaises(app.DataError):
            app.select_model('synthetic-key')


class FallbackTests(unittest.TestCase):
    def setUp(self):
        printer = patch('builtins.print'); printer.start(); self.addCleanup(printer.stop)
        self.refs = [{'rank': i, 'name': f'機種{i}'} for i in range(1, 101)]
        self.rows = [app.Row(r['rank'], r['name'], 123456, 0) for r in self.refs]
        self.images = {'パチンコ': [(Path('p.png'), self.refs)], 'パチスロ': [(Path('s.png'), self.refs)]}

    def test_unavailable_model_falls_back_and_rechecks_same_model(self):
        with patch.object(app, 'analyze_chunk', side_effect=[app.GeminiAPIError(503, 'test'), self.rows, self.rows, self.rows, self.rows]) as analyze, patch.object(app.time, 'sleep'):
            data, used = app.analyze_images(self.images, 'synthetic-key', 'gemini-3.6-flash', ['gemini-3.8-flash'])
            self.assertEqual(len(data['パチスロ']), 100)
            self.assertEqual(used, ['gemini-3.8-flash'])
            self.assertEqual(analyze.call_args_list[1].args[3], 'gemini-3.8-flash')
            self.assertEqual(analyze.call_args_list[2].args[3], 'gemini-3.8-flash')

    def test_no_model_switch_for_quota_or_authentication(self):
        for status in (429, 401, 403):
            with patch.object(app, 'analyze_chunk', side_effect=app.GeminiAPIError(status, 'test')) as analyze, self.assertRaises(app.DataError):
                app.analyze_images(self.images, 'synthetic-key', 'gemini-3.6-flash', ['gemini-3.8-flash'])
            analyze.assert_called_once()
