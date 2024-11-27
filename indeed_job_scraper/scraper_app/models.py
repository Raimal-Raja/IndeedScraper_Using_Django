from django.db import models

# Create your models here.
class JobPosting(models.Model):
    title = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255)
    company_location = models.CharField(max_length=255)
    job_url = models.URLField(unique=True)
    company_detail_url = models.URLField(null=True, blank=True)
    job_description = models.TextField()
    post_date = models.DateField()
    search_term = models.CharField(max_length=100)
    country = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} at {self.company_name}"

    class Meta:
        ordering = ['-created_at']