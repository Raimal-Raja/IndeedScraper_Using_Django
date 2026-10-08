# IndeedScraper Using Django

Django job-scraping application with search forms, browser-assisted extraction, database storage, and CSV downloads.

## Repository guide

### Contents

- [README.md](README.md)
- [indeed_job_scraper](indeed_job_scraper)
- [requirements.txt](requirements.txt)

### Getting started

```bash
git clone https://github.com/Raimal-Raja/IndeedScraper_Using_Django.git
cd IndeedScraper_Using_Django
```

Create and activate a virtual environment, then install the project dependencies:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r "requirements.txt"
```

Run each Django project from the folder containing its manage.py file:

```bash
cd "indeed_job_scraper"
python manage.py check
python manage.py migrate
python manage.py runserver
```

### Configuration and limitations

Live scraping depends on site permissions, browser availability, current page markup, and anti-bot responses. Passing syntax checks does not verify live collection. Browser-handling code does not guarantee access.

### Validation

Reviewed on 2026-10-08. Django manage.py check identified no issues. Python syntax checks passed; live bookings and live scraping were not exercised.

### Contributions

Describe the issue, reproduction steps, environment, and expected behavior when proposing a change. Keep generated environments, credentials, and unnecessary build artifacts out of new commits.

### License

No top-level license file was found during this review.
