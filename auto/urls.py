"""auto URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from app.views import *
from auto import settings
from django.views.decorators.csrf import csrf_exempt
import debug_toolbar

admin.site.site_header = "Ninja Admin"
admin.site.site_title = "Ninja Admin Portal"
admin.site.index_title = "Welcome to Ninja Taxi"

urlpatterns = [
    path('admin/', admin.site.urls, name='admin'),
    path('api/', include('api.urls')),
    path('rating/', DriversRatingView.as_view()),
    path('drivers_total_weekly_rating/', drivers_total_weekly_rating, name='app/drivers_total_weekly_rating'),
    path('gps/data', GpsData.as_view()),
    path('fake_uklon/', include('fake_uklon.urls')),
    path('cars/', gps_cars, name='map'),
    path('', include('taxi_service.urls')),
    path('__debug__/', include(debug_toolbar.urls)),
    path('webhook/', csrf_exempt(TelegramBotWebhookView.as_view())),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
