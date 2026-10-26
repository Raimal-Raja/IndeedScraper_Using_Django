from unittest.mock import patch, Mock
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from .utils.cloudflare_handler import CloudflareHandler

class ScrapeResponseTests(TestCase):
    def post(self, data=None):
        return self.client.post('/scrape/', data if data is not None else {'keyword': 'Python/C++', 'country': 'United States'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_form_page_and_footer(self):
        response = self.client.get('/scrape/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<main id="main-content">')
        self.assertContains(response, 'min-height: 100dvh')
        self.assertContains(response, '/static/js/scrape.js')

    @patch('scraper_app.views.Scraper')
    def test_invalid_form_returns_json_without_starting_browser(self, scraper):
        response = self.post({'keyword': '', 'country': 'invalid'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('errors', response.json())
        scraper.assert_not_called()

    @patch('scraper_app.views.Scraper', side_effect=RuntimeError('driver unavailable'))
    def test_startup_failure_is_json(self, scraper):
        response = self.post()
        self.assertEqual(response.status_code, 500)
        self.assertIn('error', response.json())
        self.assertNotIn('driver unavailable', response.json()['error'])

    @patch('scraper_app.views.Scraper')
    def test_success_has_safe_download_url_and_closes_browser(self, scraper):
        scraper.return_value.scrape_jobs.return_value = (3, {})
        scraper.return_value.errors = []
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total_jobs'], 3)
        self.assertIn('keyword=Python%2FC%2B%2B', response.json()['download_url'])
        self.assertEqual(self.client.get(response.json()['download_url']).status_code, 200)
        scraper.return_value.close.assert_called_once()

    @patch('scraper_app.views.Scraper')
    def test_runtime_failure_closes_browser(self, scraper):
        scraper.return_value.scrape_jobs.side_effect = RuntimeError('network failed')
        self.assertEqual(self.post().status_code, 500)
        scraper.return_value.close.assert_called_once()

    @patch('scraper_app.views.Scraper')
    def test_blocked_source_is_json_error(self, scraper):
        scraper.return_value.scrape_jobs.return_value = (0, {'United States': 1})
        self.assertEqual(self.post().status_code, 502)
        scraper.return_value.close.assert_called_once()

    @patch('scraper_app.views.Scraper')
    def test_zero_results_does_not_download(self, scraper):
        scraper.return_value.scrape_jobs.return_value = (0, {})
        scraper.return_value.errors = []
        self.assertIsNone(self.post().json()['download_url'])

    def test_csrf_protection_is_preserved(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post('/scrape/', {'keyword': 'Python', 'country': 'United States'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 403)

    @patch('scraper_app.utils.cloudflare_handler.webdriver.Chrome')
    @override_settings(SCRAPER_DRIVER_PATH='chosen-driver.exe')
    def test_configurable_driver_path(self, chrome):
        handler = CloudflareHandler()
        self.assertEqual(chrome.call_args.kwargs['service'].path, 'chosen-driver.exe')
        handler.close()
        handler.close()
        chrome.return_value.quit.assert_called_once()

    @patch('scraper_app.utils.cloudflare_handler.webdriver.Chrome')
    @override_settings(SCRAPER_DRIVER_PATH=None)
    def test_default_uses_selenium_manager(self, chrome):
        handler = CloudflareHandler()
        self.assertNotIn('130.0', str(chrome.call_args))
        handler.close()


class ProgressAndStopTests(TestCase):
    def setUp(self):
        from uuid import uuid4
        self.run_id = str(uuid4())

    def test_two_rows_stop_control_and_account_links(self):
        response = self.client.get('/scrape/')
        for value in ('scrape-progress-row', 'scrape-warning-row', 'stopScrapingBtn', 'https://github.com/Raimal-Raja', 'https://www.linkedin.com/in/raimal-raja-kolhi-860a032bb/'):
            self.assertContains(response, value)

    def test_status_and_stop_endpoints(self):
        from .progress import create_run, update_run
        event = create_run(self.run_id)
        update_run(self.run_id, status='running', scraped=7, activity='Extracting Python developer', warning='One page unavailable')
        status = self.client.get(f'/scrape/progress/{self.run_id}/').json()
        self.assertEqual(status['scraped'], 7)
        self.assertEqual(status['warning'], 'One page unavailable')
        response = self.client.post(f'/scrape/stop/{self.run_id}/')
        self.assertEqual(response.json()['status'], 'stopping')
        self.assertTrue(event.is_set())
        self.assertEqual(self.client.get(f'/scrape/stop/{self.run_id}/').status_code, 405)

    def test_run_not_found_and_stop_requires_csrf(self):
        self.assertEqual(self.client.get(f'/scrape/progress/{self.run_id}/').status_code, 404)
        response = Client(enforce_csrf_checks=True).post(f'/scrape/stop/{self.run_id}/')
        self.assertEqual(response.status_code, 403)

    @patch('scraper_app.views.Scraper')
    def test_stopping_returns_download_and_preserves_saved_jobs(self, scraper):
        from .progress import ScrapingStopped
        from .models import JobPosting
        record = JobPosting.objects.create(title='Saved job', company_name='Company', company_location='Remote', job_url='https://example.com/job/1', job_description='Saved description', post_date='2026-10-26', search_term='Python', country='United States')
        scraper.return_value.total_jobs = 1
        scraper.return_value.scrape_jobs.side_effect = ScrapingStopped()
        response = self.client.post('/scrape/', {'keyword': 'Python', 'country': 'United States', 'run_id': self.run_id}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        data = response.json()
        self.assertEqual(data['status'], 'stopped')
        self.assertEqual(data['total_jobs'], 1)
        self.assertTrue(JobPosting.objects.filter(pk=record.pk).exists())
        self.assertContains(self.client.get(data['download_url']), 'Saved job')
        self.assertEqual(self.client.get(f'/scrape/progress/{self.run_id}/').json()['status'], 'stopped')
        scraper.return_value.close.assert_called_once()

    def test_cancellation_escapes_scraping_loop(self):
        import threading
        from .utils.Scraper import Scraper
        from .progress import ScrapingStopped
        event = threading.Event()
        with patch.object(Scraper, '_initialize_driver'):
            scraper = Scraper(stop_event=event)
        event.set()
        with self.assertRaises(ScrapingStopped):
            scraper.scrape_jobs({'United States': 'https://www.indeed.com/'}, 'Python')

    def test_listing_text_does_not_falsely_mark_source_blocked(self):
        from bs4 import BeautifulSoup
        from .utils.Scraper import Scraper
        with patch.object(Scraper, '_initialize_driver'):
            scraper = Scraper()
        soup = BeautifulSoup('<div class="job_seen_beacon">Security engineer resolves blocked requests</div>', 'html.parser')
        self.assertTrue(scraper._validate_page_content(soup, 'United States'))
        self.assertEqual(scraper.blocked_domains, {})

    def test_source_attempt_is_not_gated_by_google(self):
        from .utils.Scraper import Scraper
        with patch.object(Scraper, '_initialize_driver'):
            scraper = Scraper()
        with patch.object(scraper, '_scrape_country') as scrape:
            scraper.scrape_jobs({'United States': 'https://www.indeed.com/'}, 'Python')
        scrape.assert_called_once()


    def test_stop_after_save_keeps_current_record_and_count(self):
        import threading
        from bs4 import BeautifulSoup
        from .utils.Scraper import Scraper
        from .progress import ScrapingStopped
        from .models import JobPosting
        event = threading.Event()
        with patch.object(Scraper, '_initialize_driver'):
            scraper = Scraper(stop_event=event)
        data = dict(title='Just saved', company_name='Company', company_location='Remote', job_url='https://example.com/job/saved', job_description='Description', post_date='2026-10-26', search_term='Python', country='United States')
        create = JobPosting.objects.create
        def save_and_stop(**values):
            result = create(**values)
            event.set()
            return result
        def interruptible_sleep(seconds):
            scraper._check_stop()
        soup = BeautifulSoup('<div class="job_seen_beacon"><h2 class="jobTitle"><a data-jk="1">Just saved</a></h2></div>', 'html.parser')
        with patch.object(scraper, '_extract_job_data', return_value=data), patch.object(scraper, '_sleep', side_effect=interruptible_sleep), patch.object(JobPosting.objects, 'create', side_effect=save_and_stop):
            with self.assertRaises(ScrapingStopped):
                scraper._process_job_cards(soup, 'https://www.indeed.com/', 'Python', 'United States')
        self.assertEqual(scraper.total_jobs, 1)
        self.assertTrue(JobPosting.objects.filter(job_url=data['job_url']).exists())
