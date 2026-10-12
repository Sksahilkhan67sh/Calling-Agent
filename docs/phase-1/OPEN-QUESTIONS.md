# Phase 1 open questions and residual risks

| # | Question / risk | Owner | Blocks |
|---|---|---|---|
| OQ-01 | `API_RATE_LIMIT_PER_MINUTE` and `WEBHOOK_RATE_LIMIT_PER_MINUTE` have **no real values**. Staging/prod refuse to start without them; they must come from Load Test Plan §4.3 results with the source run/date recorded | Sahil | first staging deploy |
| OQ-02 | `DOGRAH_EFFECTIVE_CONCURRENCY` is validated but unused. Needs carrier channels (Phase 0 Q13) and Dograh capacity; formula in Phase 0 DP-12 | Sahil | Phase 4 |
| OQ-03 | CI has only been validated with `actionlint` and by running each job's commands locally. No GitHub-hosted run has been seen; the `docker` job (compose smoke test) could not run here at all (no Docker daemon) | Sahil | merging the PR |
| OQ-04 | `LOGIN_RATE_LIMIT_PER_MINUTE` default 5 per client address is my security default, not a documented requirement. Confirm with Phase 2 lockout policy (`AXES_FAILURE_LIMIT`) | Sahil | Phase 2 |
| OQ-05 | `DOGRAH_WEBHOOK_HEADER_NAME` default `X-Dograh-Webhook-Secret` is still pending Phase 0 V01 (live capture) | Sahil | Phase 5 |
| OQ-06 | Redaction masks any 10–15 digit run (for example epoch timestamps) as a possible phone number. Accepted over-redaction; revisit if it hurts debugging | Sahil | none |
| OQ-07 | Recording URL redaction relies on path segments `recording(s)/transcript(s)/artifact(s)`. Dograh's real public download path (token in path) is unverified (Phase 0 V10). Re-check the pattern once real URLs are seen | Sahil | Phase 5 |
| OQ-08 | `PHONE_HMAC_KEY` rotation is a planned migration, not implemented (D-07). Needs an owner and a runbook before go-live | Sahil | before go-live |
| OQ-09 | Phase 0 items still pending live work (V01–V14, carrier choice, status mapping) are untouched by Phase 1 and continue to gate Phases 4–5 | Sahil | see Phase 0 |
| OQ-10 | gitleaks-action needs a licence key for GitHub organisation repos (free for personal accounts). If the repo moves to an organisation, swap in the gitleaks binary | Sahil | org move |
| OQ-11 | Residual risk: staging/prod health endpoints are anonymous over HTTP inside the cluster by design (fixed tiny JSON, check names only). Restrict at the network layer (ALB/security group) | Sahil | go-live |
