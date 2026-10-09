"""Real Chromium, intercepted synthetic HTTPS pages. No site credentials/network."""
import os
import unittest
import tempfile
from playwright.sync_api import sync_playwright
import take_screenshot as app
from test_souba import fixture


class BrowserTests(unittest.TestCase):
    def test_capture_waits_for_delayed_prices(self):
        with sync_playwright() as p:
            options = {'headless': True}
            if os.getenv('TEST_CHROMIUM_PATH'):
                options['executable_path'] = os.environ['TEST_CHROMIUM_PATH']
            browser = p.chromium.launch(**options)
            try:
                page = browser.new_page()
                html = fixture(count=100).replace('123,456円', '<span class="price"></span>')
                page.set_content('<style>td{height:35px}table{width:960px}</style>' + html)
                page.evaluate("""() => setTimeout(() => {
                    document.querySelectorAll('.price').forEach(el => el.textContent = '123,456円');
                }, 700)""")
                with tempfile.TemporaryDirectory() as temp:
                    images = app.capture_chunks(page, 'パチンコ', app.Path(temp))
                    self.assertEqual(len(images), 5)
                    self.assertEqual(page.locator('.price').first.inner_text(), '123,456円')
            finally:
                browser.close()

    def test_login_and_both_rankings(self):
        with sync_playwright() as p:
            options = {'headless': True}
            if os.getenv('TEST_CHROMIUM_PATH'):
                options['executable_path'] = os.environ['TEST_CHROMIUM_PATH']
            browser = p.chromium.launch(**options)
            try:
                page = browser.new_page()
                requests = []
                def route(request_route):
                    request = request_route.request
                    requests.append((request.method, request.url))
                    if request.url.endswith('/index.php'):
                        html = '<form method="post" action="/loggedin.php"><input name="uname" type="text"><input name="pass" type="password"><button type="submit">Login</button></form>'
                    elif request.url.endswith('/loggedin.php'):
                        self.assertEqual(request.method, 'POST')
                        self.assertIn('uname=testuser', request.post_data)
                        html = '<a href="/krank_1.htm">パチンコ価格ランキング</a>'
                    elif request.url.endswith('/krank_1.htm'):
                        html = '<style>table{width:960px}td{height:35px}</style>' + fixture(count=100) + '<a href="/krank_2.htm">スロット価格ランキング</a>'
                    elif request.url.endswith('/krank_2.htm'):
                        html = '<style>table{width:960px}td{height:35px}</style>' + fixture('スロット', count=100).replace('<td>機種', '<td>スロット機種')
                    else:
                        self.fail('unexpected request')
                    request_route.fulfill(status=200, content_type='text/html; charset=utf-8', body=html)
                page.route('**/*', route)
                with tempfile.TemporaryDirectory() as temp:
                    images = app.collect_images(page, 'testuser', 'synthetic-password', app.Path(temp))
                    self.assertEqual(len(images['パチンコ']), 5)
                    self.assertEqual(len(images['パチスロ']), 5)
                    self.assertEqual(images['パチスロ'][0][1][0]['name'], 'スロット機種1')
                    self.assertTrue(all(path.is_file() for chunks in images.values() for path, _ in chunks))
                self.assertTrue(any(method == 'POST' for method, _ in requests))
            finally:
                browser.close()
