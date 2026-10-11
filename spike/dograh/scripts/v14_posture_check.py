"""V14: check a Dograh stack env file (KEY=VALUE lines) against the required production posture.

Usage: v14_posture_check.py path/to/dograh.env   (values are never printed)
"""
import sys

PLACEHOLDERS = {"changeme", "change-me", "secret", "your-secret", "dograh", "oss_jwt_secret", ""}


def parse(text: str) -> dict:
    env = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def check(env: dict, effective_concurrency: int | None = None) -> list:
    """Return [(setting, 'PASS'|'FAIL'|'UNSET', reason)]; never includes values."""
    jwt, ws = env.get("OSS_JWT_SECRET", ""), env.get("TELEPHONY_WS_TOKEN_SECRET", "")
    rows = [
        ("ENVIRONMENT", env.get("ENVIRONMENT") == "production", "must be production"),
        ("ENABLE_SIGNUP", env.get("ENABLE_SIGNUP", "true").lower() == "false", "must be false"),
        ("OSS_JWT_SECRET", len(jwt) >= 32 and jwt.lower() not in PLACEHOLDERS, "strong random, 32+ chars, not a placeholder"),
        ("TELEPHONY_WS_TOKEN_SECRET", len(ws) >= 32, "set, 32+ chars"),
        ("TELEPHONY_WS_TOKEN_ENFORCE", env.get("TELEPHONY_WS_TOKEN_ENFORCE", "false").lower() == "true",
         "true after the warning-free rollout step"),
        ("ENABLE_AWS_S3", env.get("ENABLE_AWS_S3", "false").lower() == "true",
         "S3-compatible backend with presigned URLs; the MinIO backend relies on public-readable objects"),
        ("LOG_LEVEL", env.get("LOG_LEVEL", "DEBUG").upper() != "DEBUG", "not DEBUG (tokens appear in logs)"),
        ("PUBLIC_BASE_URL", env.get("PUBLIC_BASE_URL", "").startswith("https://"), "https only"),
    ]
    if effective_concurrency is not None:
        rows.append(("DEFAULT_ORG_CONCURRENCY_LIMIT", env.get("DEFAULT_ORG_CONCURRENCY_LIMIT") == str(effective_concurrency),
                     "equals DOGRAH_EFFECTIVE_CONCURRENCY"))
    return [(k, "PASS" if ok else ("UNSET" if k not in env and k != "ENABLE_SIGNUP" else "FAIL"), why) for k, ok, why in rows]


if __name__ == "__main__":
    for row in check(parse(open(sys.argv[1]).read())):
        print(*row, sep=" | ")
