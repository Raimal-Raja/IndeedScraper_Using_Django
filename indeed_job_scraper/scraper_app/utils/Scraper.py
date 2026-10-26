from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote_plus
import time
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
import random
# imported files
from .cloudflare_handler import CloudflareHandler
from scraper_app.models import JobPosting
from .duplicate_checker import DuplicateChecker
from scraper_app.progress import ScrapingStopped
import threading

@dataclass
class ScraperConfig:
    PAGE_DELAY: int = 2
    MAX_RETRIES: int = 2
    RESULTS_PER_PAGE: int = 15
    MAX_PAGES: int = 50
    RETRY_DELAYS: List[int] = (2, 3)

class Scraper:
    SELECTORS = {
        'job_title': 'h2[class*="jobTitle"] a',
        'company_name': [
            'span[data-testid="company-name"]', 
            'a[data-testid="company-link"]',
            'span[class*="companyName"]',
            'a[class*="companyName"]'
        ],
        'company_location': [
            'div[data-testid="job-location"]',
            'div[class*="companyLocation"]',
            'div[class*="location"]',
            'div[class*="job-location"]',
            'span[class*="location"]'
        ],
        'job_description': [
            'div[data-testid="jobDescriptionText"]',
            '#jobDescriptionText',
            'div[class*="jobDescriptionText"]'
        ],
        'post_date': [
            'span[class*="date"]',
            'span[class*="postDate"]',
            'time[class*="date"]'
        ],
        'next_page': [
            'a[aria-label="Next"]',
            'a[data-testid="pagination-page-next"]', 
            'a[class*="pagination-next"]',
            'a[href*="start="]',
            'nav[role="navigation"] a[href*="start="]'
        ],
        'company_link': [
            'a[data-testid="company-link"]',
            'span[data-testid="company-name"] a'
        ],
        'job_cards': [
            'div.job_seen_beacon',
            'div[class*="job_seen_beacon"]',
            'div[class*="cardOutline"]',
            'div[class*="job-card"]'
        ]
    }

    def __init__(self, stop_event=None):
        self.stop_event = stop_event or threading.Event()
        self.logger = logging.getLogger(__name__)
        self.config = ScraperConfig()
        self.cf_handler = None
        self.duplicate_checker = DuplicateChecker()
        self.total_jobs = 0
        self.errors = []
        self.blocked_domains = {}
        self._initialize_driver()

    def _check_stop(self):
        if self.stop_event.is_set():
            raise ScrapingStopped('Scraping stopped by user')

    def _sleep(self, seconds):
        if self.stop_event.wait(seconds):
            self._check_stop()

    def _initialize_driver(self) -> None:
        try:
            if self.cf_handler:
                self.cf_handler.close()
            self.cf_handler = CloudflareHandler()
            self.logger.info("Chrome driver initialized successfully")
        except ScrapingStopped:
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Chrome driver: {str(e)}")
            raise
    def _get_element_text(self, element: BeautifulSoup, selectors: List[str], default: str = "N/A") -> str:
        try:
            for selector in selectors:
                elements = element.select(selector)
                if elements:
                    return ' '.join(elem.get_text(strip=True) for elem in elements if elem.get_text(strip=True))
            return default
        except ScrapingStopped:
            raise
        except Exception as e:
            self.logger.error(f"Error extracting element text: {str(e)}")
            return default
    def get_page(self, url):
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div.job_seen_beacon'))  # Wait for job cards to load
            )
            return self.driver.page_source
        except ScrapingStopped:
            raise
        except Exception as e:
            logging.error(f"Error accessing page: {str(e)}")
            return None
    
    def _has_next_page(self, soup: BeautifulSoup) -> Optional[str]:
        """Enhanced next page detection that returns the next page URL"""
        try:
            for selector in self.SELECTORS['next_page']:
                next_page = soup.select_one(selector)
                if next_page and next_page.get('href'):
                    return next_page['href']
                
            # Fallback pagination check - look for numbered pagination
            pagination = soup.select('nav[role="navigation"] a')
            current_page = None
            for page in pagination:
                if 'aria-current' in page.attrs:
                    try:
                        current_page = int(page.get_text(strip=True))
                        break
                    except ValueError:
                        continue
            
            if current_page is not None:
                next_page_num = current_page + 1
                next_page_elem = soup.select_one(f'a[href*="start={next_page_num * self.config.RESULTS_PER_PAGE}"]')
                if next_page_elem:
                    return next_page_elem['href']
            
            return None
        except ScrapingStopped:
            raise
        except Exception as e:
            self.logger.error(f"Error checking next page: {str(e)}")
            return None
        
    def _validate_page_content(self, soup: BeautifulSoup, country: str) -> bool:
        try:
            # Listing cards establish results; incidental words in job descriptions
            # (for example "blocked") do not establish an access challenge.
            for selector in self.SELECTORS['job_cards']:
                if soup.select(selector):
                    return True
            page_text = soup.get_text(' ', strip=True).lower()
            heading = soup.title.get_text().lower() if soup.title else ''
            if any(term in heading for term in ('just a moment', 'access denied', 'security check')) or any(term in page_text for term in ('verify you are human', 'verify that you are human', 'unusual traffic', 'slide to verify', 'access denied')):
                self.blocked_domains[country] = time.time()
                self.logger.warning(f"Access blocked for {country}")
                return False

            self.logger.warning(f"No job cards found for {country}")
            return False

        except ScrapingStopped:
            raise
        except Exception as e:
            self.logger.error(f"Error validating page content: {str(e)}")
            return False

    def scrape_jobs(self, domains: Dict[str, str], job_search: str) -> tuple[int, Dict[str, float]]:
        try:
            for country, base_url in domains.items():
                self._check_stop()
                if country in self.blocked_domains:
                    continue

                try:
                    self._scrape_country(base_url, job_search, country)
                except TimeoutException:
                    self.errors.append(f"Timeout while scraping {country}")
                    self.logger.error(f"Timeout occurred while scraping {country}")
                    continue
                except ScrapingStopped:
                    raise
                except Exception as e:
                    self.errors.append(str(e))
                    if any(term in str(e).lower() for term in ['blocked', 'captcha', 'security']):
                        self.blocked_domains[country] = time.time()
                        self.logger.warning(f"Access blocked for {country}: {str(e)}")
                    else:
                        self.logger.error(f"Error scraping {country}: {str(e)}")
                    continue

        except KeyboardInterrupt:
            self.logger.info("\nScraping stopped by user")
            self.close()
        
        return self.total_jobs, self.blocked_domains

    def _scrape_country(self, base_url: str, job_search: str, country: str) -> None:
        page = 0
        search_url = f"{base_url}jobs?q={quote_plus(job_search)}&l=&fromage=1"
        current_url = search_url
        
        while page < self.config.MAX_PAGES:
            self._check_stop()
            try:
                self.logger.info(f"Processing page {page + 1} for {country}")
                
                html = None
                for retry in range(self.config.MAX_RETRIES):
                    self._check_stop()
                    html = self.cf_handler.get_page(current_url)
                    self._check_stop()
                    if html:
                        break
                    self._sleep(self.config.RETRY_DELAYS[retry])

                if not html:
                    raise RuntimeError(f"Failed to get HTML content for {country} page {page + 1}")

                soup = BeautifulSoup(html, "html.parser")
                if not self._validate_page_content(soup, country):
                    break
                
                WebDriverWait(self.cf_handler.driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div.job_seen_beacon'))
            )
                
                jobs_processed = self._process_job_cards(soup, base_url, job_search, country)
                if jobs_processed == 0:
                    self.logger.warning(f"No jobs processed on page {page + 1} for {country}")
                    break

                next_page_url = self._has_next_page(soup)
                if not next_page_url:
                    self.logger.info(f"No more pages available for {country}")
                    break

                current_url = urljoin(base_url, next_page_url)
                page += 1
                
                self._sleep(self.config.PAGE_DELAY)

            except ScrapingStopped:
                raise
            except Exception as e:
                self.logger.exception(f"Error processing {country} page {page + 1}")
                raise

    def _process_job_cards(self, soup: BeautifulSoup, base_url: str, job_search: str, country: str) -> int:
        jobs_processed = 0
        
        for selector in self.SELECTORS['job_cards']:
            job_cards = soup.select(selector)
            if not job_cards:
                continue
                
            for card in job_cards:
                self._check_stop()
                try:
                    self._sleep(random.uniform(1.5, 3.0))
                #     WebDriverWait(self, 10).until(
                #     EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                # )
                    self.logger.info("Extracting job: %s", self._get_element_text(card, [self.SELECTORS['job_title']]))
                    job_data = self._extract_job_data(card, base_url, job_search, country)
                    if job_data:
                        # Each record is committed before counting it as saved.
                        # Create JobPosting model instance directly
                        job_posting = JobPosting.objects.create(**job_data)
                        self.total_jobs += 1
                        jobs_processed += 1
                        self.logger.info(f"Saved job: {job_posting.title} from {country}")
                        self._sleep(random.uniform(0.5, 1.5))
                except ScrapingStopped:
                    raise
                except Exception as e:
                    self.logger.error(f"Error processing job card: {str(e)}")
                    continue
                    
        return jobs_processed
    def _extract_job_data(self, card: BeautifulSoup, base_url: str, job_search: str, country: str) -> Optional[Dict]:
        try:
            title_elem = card.select_one(self.SELECTORS['job_title'])
            if not title_elem or 'data-jk' not in title_elem.attrs:
                return None

            job_key = title_elem['data-jk']
            job_url = urljoin(base_url, f"viewjob?jk={job_key}")
            
            if self.duplicate_checker.is_duplicate(job_url):
                return None

            company_name = self._get_element_text(card, self.SELECTORS['company_name'])
            location = self._get_element_text(card, self.SELECTORS['company_location'])
            
            if location == "N/A":
                location_elements = card.select('[class*="location"], [class*="Location"]')
                if location_elements:
                    location = ' '.join(elem.get_text(strip=True) for elem in location_elements)

            company_detail_url = self._extract_company_detail_url(card, base_url, job_url)

            job_desc = None
            for retry in range(self.config.MAX_RETRIES):
                job_desc = self._get_job_description(job_url)
                if job_desc:
                    break
                self._sleep(self.config.RETRY_DELAYS[retry])

            if not job_desc:
                return None

            return {
                'post_date': self._extract_post_date(card),
                'title': title_elem.get_text(strip=True),
                'company_name': company_name,
                'company_location': location,
                'company_detail_url': company_detail_url,
                'job_url': job_url,
                'job_description': job_desc,
                'search_term': job_search,
                'country': country
            }
        except ScrapingStopped:
            raise
        except Exception as e:
            self.logger.error(f"Error extracting job data: {str(e)}")
            return None
        
    def _extract_company_detail_url(self, card: BeautifulSoup, base_url: str, job_url: str) -> str:
        try:
            # First, try to extract company name from the card
            company_name = None
            for selector in self.SELECTORS.get('company_name', []):
                company_element = card.select_one(selector)
                if company_element:
                    company_name = company_element.get_text(strip=True)
                    break
            
            # If company name not found, try alternative methods
            if not company_name:
                # Try extracting from selectors
                for selector in self.SELECTORS.get('company_link', []):
                    company_link = card.select_one(selector)
                    if company_link:
                        # Extract company name from the link text or title
                        company_name = company_link.get_text(strip=True)
                        break
            
            # If still no company name, try extracting from job URL
            if not company_name and 'viewjob' in job_url:
                company_key = job_url.split('?jk=')[-1]
                # Fallback to job-based company URL
                return urljoin(base_url, f"company?from=serp&company={company_key}")
            
            # Generate company URL using the new method
            if company_name and company_name != "N/A":
                # Create a slug similar to the get_company_url method
                company_slug = ''.join(c for c in company_name.lower() 
                                    if c.isalnum() or c in ' -')
                company_slug = company_slug.replace(' ', '-')
                company_url = f"{base_url}cmp/{quote_plus(company_slug)}"
                return company_url
            
            return "N/A"
        
        except ScrapingStopped:
            raise
        except Exception as e:
            self.logger.error(f"Error extracting company detail URL: {str(e)}")
            return "N/A"
    
    def _get_job_description(self, url: str) -> Optional[str]:
        try:
            if html := self.cf_handler.get_page(url):
                soup = BeautifulSoup(html, 'html.parser')
                return self._get_element_text(soup, self.SELECTORS['job_description'])
        except ScrapingStopped:
            raise
        except Exception as e:
            self.logger.error(f"Failed to fetch job description: {str(e)}")
        return None
        
    def _extract_post_date(self, card: BeautifulSoup) -> str:
        try:
            date_text = self._get_element_text(card, self.SELECTORS['post_date'])
            if date_text == "N/A":
                return time.strftime('%Y-%m-%d')

            date_text = date_text.lower()
            if any(x in date_text for x in ['just posted', 'today']):
                return time.strftime('%Y-%m-%d')

            if 'day' in date_text and 'ago' in date_text:
                if days := int(''.join(filter(str.isdigit, date_text))):
                    return time.strftime('%Y-%m-%d', 
                                       time.localtime(time.time() - (days * 86400)))

            return time.strftime('%Y-%m-%d')
        except Exception:
            return time.strftime('%Y-%m-%d')
    

    def close(self) -> None:
        try:
            if self.cf_handler:
                self.cf_handler.close()
                self.logger.info("Chrome driver closed successfully")
        except ScrapingStopped:
            raise
        except Exception as e:
            self.logger.error(f"Error closing Chrome driver: {str(e)}")
