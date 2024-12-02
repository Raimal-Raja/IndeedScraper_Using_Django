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

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.config = ScraperConfig()
        self.cf_handler = None
        self.duplicate_checker = DuplicateChecker()
        self.total_jobs = 0
        self.blocked_domains = {}
        self._initialize_driver()

    def _initialize_driver(self) -> None:
        try:
            if self.cf_handler:
                self.cf_handler.close()
            self.cf_handler = CloudflareHandler()
            self.logger.info("Chrome driver initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Chrome driver: {str(e)}")
            raise
    def _check_internet_connection(self):
        try:
            requests.get("http://www.google.com", timeout=5)
            return True
        except requests.RequestException:
            return False
        
    def _get_element_text(self, element: BeautifulSoup, selectors: List[str], default: str = "N/A") -> str:
        try:
            for selector in selectors:
                elements = element.select(selector)
                if elements:
                    return ' '.join(elem.get_text(strip=True) for elem in elements if elem.get_text(strip=True))
            return default
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
        except Exception as e:
            self.logger.error(f"Error checking next page: {str(e)}")
            return None
        
    def _validate_page_content(self, soup: BeautifulSoup, country: str) -> bool:
        try:
            page_text = soup.get_text().lower()
            if any(term in page_text for term in ['captcha', 'security check', 'access denied', 'blocked']):
                self.logger.warning(f"Access blocked for {country}")
                return False

            for selector in self.SELECTORS['job_cards']:
                if soup.select(selector):
                    return True

            self.logger.warning(f"No job cards found for {country}")
            return False

        except Exception as e:
            self.logger.error(f"Error validating page content: {str(e)}")
            return False

    def scrape_jobs(self, domains: Dict[str, str], job_search: str) -> tuple[int, Dict[str, float]]:
        try:
            for country, base_url in domains.items():
                if country in self.blocked_domains:
                    continue

                try:
                    if not self._check_internet_connection():
                        self.logger.error("Internet connection lost")
                        time.sleep(5)
                        continue
                    self._scrape_country(base_url, job_search, country)
                except TimeoutException:
                    self.logger.error(f"Timeout occurred while scraping {country}")
                    continue
                except Exception as e:
                    if any(term in str(e).lower() for term in ['blocked', 'captcha', 'security']):
                        self.blocked_domains[country] = time.time()
                        self.logger.warning(f"Access blocked for {country}: {str(e)}")
                    else:
                        self.logger.error(f"Error scraping {country}: {str(e)}")
                    continue

        except KeyboardInterrupt:
            self.logger.info("\nScraping stopped by user")
            self.close()
        
        finally:
            return self.total_jobs, self.blocked_domains

    def _scrape_country(self, base_url: str, job_search: str, country: str) -> None:
        page = 0
        search_url = f"{base_url}jobs?q={quote_plus(job_search)}&l=&fromage=1"
        current_url = search_url
        
        while page < self.config.MAX_PAGES:
            try:
                self.logger.info(f"Processing page {page + 1} for {country}")
                
                html = None
                for retry in range(self.config.MAX_RETRIES):
                    html = self.cf_handler.get_page(current_url)
                    if html:
                        break
                    time.sleep(self.config.RETRY_DELAYS[retry])

                if not html:
                    self.logger.warning(f"Failed to get HTML content for {country} page {page + 1}")
                    break

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
                
                time.sleep(self.config.PAGE_DELAY)

            except Exception as e:
                self.logger.error(f"Error processing {country} page {page + 1}: {str(e)}")
                break
            
    def _process_job_cards(self, soup: BeautifulSoup, base_url: str, job_search: str, country: str) -> int:
        jobs_processed = 0
        
        for selector in self.SELECTORS['job_cards']:
            job_cards = soup.select(selector)
            if not job_cards:
                continue
                
            for card in job_cards:
                try:
                    time.sleep(random.uniform(1.5, 3.0))
                #     WebDriverWait(self, 10).until(
                #     EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                # )
                    job_data = self._extract_job_data(card, base_url, job_search, country)
                    if job_data:
                        # Create JobPosting model instance directly
                        job_posting = JobPosting.objects.create(**job_data)
                        self.total_jobs += 1
                        jobs_processed += 1
                        self.logger.info(f"Saved job: {job_posting.title} from {country}")
                        time.sleep(random.uniform(0.5, 1.5))
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
                time.sleep(self.config.RETRY_DELAYS[retry])

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
        except Exception as e:
            self.logger.error(f"Error extracting job data: {str(e)}")
            return None
        
    def _extract_company_detail_url(self, card: BeautifulSoup, base_url: str, job_url: str) -> str:
        try:
            for selector in self.SELECTORS['company_link']:
                company_link = card.select_one(selector)
                if company_link and company_link.get('href'):
                    return urljoin(base_url, company_link['href'])

            if 'viewjob' in job_url:
                company_key = job_url.split('?jk=')[-1]
                return urljoin(base_url, f"company?from=serp&company={company_key}")

            return "N/A"
        except Exception as e:
            self.logger.error(f"Error extracting company detail URL: {str(e)}")
            return "N/A"
    
    def _get_job_description(self, url: str) -> Optional[str]:
        try:
            if html := self.cf_handler.get_page(url):
                soup = BeautifulSoup(html, 'html.parser')
                return self._get_element_text(soup, self.SELECTORS['job_description'])
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
        except Exception as e:
            self.logger.error(f"Error closing Chrome driver: {str(e)}")
