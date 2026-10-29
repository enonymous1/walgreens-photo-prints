# Changelog

## 1.0.0 — 2026-10-29

Standalone modernization of the March 2024 `ss-walgreens` client (3 commits, 6 Python files, ~190 lines, plus a copy of the Walgreens API reference). The original is untouched; this is a fresh rewrite, not a patch on its history. The API reference was summarized in the README, not copied into this repo.

Added:

- Installable `walgreens_photo_prints` package and `walgreens-prints` CLI (`python -m walgreens_photo_prints` also works).
- All six v3 endpoints: upload credentials, products, coupon validation, store search, order submit, and order status. The original implemented only the first three.
- Environment-based configuration (`.env` supported, real environment wins), with the API key excluded from `repr` and from CLI output. No credentials in source.
- Timeouts, HTTP and API-level error handling, and 429 handling that flags throttled results instead of returning partial data.
- Typed response models that preserve API ordering and tolerate absent or null fields, with named nullable-field filtering for products and stores.
- Upload flow with a fail-loud SAS-token invariant and a fresh UUID request ID per upload, fetching credentials exactly once.
- Client-side order limits (200 distinct images, 20 prints per image URL) and a terms-action gate on submit; the CLI refuses to submit without `--confirm --accept-terms`.
- Tests (mocked responses only; no live Walgreens run) and CI.

Fixed from the original:

- Modules no longer make network calls on import; `UploadImages.py` no longer fails on import (undefined `upload_url`, missing `os` import).
- The hardcoded API key and affiliate ID are removed; the mislabeled `production_url` is replaced by a single validated base URL.
- `GenerateUploadToken` no longer trusts the credentials response shape or unpacks the SAS token without validation, and no longer triggers a second credentials fetch.
- Placeholder app version / device info are explicit, overridable configuration instead of literals scattered through calls.

Unverified: no live sandbox or production run has been made with this package. The submit endpoint's second, conflicting example in the reference (see README) and the status code `2` duplication are documented, not resolved. A sandbox run with a fresh key is the gate before any real order.
