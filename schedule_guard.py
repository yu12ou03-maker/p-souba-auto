"""At-most-once collection across scheduled, external/manual and rerun attempts."""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

COLLECTION_STEP = 'ランキング撮影・ローカルOCR・正常時のみ保存'
PRODUCTION_EVENTS = {'schedule', 'workflow_dispatch'}
JST = ZoneInfo('Asia/Tokyo')


def already_attempted(runs, current_id, today, jobs):
    for run in runs:
        if run['event'] not in PRODUCTION_EVENTS:
            continue
        # Keep current_id: an earlier attempt of this same run may have sent.
        for job in jobs(run['id']):
            for step in job.get('steps', []):
                if step['name'] != COLLECTION_STEP or step.get('conclusion') == 'skipped':
                    continue
                if step.get('status') not in ('in_progress', 'completed'):
                    continue
                if not step.get('started_at'):
                    raise ValueError('Started collection has no timestamp')
                start = datetime.fromisoformat(step['started_at'].replace('Z', '+00:00'))
                end = datetime.fromisoformat(step['completed_at'].replace('Z', '+00:00')) if step.get('completed_at') else None
                # Step dates handle delayed runs and collection crossing midnight.
                if start.astimezone(JST).date() <= today and (end is None or end.astimezone(JST).date() >= today):
                    return True
    return False


def main():
    proceed = True
    if os.environ['GITHUB_EVENT_NAME'] in PRODUCTION_EVENTS:
        if os.environ['GITHUB_REF'] != 'refs/heads/main':
            raise ValueError('Production collection is restricted to main')
        root = f'https://api.github.com/repos/{os.environ["GITHUB_REPOSITORY"]}/actions/'

        def get(path):
            request = urllib.request.Request(root + path, headers={
                'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28',
            })
            # No retries or credential/response logging. API failure stops the job.
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)

        def pages(path, key):
            values = []
            for page in range(1, 101):
                batch = get(f'{path}&per_page=100&page={page}')[key]
                values.extend(batch)
                if len(batch) < 100:
                    return values
            raise ValueError('History pagination limit; refusing collection')

        today = datetime.now(JST).date()
        since = (today - timedelta(days=2)).isoformat() + 'T15:00:00Z'
        query = urllib.parse.urlencode({'created': '>=' + since})
        runs = pages('workflows/daily_screenshot.yml/runs?' + query, 'workflow_runs')
        proceed = not already_attempted(runs, os.environ['GITHUB_RUN_ID'], today,
            lambda run_id: pages(f'runs/{run_id}/jobs?filter=all', 'jobs'))
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write(f'proceed={str(proceed).lower()}\n')
    if not proceed:
        print('::notice::本日取得開始済み。重複取得・GAS再送を行いません。')


if __name__ == '__main__':
    main()
