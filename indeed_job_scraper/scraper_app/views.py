from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from .forms import JobSearchForm
from .models import JobPosting
from .utils.Scraper import Scraper
import csv

def index(request):
    return render(request, 'index.html')

def start_scraping(request):
    form = JobSearchForm()
    
    if request.method == 'POST':
        form = JobSearchForm(request.POST)
        if form.is_valid():
            keyword = form.cleaned_data['keyword']
            country = form.cleaned_data['country']
            
            # Create scraper instance
            scraper = Scraper()
            domains = {country: settings.JOB_DOMAINS[country]}
            
            # Scrape jobs
            total_jobs, blocked_domains = scraper.scrape_jobs(domains, keyword)
            
            # If it's an AJAX request, return JSON response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'total_jobs': total_jobs,
                    'keyword': keyword,
                    'country': country
                })
            
            context = {
                'form': form,
                'total_jobs': total_jobs,
                'keyword': keyword,
                'country': country
            }
            return render(request, 'results.html', context)
    
    return render(request, 'results.html', {'form': form})

def download_csv(request, keyword, country):
    jobs = JobPosting.objects.filter(
        search_term=keyword, 
        country=country
    )
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{keyword}_{country}_jobs.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Title', 'Company', 'Location', 
        'Job URL', 'Company URL', 
        'Post Date', 'Description'
    ])
    
    for job in jobs:
        writer.writerow([
            job.title, 
            job.company_name, 
            job.company_location,
            job.job_url, 
            job.company_detail_url,
            job.post_date, 
            job.job_description
        ])
    
    return response