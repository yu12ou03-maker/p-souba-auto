"""Allow one scheduled collection attempt per JST day, under workflow concurrency."""
import json
import os
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo


COLLECTION_STEP = 'ランキング撮影・ローカルOCR・正常時のみ保存'


def already_attempted(runs, current_id, today, jobs):
    for run in runs:
        if str(run['id']) == str(current_id) or run['event'] != 'schedule':
            continue
        created = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00'))
        if created.astimezone(ZoneInfo('Asia/Tokyo')).date() != today:
            continue
        for job in jobs(run['id']):
            for step in job.get('steps', []):
                # A failed/ambiguous POST or access restriction must not cause a retry.
                if (step['name'] == COLLECTION_STEP and step.get('started_at')
                        and step.get('conclusion') != 'skipped'):
                    return True
    return False


def main():
    proceed = True
    if os.environ['GITHUB_EVENT_NAME'] == 'schedule':
        repo = os.environ['GITHUB_REPOSITORY']
        root = f'https://api.github.com/repos/{repo}/actions/'

        def get(path):
            request = urllib.request.Request(root + path, headers={
                'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28',
            })
            # Fail closed; do not retry 403/429 or expose response bodies/tokens.
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)

        def pages(path, key):
            values = []
            page = 1
            while True:
                batch = get(f'{path}&per_page=100&page={page}')[key]
                values.extend(batch)
                if len(batch) < 100:
                    return values
                page += 1

        today = datetime.now(ZoneInfo('Asia/Tokyo')).date()
        # Bound the query to this JST day, including the preceding UTC afternoon.
        from datetime import timedelta
        since = (today - timedelta(days=1)).isoformat() + 'T15:00:00Z'
        runs = pages('workflows/daily_screenshot.yml/runs?event=schedule&created=>=' + since,
                     'workflow_runs')
        proceed = not already_attempted(runs, os.environ['GITHUB_RUN_ID'], today,
            lambda run_id: pages(f'runs/{run_id}/jobs?filter=all', 'jobs'))
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write(f'proceed={str(proceed).lower()}\n')
    if not proceed:
        print('::notice::本日取得開始済み。重複取得・GAS再送を行いません。')


if __name__ == '__main__':
    main()
