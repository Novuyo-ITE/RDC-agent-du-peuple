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
    Public national landing page designed with professional, modern civic aesthetics:
    - Retains the exact deep midnight blue hero background chosen earlier
    - Clean modern sans-serif typography (Plus Jakarta Sans)
    - Real official news articles with authentic imagery
    - Real-time verified X / Twitter dispatches from Congolese institutions and correspondents
    - Direct access button to "Essayer Agent du Peuple"
    - Clear, clean service catalog cards without excessive artificial gradients
    """
    from apps.rag_engine.models import OfficialServiceRegistry, OfficialNews, CommunityPost
    from apps.rag_engine.official_portals import OFFICIAL_DRC_PORTALS

    featured_services = OfficialServiceRegistry.objects.filter(is_active=True).order_by('id')[:6]

    def get_source_logo(source_name="", source_url=""):
        sn = (source_name or "").lower()
        su = (source_url or "").lower()
        if "okapi" in sn or "okapi" in su:
            return "img/sources/radiookapi.png"
        if "actualite" in sn or "actualite" in su:
            return "img/sources/actualite_cd.png"
        if "rtnc" in sn or "rtnc" in su:
            return "img/sources/rtnc.png"
        if "primature" in sn or "primature" in su:
            return "img/sources/primature.png"
        if "presid" in sn or "presid" in su:
            return "img/sources/presidence.png"
        if "journal" in sn or "journal" in su or "jo" in sn:
            return "img/sources/journal_officiel.png"
        if "rfi" in sn or "rfi" in su:
            return "img/sources/rfi.png"
        return "img/armoirie_rdc.png"

    # Priority to news with images (3 for the top carousel headline + 4 for the secondary grid)
    latest_news = list(OfficialNews.objects.approved().filter(is_verified=True).exclude(image_url='').order_by('-published_at')[:7])
    if len(latest_news) < 7:
        extra_news = list(OfficialNews.objects.approved().filter(is_verified=True).filter(image_url='').order_by('-published_at')[:7 - len(latest_news)])
        latest_news.extend(extra_news)

    # Attach respective media logo to each news item
    for item in latest_news:
        item.logo_path = get_source_logo(item.source_name, getattr(item, 'source_url', ''))

    headline_news = latest_news[:3]
    secondary_news = latest_news[3:]
    
    # Fetch real tweets / X dispatches
    raw_tweets = CommunityPost.objects.filter(
        platform__icontains='Twitter',
        is_visible=True
    ).order_by('-created_at')[:4]

    # Pre-extract tweet images, profile data and logos for easy template rendering
    tweet_list = []
    for t in raw_tweets:
        img = None
        if t.source_metadata and isinstance(t.source_metadata, dict):
            imgs = t.source_metadata.get('images', [])
            if imgs and isinstance(imgs, list) and len(imgs) > 0:
                img = imgs[0]
        
        author_name = t.author or 'Correspondant RDC'
        author_lower = author_name.lower()
        if "presid" in author_lower:
            t_logo = "img/sources/presidence.png"
            account_handle = "@Presidence_RDC"
        elif "bujakera" in author_lower:
            t_logo = "img/sources/actualite_cd.png"
            account_handle = "@StanysBujakera"
        elif "actualite" in author_lower:
            t_logo = "img/sources/actualite_cd.png"
            account_handle = "@actualitecd"
        elif "okapi" in author_lower:
            t_logo = "img/sources/radiookapi.png"
            account_handle = "@radiookapi"
        elif "rtnc" in author_lower:
            t_logo = "img/sources/rtnc.png"
            account_handle = "@officiel_rtnc"
        else:
            t_logo = "img/sources/presidence.png"
            account_handle = "@RDC_Gouv"

        tweet_list.append({
            'author': author_name,
            'handle': account_handle,
            'logo': t_logo,
            'body': t.body,
            'created_at': t.created_at,
            'source_url': t.source_url,
            'image': img,
        })

    # Verified civic media and government broadcast sources with their respective logos/favicons
    verified_sources = [
        {
            'name': 'RTNC',
            'full_name': 'Radio Télévision Nationale Congolaise',
            'type': 'Média Public & Télévision d\'État',
            'description': 'Diffuseur audiovisuel officiel de la République, direct institutionnel et journal télévisé.',
            'url': 'https://rtnc.cd',
            'logo': 'img/sources/rtnc.png',
            'icon': 'tv',
            'badge': 'Télévision Publique',
        },
        {
            'name': 'Radio Okapi',
            'full_name': 'Radio de la Paix en RDC',
            'type': 'Presse Indépendante & Réseau National',
            'description': 'Couverture journalistique neutre à travers les 26 provinces en Français, Lingála, Kiswahili et Kikongo.',
            'url': 'https://www.radiookapi.net',
            'logo': 'img/sources/radiookapi.png',
            'icon': 'radio',
            'badge': 'Radio Nationale',
        },
        {
            'name': 'Actualite.cd',
            'full_name': 'Actualité & Société RDC',
            'type': 'Presse Numérique d\'Investigation',
            'description': 'Dépêches politiques, économiques et civiques vérifiées avec correspondants permanents.',
            'url': 'https://actualite.cd',
            'logo': 'img/sources/actualite_cd.png',
            'icon': 'newspaper',
            'badge': 'Presse En Ligne',
        },
        {
            'name': 'Primature RDC',
            'full_name': 'Gouvernement de la République',
            'type': 'Pouvoir Exécutif',
            'description': 'Comptes-rendus hebdomadaires des Conseils des Ministres et politiques gouvernementales.',
            'url': 'https://www.primature.gouv.cd',
            'logo': 'img/sources/primature.png',
            'icon': 'landmark',
            'badge': 'Gouvernement',
        },
        {
            'name': 'Présidence de la République',
            'full_name': 'Palais de la Nation',
            'type': 'Institution Constitutionnelle',
            'description': 'Ordonnances du Chef de l\'État, discours à la Nation et décisions républicaines majeures.',
            'url': 'http://presidentrdc.cd',
            'logo': 'img/sources/presidence.png',
            'icon': 'shield',
            'badge': 'Présidence',
        },
        {
            'name': 'Journal Officiel',
            'full_name': 'Dépôt Légal de la République',
            'type': 'Registre Législatif Officiel',
            'description': 'Lois promulguées, arrêtés ministériels et immatriculations d\'entreprises au Congo.',
            'url': 'https://journalofficiel.cd',
            'logo': 'img/sources/journal_officiel.png',
            'icon': 'book-open',
            'badge': 'Droit Positif',
        },
    ]

    return render(request, 'landing.html', {
        'featured_services': featured_services,
        'headline_news': headline_news,
        'secondary_news': secondary_news,
        'latest_news': latest_news,
        'tweets': tweet_list,
        'verified_sources': verified_sources,
        'total_portals': len(OFFICIAL_DRC_PORTALS),
        'total_services': OfficialServiceRegistry.objects.filter(is_active=True).count(),
        'total_news': OfficialNews.objects.approved().filter(is_verified=True).count(),
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

