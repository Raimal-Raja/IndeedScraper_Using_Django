"""Standard Selenium browser with explicit access-challenge reporting."""
import logging
import importlib
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from django.conf import settings
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger(__name__)

class BrowserStartupError(RuntimeError):
    """A browser configuration/download/startup failure safe to show locally."""

def installed_chrome_major():
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for key in (r'Software\Google\Chrome\BLBeacon', r'Software\WOW6432Node\Google\Chrome\BLBeacon'):
                try:
                    with winreg.OpenKey(hive, key) as handle:
                        version, _ = winreg.QueryValueEx(handle, 'version')
                        return int(version.split('.')[0])
                except OSError:
                    continue
    except ImportError:
        pass
    return None

def cached_matching_driver(major=None, cache=None):
    major = major or installed_chrome_major()
    if major is None:
        return None
    cache = Path(cache) if cache else Path.home() / '.cache' / 'selenium' / 'chromedriver'
    candidates = []
    for candidate in cache.glob(f'*/{major}.*/*chromedriver*'):
        if candidate.is_file() and candidate.name in ('chromedriver.exe', 'chromedriver'):
            try:
                version = tuple(int(part) for part in candidate.parent.name.split('.'))
            except ValueError:
                continue
            candidates.append((version, candidate))
    return str(max(candidates)[1]) if candidates else None

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
        try:
            self._setup_driver()
        except BrowserStartupError:
            raise
        except Exception as exc:
            detail = ' '.join(str(exc).splitlines()[:3]).strip()[:600] or type(exc).__name__
            raise BrowserStartupError(f'{self.backend} browser could not start ({type(exc).__name__}): {detail}. Check the driver version/path, network access for driver downloads, and whether the configured Chrome profile is already open.') from exc

    def _setup_driver(self):
        uc = None
        if self.backend == 'undetected':
            try:
                uc = importlib.import_module('undetected_chromedriver')
            except ImportError as exc:
                raise BrowserStartupError('UC mode is unavailable. Install undetected-chromedriver==3.5.5 and setuptools in the server Python environment, or select Standard Chrome.') from exc
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
        major = getattr(settings, 'SCRAPER_CHROME_MAJOR', None) or installed_chrome_major()
        if uc is not None and not driver_path:
            driver_path = cached_matching_driver(major)
            if driver_path:
                logger.info('Using cached matching ChromeDriver for Chrome %s: %s', major, driver_path)
            else:
                logger.info('No matching cached UC driver; automatic driver download may require network access')
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
                                            version_main=major,
                                            use_subprocess=True, no_sandbox=False)
            else:
                self.driver = webdriver.Chrome(service=Service(driver_path) if driver_path else Service(), options=options)
            logger.info('Browser backend: %s | headless: %s', self.backend, getattr(settings, 'SCRAPER_HEADLESS', False))
            self.driver.set_page_load_timeout(45)
        except Exception:
            try:
                self.close()
            except Exception:
                logger.warning('Browser cleanup failed during startup', exc_info=True)
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
