# Local customer-data security and retention

## Chat leads

The FastAPI chat stores customer leads in the ignored local file
`data/local/interactions.sqlite3`. This lead table currently stores name, phone,
email, callback time, problem brief, recommendation, consent wording and a
consent timestamp in SQLite **without encryption**. There is no automatic lead
retention or deletion job yet.

`GET /api/admin/leads` is disabled unless the service process has
`AURORA_LEAD_ADMIN_KEY`. Requests must supply that value in the
`X-Aurora-Lead-Admin-Key` header. This is a single shared secret, not
user-specific authentication or role-based access; calls are not currently
written to the audit log. Keep the service bound to `127.0.0.1`, keep the key
outside Git and browser code, and do not expose this endpoint to a network or
real customer data until encryption, approved retention/deletion, individual
operator authentication, access logging and transport security are implemented.

Consent is recorded when a customer supplies a parseable contact method after
being shown the contact-use wording. This prototype does not collect an
explicit yes/no acknowledgement or verify contact ownership. The consent text
and timestamp are operational records, not legal advice or a substitute for an
approved privacy notice and consent process.

## Standalone review queue

`audit_store.py` is a standalone encrypted-capable review-queue utility stored
in `data/local/review_queue.sqlite3`; it is not connected to the FastAPI
conversation flow. Its default review retention is 30 days. Set
`AUDIT_RETENTION_DAYS` to an approved value and run
`python scripts/purge_audit.py` on a schedule. Purging removes expired review
payloads and their events.

For any use of this separate utility with real customer data, encryption is
mandatory:

1. Generate a Fernet key using an approved secret-management process.
2. Store it outside Git as `AUDIT_ENCRYPTION_KEY`.
3. Set `AUDIT_REQUIRE_ENCRYPTION=true`.
4. Set `AUDIT_APPROVERS` to a comma-separated allowlist of reviewer identifiers.
5. Set the current authenticated reviewer identifier as `AUDIT_REVIEWER`.

If the encryption key is lost, encrypted payloads cannot be recovered. Back up
and rotate it according to company policy. Do not expose either SQLite file
through a shared drive or web endpoint. A production service needs authenticated
users, role-based authorisation, TLS, request logging, secret rotation, approved
retention and an encrypted database before deployment.
