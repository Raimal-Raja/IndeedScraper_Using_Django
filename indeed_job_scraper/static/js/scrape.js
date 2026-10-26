(() => {
    const form = document.getElementById('scrapeForm');
    const start = document.getElementById('startScrapingBtn');
    const stop = document.getElementById('stopScrapingBtn');
    const resume = document.getElementById('resumeScrapingBtn');
    const download = document.getElementById('downloadResultsBtn');
    const progress = document.getElementById('scrape-progress-row');
    const warning = document.getElementById('scrape-warning-row');
    let active = false, runId = null, timer = null, polling = false, saved = 0, latestWarning = '', latestStats = {};
    const placeholder = '00000000-0000-0000-0000-000000000000';
    const endpoint = key => form.dataset[key].replace(placeholder, runId);
    const headers = { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' };
    function show(data) {
        if (Number.isInteger(data.scraped)) saved = data.scraped;
        if (data.warning) latestWarning = data.warning;
        if (data.stats) latestStats = data.stats;
        if (data.status) {
            resume.hidden = data.status !== 'awaiting_verification';
            resume.disabled = data.status !== 'awaiting_verification';
        }
        const stats = latestStats;
        const counts = `Pages read: ${stats.pages_visited || 0} (attempted: ${stats.pages_attempted || 0}) | Found: ${stats.found || 0} | Saved: ${saved} | Updated: ${stats.updated || 0} | Duplicates: ${stats.duplicates || 0} | Skipped/errors: ${(stats.missing_title || 0) + (stats.missing_job_key || 0) + (stats.extraction_errors || 0) + (stats.database_errors || 0)}`;
        progress.textContent = `${counts} | ${data.activity || data.status || 'Scraping...'}`;
        warning.textContent = `Warnings: ${latestWarning || 'None'}`;
        if (data.download_url && (saved > 0 || data.available_jobs > 0)) {
            const url = new URL(data.download_url, window.location.href);
            if (url.origin !== window.location.origin) throw new Error('Invalid download URL.');
            download.href = url.href;
            download.hidden = false;
        }
    }
    async function parse(response) {
        if (!(response.headers.get('Content-Type') || '').includes('application/json')) {
            throw new Error(response.status === 403 ? 'HTTP 403: Security verification failed. Refresh the page.' : `HTTP ${response.status}: The server returned HTML instead of JSON. Check the server logs.`);
        }
        let data;
        try { data = await response.json(); }
        catch (_) { throw new Error('The server returned invalid JSON.'); }
        if (!data || typeof data !== 'object') throw new Error('The server returned an invalid result.');
        if (!response.ok || data.error) {
            const details = data.errors ? Object.entries(data.errors).flatMap(([field, errors]) => errors.map(item => `${field}: ${item.message}`)).join(' ') : '';
            throw new Error([data.error || `HTTP ${response.status}`, details].filter(Boolean).join(' '));
        }
        return data;
    }
    async function poll() {
        if (!active || polling) return;
        polling = true;
        try {
            const response = await fetch(endpoint('progressUrl'), { headers, credentials: 'same-origin', cache: 'no-store' });
            if (response.status === 404) return; // POST may still be reaching the server.
            const data = await parse(response);
            if (!active) return;
            show(data);
            stop.disabled = !['starting', 'running', 'awaiting_verification'].includes(data.status);
        } catch (error) {
            if (active) warning.textContent = `Warnings: Progress update unavailable: ${error.message}`;
        } finally { polling = false; }
    }
    stop.addEventListener('click', async () => {
        if (!active || stop.disabled) return;
        stop.disabled = true;
        show({ activity: 'Stopping after the current operation; saved records are preserved.' });
        try {
            const data = new FormData(form);
            await parse(await fetch(endpoint('stopUrl'), { method: 'POST', body: data, headers, credentials: 'same-origin' }));
        } catch (error) {
            latestWarning = `Stop request failed: ${error.message}`;
            show({ activity: 'Still scraping. You can retry Stop.' });
            if (active) stop.disabled = false;
        }
    });
    resume.addEventListener('click', async () => {
        if (!active || resume.disabled) return;
        resume.disabled = true;
        try {
            const data = await parse(await fetch(endpoint('resumeUrl'), { method: 'POST', body: new FormData(form), headers, credentials: 'same-origin' }));
            show(data);
        } catch (error) {
            latestWarning = `Resume failed: ${error.message}`;
            show({ activity: 'Complete verification in Chrome, then retry Resume.' });
            if (active) resume.disabled = false;
        }
    });
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (active) return;
        active = true;
        saved = 0; latestWarning = ''; latestStats = {};
        runId = crypto.randomUUID();
        start.disabled = true; stop.disabled = true; download.hidden = true; resume.hidden = true;
        document.getElementById('logging-area').style.display = 'block';
        show({ activity: 'Starting scraping process...' });
        const body = new FormData(form);
        body.set('run_id', runId);
        timer = setInterval(poll, 1000);
        try {
            const data = await parse(await fetch(form.action, { method: 'POST', body, headers, credentials: 'same-origin' }));
            if (!Number.isInteger(data.total_jobs) || data.total_jobs < 0) throw new Error('The server returned an invalid job count.');
            active = false;
            show({ scraped: data.total_jobs, activity: data.status === 'stopped' ? 'Stopped. Saved records are ready to download.' : data.message || (data.total_jobs ? 'Scraping complete. CSV is ready to download.' : 'Complete. No new jobs saved.'), warning: data.warning, download_url: data.download_url, stats: data.stats, available_jobs: data.available_jobs });
        } catch (error) {
            // Recover the saved count/download when the request failed after saving records.
            try {
                const status = await parse(await fetch(endpoint('progressUrl'), { headers, credentials: 'same-origin', cache: 'no-store' }));
                show(status);
            } catch (_) { /* retain the last known count */ }
            active = false;
            latestWarning = error.message;
            show({ activity: 'Scraping could not complete. Saved records are preserved.' });
        } finally {
            active = false;
            clearInterval(timer);
            start.disabled = false; stop.disabled = true; resume.hidden = true;
        }
    });
})();
