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

    def test_four_images_are_read_once_each(self):
        refs = [{'rank': i, 'name': f'機種{i}'} for i in range(1, 101)]
        images = {label: [(Path(f'{label}-{offset}.png'), refs[offset:offset+50])
                         for offset in (0, 50)] for label in ('パチンコ', 'パチスロ')}
        def read(path, chunk_refs, key, model):
            return [app.Row(r['rank'], r['name'], 123456, -1234) for r in chunk_refs]
        with patch.object(app, 'analyze_chunk', side_effect=read) as analyze, patch.object(app.time, 'sleep'):
            data, used = app.analyze_images(images, 'synthetic-key', 'gemini-3.6-flash')
            self.assertEqual(analyze.call_count, 4)
            self.assertEqual([len(data[label]) for label in ('パチンコ', 'パチスロ')], [100, 100])
            self.assertEqual([call.args[1][0]['rank'] for call in analyze.call_args_list], [1, 51, 1, 51])

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

    def test_image_payload_and_single_read_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / 'image.png'; image.write_bytes(b'synthetic-image')
            with patch.object(app, 'gemini_request', return_value=response(self.rows)) as request:
                app.analyze_chunk(image, self.refs, 'synthetic-key', 'gemini-2.5-flash')
                payload = request.call_args.args[2]
                self.assertEqual(payload['contents'][0]['parts'][1]['inlineData']['mimeType'], 'image/png')
                self.assertIn('上から', payload['contents'][0]['parts'][0]['text'])


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

    def test_service_error_stops_without_model_switch(self):
        for status in (404, 500, 502, 503, 504):
            with patch.object(app, 'analyze_chunk', side_effect=app.GeminiAPIError(status, 'test')) as analyze, self.assertRaises(app.GeminiAPIError):
                app.analyze_images(self.images, 'synthetic-key', 'gemini-3.6-flash', ['gemini-3.8-flash'])
            analyze.assert_called_once()

    def test_http_service_error_and_timeout_are_not_retried(self):
        errors = [app.urllib.error.HTTPError('https://example.test', code, 'error', {}, None) for code in (429, 503)] + [TimeoutError()]
        for error in errors:
            with patch.object(app.urllib.request, 'urlopen', side_effect=error) as request, self.assertRaises(app.DataError):
                app.gemini_request('models/test:generateContent', 'synthetic-key', {})
            request.assert_called_once()

    def test_invalid_analysis_is_not_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / 'image.png'; image.write_bytes(b'image')
            with patch.object(app, 'gemini_request', return_value=response([], 'MAX_TOKENS')) as request, self.assertRaises(app.DataError):
                app.analyze_chunk(image, self.refs, 'synthetic-key', 'gemini-3.6-flash')
            request.assert_called_once()

    def test_no_model_switch_for_quota_or_authentication(self):
        for status in (429, 401, 403):
            with patch.object(app, 'analyze_chunk', side_effect=app.GeminiAPIError(status, 'test')) as analyze, self.assertRaises(app.DataError):
                app.analyze_images(self.images, 'synthetic-key', 'gemini-3.6-flash', ['gemini-3.8-flash'])
            analyze.assert_called_once()


class DiagnosticTests(unittest.TestCase):
    def test_diagnostics_do_not_include_response_names_prices_or_secrets(self):
        ref = [{'rank': 1, 'name': '参照機種'}]
        result = response([{'rank': 1, 'name': '秘密の文字列', 'price': 98765432, 'change': None}])
        diagnostic = app.gemini_diagnostics(result, ref)
        self.assertEqual(diagnostic['name_mismatches'], [1])
        self.assertEqual(diagnostic['unreadable_amounts'], [1])
        serialized = json.dumps(diagnostic, ensure_ascii=False)
        self.assertNotIn('秘密の文字列', serialized)
        self.assertNotIn('98765432', serialized)

    def test_truncated_output_is_identified(self):
        diagnostic = app.gemini_diagnostics(response([], 'MAX_TOKENS'), [{'rank': 1, 'name': '参照'}])
        self.assertEqual(diagnostic['finish_reason'], 'MAX_TOKENS')
