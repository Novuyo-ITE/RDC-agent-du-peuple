"""
Django admin configuration for DRC RAG Engine.
"""

from django.contrib import admin
from .models import KnowledgeBase, DocumentChunk, OfficialServiceRegistry, QueryAuditLog
from .models import CommunityPost, CommunityComment, CommunityReaction


@admin.register(CommunityPost)
class CommunityPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'kind', 'author', 'platform', 'is_visible', 'created_at')
    list_filter = ('kind', 'is_visible', 'platform')
    search_fields = ('title', 'body', 'author')
    readonly_fields = ('visitor', 'created_at')


@admin.register(CommunityComment)
class CommunityCommentAdmin(admin.ModelAdmin):
    list_display = ('author', 'article', 'post', 'is_ai', 'is_visible', 'created_at')
    list_filter = ('is_ai', 'is_visible')
    search_fields = ('author', 'body')
    readonly_fields = ('visitor', 'created_at')


@admin.register(CommunityReaction)
class CommunityReactionAdmin(admin.ModelAdmin):
    list_display = ('article', 'post', 'created_at')
    readonly_fields = ('visitor', 'created_at')


class DocumentChunkInline(admin.TabularInline):
    model = DocumentChunk
    extra = 0
    fields = ('chunk_index', 'token_count', 'content')
    readonly_fields = ('chunk_index', 'token_count', 'content')
    can_delete = False
    show_change_link = True


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ('title', 'source_type', 'institution', 'language', 'verification_status', 'verified_at')
    list_filter = ('source_type', 'verification_status', 'language', 'institution')
    search_fields = ('title', 'institution', 'raw_content')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [DocumentChunkInline]


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ('id', 'knowledge_base', 'chunk_index', 'token_count', 'created_at')
    list_filter = ('knowledge_base__source_type', 'knowledge_base__institution')
    search_fields = ('content', 'knowledge_base__title')


@admin.register(OfficialServiceRegistry)
class OfficialServiceRegistryAdmin(admin.ModelAdmin):
    list_display = (
        'service_name',
        'category',
        'institution',
        'official_cost_usd',
        'official_cost_cdf',
        'processing_time_days',
        'is_active',
        'verified_at'
    )
    list_filter = ('category', 'is_active', 'institution')
    search_fields = ('service_name', 'description', 'institution')
    prepopulated_fields = {'service_code': ('service_name',)}


@admin.register(QueryAuditLog)
class QueryAuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'detected_language', 'tool_fallback_used', 'user_satisfaction', 'short_query')
    list_filter = ('detected_language', 'tool_fallback_used', 'user_satisfaction')
    search_fields = ('query_text', 'response_text')
    readonly_fields = ('created_at',)

    def short_query(self, obj):
        return obj.query_text[:60]
    short_query.short_description = "Question"

