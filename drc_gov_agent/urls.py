"""
URL configuration for drc_gov_agent project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/rag/', include('apps.rag_engine.urls')),
    path('api/voice/', include('apps.voice.urls')),
    path('', include('apps.web_ui.urls')),
] + static(settings.STATIC_URL, document_root=settings.BASE_DIR / 'static')

