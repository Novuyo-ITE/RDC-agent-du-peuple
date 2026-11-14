"""
URLs for the DRC Government Web Portal UI.
"""
from django.urls import path
from apps.web_ui import views
from apps.web_ui import community

app_name = 'web_ui'

urlpatterns = [
    path('', views.landing_view, name='landing'),
    path('accueil/', views.landing_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('communaute/', community.community_page, name='community'),
    path('api/community/feed/', community.feed, name='community_feed'),
    path('api/community/<str:kind>/<int:pk>/comments/', community.comments, name='community_comments'),
    path('api/community/<str:kind>/<int:pk>/like/', community.reaction, name='community_reaction'),
    path('api/community/<str:kind>/<int:pk>/ai/', community.ask_ai, name='community_ai'),
    path('chat/', views.chat_view, name='chat'),
    path('repertoire/', views.directory_view, name='directory'),
    path('demarches/', views.services_view, name='services'),
    path('demarches/<slug:service_code>/', views.service_workspace, name='service_workspace'),
    path('actualites/', views.news_view, name='news'),
    path('news/', views.news_view, name='news_alias'),
]

