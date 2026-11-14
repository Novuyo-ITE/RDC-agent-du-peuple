"""
Views for the DRC Government Web Portal UI (mirroring uggovagent.ug layout).
"""

from django.shortcuts import render, redirect
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.views.decorators.cache import never_cache
from apps.rag_engine.models import OfficialServiceRegistry, KnowledgeBase, VerificationStatus
from apps.rag_engine.official_portals import get_all_portals_grouped, OFFICIAL_DRC_PORTALS


def landing_view(request):
    """
    Public republican landing page.
    Authentic, civic, dignified presence with direct access to 'Agent du Peuple'.
    """
    return render(request, 'landing.html', {
        'page_title': 'RDC Agent du Peuple — Guichet Républicain d’Accompagnement Citoyen',
    })


def home_view(request):
    """Direct route for /: displays the landing page."""
    return landing_view(request)


def login_view(request):
    """Citoyen authentication login view."""
    if request.user.is_authenticated:
        return redirect('web_ui:chat')

    next_url = request.GET.get('next') or request.POST.get('next') or 'web_ui:chat'
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            return redirect(next_url)
    else:
        form = AuthenticationForm(request)

    return render(request, 'auth/login.html', {
        'form': form,
        'next': next_url,
    })


def register_view(request):
    """Citoyen registration view."""
    if request.user.is_authenticated:
        return redirect('web_ui:chat')

    next_url = request.GET.get('next') or request.POST.get('next') or 'web_ui:chat'
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect(next_url)
    else:
        form = UserCreationForm()

    return render(request, 'auth/register.html', {
        'form': form,
        'next': next_url,
    })


def logout_view(request):
    """Logout citoyen view."""
    auth_logout(request)
    return redirect('web_ui:landing')


@never_cache
def chat_view(request):
    return render(request, 'index.html', {
        'recent_news': KnowledgeBase.objects.filter(verification_status=VerificationStatus.VERIFIED).order_by('-verified_at', '-created_at')[:8],
        'featured_services': OfficialServiceRegistry.objects.filter(is_active=True).order_by('category', 'service_name')[:4],
    })


def directory_view(request):
    """Official government directory & verified institutions."""
    grouped_portals = get_all_portals_grouped()
    return render(request, 'directory.html', {
        'grouped_portals': grouped_portals,
        'total_portals': len(OFFICIAL_DRC_PORTALS),
    })


def services_view(request):
    from apps.rag_engine.models import ServiceCategory
    from django.db.models import Q
    from .service_news import recent_service_news

    services = OfficialServiceRegistry.objects.filter(is_active=True)
    category = request.GET.get('category', '')
    query = request.GET.get('q', '').strip()
    if category:
        services = services.filter(category=category)
    if query:
        services = services.filter(Q(service_name__icontains=query) | Q(description__icontains=query) | Q(institution__icontains=query))
    from django.core.cache import cache
    from urllib.parse import urlsplit
    from django.utils.dateparse import parse_datetime
    services = list(services.order_by('category', 'service_name'))
    for service in services:
        service.source_host = urlsplit(service.official_portal_url or '').hostname or ''
        service.live_snapshot = service.source_snapshot or cache.get('official-service-page-v2:' + service.service_code) or {}
        service.source_checked_at = parse_datetime(service.live_snapshot.get('checked_at', ''))
    return render(request, 'services.html', {
        'services': services,
        'categories': ServiceCategory.choices, 'selected_category': category, 'query': query,
        'service_count': OfficialServiceRegistry.objects.filter(is_active=True).count(),
        'featured_service_options': OfficialServiceRegistry.objects.filter(is_active=True).order_by('service_name')[:8],
        'service_news': recent_service_news(),
    })


def service_workspace(request, service_code):
    from apps.rag_engine.service_assistance import service_data, resolve_service
    if service_code.startswith('site-') and request.GET.get('session'):
        from apps.rag_engine.chroma_session_manager import ChromaSessionManager
        from django.core.cache import caches
        metadata = ChromaSessionManager().get_session(request.GET['session'])
        if metadata and metadata.get('kind') == 'service' and metadata.get('service_code') == service_code and metadata.get('source_url'):
            caches['service_sources'].set(service_code, {'title': metadata.get('service_title', service_code), 'url': metadata['source_url']})
    service = resolve_service(service_code)
    snapshot = service.source_snapshot or {}
    from django.utils.dateparse import parse_datetime
    return render(request, 'service_workspace.html', {
        'service': service, 'service_data': service_data(service), 'initial_snapshot': snapshot,
        'is_search_source': service.service_code.startswith('site-'),
        'source_checked_at': parse_datetime(snapshot.get('checked_at', '')),
        'facts': snapshot.get('facts', {}), 'form_resources': snapshot.get('form_resources', []),
    })


