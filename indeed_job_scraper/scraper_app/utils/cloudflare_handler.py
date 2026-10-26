"""Standard Selenium browser with explicit access-challenge reporting."""
import logging
import importlib
import shutil
import tempfile
import threading
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from uuid import uuid4
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from django.conf import settings
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger(__name__)
_manual_profile_lock = threading.Lock()

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
    def __init__(self, backend=None, verification_callback=None):
        self.verification_callback = verification_callback
        self._profile_lock_held = False
        self.backend = backend or getattr(settings, 'SCRAPER_BROWSER_BACKEND', 'selenium')
        if self.backend not in ('selenium', 'undetected'):
            raise ValueError('Unsupported browser backend')
        self._driver_copy = None
        self.driver = None
        try:
            self._setup_driver()
        except Exception as exc:
            try:
                self.close()
            except Exception:
                logger.warning('Browser cleanup failed after startup failure', exc_info=True)
            if isinstance(exc, BrowserStartupError):
                raise
            detail = ' '.join(str(exc).splitlines()[:3]).strip()[:600] or type(exc).__name__
            raise BrowserStartupError(f'{self.backend} browser could not start ({type(exc).__name__}): {detail}. Check the driver version/path, network access for driver downloads, and whether the configured Chrome profile is already open.') from exc

    def _setup_driver(self):
        if self.verification_callback:
            if getattr(settings, 'SCRAPER_HEADLESS', False):
                raise BrowserStartupError('Manual verification requires visible Chrome. Set SCRAPER_HEADLESS=False or disable manual verification.')
            if not _manual_profile_lock.acquire(blocking=False):
                raise BrowserStartupError('A manual-verification browser is already open. Stop that run before starting another.')
            self._profile_lock_held = True
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
        if self.verification_callback and not profile:
            profile = Path(settings.BASE_DIR) / '.scraper-browser'
        if profile:
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

    @staticmethod
    def diagnostic_url(url):
        parts = urlsplit(url)
        # Drop auth/redirect/tracking query values and URL credentials from diagnostics.
        query = urlencode([(key, value) for key, value in parse_qsl(parts.query) if key in ('q', 'start', 'jk', 'vjk')])
        return urlunsplit((parts.scheme, parts.hostname or '', parts.path, query, ''))

    def _capture_diagnostic(self, requested_url, reason, title, visible):
        try:
            base = Path(getattr(settings, 'SCRAPER_LOG_DIR', Path(settings.BASE_DIR) / 'logs'))
            directory = Path(getattr(settings, 'SCRAPER_DIAGNOSTIC_DIR', base / 'diagnostics'))
            directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(ZoneInfo('Asia/Karachi')).strftime('%Y%m%d_%H%M%S_%f')
            stem = f'page_{stamp}_{uuid4().hex[:8]}'
            picture = directory / (stem + '.png')
            screenshot = None
            try:
                self.driver.save_screenshot(str(picture))
                if picture.exists():
                    screenshot = picture.name
            except Exception:
                logger.warning('Could not save source-page screenshot', exc_info=True)
            metadata = dict(timestamp=datetime.now(ZoneInfo('Asia/Karachi')).isoformat(timespec='seconds'),
                            reason=reason, requested_url=self.diagnostic_url(requested_url),
                            final_url=self.diagnostic_url(self.driver.current_url), title=title,
                            visible_text_excerpt=visible[:2000], screenshot=screenshot, backend=self.backend)
            path = directory / (stem + '.json')
            path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
            logger.warning('Source diagnostic: %s | reason=%s | final_url=%s | title=%r', path, reason, metadata['final_url'], title)
            return path.name
        except Exception:
            logger.warning('Could not save source-page diagnostics', exc_info=True)
            return None

    def get_page(self, url):
        try:
            return self._read_page(url)
        except (LoginRequired, SourceAccessBlocked) as exc:
            callback = getattr(self, 'verification_callback', None)
            if callback and callback(url, str(exc)):
                # Only an explicit user Resume action triggers this one recheck.
                return self._read_page(url)
            raise

    def _read_page(self, url):
        logger.info('Accessing %s', url)
        self.driver.get(url)
        WebDriverWait(self.driver, 20).until(lambda driver: driver.find_elements(By.TAG_NAME, 'body'))
        title = self.driver.title
        visible = self.driver.find_element(By.TAG_NAME, 'body').text
        parts = urlsplit(self.driver.current_url)
        lower_title, lower_text = title.lower().strip(), visible.lower()
        login_path = any(marker in parts.path.lower() for marker in ('/account/login', '/auth', '/signin', '/login'))
        login_title = bool(re.fullmatch(r'(?:sign in|log in|login|create an account)(?:\s*[|\u2013-]\s*.*indeed.*)?', lower_title))
        challenge_title = lower_title.startswith(('blocked - indeed', 'access denied', 'just a moment', 'security check', 'attention required'))
        reason, exception_type = None, None
        if login_path or login_title:
            reason, exception_type = 'login URL/title', LoginRequired
        elif challenge_title:
            reason, exception_type = 'verification/access-challenge title', SourceAccessBlocked
        else:
            content = self.driver.find_elements(By.CSS_SELECTOR, '#jobDescriptionText, [data-testid="jobDescriptionText"], h2.jobTitle a, a.jcs-JobTitle')
            has_content = any(element.is_displayed() and element.text.strip() for element in content)
            # A footer sign-in invitation or job text mentioning access denial does
            # not establish that an otherwise visible result page is inaccessible.
            if not has_content:
                if 'sign in to view this job' in lower_text:
                    reason, exception_type = 'login-required text without recognized job content', LoginRequired
                elif any(term in lower_text for term in ('verify you are human', 'verify that you are human', 'unusual traffic', 'slide to verify', 'access denied', 'additional verification required')):
                    reason, exception_type = 'verification text without recognized job content', SourceAccessBlocked
        if exception_type:
            diagnostic = self._capture_diagnostic(url, reason, title, visible)
            message = 'Indeed requires login to view this page' if exception_type is LoginRequired else 'Source access blocked by a verification challenge'
            raise exception_type(message + (f' [diagnostic: {diagnostic}]' if diagnostic else ''))
        return self.driver.page_source

    def close(self):
        try:
            if self.driver is not None:
                driver, self.driver = self.driver, None
                driver.quit()
        finally:
            try:
                if self._driver_copy is not None:
                    self._driver_copy.cleanup()
                    self._driver_copy = None
            finally:
                if getattr(self, '_profile_lock_held', False):
                    self._profile_lock_held = False
                    _manual_profile_lock.release()
