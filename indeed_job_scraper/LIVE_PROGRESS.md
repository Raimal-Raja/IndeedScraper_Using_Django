# Live scraping progress and Stop

The scrape page displays exactly two live status rows: the number of jobs saved
and the current action, followed by the latest warning/error. It polls once per
second while the scraping POST is running. Log text is rendered as plain text.

Stop Scraping requests cooperative cancellation. It does not discard saved
JobPosting records or abort a database write. A completed job extraction is saved
before cancellation takes effect at the next boundary. The browser is closed on
exit. A navigation already in flight can take up to its configured timeout to
return. The page shows Stopping until the server confirms it has stopped.

Download CSV remains available for partial results. It exports the saved records
for the selected keyword and country, including matching records from earlier
runs. Existing database rows are not removed on Stop or on a source error.

The progress/stop registry is bounded, thread-safe, and process-local. Run the
Django development server normally, with threading enabled. Multiple production
workers require a shared job queue/state store; progress does not survive server
restarts, although database records do. No database migration is required.

The previous HTTP Google connectivity probe has been removed: failure to reach
Google does not establish that Indeed is unreachable. Indeed navigation now
reports its own failures. Verification challenges stop collection and appear as
warnings; access controls and TLS verification are not bypassed. Chrome updater
IPC messages and the DevTools discovery 404 are not job-collection results.

The footer links to Raimal Raja's supplied LinkedIn and GitHub profiles.

Verification: 18 Django regressions, including immediate-stop record preservation,
and 7 JavaScript scenarios. Run `python manage.py test scraper_app` from
indeed_job_scraper, and run the frontend checks with
`node scraper_app/frontend_tests.cjs`.

## Listing extraction and zero-new-results handling

Recognized job IDs can come from the title link's data-jk, a card's data-jk,
the jk/vjk URL query, or a job_ anchor ID. Listing extraction waits for the current
DOM when cards have not yet loaded. Only one matching card selector family is
processed, avoiding duplicate work caused by overlapping CSS selectors.

A missing description no longer discards a valid title/ID: the record is saved
with an empty description and a warning. Repeated database records are counted
as duplicates, not new saves. Duplicate-only pages do not stop pagination;
visited-page detection prevents loops and numbered pagination only advances.
The implicit last-24-hours search filter has been removed.

Two status rows include found, saved, duplicate and skipped/error counts. All
recognized duplicates are reported as already saved, with a CSV link when the
current search has saved database records. If cards were found but none could
be parsed or saved, the request reports a failure with skip counts rather than
claiming there were no matching jobs. An unknown page layout is an error, not
an empty search. Only explicit no-results text establishes an empty listing.

Verification for these changes: 27 Django tests and 9 frontend scenarios, using
fixtures and mocked source/browser operations. This does not establish live
Indeed availability or bypass its source access controls.

## Pagination, login-gated descriptions, and export format

Both linked pagination and enabled Next buttons are followed, up to the existing
50-page limit. Relative ?start= links preserve the /jobs path. The live display
includes pages visited. Navigation still stops for a login wall or source access
challenge; partial saved rows remain available.

A new Selenium session does not inherit the user's normal Chrome login. Source
login redirects are detected explicitly. When a full job description requires
login, the scraper warns once, avoids repeatedly requesting gated detail pages,
and retains public listing fields. A listing summary, if present, is labelled
as a summary rather than presented as the full description. Missing descriptions
remain blank. Dynamic public descriptions are given time to render.

CSV columns in order:
Title | Post Date | Company name | company Url | Location | Country | Job URL | Description

Only company URLs actually present in listing links are used; no company URL is
invented from a company name. Each saved database record triggers a CSV snapshot
under indeed_job_scraper/exports (override with SCRAPER_EXPORT_DIR). Snapshot
writes are flushed and replaced atomically, and saved records survive Stop.
Existing rows for the same keyword and country are included in that snapshot.
Download CSV uses the same format and regenerates the snapshot from saved data.

Filenames contain safe country and keyword names followed by month_day_year in
Pakistan time, for example united_states_python_developer_10_26_2026.csv.

Validation: 33 Django regressions and 9 frontend scenarios. Live source login or
access restrictions are not bypassed. These tests verify behavior with fixtures
and mocks; they do not guarantee that Indeed makes full descriptions public.

## Source links, incomplete-record repair, and real access limits

The latest live diagnostic returned "Blocked - Indeed.com" before exposing any
listing links. No full live-description success is claimed from that connection.
A source login requirement or access block cannot be repaired by inventing URLs
or suppressing the warning.

Description login detection is now per job. A gated first result no longer skips
all later public descriptions. The scraper follows and saves the supplied Indeed
title href when available instead of rebuilding every detail URL. Public
JobPosting JSON-LD descriptions are accepted alongside rendered description text.
Existing incomplete records are eligible for update, deduplicated by job key,
without deleting the record or replacing an existing nonempty value with blank.
The display distinguishes newly saved jobs from updated records. Source-provided
company /cmp/ links are recognized even without the older CSS test identifiers.

