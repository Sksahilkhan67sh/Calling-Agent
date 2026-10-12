"""Role names. Pure constants (no Django imports) so settings can validate against them.

P2-04 extends this module with the capability registry and the role matrix.
"""

ROLE_ADMIN = "Admin"
ROLE_CAMPAIGN_MANAGER = "Campaign Manager"
ROLE_SALES_FOLLOW_UP = "Sales / Follow-up"
ROLE_SYSTEM = "System"

ALL_ROLES = (ROLE_ADMIN, ROLE_CAMPAIGN_MANAGER, ROLE_SALES_FOLLOW_UP, ROLE_SYSTEM)
# MFA is mandatory for these roles in production (Django-Backend-Design §4.1).
MFA_MANDATORY_ROLES = (ROLE_ADMIN, ROLE_CAMPAIGN_MANAGER)
