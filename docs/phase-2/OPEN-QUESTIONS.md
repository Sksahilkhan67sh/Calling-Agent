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

## From P2-07
- **OQ2-12 Recovery codes / multiple devices / voluntary enrolment.** Loss of the authenticator needs an operator running `mfa_reset` (audited). Recovery codes would need one-time, hashed, single-use storage and their own brute-force limits; a second device needs the one-active constraint relaxed. Users whose roles do not require MFA cannot enrol in Phase 2 (the enrolment endpoints accept only the restricted credential).
- **OQ2-13 HTTP-level restriction retest.** Default DRF authentication is still empty until P2-08, so "the enrolment credential is rejected by ordinary endpoints" is trivially true today. P2-09/P2-15 must repeat it against the real cookie-JWT default authenticators.
- **OQ2-14 TOTP clock source.** Verification uses the application server clock (`time.time()`); NTP on all app hosts is an operational requirement (a +/- 30 s window tolerates small drift only).

## From P2-08
- **OQ2-15 Parallel refresh = false theft signal.** The frontend must serialise refresh calls (single-flight) and must not retry a refresh whose response was lost. Decide whether a short grace window for the immediately previous token is acceptable (it weakens theft detection).
- **OQ2-16 Access token outlives logout by up to 15 min.** Closing it needs a per-session id claim and a denylist (Redis) checked per request; costs one extra lookup per request. Decide with the product's risk appetite.
- **OQ2-17 Per-request database cost.** Every authenticated request loads the user (epoch, `is_active`) and capabilities once. If this becomes a bottleneck, cache `(user_id, auth_epoch, is_active)` in Redis with epoch-bump invalidation; not needed at the expected volume.
- **OQ2-18 Beat schedule for `flushexpiredtokens`** to be added with the Phase 4 worker.

## From P2-09
- **OQ2-19 First-enrolment takeover window (important).** A user whose roles require MFA but who has not enrolled yet receives the enrolment credential on a correct password alone, so **anyone who learns that password before the legitimate user enrols can enrol their own authenticator and lock the user out**. The design in the brief requires this flow; mitigations: (a) the provisioning commands (`bootstrap_admin`, `create_user`, P2-13) must hand the user a one-time password and the user must enrol immediately; (b) stronger option: an out-of-band one-time *enrolment code* printed by the provisioning command and required at `/auth/mfa/enroll`. Needs a decision before real users are onboarded.
- **OQ2-20 Error shape drift.** The contract's `Error` is `{code, message}`; the Phase 1 global handler returns `{detail}`. Auth views follow the contract. Decide whether to move the global handler to the contract shape (touches many Phase 1 tests).
- **OQ2-21 No identity endpoint.** The contract has no `GET /me`; after login the SPA cannot learn the user's name or roles (the access cookie is HttpOnly). Propose adding one (capability-gated by authentication only).
- **OQ2-22 Logout with an expired access token.** Logout requires authentication, so once the access cookie has expired the SPA must refresh first; otherwise the refresh cookie lingers until it expires. Alternative: let logout accept the refresh cookie alone (CSRF-protected).
- **OQ2-23 Login throttle bucket is shared** by login, refresh and the enrolment endpoints per client address; a household or office NAT shares it. Rates come from load tests (OQ-01/OQ2-02); per-account throttling is the lockout in P2-10.

## From R1
- **OQ2-24 `main` moved ahead of the branch (needs a human decision).** After this branch was cut, `main` merged Dependabot PRs: Django 5.2.17 -> 6.1.2, Python base image 3.14, ruff and other minor bumps (8 commits). The fixed design decision is the Django 5.2 LTS line and this branch's lock files pin 5.2.17. Merging `main` into this branch will conflict in the hash-locked requirements and brings a Django major version this phase was not tested against. Recommendation: keep Phase 2 on 5.2 LTS, finish it, then decide separately (and test) whether to move to 6.x; revert or pin the Dependabot change on `main`. Not acted on.
- **OQ2-25 A GitHub personal access token was shared in the chat/upload.** It was not needed (the repo is public) and was not used. Treat it as exposed: revoke it on GitHub and create a new one only if a push is wanted.

