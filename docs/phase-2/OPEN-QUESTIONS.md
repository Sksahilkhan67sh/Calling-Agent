# Phase 2 — Open questions

_Populated by the task that owns it (see PROGRESS.md)._

## From P2-02
- **OQ2-01 Absolute session lifetime.** Rotation makes the refresh lifetime a sliding idle timeout; an actively used session never expires. Needs a product decision on a maximum session age (would need an `auth_time` claim carried through rotation).
- **OQ2-02 Rate values.** Phase 1 OQ-01 stays open: prod `API_`, `WEBHOOK_` and `LOGIN_RATE_LIMIT_PER_MINUTE` must come from load-test results (Environment-Config §4); record the source run and date with the deployment config.
- **OQ2-03 Dashboard domain.** SameSite=Lax assumes dashboard and API share a registrable domain. Confirm the real hostnames (`DASHBOARD_ORIGIN` input is still an example).
