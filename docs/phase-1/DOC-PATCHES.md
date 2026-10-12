# Proposed design-document patches (not applied; design docs are never edited in Phase 1)

| ID | File | Section | Current | Proposed | Reason |
|---|---|---|---|---|---|
| DP1-01 | Deployment/Environment-Config.md | §2.1 / §2.5 | No variable for the Redis used for cache, locks and rate limits (only `MEMORY_STORE_URL`, which is the working-memory store, and `CALL_QUEUE_BROKER_URL`) | Add `CACHE_REDIS_URL` (secret): Redis for cache, throttle counters and locks; use a different DB index than the broker | Django-Backend-Design §1 requires Redis for locks/rate limits; Phase 1 needs a name |
| DP1-02 | Backend/Django-Backend-Design.md | §6 Celery configuration | Queues `dial`, `webhook`, `recovery`, `analysis`, `default` | Either rename to `webhooks` (as the Phase 1 prompt does) or change the prompt back to `webhook`; pick one before Phase 5 | Design and phase prompt disagree |
| DP1-03 | Deployment/Environment-Config.md | §2.4 | Lists `API_RATE_LIMIT_PER_MINUTE`, `WEBHOOK_RATE_LIMIT_PER_MINUTE` only | Add `LOGIN_RATE_LIMIT_PER_MINUTE` (security default 5) and note the `login` scope is not load-derived | Backend Design §4.5 names a `login` scope with no source for its rate |
| DP1-04 | Deployment/Environment-Config.md | §2.8 | `DJANGO_SETTINGS_MODULE` listed as an environment variable | State that the settings module also selects `staging`, which equals `prod` posture | Clarity |
| DP1-05 | Deployment/Environment-Config.md | §2.8 `FIELD_ENCRYPTION_KEYS`, `PHONE_HMAC_KEY` | Format unspecified | Document formats: `id:base64(32 bytes)[,id:…]` newest first; base64 key ≥ 32 bytes | Needed to provision the secrets manager |
| DP1-06 | Backend/Django-Backend-Design.md | §4.4 | Production settings list | Add `SECURE_REDIRECT_EXEMPT` for `/healthz` and `/readyz`, and the rule that the DB URL must carry a verifying `sslmode` | Probes would otherwise get 301 behind `SECURE_SSL_REDIRECT`; transit encryption |
| DP1-07 | Backend/Django-Backend-Design.md | §7 | "any URL query token" redacted | Add: recording/transcript/artifact URLs are redacted to host only, URL userinfo passwords too | Matches the §8 "recording URLs never appear in logs" test |
| DP1-08 | Phase 0 DP-14 (Environment-Config §2.9) | Dograh posture | n/a | Unchanged; Phase 1 adds nothing for Dograh beyond `DOGRAH_EFFECTIVE_CONCURRENCY` and `DOGRAH_WEBHOOK_HEADER_NAME` | Traceability |
