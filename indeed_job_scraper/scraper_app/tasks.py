from django.conf import settings
from .models import JobPosting
from .utils.Scraper import Scraper
import logging

def run_job_scraping(keyword, country):
    try:
        # Validate input
        if not keyword or not country:
            logging.error("Invalid scraping parameters")
            return 0
        
        # Create scraper instance
        scraper = Scraper()
        
        # Get domain for specific country
        domains = {country: settings.JOB_DOMAINS.get(country)}
        
        # Scrape jobs
        total_jobs, blocked_domains = scraper.scrape_jobs(domains, keyword)
        
        # Log results
        logging.info(f"Scraped {total_jobs} jobs for '{keyword}' in {country}")
        
        return total_jobs
    
    except Exception as e:
        logging.error(f"Job scraping failed: {str(e)}")
        return 0