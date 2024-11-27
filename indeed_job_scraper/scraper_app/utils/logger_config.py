import logging
import os
from django.conf import settings

def setup_logger():
    """
    Configure logging for scraper application
    """
    # Ensure log directory exists
    log_dir = os.path.join(settings.BASE_DIR, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(log_dir, 'scraper.log')),
            logging.StreamHandler()  # Also log to console
        ]
    )

    # Optional: Set specific loggers
    logger = logging.getLogger('scraper_app')
    logger.setLevel(logging.INFO)

    return logger