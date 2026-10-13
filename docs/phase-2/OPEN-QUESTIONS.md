# Phase 2 — Open questions

_Populated by the task that owns it (see PROGRESS.md)._

## From P2-02
- **OQ2-01 Absolute session lifetime.** Rotation makes the refresh lifetime a sliding idle timeout; an actively used session never expires. Needs a product decision on a maximum session age (would need an `auth_time` claim carried through rotation).
- **OQ2-02 Rate values.** Phase 1 OQ-01 stays open: prod `API_`, `WEBHOOK_` and `LOGIN_RATE_LIMIT_PER_MINUTE` must come from load-test results (Environment-Config §4); record the source run and date with the deployment config.
- **OQ2-03 Dashboard domain.** SameSite=Lax assumes dashboard and API share a registrable domain. Confirm the real hostnames (`DASHBOARD_ORIGIN` input is still an example).

## From P2-04
- **OQ2-04 Recordings/transcripts for Admin.** Currently granted to nobody by default (per-user grant). Should Admin hold `transcripts.view`/`recordings.listen` by default?
- **OQ2-05 Sales scope.** What does "assigned" mean for Sales / Follow-up (per-campaign assignment, or all contacts)? Does the contact view include attempt history for Sales? Phase 3 must decide with `for_user()`.
- **OQ2-06 Per-user grant workflow.** Phase 2 has no command or endpoint to grant `recordings.listen` to a single user; `assign_role`/Django ORM only. Decide if a `grant_capability` command is needed before Phase 5/6.

## From P2-05
- **OQ2-07 Scoping lint coverage.** A view that builds its queryset only in `get_queryset()` is not detected by the lint (see DECISIONS P2-05). Phase 3 should either keep the `queryset =` idiom or extend the lint (e.g. require `scoped_model` on every view with a serializer over a scoped model).

## From P2-06
- **OQ2-08 Audit retention, export and tamper-evidence.** Who deletes old events, after how long, and how (privileged role that detaches the trigger)? Export to external immutable storage (S3 Object Lock / SIEM)? Hash-chaining of rows? Monthly partitioning once the table is large.
- **OQ2-09 Client IP in audit events** is empty until P2-10 binds the trusted-proxy resolver; CLI events never have one.
- **OQ2-10 Capability-grant audit.** Per-user grants of `recordings.listen` (OQ2-06) must produce an audit event when that workflow exists.
- **OQ2-11 Load-sensitive Phase 1 tests.** `test_health.py` (readiness must return in < 1.5 s despite a 3 s hang) and `test_celery_integration.py` (30 s worker start-up wait) use wall-clock bounds. They passed under CPU load in P2-06 but may flake on a slow CI runner; if they do, convert to CPU time or widen relative to the configured timeout.
