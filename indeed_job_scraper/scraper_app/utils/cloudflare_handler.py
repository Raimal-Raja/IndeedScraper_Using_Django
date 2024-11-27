import undetected_chromedriver as uc
from fake_useragent import UserAgent
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

class CloudflareHandler:
    def __init__(self):
        self.ua = UserAgent()
        self.driver = None
        self._setup_driver()
    
    def _setup_driver(self):
        if not self.driver:
            self.driver = self.get_driver()
    
    def get_driver(self):
        options = Options()
        options.add_argument(f'user-agent={self.ua.random}')
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument('--ignore-certificate-errors')
        
        # Automatically manage ChromeDriver
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        return self.driver
    
    def get_page(self, url):
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            return self.driver.page_source
        except Exception as e:
            logging.error(f"Error accessing page: {str(e)}")
            return None
    
    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None