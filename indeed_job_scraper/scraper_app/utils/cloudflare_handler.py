"""Standard Selenium browser with explicit access-challenge reporting."""
import logging
import importlib
import shutil
import tempfile
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
    def __init__(self, backend=None):
        self.backend = backend or getattr(settings, 'SCRAPER_BROWSER_BACKEND', 'selenium')
        if self.backend not in ('selenium', 'undetected'):
            raise ValueError('Unsupported browser backend')
        self._driver_copy = None
        self.driver = None
        self._setup_driver()

    def _setup_driver(self):
        uc = None
        if self.backend == 'undetected':
            try:
                uc = importlib.import_module('undetected_chromedriver')
            except ImportError as exc:
                raise RuntimeError('UC mode is unavailable. Install undetected-chromedriver==3.5.5 and setuptools in the server Python environment, or select Standard Chrome.') from exc
            class SandboxedOptions(uc.ChromeOptions):
                def add_argument(self, argument):
                    if argument not in ('--no-sandbox', '--ignore-certificate-errors'):
                        return super().add_argument(argument)
            options = SandboxedOptions()
            options.set_capability('acceptInsecureCerts', False)
        else:
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
            if uc is not None:
                # UC patches its driver; never modify the standard driver's configured binary.
                if driver_path:
                    from pathlib import Path
                    self._driver_copy = tempfile.TemporaryDirectory(prefix='indeed-uc-driver-')
                    copied = Path(self._driver_copy.name) / Path(driver_path).name
                    shutil.copy2(driver_path, copied)
                    driver_path = str(copied)
                class WindowsChrome(uc.Chrome):
                    def quit(self):
                        try:
                            return super().quit()
                        except OSError:
                            logger.debug('UC driver handle was already closed', exc_info=True)
                self.driver = WindowsChrome(options=options, driver_executable_path=driver_path,
                                            headless=getattr(settings, 'SCRAPER_HEADLESS', False),
                                            version_main=getattr(settings, 'SCRAPER_CHROME_MAJOR', None),
                                            use_subprocess=True, no_sandbox=False)
            else:
                self.driver = webdriver.Chrome(service=Service(driver_path) if driver_path else Service(), options=options)
            logger.info('Browser backend: %s | headless: %s', self.backend, getattr(settings, 'SCRAPER_HEADLESS', False))
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
        try:
            if self.driver is not None:
                driver, self.driver = self.driver, None
                driver.quit()
        finally:
            if self._driver_copy is not None:
                self._driver_copy.cleanup()
                self._driver_copy = None
