from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('index/', views.index, name='index'),
    path('scrape/', views.start_scraping, name='scrape_jobs'),
    path('scrape/progress/<uuid:run_id>/', views.scraping_progress, name='scrape_progress'),
    path('scrape/resume/<uuid:run_id>/', views.resume_scraping, name='resume_scraping'),
    path('scrape/stop/<uuid:run_id>/', views.stop_scraping, name='stop_scraping'),
    path('download/', views.download_csv, name='download_results'),
    path('download/<str:keyword>/<str:country>/', views.download_csv, name='download_csv'),
]
