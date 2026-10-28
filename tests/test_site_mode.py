import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright
import take_screenshot as app
from test_souba import fixture


def temporary_fixture(category='パチンコ'):
    html = fixture(category, count=100).replace('価格ランキング', 'ランキング')
    import re
    html = re.sub(r'(\d+)位', r'\1', html)
    return '<main><p>平均価格の高い順（上位100機種） ／ 10/27時点</p>' + html + '</main>'


class SiteModeTests(unittest.TestCase):
    def test_manual_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'config.json'
            with patch.object(app, 'CONFIG_PATH', path):
                for mode in ('normal', 'temporary'):
                    path.write_text(json.dumps({'site_mode': mode}))
                    self.assertEqual(app.load_site_mode(), mode)
                path.write_text('{"site_mode":"auto"}')
                with self.assertRaises(ValueError):
                    app.load_site_mode()

    def test_host_isolation(self):
        with patch.object(app, 'SITE_MODE', 'temporary'):
            self.assertEqual(app.site_url(app.TEMP_BASE), app.TEMP_BASE)
            for url in (app.BASE, 'http://sub.p-souba.com/login', 'https://evil.example/'):
                with self.assertRaises(app.DataError):
                    app.site_url(url)
        with patch.object(app, 'SITE_MODE', 'normal'):
            with self.assertRaises(app.DataError):
                app.site_url(app.TEMP_BASE)

    def test_temporary_ranks_and_date(self):
        from unittest.mock import Mock
        page = Mock()
        page.content.return_value = temporary_fixture()
        with patch.object(app, 'SITE_MODE', 'temporary'):
            refs = app.ranking_snapshot(page, 'パチンコ')[3]
            self.assertEqual([r['rank'] for r in refs], list(range(1, 101)))
            self.assertEqual(app.temporary_reference_date(page), '10/27時点')
            page.content.return_value = temporary_fixture().replace('10/27時点', '')
            with self.assertRaises(app.DataError):
                app.temporary_reference_date(page)

    def test_temporary_login_capture_both(self):
        import os
        with sync_playwright() as p, patch.object(app, 'SITE_MODE', 'temporary'):
            opts = {'headless': True}
            if os.getenv('TEST_CHROMIUM_PATH'):
                opts['executable_path'] = os.environ['TEST_CHROMIUM_PATH']
            browser = p.chromium.launch(**opts)
            try:
                page = browser.new_page()
                def route(r):
                    if r.request.url.endswith('/login'):
                        body = '<form method="post" action="/login"><input name="uname"><input type="password" name="password"><button>Login</button></form>' if r.request.method == 'GET' else '<main>ログイン完了</main>'
                    else:
                        self.assertIn(r.request.url, [app.TEMP_BASE + 'pachinko/ranking', app.TEMP_BASE + 'slot/ranking'])
                        body = '<style>table{width:960px}td{height:35px}</style>' + temporary_fixture('スロット' if '/slot/' in r.request.url else 'パチンコ')
                    r.fulfill(status=200, content_type='text/html; charset=utf-8', body=body)
                page.route('**/*', route)
                with tempfile.TemporaryDirectory() as temp:
                    dates = {}
                    images = app.collect_images(page, 'test', 'test', Path(temp), reference_dates=dates)
                    self.assertEqual(dates, {'パチンコ': '10/27時点', 'パチスロ': '10/27時点'})
                    self.assertTrue(all(len(chunks) == 4 for chunks in images.values()))
            finally:
                browser.close()
