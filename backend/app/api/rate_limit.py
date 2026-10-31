from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

_settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_settings.api_rate_limit],
    storage_uri=_settings.rate_limit_storage or _settings.redis_url,
)
