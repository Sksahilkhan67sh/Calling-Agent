"""Print a throwaway, randomly generated production-shaped environment (KEY=VALUE lines).

For CI deploy checks only. Values are generated per run, never stored, and unusable anywhere.
"""

import base64
import secrets


def main() -> None:
    values = {
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
        "DJANGO_ALLOWED_HOSTS": "api.calls.test",
        "PRIMARY_DB_URL": f"postgres://app:{secrets.token_hex(12)}@db.internal:5432/app?sslmode=require",
        "PRIMARY_DB_POOL_SIZE": "20",
        "CACHE_REDIS_URL": f"redis://:{secrets.token_hex(12)}@cache.internal:6379/1",
        "CALL_QUEUE_BROKER_URL": f"redis://:{secrets.token_hex(12)}@cache.internal:6379/0",
        "JWT_SIGNING_KEY": secrets.token_urlsafe(48),
        "FIELD_ENCRYPTION_KEYS": "ci1:" + base64.b64encode(secrets.token_bytes(32)).decode(),
        "PHONE_HMAC_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
        "DOGRAH_EFFECTIVE_CONCURRENCY": "20",
        "API_RATE_LIMIT_PER_MINUTE": "600",
        "WEBHOOK_RATE_LIMIT_PER_MINUTE": "1200",
        "LOGIN_RATE_LIMIT_PER_MINUTE": "5",
        "SESSION_ABSOLUTE_MAX_DAYS": "7",
        "AXES_FAILURE_LIMIT": "5",
        "TRUSTED_PROXY_COUNT": "1",
        "CORS_ALLOWED_ORIGINS": "https://dashboard.calls.test",
        "CSRF_TRUSTED_ORIGINS": "https://dashboard.calls.test",
    }
    for name, value in values.items():
        print(f"{name}={value}")


if __name__ == "__main__":
    main()