Pages read counts successfully parsed listing pages. Page attempts also count
failed navigation, so a blocked second-page request is no longer shown as two
successfully scraped pages. The final warning includes why pagination stopped,
instead of allowing a description-login warning to hide the collection failure.

Optional manual-login persistence: set SCRAPER_CHROME_PROFILE_DIR in Django
settings to a dedicated directory, e.g. BASE_DIR / '.scraper-browser'. Use only a
separate scraper profile, not the normal Chrome profile while Chrome is running.
Sign in yourself using that profile and close that browser before scraping.
The application does not collect credentials or automate login. Use one scraper
browser at a time with a shared profile. Keep this directory out of version
control; it contains browser session data. A saved login is not a guarantee that
Indeed will permit automated requests.

Validation: 37 Django tests and 9 frontend scenarios (fixture/mocked source
operations). Existing database contents and exports are not overwritten by tests.

## Detail-page failure isolation

A blocked description request is now a typed source exception handled at the
description boundary. It no longer aborts processing all remaining cards from an
already loaded listing page. After a confirmed detail access challenge, further
detail requests are disabled for the run (no challenge retries), and public
listing fields continue to be retained. This differs from per-job login gates,
which do not establish that all other public descriptions are inaccessible.
A blocked listing/navigation request still stops source pagination. The final
warning explicitly distinguishes a detail block from a collection-level block.
Tests cover a blocked existing job followed by a new card and confirm that the
new job is saved, plus stopping on listing blocks. Verification: 40 Django tests
and 9 frontend scenarios, using fixtures and mocked browser operations.

## Optional UC browser and request pacing

The scrape form now offers Standard Chrome (default) and experimental Undetected
Chrome. Request pacing defaults to a 5-second delay plus up to 2 seconds of jitter;
normal pacing uses 2 seconds plus the same jitter. These waits remain interruptible
by Stop. No fake clicks, proxy rotation, CAPTCHA solving, or forced challenge
retries are added. Both modes retain login/challenge detection, saved rows, and
CSV checkpoints. Browser mode/headless status is logged when the browser starts.

UC is lazy-loaded only when selected. Install requirements.txt in the server's
Python environment; UC is tested at version 3.5.5, with setuptools for Python 3.12.
SCRAPER_DRIVER_PATH is copied to a temporary location for UC so its binary patcher
does not alter the configured standard driver. Optional SCRAPER_CHROME_MAJOR can
pin the installed Chrome major if UC's automatic download chooses the wrong one.
Existing SCRAPER_CHROME_PROFILE_DIR works for either mode; only one browser may
use a particular profile at a time. Credentials are not collected or automated.
The integration preserves certificate validation and filters UC's no-sandbox
argument; no additional fingerprint or TLS patches are added by this project.

Live test on 27 October 2026: UC 3.5.5 started with a copied matching ChromeDriver
155 and a disposable headless profile. A single public Indeed Data Scientist
search returned title "Blocked - Indeed.com" and zero listing links. Therefore UC
has not resolved access on this connection and Standard Chrome remains default.
No existing database records, exports, or normal Chrome profiles were used in
that probe. A known UC Windows double-close handle error is handled by the wrapper.

The upstream documentation explicitly says it does not hide IP reputation and
results vary: https://github.com/ultrafunkamsterdam/undetected-chromedriver

Validation: 46 Django regressions and 9 frontend scenarios; live source availability
is reported separately from fixture-based integration checks.

## Browser startup and missing tracebacks

Pages attempted = 0 means startup failed before an Indeed request. Run-local
logging now explicitly writes to the Django terminal and to
indeed_job_scraper/logs/scrape_TIMESTAMP_RUNID.log (override SCRAPER_LOG_DIR).
Timestamps use Pakistan time. The progress snapshot includes the log filename.
BrowserStartupError exposes the original failure type and a bounded detail
message on the website; full tracebacks stay in the terminal/log. Unrelated
runtime errors retain a generic message. Cleanup failures cannot replace the
original startup exception.

On Windows, installed Chrome's major is read from BLBeacon registry version
metadata. UC first tries the newest matching-major driver in Selenium's cache.
It copies that binary before patching it. Explicit SCRAPER_DRIVER_PATH remains
supported. If no compatible cache entry exists, UC's automatic download remains
available and its failure will be visible instead of a silent generic 500.

Real local startup test on 27 October 2026 succeeded: installed Chrome major 155,
cache driver 155.0.8059.84, running Chrome 155.0.8059.86, backend undetected,
headless local page title "UC startup verified". No Indeed request or logged-in
profile was used for this test. This verifies startup, not Indeed availability.

Validation: 49 Django regressions and 9 frontend scenarios, plus the real local
Chrome startup test. Existing database contents and exports remain untouched.
