"""
Celery background tasks for crawling DRC portals, chunking text,
generating embeddings with BAAI/bge-m3, and updating pgvector KnowledgeBase.
Scheduled via Celery Beat every 2 hours.
"""

import logging
from datetime import timedelta
from django.utils import timezone
from django.utils.text import slugify
from celery import shared_task

from apps.rag_engine.models import KnowledgeBase, DocumentChunk, VerificationStatus
from apps.rag_engine.services import get_embedding_model
from apps.scraper.extractors import RadioOkapiExtractor, PresidenceRdcExtractor

logger = logging.getLogger(__name__)


def chunk_text(text: str, chunk_size: int = 512, chunk_overlap: int = 64) -> list[str]:
    """
    Splits text into chunks of roughly ~512 tokens using character approximation.
    """
    words = text.split()
    chunks = []
    i = 0
    step = chunk_size - chunk_overlap
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
        i += step
    return chunks if chunks else [text]


@shared_task(name="apps.scraper.tasks.scrape_and_index_drc_portals")
def scrape_and_index_drc_portals():
    """
    Crawls official DRC channels and public news outlets.
    Extracts text, creates chunks, computes embeddings on host GPU,
    and upserts into PostgreSQL pgvector KnowledgeBase.
    """
    logger.info("Starting scheduled DRC portal scraping & indexing...")
    embedder = get_embedding_model()

    extractors = [
        RadioOkapiExtractor(),
        PresidenceRdcExtractor(),
    ]

    new_articles_count = 0
    new_chunks_count = 0

    for extractor in extractors:
        try:
            if isinstance(extractor, RadioOkapiExtractor):
                items = extractor.extract_recent_articles(limit=5)
            else:
                items = extractor.extract_press_releases(limit=5)

            for item in items:
                title = item.get("title", "").strip()
                if not title:
                    continue

                slug = slugify(title)[:200]
                kb_doc, created = KnowledgeBase.objects.get_or_create(
                    slug=slug,
                    defaults={
                        "title": title,
                        "source_type": item.get("source_type", "actualite_officielle"),
                        "institution": item.get("institution", "Gouvernement RDC"),
                        "original_url": item.get("url", ""),
                        "language": item.get("language", "fr"),
                        "raw_content": item.get("raw_text", ""),
                        "verification_status": VerificationStatus.VERIFIED,
                        "verified_at": timezone.now(),
                    }
                )

                if created:
                    new_articles_count += 1
                    raw_text = item.get("raw_text", "")
                    if not raw_text:
                        raw_text = title

                    chunks = chunk_text(raw_text, chunk_size=300, chunk_overlap=40)
                    for idx, chunk_str in enumerate(chunks):
                        embedding_vector = None
                        if embedder:
                            try:
                                embedding_vector = embedder.encode(chunk_str, normalize_embeddings=True).tolist()
                            except Exception as embed_err:
                                logger.error(f"Failed to embed chunk #{idx}: {embed_err}")

                        DocumentChunk.objects.create(
                            knowledge_base=kb_doc,
                            chunk_index=idx,
                            content=chunk_str,
                            token_count=len(chunk_str.split()),
                            embedding=embedding_vector or [0.0] * 1024
                        )
                        new_chunks_count += 1

        except Exception as e:
            logger.error(f"Error executing scraper {extractor.__class__.__name__}: {e}")

    logger.info(f"Scraping completed. Added {new_articles_count} articles and {new_chunks_count} vector chunks.")
    return {"articles_indexed": new_articles_count, "chunks_indexed": new_chunks_count}


@shared_task(name="apps.scraper.tasks.archive_expired_news")
def archive_expired_news():
    """
    Archives news articles older than 30 days as mandated by Section 3 Module A.
    """
    cutoff_date = timezone.now() - timedelta(days=30)
    archived_count = KnowledgeBase.objects.filter(
        source_type="actualite_officielle",
        created_at__lt=cutoff_date,
        verification_status=VerificationStatus.VERIFIED
    ).update(verification_status=VerificationStatus.ARCHIVED)

    logger.info(f"Archived {archived_count} news items older than 30 days.")
    return {"archived_count": archived_count}

