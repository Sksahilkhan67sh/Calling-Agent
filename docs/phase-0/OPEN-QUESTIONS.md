# Open questions (everything still UNVERIFIED)

Owner for all live items: **Sahil** (needs `DOGRAH_BASE_URL`, `DOGRAH_API_KEY`, `DOGRAH_WORKFLOW_UUID`, `PUBLIC_WEBHOOK_URL`, `SPIKE_TEST_NUMBERS`, `LIVE_TESTING=yes`, and a non-zero `MAX_TEST_CALLS`/`MAX_TEST_SPEND`). Exact steps: VERIFICATION-REPORT.md.

| # | Question | Fallback in place | Becomes blocking |
|---|---|---|---|
| Q1 | Does the webhook carry any signature/timestamp header; exact header format and source IPs (V01) | shared secret + network allowlist + verify-by-pull | Phase 5 |
| Q2 | How do numbers and nulls render in the payload (V02) | tolerant parsing | Phase 5 |
| Q3 | Does Dograh retry non-2xx; is `retry_config` real; does the webhook fire for never-connected and abnormal ends (V03/V06/V07) | reconciler is primary | Phase 5 |
| Q4 | Run completion lag after the webhook; in-progress and unknown-id responses (V04) | backoff 2/10/30/90 s then reconciler | Phase 5 |
| Q5 | Observed values of `call_status`/`call_disposition` per scenario; `invalid_number` signal per carrier (V06) | mapping v0.1, unknown → `provider_error` + alert | Phase 5 |
| Q6 | Trigger behaviour on timeout/duplicate; 4xx means no run? (V08) | unknown outcome → reconcile, never redial | Phase 4 |
| Q7 | Does the seeded context drive the greeting; size limit (V09) | flat keys, 8 KB | Phase 6 (reconnect) |
| Q8 | Artifact expiry, formats, lag (V10) | download immediately; allowlist | Phase 5 |
| Q9 | How is a new workflow version published; can a webhook credential be created by API (V11) | UI publish + credential; guard before campaign start | Phase 6 / sync |
| Q10 | Does `DEFAULT_ORG_CONCURRENCY_LIMIT` apply to API triggers; rate limits (V12) | Django semaphore | Phase 4 |
| Q11 | Auth for `/user/api-keys`; IP allowlist at proxy (V13) | manual rotation runbook | Phase 8 |
| Q12 | Posture of the running Dograh stack (V14) | `v14_posture_check.py` | before go-live |
| Q13 | Target country, carrier choice, channels, CPS, price, caller-ID rules (CARRIER-SHORTLIST) | shortlist; none chosen | Phase 1 cost model, Phase 4 |
| Q14 | Does Dograh verify signatures for Exotel, Telnyx, Cloudonix | avoid those carriers or add proxy controls | carrier choice |
| Q15 | Per-carrier Dograh pages, create-from-definition, validate, create-test-run and API-key pages were not read | read during the live run | V11, V13 |
| Q16 | If cloud is reconsidered: retention, regions, subprocessors, deletion at Dograh Cloud | self-hosted | only if cloud is chosen |
