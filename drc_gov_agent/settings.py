"""
Django settings for drc_gov_agent project.
DRC Government Multilingual Digital Assistant Platform.
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env', override=False, encoding='utf-8-sig')
TAVILY_API_KEY = os.environ.get('TAVILY_API_KEY', '')
TAVILY_SEARCH_DEPTH = os.environ.get('TAVILY_SEARCH_DEPTH', 'basic')
SERVICE_BROWSER_CHANNEL = os.environ.get('SERVICE_BROWSER_CHANNEL', 'msedge' if os.name == 'nt' else '')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-drc-gov-agent-key-rtx4060ti-2026')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0,testserver,*').split(',')

# Only the loopback proxy middleware can set this internal header.  ngrok
# terminates HTTPS before forwarding to the local HTTP development server.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_LOCAL_PROXY_SCHEME', 'https')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'channels',
    'corsheaders',

    # Local application modules
    'apps.rag_engine',
    'apps.scraper',
    'apps.voice',
    'apps.web_ui',
]

try:
    import rest_framework
    INSTALLED_APPS.insert(6, 'rest_framework')
except ImportError:
    pass

MIDDLEWARE = [
    'drc_gov_agent.middleware.LocalProxySchemeMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'drc_gov_agent.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'apps' / 'web_ui' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'drc_gov_agent.wsgi.application'
ASGI_APPLICATION = 'drc_gov_agent.asgi.application'

# Database Configuration
# Auto-detects PostgreSQL (port 5432) or defaults to SQLite for immediate out-of-the-box local running.
import socket

def is_service_listening(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.environ.get('POSTGRES_PORT', 5432))

explicit_engine = os.environ.get('DB_ENGINE')
if explicit_engine:
    DB_ENGINE = explicit_engine
else:
    # Auto-detect: if PostgreSQL is reachable on port 5432, use it; otherwise fallback to sqlite
    DB_ENGINE = 'postgres' if is_service_listening(POSTGRES_HOST, POSTGRES_PORT) else 'sqlite'

if DB_ENGINE == 'postgres':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('POSTGRES_DB', 'drc_gov_db'),
            'USER': os.environ.get('POSTGRES_USER', 'drc_admin'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'drc_secret_pass_2026'),
            'HOST': POSTGRES_HOST,
            'PORT': str(POSTGRES_PORT),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'fr-cd'
TIME_ZONE = 'Africa/Kinshasa'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# One source-grounded community brief per ten minutes while Community is visited.
COMMUNITY_AUTO_BRIEFS = os.environ.get('COMMUNITY_AUTO_BRIEFS', 'true').lower() == 'true'
COMMUNITY_SOCIAL_DISCOVERY = os.environ.get('COMMUNITY_SOCIAL_DISCOVERY', 'true').lower() == 'true'
COMMUNITY_SOCIAL_REFRESH_SECONDS = int(os.environ.get('COMMUNITY_SOCIAL_REFRESH_SECONDS', '900'))

# Public source references survive restarts; citizen drafts remain in the browser.
CACHES = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    'service_sources': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': BASE_DIR / 'service_sources_cache',
        'TIMEOUT': 86400,
        'OPTIONS': {'MAX_ENTRIES': 500},
    },
}

# Channels Configuration (Redis Layer if available, otherwise InMemoryChannelLayer)
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))

if is_service_listening(REDIS_HOST, REDIS_PORT):
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                "hosts": [(REDIS_HOST, REDIS_PORT)],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer'
        }
    }

# Celery Configuration
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', f'redis://{REDIS_HOST}:{REDIS_PORT}/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', f'redis://{REDIS_HOST}:{REDIS_PORT}/0')
CELERY_TIMEZONE = 'Africa/Kinshasa'
CELERY_TASK_TRACK_STARTED = True

# Native Host AI Inference Configuration (RTX 4060 Ti 16GB VRAM)
OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'qwen2.5:7b')
# Enabled by setup only after the Lingala model imports and generates successfully.
OLLAMA_LINGALA_MODEL = os.environ.get('OLLAMA_LINGALA_MODEL', '')
OLLAMA_KEEP_ALIVE = os.environ.get('OLLAMA_KEEP_ALIVE', '24h')
OLLAMA_NUM_CTX = int(os.environ.get('OLLAMA_NUM_CTX', 8192))
OLLAMA_TEMPERATURE = float(os.environ.get('OLLAMA_TEMPERATURE', 0.2))
# The local 14B model can take over two minutes to load from disk on a cold start.
OLLAMA_REQUEST_TIMEOUT = float(os.environ.get('OLLAMA_REQUEST_TIMEOUT', '300'))

# Vector Embeddings
EMBEDDING_MODEL_NAME = os.environ.get('EMBEDDING_MODEL_NAME', 'BAAI/bge-m3')
EMBEDDING_ALLOW_DOWNLOAD = os.environ.get('EMBEDDING_ALLOW_DOWNLOAD', 'False').lower() in ('true', '1', 'yes')
EMBEDDING_DIM = int(os.environ.get('EMBEDDING_DIM', 1024))

# Voice Configuration
FASTER_WHISPER_MODEL = os.environ.get('WHISPER_MODEL', 'medium')
FASTER_WHISPER_DEVICE = os.environ.get('WHISPER_DEVICE', 'cuda')
FASTER_WHISPER_COMPUTE_TYPE = os.environ.get('WHISPER_COMPUTE', 'float16')

# CORS settings for API access
CORS_ALLOW_ALL_ORIGINS = True
