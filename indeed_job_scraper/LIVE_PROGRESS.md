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
