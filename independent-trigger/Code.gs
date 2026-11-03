/* Standalone project only. No Drive/Sheets/GAS collector writes or X calls. */
const SOUBA = Object.freeze({
  repo: 'yu12ou03-maker/p-souba-auto', workflow: 'daily_screenshot.yml',
  startMinute: 8 * 60 + 55, endMinute: 9 * 60 + 30,
  collectionStep: 'ランキング撮影・ローカルOCR・正常時のみ保存',
  guardSha: '9b6903604e54f64c6f02849c25cbd4848e3cb3bc', workflowSha: '6e5fa53251812092ec8362500023131e57611702'
});

function soubaRequest_(path, token, payload) {
  const options = {method: payload === undefined ? 'get' : 'post',
    headers: {Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28'}, muteHttpExceptions: true,
    followRedirects: false};
  if (payload !== undefined) {
    options.contentType = 'application/json'; options.payload = JSON.stringify(payload);
  }
  const response = UrlFetchApp.fetch('https://api.github.com/repos/' + SOUBA.repo + '/' + path, options);
  const status = response.getResponseCode();
  if (payload !== undefined) {
    if (status !== 204) throw new Error('Dispatch result not confirmed: HTTP ' + status + '; no automatic resend');
    return null;
  }
  if (status !== 200) throw new Error('GitHub read failed: HTTP ' + status);
  return JSON.parse(response.getContentText());
}

function soubaPages_(path, key, token) {
  const result = [];
  for (let page = 1; page <= 100; page++) {
    const data = soubaRequest_(path + '&per_page=100&page=' + page, token)[key];
    if (!Array.isArray(data)) throw new Error('Invalid GitHub history');
    result.push.apply(result, data);
    if (data.length < 100) return result;
  }
  throw new Error('History limit; dispatch refused');
}

function soubaHasAttempt_(runs, today, getJobs) {
  return runs.some(run => {
    if (!['schedule', 'workflow_dispatch'].includes(run.event)) return false;
    return getJobs(run.id).some(job => (job.steps || []).some(step => {
      if (step.name !== SOUBA.collectionStep || step.conclusion === 'skipped' ||
          !['in_progress', 'completed'].includes(step.status)) return false;
      if (!step.started_at) throw new Error('Missing collection timestamp');
      const start = Utilities.formatDate(new Date(step.started_at), 'Asia/Tokyo', 'yyyy-MM-dd');
      const end = step.completed_at ? Utilities.formatDate(new Date(step.completed_at), 'Asia/Tokyo', 'yyyy-MM-dd') : null;
      return start <= today && (end === null || end >= today);
    }));
  });
}

function soubaVerifyMain_(token) {
  [['schedule_guard.py', SOUBA.guardSha], ['.github/workflows/daily_screenshot.yml', SOUBA.workflowSha]].forEach(pair => {
    if (soubaRequest_('contents/' + pair[0] + '?ref=main', token).sha !== pair[1])
      throw new Error('Main safety code differs from reviewed version; dispatch refused');
  });
}

function soubaWatchdog() { return soubaWatchdogAt_(new Date()); }

function soubaWatchdogAt_(now) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return 'locked';
  try {
    const properties = PropertiesService.getScriptProperties();
    if (properties.getProperty('SOUBA_ENABLED') !== 'true') return 'disabled';
    const minute = Number(Utilities.formatDate(now, 'Asia/Tokyo', 'H')) * 60 +
      Number(Utilities.formatDate(now, 'Asia/Tokyo', 'm'));
    if (minute < SOUBA.startMinute || minute > SOUBA.endMinute) return 'outside_window';
    const today = Utilities.formatDate(now, 'Asia/Tokyo', 'yyyy-MM-dd');
    const key = 'SOUBA_DISPATCH_' + today;
    if (properties.getProperty(key)) return 'already_reserved';
    const token = properties.getProperty('SOUBA_GITHUB_TOKEN');
    if (!token) throw new Error('Dedicated GitHub token not configured');
    soubaVerifyMain_(token);
    const since = new Date(now.getTime() - 48 * 3600 * 1000).toISOString();
    const runs = soubaPages_('actions/workflows/' + SOUBA.workflow + '/runs?created=' +
      encodeURIComponent('>=' + since), 'workflow_runs', token);
    if (soubaHasAttempt_(runs, today,
      id => soubaPages_('actions/runs/' + id + '/jobs?filter=all', 'jobs', token))) return 'collection_already_started';
    // An existing dispatch (queued, running or completed before collection) is
    // not reissued automatically. The workflow itself is the final guard.
    if (runs.some(run => run.event === 'workflow_dispatch' &&
        Utilities.formatDate(new Date(run.created_at), 'Asia/Tokyo', 'yyyy-MM-dd') === today))
      return 'dispatch_already_exists';
    // Persist BEFORE sending: timeout/unknown result must never cause a resend.
    properties.setProperty(key, JSON.stringify({state: 'reserved', at: now.toISOString()}));
    soubaRequest_('actions/workflows/' + SOUBA.workflow + '/dispatches', token,
      {ref: 'main', inputs: {capture_only: false, dry_run: false}});
    properties.setProperty(key, JSON.stringify({state: 'accepted', at: now.toISOString()}));
    console.log('Independent dispatch accepted for ' + today);
    return 'accepted';
  } finally { lock.releaseLock(); }
}

function soubaInstall() {
  const properties = PropertiesService.getScriptProperties();
  const token = properties.getProperty('SOUBA_GITHUB_TOKEN');
  if (!token) throw new Error('Dedicated token required before installation');
  soubaVerifyMain_(token);
  // Preserve all other triggers; do not install duplicate watchdogs.
  if (!ScriptApp.getProjectTriggers().some(t => t.getHandlerFunction() === 'soubaWatchdog'))
    ScriptApp.newTrigger('soubaWatchdog').timeBased().everyMinutes(5).create();
  properties.setProperty('SOUBA_ENABLED', 'true');
  return 'enabled';
}
