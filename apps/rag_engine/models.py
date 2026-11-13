"""
Django models for DRC Government RAG Engine & Knowledge Base.
Implements:
1. KnowledgeBase: Institutional metadata, decrees, and official articles.
2. DocumentChunk: 512-token chunks with 1024-dim VectorField and HNSW vector index.
3. OfficialServiceRegistry: Gold-standard verified public services catalog (FRD v1.1 compliance).
4. QueryAuditLog & UserFeedback: Verification, audit trails, and feedback metrics.
"""

from django.db import models
from django.utils import timezone
from django.conf import settings

# Attempt pgvector import for VectorField and HnswIndex; fallback gracefully for SQLite development
try:
    from pgvector.django import VectorField, HnswIndex
    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False
    # Fallback placeholder for non-Postgres local testing
    class VectorField(models.Field):
        def __init__(self, dimensions=1024, *args, **kwargs):
            self.dimensions = dimensions
            super().__init__(*args, **kwargs)

        def db_type(self, connection):
            return 'text'

    class HnswIndex:
        def __init__(self, *args, **kwargs):
            pass


class LanguageChoice(models.TextChoices):
    FRENCH = 'fr', 'Français'
    SWAHILI = 'sw', 'Kiswahili (DRC)'
    LINGALA = 'ln', 'Lingála'


class VerificationStatus(models.TextChoices):
    VERIFIED = 'verified', 'Vérifié Officiellement'
    PENDING_REVIEW = 'pending', 'En Attente de Revue'
    ARCHIVED = 'archived', 'Archivé (+30 jours)'


class SourceType(models.TextChoices):
    OFFICIAL_JOURNAL = 'journal_officiel', 'Journal Officiel de la RDC'
    PRESIDENCY = 'presidence', 'Présidence de la République'
    PRIMATURE = 'primature', 'Primature du Gouvernement'
    MINISTRY = 'ministere', 'Ministère Sectoriel'
    ADMIN_REGISTRY = 'registre_admin', 'Registre Administratif & Services'
    OFFICIAL_NEWS = 'actualite_officielle', 'Média Public & Actualités Vérifiées'
    CIRCULAR = 'circulaire', 'Circulaire / Arrêté Ministériel'


class ServiceCategory(models.TextChoices):
    IDENTITY_CIVIL = 'identity', 'Identité & État Civil'
    BUSINESS_TRADE = 'business', 'Entreprise, Commerce & Investissement'
    TAX_CUSTOMS = 'tax', 'Fiscalité, Impôts & Douanes'
    TRANSPORT_VEHICLE = 'transport', 'Transport, Véhicules & Permis'
    JUSTICE_SECURITY = 'justice', 'Justice, Police & Sécurité'
    EDUCATION_HEALTH = 'education_health', 'Éducation, Formation & Santé'
    LAND_HOUSING = 'land', 'Affaires Foncières & Cadastre'


class KnowledgeBase(models.Model):
    """
    Central repository of official documents, decrees, official circulars,
    and verified news items from DRC government portals.
    """
    title = models.CharField(max_length=512, help_text="Titre officiel du document ou communiqué")
    slug = models.SlugField(max_length=512, unique=True, db_index=True)
    source_type = models.CharField(
        max_length=50,
        choices=SourceType.choices,
        default=SourceType.MINISTRY,
        db_index=True
    )
    institution = models.CharField(
        max_length=255,
        help_text="Institution émettrice (ex: Ministère des Affaires Étrangères, DGM, Presidence.cd)",
        db_index=True
    )
    original_url = models.URLField(
        max_length=1000,
        blank=True,
        null=True,
        help_text="Lien URL d'origine vers le portail officiel"
    )
    publication_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date de publication officielle"
    )
    verified_at = models.DateTimeField(
        default=timezone.now,
        help_text="Horodatage de la dernière vérification humaine ou automatisée"
    )
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.VERIFIED,
        db_index=True
    )
    language = models.CharField(
        max_length=10,
        choices=LanguageChoice.choices,
        default=LanguageChoice.FRENCH,
        db_index=True
    )
    raw_content = models.TextField(help_text="Texte brut complet extrait de la source")
    metadata_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Métadonnées supplémentaires (mots-clés, auteur, section, version juridique)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Base de Connaissance DRC"
        verbose_name_plural = "Bases de Connaissances DRC"
        ordering = ['-verified_at', '-created_at']

    def __str__(self):
        return f"[{self.get_source_type_display()}] {self.title[:80]} ({self.institution})"


