import time
import logging
import random
import requests
from fake_useragent import UserAgent
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as UC

# for simple chrome driver
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

class CloudflareHandler:
    def __init__(self, use_proxy=False, proxy=None, captcha_api_key=None):
        self.ua = UserAgent()
        self.driver = None
        self.proxy = proxy
        self.captcha_api_key = captcha_api_key
        self._setup_driver()

    def _setup_driver(self):
        # for undetected chromedriver
        # options = uc.ChromeOptions()

        # for simple chrome driver 
        options = Options()
        
        # Random user-agent
        options.add_argument(f"user-agent={self.ua.random}")

        # proxy
        if self.proxy:
            options.add_argument(f"--proxy-server={self.proxy}")

        # Stealth settings
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        # Initialize ChromeDriver
        # self.driver = uc.Chrome(options=options)
        
        # Initialize ChromeDriver using specific path
        # self.driver = uc.Chrome(
        #     driver_executable_path=r"C:\Users\Professor\OneDrive\Desktop\Updated_Scraper\undetected_chromedriver.exe", 
        #     options=options
        # )

        #initialize simplle chromedriver using specific path
        self.driver = webdriver.Chrome(service=Service(r'C:\Users\Professor\.wdm\drivers\chromedriver\win64\130.0.6723.58\chromedriver-win32\chromedriver.exe'), options=options)
        # return self.driver

        # Further WebDriver stealth
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """
        })
        logging.info("Driver initialized successfully.")

    def get_page(self, url):
        try:
            logging.info(f"Accessing: {url}")
            self.driver.get(url)

            # Random human-like delay
            time.sleep(random.uniform(2, 4))

            # Wait for the page to load
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Simulate interaction
            self.simulate_user_behavior()
            return self.driver.page_source
        except Exception as e:
            logging.error(f"Error accessing URL {url}: {e}")
            return None
    
    def simulate_user_behavior(self):
        try:
            # Get the current window size
            window_size = self.driver.get_window_size()
            
            # Scroll interactions
            total_scroll_height = self.driver.execute_script("return document.body.scrollHeight")
            
            # Perform multiple scroll actions
            scroll_steps = random.randint(2, 5)
            for _ in range(scroll_steps):
                # Calculate a random scroll position
                scroll_position = random.randint(0, max(0, total_scroll_height - window_size['height']))
                
                # Scroll to the position
                self.driver.execute_script(f"window.scrollTo(0, {scroll_position});")
                
                # Random pause between scrolls
                time.sleep(random.uniform(1, 3))
            
            # Instead of mouse movement, use JavaScript to simulate interaction
            self.driver.execute_script("""
                // Simulate mouse hover on a random element
                var elements = document.querySelectorAll('a, button, input');
                if (elements.length > 0) {
                    var randomElement = elements[Math.floor(Math.random() * elements.length)];
                    
                    // Trigger mouseenter event
                    var mouseEnterEvent = new MouseEvent('mouseenter', {
                        'view': window,
                        'bubbles': true,
                        'cancelable': true
                    });
                    randomElement.dispatchEvent(mouseEnterEvent);
                }
            """)
            
            #a small random delay
            time.sleep(random.uniform(1, 2))
            
        except Exception as e:
            logging.error(f"Error simulating behavior: {e}")
        
    def retry_with_cloudscraper(self, url):
        import cloudscraper
        try:
            scraper = cloudscraper.create_scraper()
            response = scraper.get(url)
            if response.status_code == 200:
                logging.info("Successfully bypassed using cloudscraper.")
                return response.text
        except Exception as e:
            logging.error(f"Cloudscraper failed: {e}")
        return None

    def solve_captcha(self, site_key, url):
        if not self.captcha_api_key:
            logging.warning("No CAPTCHA API key provided.")
            return None

        try:
            response = requests.post("http://2captcha.com/in.php", data={
                'key': self.captcha_api_key,
                'method': 'userrecaptcha',
                'googlekey': site_key,
                'pageurl': url,
                'json': 1
            })
            request_id = response.json().get('request')

            for _ in range(20):
                time.sleep(3)
                result = requests.get(f"http://2captcha.com/res.php?key={self.captcha_api_key}&action=get&id={request_id}&json=1")
                if result.json().get('status') == 1:
                    logging.info("CAPTCHA solved successfully.")
                    return result.json().get('request')
        except Exception as e:
            logging.error(f"Error solving CAPTCHA: {e}")
        return None

    def close(self):
        if self.driver:
            self.driver.quit()
            logging.info("Driver closed.")
