# DataScraper Pro - Indeed Job Scraper 🚀

A powerful Django web application that scrapes job listings from Indeed across multiple countries. Built with Python, Selenium, and Django, this tool helps you gather job data efficiently while handling anti-bot measures.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Django](https://img.shields.io/badge/django-5.1+-green.svg)
![Selenium](https://img.shields.io/badge/selenium-4.0+-orange.svg)

## 📌 Table of Contents
- [Features](#-features)
- [Technology Stack](#️-technology-stack)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Project Structure](#-project-structure)
- [Usage](#-usage)
- [Resources](#-resources)
- [Contributing](#-contributing)
- [License](#-license)
- [Contact](#-contact)

## ✨ Features

- **Multi-Country Support**: Scrape job listings from 14 different countries
- **User-Friendly Interface**: Clean and intuitive web interface
- **Automated Scraping**: Handles Cloudflare protection and bot detection
- **Data Export**: Download scraped data in CSV format
- **Duplicate Prevention**: Intelligent system to prevent duplicate listings
- **Real-Time Progress**: Live updates during scraping
- **Responsive Design**: Works on all devices
- **Error Handling**: Robust error management system
- **Logging**: Comprehensive logging system

## 🛠️ Technology Stack

### Core Technologies
- Python 3.8+
- Django 5.1+
- Selenium WebDriver
- SQLite3

### Frontend
- HTML5
- CSS3 (Bootstrap 5)
- JavaScript (ES6+)

### Additional Tools
- Chrome/Firefox WebDriver
- Virtual Environment
- Git

## 📋 Prerequisites

1. Python 3.8+
2. pip (Python package manager)
3. Virtual Environment
4. Chrome/Firefox Browser
5. Git
6. Basic knowledge of Django and Python

## 🚀 Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/datascraper-pro.git
cd datascraper-pro
```

2. **Create and activate virtual environment**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**
```bash
# Create .env file
cp .env.example .env

# Edit .env with your configurations
nano .env
```

5. **Run migrations**
```bash
python manage.py makemigrations
python manage.py migrate
```

6. **Create superuser (optional)**
```bash
python manage.py createsuperuser
```

7. **Run development server**
```bash
python manage.py runserver
```

## 🔧 Configuration

### WebDriver Setup
1. Download Chrome WebDriver:
   - [Chrome WebDriver](https://sites.google.com/chromium.org/driver/)
   - [Firefox GeckoDriver](https://github.com/mozilla/geckodriver/releases)

2. Add to PATH:
```bash
# Linux/Mac
export PATH=$PATH:/path/to/webdriver

# Windows
setx PATH "%PATH%;C:\path\to\webdriver"
```

### Required Packages
```txtbeautifulsoup4==4.12.2
urllib3==2.0.4
selenium==4.11.2
undetected-chromedriver==3.4.6
fake-useragent==1.2.0
requests==2.31.0
dataclasses==0.6
typing-extensions==4.8.0
webdriver-manager==4.0.0
```

## 📚 Project Structure
```
indeed_job_scraper/
├── .env
├── .gitignore
├── README.md
├── manage.py
├── static/
│   ├── css/
│   │   ├── custom.css
│   │   └── style.css
│   └── images/
│       ├── analytics.jpg
|       ├── data.jpg
|       ├── search.jpg
│       └── data-bg.jpg
├── templates/
│   ├── base.html
│   ├── index.html
│   └── results/
├── scraper_app/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── forms.py
│   ├── models.py
    ├── tasks.py
│   ├── urls.py
│   ├── views.py
│   ├── _pychache_/
│   │   ├── __init__.cpython-312.pyc
│   │   ├── admin.cpython-312.pyc
|   |   ├── apps.cpython-312.pyc
|   |   ├── forms.cpython-312.pyc
|   |   ├── models.cpython-312.pyc
|   |   ├── tasks.cpython-312.pyc
|   |   ├── urls.cpython-312.pyc
│   │   └── views.cpython-312.pyc
│   └── utils/
|       ├── logger_config.py
│       ├── Scraper.py
│       ├── Cloudflare_Handler.py
│       ├── Duplicate_checker.py
│       └──__pycache__
|                     ├── logger_config.pyc
│                     ├── Scraper.pyc
│                     ├── Cloudflare_Handler.pyc
│                     └── Duplicate_checker.pyc
└── indeed_job_scraper/
    ├── __init__.py
    ├── asgi.py
    ├── settings.py
    ├── urls.py
    └── wsgi.py
```

## 📖 Usage

1. Access the application:
```
http://localhost:8000
```

2. Navigate to "Scrape Data"
3. Enter job parameters:
   - Job Title (e.g., "Python Developer")
   - Country (select from dropdown)
4. Click "Start Scraping"
5. Monitor progress
6. Download results

## 📚 Learning Resources

### Python & Django
- [Real Python](https://realpython.com/)
- [Django Documentation](https://docs.djangoproject.com/)
- [Python Web Scraping Tutorials](https://www.scrapingbee.com/blog/web-scraping-101-with-python/)
- [Django Girls Tutorial](https://tutorial.djangogirls.org/)

### Web Scraping
- [Selenium Python Documentation](https://selenium-python.readthedocs.io/)
- [Web Scraping with Python Book](https://www.amazon.com/Web-Scraping-Python-Collecting-Modern/dp/1491910291)
- [Scraping Hub Blog](https://blog.scrapinghub.com/)
- [Beautiful Soup Documentation](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)

### Development Tools
- [Git Tutorial](https://git-scm.com/book/en/v2)
- [VS Code Python Setup](https://code.visualstudio.com/docs/python/python-tutorial)
- [PyCharm Tutorial](https://www.jetbrains.com/help/pycharm/quick-start-guide.html)

### API Documentation
- [Indeed API](https://developer.indeed.com/)
- [Selenium WebDriver API](https://www.selenium.dev/selenium/docs/api/py/)
- [Django REST Framework](https://www.django-rest-framework.org/)

### YouTube Channels
- [Corey Schafer](https://www.youtube.com/user/schafer5)
- [Pretty Printed](https://www.youtube.com/c/PrettyPrintedTutorials)
- [Dennis Ivy](https://www.youtube.com/c/DennisIvy)

### GitHub Repositories
- [Scrapy](https://github.com/scrapy/scrapy)
- [Beautiful Soup](https://github.com/waylan/beautifulsoup)
- [Selenium](https://github.com/SeleniumHQ/selenium)
- [Django Examples](https://github.com/django/django/tree/main/examples)

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
```bash
git checkout -b feature/YourFeature
```
3. Commit changes
```bash
git commit -m 'Add YourFeature'
```
4. Push to branch
```bash
git push origin feature/YourFeature
```
5. Open Pull Request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📧 Contact & Support

- **Website**: [Your Website](https://your-website.com)
- **Email**: your.email@example.com
- **LinkedIn**: [Your LinkedIn](https://linkedin.com/in/your-profile)
- **Twitter**: [@YourTwitter](https://twitter.com/your-profile)

### Support Development
- **Buy Me a Coffee**: [Link](https://buymeacoffee.com/your-profile)
- **GitHub Sponsors**: [Link](https://github.com/sponsors/your-profile)