class DocumentChunk(models.Model):
    """
    512-token chunk of a KnowledgeBase document with vector embedding for semantic search.
    Vector dimension: 1024 (BAAI/bge-m3) or configurable via settings.
    """
    knowledge_base = models.ForeignKey(
        KnowledgeBase,
        on_delete=models.CASCADE,
        related_name='chunks'
    )
    chunk_index = models.PositiveIntegerField(help_text="Index séquentiel du fragment dans le document")
    content = models.TextField(help_text="Fragment de texte (environ 512 tokens)")
    token_count = models.PositiveIntegerField(default=0, help_text="Nombre approximatif de tokens")
    
    # Vector embedding (1024 dims for BAAI/bge-m3)
    embedding = VectorField(
        dimensions=getattr(settings, 'EMBEDDING_DIM', 1024),
        help_text="Vecteur sémantique BAAI/bge-m3 (1024 dimensions)"
    )
    chunk_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Métadonnées locales au fragment (titre de section, sous-titres, pages)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Fragment Document RAG"
        verbose_name_plural = "Fragments Documents RAG"
        ordering = ['knowledge_base', 'chunk_index']
        indexes = [
            models.Index(fields=['knowledge_base', 'chunk_index']),
        ]
        # Register HNSW index on pgvector if available
        if PGVECTOR_AVAILABLE and getattr(settings, 'DB_ENGINE', 'postgres') == 'postgres':
            indexes.append(
                HnswIndex(
                    name='doc_chunk_embedding_hnsw_idx',
                    fields=['embedding'],
                    m=16,
                    ef_construction=64,
                    opclasses=['vector_cosine_ops'],
                )
            )

    def __str__(self):
        return f"Chunk #{self.chunk_index} - {self.knowledge_base.title[:50]}"


class OfficialServiceRegistry(models.Model):
    """
    Official Public Services Registry for the Democratic Republic of the Congo.
    Strict Ground Truth for citizen procedures (Passport, Civil Status, Driving License, Guichet Unique).
    Enforces Zero-Hallucination and safe payment channels (FRD v1.1 compliance EF-04, EF-05, EF-14.3).
    """
    service_name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Nom officiel de la démarche (ex: Passeport biométrique ordinaire)"
    )
    service_code = models.SlugField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Identifiant unique normalisé (ex: passeport-biometrique)"
    )
    category = models.CharField(
        max_length=50,
        choices=ServiceCategory.choices,
        default=ServiceCategory.IDENTITY_CIVIL,
        db_index=True
    )
    institution = models.CharField(
        max_length=255,
        help_text="Institution ou Ministère responsable (ex: DGM / Ministère des Affaires Étrangères)"
    )
    description = models.TextField(help_text="Description complète de la démarche administrative")
    eligibility_criteria = models.TextField(
        blank=True,
        help_text="Critères d'éligibilité (ex: Être de nationalité congolaise, âgé de 18 ans minimum)"
    )
    required_documents = models.JSONField(
        default=list,
        help_text="Liste des pièces justificatives exigées (ex: ['Attestation de nationalité', 'Photos passeport'])"
    )
    official_cost_cdf = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Frais légaux en Francs Congolais (CDF)"
    )
    official_cost_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Frais légaux en Dollars Américains (USD)"
    )
    payment_instructions = models.TextField(
        help_text="Procédure de paiement officielle vérifiée (Banque agréée, Guichet bancaire officiel, Trésor Public)"
    )
    processing_time_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=None,
        help_text="Délai moyen de délivrance officiel en jours ouvrés"
    )
    physical_locations = models.JSONField(
        default=list,
        blank=True,
        help_text="Adresses des bureaux de dépôt et capture physique (Kinshasa, Goma, Lubumbashi...)"
    )
    official_portal_url = models.URLField(
        max_length=1000,
        blank=True,
        null=True,
        help_text="Lien officiel de prise de rendez-vous ou formulaire en ligne"
    )
    source_snapshot = models.JSONField(
        default=dict, blank=True,
        help_text="Dossier de procédure recherché : informations, sources, formulaires et date de vérification."
    )
    contact_phone = models.CharField(max_length=100, blank=True, null=True, help_text="Téléphone d'assistance officiel")
    contact_email = models.EmailField(blank=True, null=True, help_text="Courriel officiel du service")
    verified_at = models.DateTimeField(
        default=timezone.now,
        help_text="Date de dernière validation légale par l'institution"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Indique si la démarche est actuellement ouverte et opérationnelle"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Registre des Services Publics RDC"
        verbose_name_plural = "Registre des Services Publics RDC"
        ordering = ['category', 'service_name']

    def __str__(self):
        return f"{self.service_name} ({self.institution})"

    def format_citation(self) -> str:
        """Outputs standard FRD v1.1 mandatory citation block."""
        date_str = self.verified_at.strftime('%d/%m/%Y') if self.verified_at else "N/A"
        link_str = self.official_portal_url if self.official_portal_url else "Guichet officiel"
        return (
            f"🏛️ Source Officielle: {self.institution}\n"
            f"📅 Date de vérification: {date_str}\n"
            f"🔗 Lien officiel: {link_str}"
        )


class QueryAuditLog(models.Model):
    """
    Log of citizen inquiries, retrieved sources, and agent responses.
    Strictly scrubs private personal identifiable data (FRD EF-10, EF-14).
    """
    query_text = models.TextField(help_text="Question du citoyen (sans informations nominatives)")
    detected_language = models.CharField(max_length=10, default='fr')
    response_text = models.TextField(help_text="Réponse synthétisée par l'agent IA")
    sources_cited = models.JSONField(default=list, blank=True, help_text="Liste des sources citées")
    tool_fallback_used = models.BooleanField(default=False, help_text="Indique si DuckDuckGo ou MCP a été activé")
    execution_time_ms = models.PositiveIntegerField(default=0)
    user_satisfaction = models.IntegerField(null=True, blank=True, help_text="1: Thumbs Up, -1: Thumbs Down")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Journal d'Audit RAG"
        verbose_name_plural = "Journaux d'Audit RAG"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.created_at.strftime('%Y-%m-%d %H:%M')}] {self.query_text[:50]}"


