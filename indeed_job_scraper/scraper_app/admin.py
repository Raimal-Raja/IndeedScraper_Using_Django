from django.contrib import admin
from .models import JobPosting

# Register your models here.
@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = ('title', 'company_name', 'company_location', 'post_date', 'country')
    list_filter = ('country', 'post_date', 'search_term')
    search_fields = ('title', 'company_name', 'job_description')
    readonly_fields = ('created_at',)