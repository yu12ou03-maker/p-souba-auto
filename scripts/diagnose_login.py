"""Read-only diagnostic: no GAS/Drive code, no raw page/credential output."""
import json
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

OUT = Path('diagnostics/login-summary.json')
BASE = 'http://www.p-souba.com/'


def summarize(page):
    tables = page.evaluate('''() => Array.from(document.querySelectorAll('table')).map(table =>
      Array.from(table.querySelectorAll('tr')).filter(tr => tr.closest('table') === table).map(tr =>
        Array.from(tr.children).filter(c => ['TD','TH'].includes(c.tagName)).map(c =>
          ({text: c.innerText.trim(), images: c.querySelectorAll('img').length, span: c.colSpan}))))''')
    results = []
    for rows in tables:
        for i, row in enumerate(rows):
            headings = [c['text'] for c in row]
            if not all(key in headings for key in ('順位', '機種名', '平均価格', '前日差額')):
                continue
            indexes = {key: headings.index(key) for key in ('順位', '機種名', '平均価格', '前日差額')}
            result = {'rows': 0, 'readable_price_rows': 0, 'numeric_image_cells': 0, 'merged_rows': 0, 'zero_change_rows': 0}
            for data in rows[i + 1:]:
                if not data or not re.fullmatch(r'\d+位', unicodedata.normalize('NFKC', data[0]['text'])):
                    continue
                result['rows'] += 1
                if len(data) != len(row) or any(c['span'] != 1 for c in data):
                    result['merged_rows'] += 1
                    continue
                price = data[indexes['平均価格']]
                change = data[indexes['前日差額']]
                result['numeric_image_cells'] += price['images'] + change['images']
                p = unicodedata.normalize('NFKC', price['text']).replace(' ', '')
                d = unicodedata.normalize('NFKC', change['text']).replace(' ', '').replace('−', '-')
                if re.fullmatch(r'[\d,]+円', p) and re.fullmatch(r'(?:[+-][\d,]+|±?0)円', d):
                    result['readable_price_rows'] += 1
                if d in ('±0円', '0円', '+0円', '-0円'):
                    result['zero_change_rows'] += 1
            results.append(result)
    return results


def main():
    result = {'mode': 'diagnostic_only', 'drive_requests': 0, 'pages': {}}
    OUT.parent.mkdir(exist_ok=True)
    try:
        for key in ('P_SOUBA_USER', 'P_SOUBA_PASS'):
            if not os.getenv(key):
                result['missing_variable'] = key
                raise RuntimeError('missing credential')
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                def guard(route):
                    url = urlsplit(route.request.url)
                    # No Google/Drive or foreign navigation, even through site redirects.
                    if url.hostname not in ('www.p-souba.com', 'p-souba.com') or url.scheme not in ('http', 'https'):
                        route.abort()
                    else:
                        route.continue_()
                context.route('**/*', guard)
                page = context.new_page()
                page.set_default_timeout(30000)
                response = page.goto(BASE + 'index.php', wait_until='domcontentloaded', timeout=60000)
                result['login_page_status'] = response.status if response else None
                if not response or response.status >= 400:
                    raise RuntimeError('login page failed')
                field = page.locator('input[type="password"]').first
                form = field.locator('xpath=ancestor::form[1]')
                form.locator('input[name="uname"], input[type="text"]').first.fill(os.environ['P_SOUBA_USER'])
                field.fill(os.environ['P_SOUBA_PASS'])
                submit = form.locator('input[type="submit"], input[type="image"], button').first
                if submit.count():
                    submit.click()
                else:
                    field.press('Enter')
                page.wait_for_timeout(4000)
                for label, path in (('pachinko', 'krank_1.htm'), ('slot', 'krank_2.htm')):
                    response = page.goto(BASE + path, wait_until='domcontentloaded', timeout=60000)
                    if not response or response.status >= 400:
                        raise RuntimeError('ranking page failed')
                    page.wait_for_timeout(2000)
                    result['pages'][label] = {'http_status': response.status, 'ranking_tables': summarize(page)}
            finally:
                browser.close()
        result['both_prices_visible'] = all(
            len(result['pages'][label]['ranking_tables']) == 1 and
            result['pages'][label]['ranking_tables'][0]['readable_price_rows'] == 100
            for label in ('pachinko', 'slot')
        )
        return 0 if result['both_prices_visible'] else 1
    except Exception as exc:
        # Exceptions may include credential-filled DOM snippets; never persist them.
        result['error_type'] = type(exc).__name__
        return 1
    finally:
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    raise SystemExit(main())
