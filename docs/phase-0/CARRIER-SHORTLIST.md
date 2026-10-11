# Carrier shortlist (docs-only; no vendor contacted, no account opened)

Sources: Dograh docs `/integrations/telephony/overview`, `/integrations/telephony/webhooks`, `/developer/environment-variables` (read 2026-10-11); per-carrier Dograh pages and carrier websites were **not** read. Anything not stated there is `UNVERIFIED-NEEDS-VENDOR`.
Missing decision inputs: target country(ies) (the design docs are multi-jurisdiction and name none), monthly volume per country (baseline 100 000 contacts/month), budget.

| Carrier | In Dograh docs | Signature check inside Dograh | Audio in Dograh | Notes from Dograh docs | Channels / CPS | Caller-ID and number rules | Pricing | Invalid-number signal | Region / data residency |
|---|---|---|---|---|---|---|---|---|---|
| Twilio | yes | yes, HMAC-SHA1 | 8 kHz μ-law | TwiML answer webhook; `<Stream>` drops query strings (hence path token) | NEEDS-VENDOR | NEEDS-VENDOR | NEEDS-VENDOR | not documented | NEEDS-VENDOR |
| Plivo | yes | yes, HMAC-SHA256 | 8 kHz μ-law | hangup and ring callbacks | NEEDS-VENDOR | NEEDS-VENDOR | NEEDS-VENDOR | not documented | NEEDS-VENDOR |
| Vobiz | yes | yes, HMAC-SHA256 | 8 kHz μ-law | described as global reach, competitive pricing | NEEDS-VENDOR | NEEDS-VENDOR | NEEDS-VENDOR | not documented | NEEDS-VENDOR |
| Vonage | yes | yes, JWT | 16 kHz PCM | NCCO answer webhook (GET) | NEEDS-VENDOR | NEEDS-VENDOR | NEEDS-VENDOR | not documented | NEEDS-VENDOR |
| Exotel | yes | **not documented** | not stated | described as India-focused; no answer webhook, stream URL attached at dial time | NEEDS-VENDOR | NEEDS-VENDOR | NEEDS-VENDOR | not documented | NEEDS-VENDOR |
| Telnyx | yes (page exists) | **no carrier signature**; events URL protected only by a `?token=` signed with `TELEPHONY_WS_TOKEN_SECRET` (bearer, appears in logs) | not stated | call-control style | NEEDS-VENDOR | NEEDS-VENDOR | NEEDS-VENDOR | not documented | NEEDS-VENDOR |
| Cloudonix | yes | **not documented** | not stated | also backs the Dograh-managed SIP | NEEDS-VENDOR | NEEDS-VENDOR | NEEDS-VENDOR | not documented | NEEDS-VENDOR |
| Asterisk ARI | yes | not applicable (own PBX, token on the ARI socket) | 8 kHz PCM | self-hosted only; you still need a SIP trunk | your trunk | your trunk | trunk price | not documented | yours |

## Recommendation (provisional)
1. No carrier can be chosen without the target country and a price. **Do not pick on features alone.**
2. Request quotes and answers from carriers whose signature verification Dograh documents: **Twilio, Plivo, Vobiz, Vonage**. This removes the open `[verify]` for Security-Architecture row 6.
3. If calls go to India, add **Exotel** to the quote round, but treat its signature verification as absent until Dograh or Exotel confirms; compensate with `TELEPHONY_WS_TOKEN_SECRET` + enforce on the media socket and source-IP restriction of the status callbacks at the proxy.
4. Avoid **Telnyx, Cloudonix, Asterisk** for the first release unless the vendor answers below are satisfactory (no documented carrier-signature check for the first two).
5. Dograh sells no numbers or minutes, so the carrier account, KYC and number purchase are on the project.

## Vendor questions (send to each shortlisted carrier)
1. Concurrent channel limit and calls-per-second on our account tier; how to raise them and lead time.
2. Rules for outbound caller ID in each target country (own number, verified numbers, registration of AI/automated callers, any prohibition on voice AI).
3. Required registrations or templates for automated outbound calling in each target country, and do-not-call registry obligations.
4. Recording and consent obligations they enforce or recommend per country.
5. Pricing model: per-minute by destination, billing increment, number rental, channel fees, minimum commit.
6. How an invalid, unallocated or disconnected number is reported (status value, SIP code, timing) and how a callee rejection is distinguished from busy.
7. Signed status callbacks: algorithm and what Dograh verifies (ask Dograh: is verification implemented for this carrier).
8. Data residency and retention of call detail records and any media; region of signalling and media.
9. Support: SLA, status page, escalation path.
Questions for Dograh: signature verification coverage for Exotel, Telnyx, Cloudonix; how carrier statuses map to `gathered_context.call_status`.