def news_view(request):
    """
    Official news catalog with period filtering:
    - 'today': published today (02/11/2026)
    - '7days': published in the last 7 days
    - '1month': published in the last 30 days
    - 'all': all news
    Supports category filtering and instant search.
    """
    from apps.rag_engine.models import OfficialNews
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Q, Case, When, Value, IntegerField
    from .news_refresh import refresh_news_if_due

    refresh_news_if_due()

    period = request.GET.get('period', 'all')
    selected_category = request.GET.get('category', 'all')
    query = request.GET.get('q', '').strip()

    now = timezone.localtime()
    qs = OfficialNews.objects.approved().filter(is_verified=True)

    # Date filter
    if period == 'today':
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        qs = qs.filter(published_at__gte=today_start)
    elif period == '7days':
        seven_days_ago = now - timedelta(days=7)
        qs = qs.filter(published_at__gte=seven_days_ago)
    elif period == '1month':
        one_month_ago = now - timedelta(days=30)
        qs = qs.filter(published_at__gte=one_month_ago)

    # Category filter
    if selected_category and selected_category != 'all':
        qs = qs.filter(category=selected_category)

    # Text search
    if query:
        qs = qs.filter(
            Q(title__icontains=query) |
            Q(summary__icontains=query) |
            Q(full_content__icontains=query) |
            Q(region__icontains=query)
        )

    # The lead must follow the latest publication, regardless of publisher.
    # Prefer local media only when two articles have exactly the same timestamp.
    from apps.rag_engine.management.commands.fetch_drc_news import DRC_RSS_SOURCES
    local_sources = [source['name'] for source in DRC_RSS_SOURCES
                     if source.get('category_override') != 'international']
    news_list = qs.annotate(source_priority=Case(
        When(source_name__in=local_sources, then=Value(0)),
        default=Value(1), output_field=IntegerField(),
    )).order_by('-published_at', 'source_priority', '-pk')

    # Counts for filter badges
    today_count = OfficialNews.objects.approved().filter(
        is_verified=True,
        published_at__gte=now.replace(hour=0, minute=0, second=0, microsecond=0)
    ).count()
    seven_days_count = OfficialNews.objects.approved().filter(
        is_verified=True,
        published_at__gte=now - timedelta(days=7)
    ).count()
    one_month_count = OfficialNews.objects.approved().filter(
        is_verified=True,
        published_at__gte=now - timedelta(days=30)
    ).count()
    total_count = OfficialNews.objects.approved().filter(is_verified=True).count()

    categories = OfficialNews.CATEGORY_CHOICES
    deep_link_article = None
    selected_id = request.GET.get('article', '')
    if selected_id.isdigit() and len(selected_id) <= 18:
        selected = OfficialNews.objects.approved().filter(pk=int(selected_id), is_verified=True).first()
        if selected:
            deep_link_article = {'id': str(selected.pk), 'title': selected.title, 'category': selected.get_category_display(),
                'region': selected.region, 'date': timezone.localtime(selected.published_at).strftime('%d/%m/%Y %H:%M'),
                'source': selected.source_name, 'url': selected.source_url, 'image': selected.image_url or '',
                'full': selected.full_content, 'summary': selected.summary}

    from django.core.paginator import Paginator
    page_obj = Paginator(news_list, 9).get_page(request.GET.get('page'))
    edition_articles = list(page_obj.object_list)
    context = {
        'news_list': page_obj.object_list,
        'timeline_news': edition_articles[:9],
        'page_obj': page_obj,
        'current_period': period,
        'selected_category': selected_category,
        'query': query,
        'today_count': today_count,
        'seven_days_count': seven_days_count,
        'one_month_count': one_month_count,
        'total_count': total_count,
        'categories': categories,
        'deep_link_article': deep_link_article,
    }
    response = render(request, 'news.html', context)
    response['Cache-Control'] = 'no-store'
    return response

