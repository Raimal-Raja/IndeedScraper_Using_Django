"""Thread-safe run progress/cancellation for the single-process development server.
Saved job records live in the database, independently of this bounded registry.
"""
import logging
import threading
import time
from uuid import UUID

class ScrapingStopped(Exception):
    pass

_lock = threading.RLock()
_runs = {}

def create_run(run_id):
    run_id = str(UUID(str(run_id)))
    with _lock:
        for key, run in list(_runs.items()):
            if run['status'] not in ('starting', 'running', 'stopping', 'awaiting_verification') and time.monotonic() - run['updated'] > 3600:
                del _runs[key]
        if run_id in _runs:
            raise ValueError('This run ID was already used. Start a new search.')
        if len(_runs) >= 128:
            finished = [key for key, run in _runs.items() if run['status'] not in ('starting', 'running', 'stopping', 'awaiting_verification')]
            if not finished:
                raise ValueError('Too many active searches. Stop an existing search first.')
            del _runs[finished[0]]
        event = threading.Event()
        _runs[run_id] = dict(status='starting', scraped=0, activity='Starting browser...', warning='', event=event, updated=time.monotonic(), download_url=None, stats={}, resume_event=threading.Event(), verification_requests=0)
        return event

def update_run(run_id, **values):
    with _lock:
        run = _runs[run_id]
        if run['event'].is_set() and values.get('status') in ('starting', 'running'):
            values['status'] = 'stopping'
        run.update(values, updated=time.monotonic())

def get_run(run_id):
    with _lock:
        run = _runs.get(str(run_id))
        if run is None:
            return None
        return {key: value for key, value in run.items() if key not in ('event', 'updated', 'resume_event')}

def stop_run(run_id):
    with _lock:
        run = _runs.get(str(run_id))
        if run is None:
            return None
        if run['status'] in ('starting', 'running', 'stopping', 'awaiting_verification'):
            run['event'].set()
            run['resume_event'].set()
            run.update(status='stopping', activity='Stopping after the current operation; saved records are preserved.')
        return get_run(run_id)

def resume_run(run_id):
    with _lock:
        run = _runs.get(str(run_id))
        if run is None:
            return None
        if run['status'] != 'awaiting_verification':
            return {'error': 'This run is not waiting for manual verification.'}
        run['resume_event'].set()
        run.update(status='running', activity='Rechecking the source after manual verification...')
        return get_run(run_id)


def wait_for_verification(run_id, stop_event, reason, timeout=300, max_requests=3):
    with _lock:
        run = _runs[run_id]
        if stop_event.is_set():
            raise ScrapingStopped('Stopped while waiting for verification')
        if run['verification_requests'] >= max_requests:
            update_run(run_id, warning='Manual verification attempt limit reached; partial records remain saved.')
            return False
        run['verification_requests'] += 1
        resume = run['resume_event']
        resume.clear()
        update_run(run_id, status='awaiting_verification', activity='Needs verification: complete login/verification in the open Chrome window, then click Resume Scraping.', warning=reason)
    deadline = time.monotonic() + timeout
    while True:
        if stop_event.is_set():
            raise ScrapingStopped('Stopped while waiting for verification')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            update_run(run_id, status='running', warning='Manual verification timed out. Saved records are preserved.')
            return False
        if resume.wait(min(0.25, remaining)):
            if stop_event.is_set():
                raise ScrapingStopped('Stopped while waiting for verification')
            update_run(run_id, status='running', activity='Rechecking the source after manual verification...')
            return True


class ProgressHandler(logging.Handler):
    def __init__(self, run_id, count, stats=None):
        super().__init__(logging.INFO)
        self.run_id, self.count = run_id, count
        self.stats = stats
        self.thread_id = threading.get_ident()

    def emit(self, record):
        if record.thread != self.thread_id:
            return
        message = record.getMessage()
        count = self.count()
        values = {'scraped': count if isinstance(count, int) else 0}
        if self.stats:
            stats = self.stats()
            if isinstance(stats, dict):
                values['stats'] = dict(stats)
        if record.levelno >= logging.WARNING:
            values['warning'] = message
        else:
            values['activity'] = message
        update_run(self.run_id, **values)
