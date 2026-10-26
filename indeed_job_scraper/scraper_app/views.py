from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from .forms import JobSearchForm
from .models import JobPosting
from .utils.Scraper import Scraper
from .progress import create_run, get_run, update_run, stop_run, ProgressHandler, ScrapingStopped, wait_for_verification, resume_run
from uuid import uuid4, UUID
from django.views.decorators.http import require_GET, require_POST
from .csv_export import export_search
import logging
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from .utils.cloudflare_handler import BrowserStartupError
from urllib.parse import urlencode
from django.urls import reverse

logger = logging.getLogger(__name__)

class PakistanRunFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, ZoneInfo('Asia/Karachi')).strftime('%Y-%m-%d %H:%M:%S %z')

def index(request):
    return render(request, 'index.html')

def start_scraping(request):
    ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method != 'POST':
        return render(request, 'results.html', {'form': JobSearchForm()})
    form = JobSearchForm(request.POST)
    if not form.is_valid():
        if ajax:
            return JsonResponse({'error': 'Please correct the search fields.', 'errors': form.errors.get_json_data()}, status=400)
        return render(request, 'results.html', {'form': form}, status=400)
    keyword = form.cleaned_data['keyword']
    country = form.cleaned_data['country']
    run_id = request.POST.get('run_id') or str(uuid4())
    try:
        run_id = str(UUID(run_id))
        stop_event = create_run(run_id)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    scraper = None
    app_logger = logging.getLogger('scraper_app')
    app_logger.setLevel(logging.INFO)
    handler = ProgressHandler(run_id, lambda: getattr(scraper, 'total_jobs', 0), lambda: getattr(scraper, 'stats', {}))
    app_logger.addHandler(handler)
    # A progress handler consumes log records but does not print them. Add explicit
    # run-local terminal/file handlers so startup exceptions cannot disappear.
    thread_id = threading.get_ident()
    run_filter = lambda record: record.thread == thread_id
    formatter = PakistanRunFormatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s')
    terminal_handler = logging.StreamHandler()
    terminal_handler.setFormatter(formatter)
    terminal_handler.addFilter(run_filter)
    app_logger.addHandler(terminal_handler)
    file_handler = None
    try:
        log_dir = Path(getattr(settings, 'SCRAPER_LOG_DIR', Path(settings.BASE_DIR) / 'logs'))
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(ZoneInfo('Asia/Karachi')).strftime('%Y%m%d_%H%M%S')
        log_path = log_dir / f'scrape_{stamp}_{run_id}.log'
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.addFilter(run_filter)
        app_logger.addHandler(file_handler)
        update_run(run_id, log_file=log_path.name)
    except OSError:
        logger.exception('Could not create run log; terminal logging remains enabled')
    def download_url():
        return reverse('download_results') + '?' + urlencode({'keyword': keyword, 'country': country})
    def verify_manually(url, reason):
        available = JobPosting.objects.filter(search_term=keyword, country=country).count()
        update_run(run_id, available_jobs=available, download_url=download_url() if available else None)
        return wait_for_verification(run_id, stop_event, reason,
                                     timeout=getattr(settings, 'SCRAPER_MANUAL_VERIFICATION_TIMEOUT', 300))
    try:
        scraper = Scraper(stop_event=stop_event, browser_backend=form.cleaned_data.get('browser_backend') or 'selenium', pacing=form.cleaned_data.get('pacing') or 'slow', verification_callback=verify_manually if form.cleaned_data.get('manual_verification') else None)
        if stop_event.is_set():
            raise ScrapingStopped()
        update_run(run_id, status='running', activity=f'Searching {keyword} in {country}')
        total_jobs, blocked_domains = scraper.scrape_jobs({country: settings.JOB_DOMAINS[country]}, keyword)
        raw_stats = getattr(scraper, 'stats', {})
        stats = dict(raw_stats) if isinstance(raw_stats, dict) else {}
        failed_cards = sum(stats.get(key, 0) for key in ('missing_title', 'missing_job_key', 'extraction_errors', 'database_errors'))
        available = JobPosting.objects.filter(search_term=keyword, country=country).count()
        summary = (f"Found: {stats.get('found', 0)} | Saved: {total_jobs} | "
                   f"Updated: {stats.get('updated', 0)} | Duplicates: {stats.get('duplicates', 0)} | Skipped/errors: {failed_cards} | "
                   f"Missing full descriptions: {stats.get('missing_description', 0)} | Pages: {stats.get('pages_visited', 0)}")
        if not (total_jobs or stats.get('updated')) and (blocked_domains or getattr(scraper, 'errors', []) or failed_cards):
            if blocked_domains:
                message = 'The job source blocked access. ' + summary
            elif failed_cards:
                message = 'Listings were found but could not be saved. ' + summary
            else:
                detail = str(scraper.errors[0]).splitlines()[0][:240]
                message = 'Collection failed before saving new jobs: ' + detail
            update_run(run_id, status='failed', activity='Collection failed; see the warning row', warning=message, stats=stats, available_jobs=available, download_url=download_url() if available else None)
            if ajax:
                return JsonResponse({'error': message, 'run_id': run_id, 'stats': stats}, status=422 if failed_cards else 502)
            form.add_error(None, message)
            return render(request, 'results.html', {'form': form}, status=502)
        if (total_jobs or stats.get('updated')) and (blocked_domains or getattr(scraper, 'errors', [])):
            message = 'Partial results saved. Some source pages were unavailable; CSV is ready to download.'
        elif total_jobs or stats.get('updated'):
            message = 'Scraping complete. CSV is ready to download.'
        elif stats.get('duplicates'):
            message = 'No new jobs: recognized listings are already saved.'
        else:
            message = 'The source returned no matching listings.'
        warning = summary if failed_cards or stats.get('missing_description') else ('Some source pages were unavailable. ' + summary if blocked_domains or getattr(scraper, 'errors', []) else '')
        if stats.get('login_required'):
            warning = 'Some job descriptions required Indeed login; other public descriptions were still attempted. ' + summary
        if stats.get('description_blocks'):
            warning = 'Indeed blocked detail-page access. Available listings were retained; further detail requests were skipped. ' + summary
        if blocked_domains or getattr(scraper, 'errors', []):
            failures = getattr(scraper, 'errors', [])
            reason = str(failures[0]).splitlines()[0][:240] if failures else 'Source access was blocked.'
            warning = (warning + ' | ' if warning else '') + f"Pagination stopped: {reason} Read {stats.get('pages_visited', 0)} pages from {stats.get('pages_attempted', 0)} attempts."
        if stats.get('csv_errors'):
            warning = f"CSV checkpoint errors: {stats['csv_errors']}. Jobs are saved in the database. " + warning
        result_url = download_url() if total_jobs or available else None
        update_run(run_id, status='completed', scraped=total_jobs, activity=message, warning=warning, stats=stats, available_jobs=available, download_url=result_url)
        if ajax:
            return JsonResponse({'run_id': run_id, 'status': 'completed', 'message': message, 'stats': stats,
                                 'total_jobs': total_jobs, 'available_jobs': available, 'keyword': keyword, 'country': country,
                                 'download_url': result_url, 'warning': warning})
        return render(request, 'results.html', {'form': form, 'total_jobs': total_jobs, 'keyword': keyword, 'country': country})
    except ScrapingStopped:
        count = getattr(scraper, 'total_jobs', 0)
        count = count if isinstance(count, int) else 0
        available = JobPosting.objects.filter(search_term=keyword, country=country).count()
        update_run(run_id, available_jobs=available)
        update_run(run_id, status='stopped', scraped=count, activity='Stopped. Saved records are preserved.', download_url=download_url() if count or available else None)
        return JsonResponse({'run_id': run_id, 'status': 'stopped', 'total_jobs': count, 'keyword': keyword, 'country': country, 'download_url': download_url() if count or available else None, 'available_jobs': available})
    except Exception as exc:
        logger.exception('Scraping failed for %r in %s', keyword, country)
        message = str(exc) if isinstance(exc, BrowserStartupError) else 'Scraping could not start or complete. Check the server logs for the browser or connection error.'
        update_run(run_id, status='failed', activity='Scraping failed', warning=message, download_url=download_url() if isinstance(getattr(scraper, 'total_jobs', None), int) and scraper.total_jobs > 0 else None)
        if ajax:
            return JsonResponse({'error': message, 'run_id': run_id}, status=500)
        form.add_error(None, message)
        return render(request, 'results.html', {'form': form}, status=500)
    finally:
        app_logger.removeHandler(handler)
        handler.close()
        if scraper is not None:
            try:
                scraper.close()
            except Exception:
                logger.exception('Could not close the scraper browser')
        for run_handler in (terminal_handler, file_handler):
            if run_handler is not None:
                app_logger.removeHandler(run_handler)
                run_handler.close()


@require_GET
def scraping_progress(request, run_id):
    data = get_run(run_id)
    return JsonResponse(data if data is not None else {'error': 'Run not found in this server process.'}, status=200 if data is not None else 404)


@require_POST
def stop_scraping(request, run_id):
    data = stop_run(run_id)
    return JsonResponse(data if data is not None else {'error': 'Run not found in this server process.'}, status=200 if data is not None else 404)


@require_POST
def resume_scraping(request, run_id):
    data = resume_run(run_id)
    if data is None:
        return JsonResponse({'error': 'Run not found in this server process.'}, status=404)
    return JsonResponse(data, status=409 if 'error' in data else 200)


def download_csv(request, keyword=None, country=None):
    form = JobSearchForm({'keyword': keyword if keyword is not None else request.GET.get('keyword'),
                          'country': country if country is not None else request.GET.get('country')})
    if not form.is_valid():
        return JsonResponse({'error': 'Invalid download parameters.'}, status=400)
    keyword, country = form.cleaned_data['keyword'], form.cleaned_data['country']
    path, content = export_search(keyword, country)
    response = HttpResponse('\ufeff' + content, content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{path.name}"'
    return response
