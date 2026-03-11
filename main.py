import logging
import os
import secrets
from pathlib import Path


def _load_dotenv() -> None:
    """Load key=value pairs from a local .env file without extra dependencies."""
    env_path = Path(__file__).resolve().with_name('.env')
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue

        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()],
)
logging.getLogger('httpx').setLevel(logging.WARNING)
logger = logging.getLogger('SalehZonBot')


def _get_env(name: str, default: str | None = None, *, sensitive: bool = False) -> str | None:
    value = os.environ.get(name)
    if value not in (None, ''):
        return value

    if default is not None:
        if sensitive:
            logger.warning('%s is not set. Using a generated/local-development fallback.', name)
        return default
    return None


def _get_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value in (None, ''):
        return default

    try:
        return int(value)
    except ValueError:
        logger.warning('%s=%r is invalid. Falling back to %s.', name, value, default)
        return default


BOT_TOKEN = _get_env('BOT_TOKEN')
ADMIN_ID = _get_int_env('ADMIN_ID', 1635871816)
API_BASE_URL = _get_env('API_BASE_URL', 'https://buzzmaster.shop')
PRODUCT_ID = _get_env('PRODUCT_ID', '24h-nongmail')

# Secrets and connection strings never fall back to embedded production credentials.
MONGO_URI = _get_env('MONGO_URI', 'mongodb://127.0.0.1:27017/salehzon_db', sensitive=True)
WEBHOOK_URL = _get_env('WEBHOOK_URL')
PORT = _get_int_env('PORT', 8080)
SECRET_TOKEN = _get_env('SECRET_TOKEN', secrets.token_urlsafe(48), sensitive=True)

# Store auth/session settings.
STORE_SESSION_COOKIE_NAME = _get_env('STORE_SESSION_COOKIE_NAME', 'store_session')
STORE_SESSION_TTL_SECONDS = _get_int_env('STORE_SESSION_TTL_SECONDS', 60 * 60 * 24 * 30)
OTP_TTL_SECONDS = _get_int_env('OTP_TTL_SECONDS', 300)
OTP_MAX_ATTEMPTS = _get_int_env('OTP_MAX_ATTEMPTS', 5)
TELEGRAM_AUTH_MAX_AGE_SECONDS = _get_int_env('TELEGRAM_AUTH_MAX_AGE_SECONDS', 300)
