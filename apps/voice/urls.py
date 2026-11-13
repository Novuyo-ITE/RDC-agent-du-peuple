"""
URL patterns for DRC Voice assistant endpoints.
"""
from django.urls import path
from apps.voice import views

app_name = 'voice'

urlpatterns = [
    path('transcribe/', views.transcribe_voice_api, name='transcribe_voice_api'),
]

