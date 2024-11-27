from ..models import JobPosting

class DuplicateChecker:
    def __init__(self, filename=None):
        """
        Initialize duplicate checker. 
        filename parameter is kept for compatibility with original implementation
        """
        pass

    def is_duplicate(self, job_url):
        """
        Check if job URL already exists in database
        """
        return JobPosting.objects.filter(job_url=job_url).exists()

    def add_job_url(self, job_url):
        """
        This method is kept for compatibility but does nothing in Django implementation
        Uniqueness is handled by model-level constraints
        """
        pass