from django.urls import path
from . import views

urlpatterns = [ 
    path('', views.index, name='index'),
    path('index/', views.index, name='index'),
    path('scrape/', views.start_scraping, name='scrape_jobs'),
    path('download/<str:keyword>/<str:country>/', views.download_csv, name='download_csv'),
]