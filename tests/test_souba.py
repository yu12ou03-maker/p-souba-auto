import unittest
from unittest.mock import Mock, patch
import take_screenshot as app


def fixture(category='パチンコ', count=10):
    return f'<h1>{category}価格ランキング</h1><table><tr><th>順位</th><th>機種名</th><th>平均価格</th><th>前日差額</th></tr>' + ''.join(f'<tr><td>{i}位</td><td>機種{i}</td><td>123,456円</td><td>{"+1,234円" if i % 2 else "-2,000円"}</td></tr>' for i in range(1, count + 1)) + '</table>'


class ParseTests(unittest.TestCase):
    def test_extract_exact_values(self):
        rows = app.parse_ranking(fixture(), 'パチンコ')
        self.assertEqual(rows[0], app.Row(1, '機種1', 123456, 1234))
        self.assertEqual(rows[1].change, -2000)
        self.assertEqual(len(rows), 10)

    def test_fullwidth_and_zero(self):
        self.assertEqual(app.money('＋１２，３４５円', True), 12345)
        self.assertEqual(app.money('0円', True), 0)
        self.assertEqual(app.money('▲1,000円', True), -1000)

    def test_reject_malformed_money(self):
        for text in ('1,23円', '不明', '--', '1,000円余分', 'NaN', '1.5円'):
            with self.subTest(text=text), self.assertRaises(app.DataError):
                app.money(text, True)
        with self.assertRaises(app.DataError):
            app.money('123円', True)
        with self.assertRaises(app.DataError):
            app.money('0円')

    def test_reject_bad_tables(self):
        original = fixture()
        samples = [fixture(count=0), fixture(count=1), original.replace('2位', '3位'), original.replace('機種2', '機種1'), original.replace('+1,234円', '不明'), original.replace('123,456円', '0円'), original.replace('価格ランキング', '機種別相場'), original.replace('<td>2位</td>', ''), original + original]
        for html in samples:
            with self.subTest(html=html[:80]), self.assertRaises(app.DataError):
                app.parse_ranking(html, 'パチンコ')

    def test_layout_table_and_extra_columns(self):
        html = fixture().replace('<th>機種名</th>', '<th>導入週</th><th>機種名</th>')
        for i in range(1, 11):
            html = html.replace(f'<td>機種{i}</td>', f'<td>2026/01</td><td>機種{i}</td>')
        self.assertEqual(len(app.parse_ranking('<table><tr><td>' + html + '</td></tr></table>', 'パチンコ')), 10)

    def test_wrong_category(self):
        with self.assertRaises(app.DataError):
            app.parse_ranking(fixture(), 'スロット')

    def test_link(self):
        html = '<a href="/krank_2.htm">スロット価格ランキング</a>'
        self.assertIn('/krank_2.htm', app.find_ranking(html, app.BASE, 'スロット'))
        for href in ('https://evil.test/krank_2.htm', 'https://user:pass@www.p-souba.com/krank_2.htm'):
            with self.assertRaises(app.DataError):
                app.find_ranking(f'<a href="{href}">スロットランキング</a>', app.BASE, 'スロット')


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.rows = app.parse_ranking(fixture(count=100), 'パチンコ')
        self.data = {'パチンコ': self.rows, 'パチスロ': [app.Row(r.rank, 'S' + r.name, r.price, r.change) for r in self.rows]}

    def test_no_post_for_invalid_data(self):
        for data in ({}, {'パチンコ': self.rows}, {'パチンコ': self.rows, 'パチスロ': []}, {'パチンコ': self.rows, 'パチスロ': self.rows[:1]}):
            with patch('take_screenshot.urllib.request.build_opener') as opener:
                with self.assertRaises(app.DataError):
                    app.publish(data, app.DEFAULT_GAS_URL)
                opener.assert_not_called()

    def test_post_validated_report_only_once(self):
        response = Mock(status=200)
        response.read.return_value = b'OK'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch('take_screenshot.urllib.request.build_opener') as factory:
            factory.return_value.open.return_value = response
            app.publish(self.data, app.DEFAULT_GAS_URL)
            factory.return_value.open.assert_called_once()
            req = factory.return_value.open.call_args.args[0]
            self.assertEqual(req.get_method(), 'POST')
            self.assertIn('■ パチスロ相場', req.data.decode())

    def test_ambiguous_post_is_not_retried(self):
        with patch('take_screenshot.urllib.request.build_opener') as factory:
            factory.return_value.open.side_effect = TimeoutError('secret should not be logged')
            with self.assertRaises(TimeoutError):
                app.publish(self.data, app.DEFAULT_GAS_URL)
            factory.return_value.open.assert_called_once()

    def test_reject_gas_urls(self):
        for url in ('http://script.google.com/macros/s/abc/exec', 'https://script.google.com.evil.test/macros/s/abc/exec', app.DEFAULT_GAS_URL + '?x=y'):
            with patch('take_screenshot.urllib.request.build_opener') as factory:
                with self.assertRaises(app.DataError):
                    app.publish(self.data, url)
                factory.assert_not_called()

    def test_navigation_retries_transient_failure(self):
        page = Mock(url=app.BASE)
        page.goto.side_effect = [TimeoutError(), Mock(status=200)]
        with patch('take_screenshot.time.sleep'):
            app.navigate(page, app.BASE)
        self.assertEqual(page.goto.call_count, 2)

    def test_no_retry_access_restrictions(self):
        for status in (401, 403, 429):
            page = Mock(url=app.BASE)
            page.goto.return_value.status = status
            with self.assertRaises(app.DataError):
                app.navigate(page, app.BASE)
            page.goto.assert_called_once()

    def test_gas_redirect_disallows_other_hosts(self):
        req = app.urllib.request.Request(app.DEFAULT_GAS_URL, data=b'test')
        with self.assertRaises(app.DataError):
            app.GASRedirect().redirect_request(req, None, 302, '', {}, 'https://evil.test/')


if __name__ == '__main__':
    unittest.main()
