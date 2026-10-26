"""Shared download and per-record checkpoint format for job CSV exports."""
import csv
import io
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from django.conf import settings
from django.utils.text import slugify
from .models import JobPosting

HEADERS = ['Title', 'Post Date', 'Company name', 'company Url', 'Location', 'Country', 'Job URL', 'Description']
_lock = threading.Lock()

def csv_filename(keyword, country, day=None):
    day = day or datetime.now(ZoneInfo('Asia/Karachi'))
    country_part = slugify(country).replace('-', '_') or 'country'
    keyword_part = slugify(keyword).replace('-', '_') or 'jobs'
    return f'{country_part[:60]}_{keyword_part[:100]}_{day:%m_%d_%Y}.csv'

def export_search(keyword, country):
    """Write a fresh snapshot after a DB save, retaining records from earlier runs."""
    directory = Path(getattr(settings, 'SCRAPER_EXPORT_DIR', Path(settings.BASE_DIR) / 'exports'))
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / csv_filename(keyword, country)
    with _lock:
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(HEADERS)
        for job in JobPosting.objects.filter(search_term=keyword, country=country).order_by('created_at', 'pk').iterator():
            writer.writerow([job.title, job.post_date, job.company_name, job.company_detail_url or '', job.company_location, job.country, job.job_url, job.job_description])
        content = stream.getvalue()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8-sig', newline='', dir=directory, suffix='.tmp', delete=False) as handle:
                temporary = handle.name
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
    return destination, content