class OfficialNewsManager(models.Manager):
    def approved(self):
        from .news_policy import rfi_condition, drc_condition
        return self.filter(is_verified=True).exclude(rfi_condition() & ~drc_condition())


class OfficialNews(models.Model):
    """
    Verified DRC official news articles and government communiqués.
    Enables citizens to consult verified updates on security, government decisions,
    economy, and administrative circulars with exact source citation and photographs.
    """
    CATEGORY_CHOICES = [
        ('securite', 'Sécurité & Est de la RDC'),
        ('gouvernement', 'Gouvernement & Présidence'),
        ('economie', 'Économie & Finances'),
        ('mines', 'Mines & Ressources'),
        ('diplomatie', 'Diplomatie & Relations Extérieures'),
        ('societe', 'Société, Éducation & Santé'),
        ('justice', 'Justice & Droits Humains'),
        ('international', 'International'),
    ]

    objects = OfficialNewsManager()
    title = models.CharField(max_length=512, help_text="Titre ou manchette de l'actualité")
    slug = models.SlugField(max_length=512, unique=True, db_index=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='gouvernement', db_index=True)
    source_name = models.CharField(max_length=255, help_text="Nom de l'institution ou média vérifié (ex: Ministère de la Communication, Radio Okapi, Présidence)")
    source_url = models.URLField(max_length=1024, help_text="URL exacte de l'article officiel original")
    image_url = models.URLField(max_length=1024, blank=True, null=True, help_text="URL de la photo ou image illustrative")
    summary = models.TextField(help_text="Résumé clair pour l'affichage en carte de synthèse")
    full_content = models.TextField(help_text="Texte intégral ou développements vérifiés de l'article")
    region = models.CharField(max_length=100, default='National', help_text="Région concernée (ex: Est / Nord-Kivu, Kinshasa, National)")
    published_at = models.DateTimeField(db_index=True, help_text="Date de publication")
    is_verified = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Actualité Officielle"
        verbose_name_plural = "Actualités Officielles"
        ordering = ['-published_at']

    def __str__(self):
        return f"[{self.published_at.strftime('%d/%m/%Y')}] {self.title[:60]}"


class CommunityPost(models.Model):
    KIND_CHOICES = [('community', 'Communauté'), ('social', 'Réseaux sociaux'), ('ai', 'Décryptage IA')]
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default='community')
    title = models.CharField(max_length=240)
    body = models.TextField()
    author = models.CharField(max_length=80, default='Citoyen')
    visitor = models.CharField(max_length=64, blank=True)
    source_url = models.URLField(max_length=1024, blank=True)
    platform = models.CharField(max_length=40, blank=True)
    import_key = models.CharField(max_length=64, unique=True, null=True, blank=True, editable=False)
    source_metadata = models.JSONField(default=dict, blank=True)
    source_article = models.OneToOneField(OfficialNews, null=True, blank=True, on_delete=models.CASCADE,
                                          related_name='community_brief')
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']


class CommunityComment(models.Model):
    article = models.ForeignKey(OfficialNews, null=True, blank=True, on_delete=models.CASCADE, related_name='community_comments')
    post = models.ForeignKey(CommunityPost, null=True, blank=True, on_delete=models.CASCADE, related_name='community_comments')
    author = models.CharField(max_length=80)
    visitor = models.CharField(max_length=64, blank=True)
    body = models.TextField()
    is_ai = models.BooleanField(default=False)
    is_visible = models.BooleanField(default=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [models.CheckConstraint(condition=(
            models.Q(article__isnull=False, post__isnull=True) | models.Q(article__isnull=True, post__isnull=False)
        ), name='community_comment_one_target')]


class CommunityReaction(models.Model):
    article = models.ForeignKey(OfficialNews, null=True, blank=True, on_delete=models.CASCADE, related_name='community_reactions')
    post = models.ForeignKey(CommunityPost, null=True, blank=True, on_delete=models.CASCADE, related_name='community_reactions')
    visitor = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=(models.Q(article__isnull=False, post__isnull=True) |
                                              models.Q(article__isnull=True, post__isnull=False)), name='community_reaction_one_target'),
            models.UniqueConstraint(fields=['article', 'visitor'], name='community_article_like_once'),
            models.UniqueConstraint(fields=['post', 'visitor'], name='community_post_like_once'),
        ]

