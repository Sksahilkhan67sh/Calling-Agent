"""Registry of audit actions. ``record()`` refuses anything not listed here (a typo must not create a
silently un-queryable event). Later phases add their constants here, e.g. retry_policy.write,
agent_config.write, suppression.write and recording/transcript access (Security-Architecture §9)."""

AUTH_LOGIN_SUCCESS = "auth.login.success"
AUTH_LOGIN_FAILURE = "auth.login.failure"
AUTH_LOGIN_LOCKED_OUT = "auth.login.locked_out"
AUTH_MFA_ENROLLMENT_STARTED = "auth.mfa.enrollment_started"
AUTH_MFA_ENROLLED = "auth.mfa.enrolled"
AUTH_MFA_FAILED = "auth.mfa.failed"
AUTH_MFA_RESET = "auth.mfa.reset"
AUTH_TOKEN_REFRESH_REUSE_DETECTED = "auth.token.refresh_reuse_detected"
AUTH_LOGOUT = "auth.logout"
AUTH_LOGOUT_ALL = "auth.logout_all"
USER_CREATED = "user.created"
USER_DEACTIVATED = "user.deactivated"
USER_ROLE_ASSIGNED = "user.role_assigned"
USER_ROLE_REMOVED = "user.role_removed"
USER_PASSWORD_CHANGED = "user.password_changed"
API_CLIENT_CREATED = "api_client.created"
API_CLIENT_REVOKED = "api_client.revoked"
RBAC_SYNC = "rbac.sync"

ACTIONS: frozenset[str] = frozenset(
    value for name, value in globals().items() if name.isupper() and isinstance(value, str)
)
