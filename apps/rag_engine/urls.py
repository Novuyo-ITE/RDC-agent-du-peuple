"""
URL patterns for RAG Engine API.
"""
from django.urls import path
from apps.rag_engine import views
from apps.rag_engine import service_assistance
from apps.rag_engine.official_service_portal import official_service_page
from apps.rag_engine.service_browser import official_browser_action

app_name = 'rag_engine'

urlpatterns = [
    path('services/<slug:service_code>/browser/', official_browser_action, name='official_browser_action'),
    path('services/<slug:service_code>/prepare/', service_assistance.prepare_official_form, name='prepare_official_form'),
    path('services/<slug:service_code>/official/', official_service_page, name='official_service_page'),
    path('services/discover/', service_assistance.discover_services, name='discover_services'),
    path('services/<slug:service_code>/guide/', service_assistance.guide_service, name='guide_service'),
    path('articles/<int:article_id>/body/', views.article_body, name='article_body'),
    path('articles/<int:article_id>/questions/', views.article_questions, name='article_questions'),
    path('articles/<int:article_id>/chat/', views.article_chat, name='article_chat'),
    path('query/', views.query_assistant, name='query_assistant'),
    path('stream/', views.stream_assistant, name='stream_assistant'),
    path('services/', views.list_official_services, name='list_official_services'),
    path('feedback/', views.submit_feedback, name='submit_feedback'),

    # ChromaDB Chat History & Session Endpoints
    path('sessions/', views.list_chat_sessions, name='list_chat_sessions'),
    path('sessions/import/', views.import_local_conversation, name='import_local_conversation'),
    path('sessions/<str:session_id>/', views.get_chat_session_detail, name='get_chat_session_detail'),
    path('sessions/<str:session_id>/rename/', views.rename_chat_session, name='rename_chat_session'),
    path('sessions/<str:session_id>/delete/', views.delete_chat_session, name='delete_chat_session'),
]
