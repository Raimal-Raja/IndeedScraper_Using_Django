"""Standard Selenium browser with explicit access-challenge reporting."""
import logging
from urllib.parse import urlsplit
from django.conf import settings
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger(__name__)

class SourceAccessBlocked(RuntimeError):
    """A source access challenge, distinct from an ordinary parsing failure."""

class LoginRequired(RuntimeError):
    """The source requires a user login; no automated login or bypass is attempted."""

class CloudflareHandler:
    def __init__(self):
        self.driver = None
        self._setup_driver()

    def _setup_driver(self):
        options = Options()
        if getattr(settings, 'SCRAPER_HEADLESS', False):
            options.add_argument('--headless=new')
        profile = getattr(settings, 'SCRAPER_CHROME_PROFILE_DIR', None)
        if profile:
            from pathlib import Path
            profile = Path(profile).resolve()
            profile.mkdir(parents=True, exist_ok=True)
            options.add_argument(f'--user-data-dir={profile}')
        driver_path = getattr(settings, 'SCRAPER_DRIVER_PATH', None)
        try:
            self.driver = webdriver.Chrome(service=Service(driver_path) if driver_path else Service(), options=options)
            self.driver.set_page_load_timeout(45)
        except Exception:
            self.close()
            logger.exception('Chrome initialization failed; check Chrome and SCRAPER_DRIVER_PATH')
            raise

    def get_page(self, url):
        logger.info('Accessing %s', url)
        self.driver.get(url)
        WebDriverWait(self.driver, 20).until(lambda driver: driver.find_elements(By.TAG_NAME, 'body'))
        title = self.driver.title.lower()
        visible = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
        parts = urlsplit(self.driver.current_url)
        has_description = self.driver.find_elements(By.CSS_SELECTOR, '#jobDescriptionText, [data-testid="jobDescriptionText"]')
        login_path = any(marker in parts.path.lower() for marker in ('/account/login', '/auth', '/signin', '/login'))
        login_title = title.startswith(('sign in', 'log in', 'create an account')) and 'indeed' in title
        if not has_description and (login_path or login_title or 'sign in to view this job' in visible):
            raise LoginRequired('Indeed requires login to view this page')
        if any(term in title for term in ('just a moment', 'access denied', 'security check')) or any(term in visible for term in ('verify you are human', 'verify that you are human', 'unusual traffic', 'slide to verify', 'access denied')):
            raise SourceAccessBlocked('Source access blocked by a verification challenge')
        return self.driver.page_source

    def close(self):
        if self.driver is not None:
            driver, self.driver = self.driver, None
            driver.quit()
