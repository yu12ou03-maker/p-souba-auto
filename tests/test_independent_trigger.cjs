const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const source = fs.readFileSync('independent-trigger/Code.gs', 'utf8');
let checks = 0;
function fixture({runs=[], jobs=[], failPost=false, failRead=false, mismatch=false, enabled=true}={}) {
  const state = new Map([['SOUBA_ENABLED', String(enabled)], ['SOUBA_GITHUB_TOKEN','test-token']]);
  let posts = 0, reads = 0, releases = 0;
  const properties = {getProperty:k=>state.get(k), setProperty:(k,v)=>state.set(k,v)};
  const context = vm.createContext({console:{log(){}}, Date, JSON, Number, Object, Array, Error,
    encodeURIComponent, PropertiesService:{getScriptProperties:()=>properties},
    LockService:{getScriptLock:()=>({tryLock:()=>true,releaseLock:()=>releases++})},
    Utilities:{formatDate:(d,tz,fmt)=> {
      const parts=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:tz,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(d).map(p=>[p.type,p.value]));
      return fmt==='H'?parts.hour:fmt==='m'?parts.minute:`${parts.year}-${parts.month}-${parts.day}`;
    }},
    UrlFetchApp:{fetch:(url,options)=> {
      assert(!url.includes('test-token')); assert.equal(options.followRedirects,false);
      if(options.method==='post') {
        posts++; assert.deepEqual(JSON.parse(options.payload), {ref:'main',inputs:{capture_only:false,dry_run:false}});
        if(failPost) throw new Error('ambiguous POST');
        return {getResponseCode:()=>204};
      }
      reads++; if(failRead) throw new Error('read unavailable');
      let data;
      if(url.includes('/contents/schedule_guard.py')) data={sha: mismatch?'bad':vm.runInContext('SOUBA.guardSha',context)};
      else if(url.includes('/contents/.github/workflows/')) data={sha:vm.runInContext('SOUBA.workflowSha',context)};
      else if(url.includes('/jobs?')) data={jobs};
      else if(url.includes('/runs?')) data={workflow_runs:runs};
      else throw new Error('Unexpected URL');
      return {getResponseCode:()=>200,getContentText:()=>JSON.stringify(data)};
    }}});
  vm.runInContext(source,context);
  const run=(when='2026-11-03T00:00:00Z')=>vm.runInContext(`soubaWatchdogAt_(new Date('${when}'))`,context);
  return {run,state,posts:()=>posts,reads:()=>reads,releases:()=>releases};
}
let f=fixture(); assert.equal(f.run(),'accepted'); assert.equal(f.run(),'already_reserved'); assert.equal(f.posts(),1); checks++;
f=fixture({failPost:true}); assert.throws(()=>f.run(),/ambiguous/); assert.equal(f.run(),'already_reserved'); assert.equal(f.posts(),1); checks++;
f=fixture({failRead:true}); assert.throws(()=>f.run(),/unavailable/); assert.equal(f.posts(),0); assert.equal(f.state.has('SOUBA_DISPATCH_2026-11-03'),false); checks++;
f=fixture({mismatch:true}); assert.throws(()=>f.run(),/reviewed/); assert.equal(f.posts(),0); checks++;
f=fixture(); assert.equal(f.run('2026-11-02T23:54:00Z'),'outside_window'); assert.equal(f.run('2026-11-03T00:31:00Z'),'outside_window'); assert.equal(f.reads(),0); checks++;
f=fixture({enabled:false}); assert.equal(f.run(),'disabled'); assert.equal(f.reads(),0); checks++;
for (const event of ['schedule','workflow_dispatch']) {
 f=fixture({runs:[{id:1,event,created_at:'2026-11-02T14:00:00Z'}],jobs:[{steps:[{name:'ランキング撮影・ローカルOCR・正常時のみ保存',status:'completed',conclusion:'failure',started_at:'2026-11-03T00:00:00Z',completed_at:'2026-11-03T00:01:00Z'}]}]});
 assert.equal(f.run(),'collection_already_started'); assert.equal(f.posts(),0); checks++;
}
f=fixture({runs:[{id:1,event:'workflow_dispatch',status:'queued',created_at:'2026-11-03T00:00:00Z'}]}); assert.equal(f.run(),'dispatch_already_exists'); assert.equal(f.posts(),0); checks++;
console.log(`${checks} independent trigger safety scenarios passed (mock services; no live calls)`);
