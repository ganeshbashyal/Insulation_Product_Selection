# Callback audit security and retention

The Streamlit POC stores callback briefs in `data/local/review_queue.sqlite3`. This directory is ignored by Git. The store has no network API; access is limited to the local operating-system account and this application process.

The default POC retention period is 30 days. Set `AUDIT_RETENTION_DAYS` to an approved value and run `python scripts/purge_audit.py` on a schedule. Purging removes the review and its event records after the retention deadline.

For any real customer or Aircall data, encryption is mandatory:

1. Generate a Fernet key using an approved secret-management process.
2. Store it outside Git as `AUDIT_ENCRYPTION_KEY`.
3. Set `AUDIT_REQUIRE_ENCRYPTION=true`.
4. Set `AUDIT_APPROVERS` to a comma-separated allowlist of reviewer identifiers.
5. Set the current authenticated reviewer identifier as `AUDIT_REVIEWER`.

If the encryption key is lost, encrypted payloads cannot be recovered. Back up and rotate it according to company policy. Do not expose the SQLite file through a shared drive or web endpoint. A production API must add authenticated users, role-based authorisation, TLS, request logging, secret rotation and a managed encrypted database before deployment.
