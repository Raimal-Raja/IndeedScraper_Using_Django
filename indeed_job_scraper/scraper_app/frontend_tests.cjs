const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const path = require('path');
const crypto = require('crypto');
const script = fs.readFileSync(path.join(__dirname, '../static/js/scrape.js'), 'utf8');
const json = (data, status=200) => ({status, ok: status < 400, headers: {get: () => 'application/json'}, json: async () => data});
function harness(fetch) {
    let submit, stopClick, poll;
    const elements = {
        scrapeForm: {action: 'http://localhost/scrape/', dataset: {progressUrl: '/scrape/progress/00000000-0000-0000-0000-000000000000/', stopUrl: '/scrape/stop/00000000-0000-0000-0000-000000000000/'}, addEventListener: (_, fn) => submit=fn},
        startScrapingBtn: {disabled:false}, stopScrapingBtn: {disabled:true, addEventListener: (_, fn) => stopClick=fn},
        downloadResultsBtn: {hidden:true}, 'scrape-progress-row': {textContent:''}, 'scrape-warning-row': {textContent:''}, 'logging-area': {style:{}}
    };
    vm.runInNewContext(script, {document: {getElementById: id => elements[id]}, crypto, URL, FormData: class {set() {}},
        window: {location: {href: 'http://localhost/scrape/', origin:'http://localhost'}},
        setInterval: fn => {poll=fn;return 1;}, clearInterval: () => {}, fetch});
    return {elements, submit: () => submit({preventDefault(){}}), stop: () => stopClick(), poll: () => poll()};
}
(async () => {
    let app = harness(async url => String(url).includes('/progress/') ? json({},404) : ({status:500,headers:{get:()=> 'text/html'}}));
    await app.submit();
    assert.match(app.elements['scrape-warning-row'].textContent,/HTML instead of JSON/);
    assert.equal(app.elements.startScrapingBtn.disabled,false);
    app=harness(async () => ({status:403,headers:{get:()=> 'text/html'}}));
    await app.submit();
    assert.match(app.elements['scrape-warning-row'].textContent,/Security verification failed/);
    app=harness(async () => json({total_jobs:0,status:'completed'}));
    await app.submit();
    assert.equal(app.elements.downloadResultsBtn.hidden,true);
    assert.match(app.elements['scrape-progress-row'].textContent,/Saved: 0/);
    app=harness(async () => json({total_jobs:2,status:'completed',download_url:'/download/?keyword=Python',warning:'One page skipped'}));
    await app.submit();
    assert.equal(app.elements.downloadResultsBtn.hidden,false);
    assert.match(app.elements['scrape-warning-row'].textContent,/One page skipped/);
    let finish;
    app=harness(async (url,options) => {
        if(String(url).includes('/progress/')) return json({scraped:3,status:'running',activity:'Extracting <script>job</script>',warning:'One page unavailable'});
        if(String(url).includes('/stop/')) return json({status:'stopping'});
        return new Promise(resolve=>finish=resolve);
    });
    const pending=app.submit();
    await app.poll();
    assert.match(app.elements['scrape-progress-row'].textContent,/Saved: 3/);
    assert.equal(app.elements.stopScrapingBtn.disabled,false);
    await app.stop();
    assert.match(app.elements['scrape-progress-row'].textContent,/Stopping/);
    finish(json({total_jobs:3,status:'stopped',download_url:'/download/?keyword=Python'}));
    await pending;
    assert.match(app.elements['scrape-progress-row'].textContent,/Stopped/);
    assert.equal(app.elements.downloadResultsBtn.hidden,false);
    assert.equal(app.elements.stopScrapingBtn.disabled,true);
    assert.equal(app.elements.startScrapingBtn.disabled,false);
    app=harness(async () => {throw new Error('Network unavailable');});
    await app.submit();
    assert.match(app.elements['scrape-warning-row'].textContent,/Network unavailable/);
    app=harness(async () => json(null));
    await app.submit();
    assert.match(app.elements['scrape-warning-row'].textContent,/invalid result/);
    app=harness(async () => json({total_jobs:0,status:'completed',message:'No new jobs: recognized listings are already saved.',stats:{found:3,duplicates:3},available_jobs:3,download_url:'/download/?keyword=Python'}));
    await app.submit();
    assert.match(app.elements['scrape-progress-row'].textContent,/Found: 3.*Duplicates: 3.*already saved/);
    assert.equal(app.elements.downloadResultsBtn.hidden,false);
    app=harness(async url => String(url).includes('/progress/') ? json({scraped:0,stats:{found:4,missing_job_key:4},status:'failed'}) : json({error:'Listings were found but could not be saved.'},422));
    await app.submit();
    assert.match(app.elements['scrape-progress-row'].textContent,/Found: 4.*Skipped\/errors: 4/);
    assert.match(app.elements['scrape-warning-row'].textContent,/could not be saved/);
    console.log('9 frontend scenarios passed, including duplicate-only results and parser-failure counters.');
})().catch(error=>{console.error(error);process.exitCode=1;});
