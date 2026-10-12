# Phase 2 — Decisions

_Populated by the task that owns it (see PROGRESS.md)._

## P2-01 Dependencies (release dates checked on PyPI, 2026-10-12)
| Package | Pin | Released | Why |
|---|---|---|---|
| djangorestframework-simplejwt | 5.5.1 | 2025-07-21 | Latest stable; declares Django 5.2 support |
| django-axes | 8.3.1 | 2026-02-11 | Latest stable; declares Django 5.2 support |
| pyotp | 2.10.0 | 2026-06-14 | Latest stable (RFC 6238 TOTP); chosen over django-otp, which stores TOTP keys in plaintext |
| pyjwt (transitive of simplejwt, pinned explicitly) | 2.15.0 | 2026-09-23 | 2.14.0 has PYSEC-2026-4141/4183 (fixed in 2.15.0); 2.15.1 (2026-09-28) is inside the 14-day cooling-off window, 2.15.0 is outside it |

`django-otp` and `allauth` deliberately not added. No other pin changed (verified by diffing pin sets of base/prod/dev against Phase 1).
The lock headers no longer reference `/tmp/constraints.txt` (regenerated with the repo's `make lock` command form); hash counts per package are unchanged.
