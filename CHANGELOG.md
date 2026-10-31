# Changelog

## 1.3.1 — 2026-10-31

Fix for a v1.3.0 packaging miss, found by a bare `pytest -q`
run: Flask is an optional `[web]` extra, but the web and freeze
tests imported it unconditionally, so a library-only install
failed with 2 failures and 7 errors (the 73 core tests passed).
Now the web/freeze tests skip cleanly when Flask is absent,
CI installs `.[dev,web]` so they actually run there instead
of being silently skipped, the freeze script reports a plain
install instruction instead of a traceback when Flask is
missing, and README Local Development installs `.[dev,web]`
for the full suite.

## 1.3.0 — 2026-10-31

Flask front-end plus a Pages freeze demo. The library and CLI are
unchanged in behaviour; this release adds a web layer on top of
them.

Added:

- Flask front-end (`walgreens_photo_prints.webapp`, optional
  `[web]` extra, run with `walgreens-prints serve`): products,
  stores, coupon, upload, two-step submit, and status pages.
  Live mode builds a real client from the environment, with
  credentials server-side only; demo mode (`--demo`) uses
  fictional data from `demo.py` and makes no network call.
- Submit in the web UI keeps the CLI's gates: a redacted
  preview first, then a second POST with both `confirm` and
  `accept_terms` checked. CSRF tokens are required on every
  POST form. Live mode has no login: run it locally only.
- `scripts/freeze.py` + `.github/workflows/pages-freeze.yml`:
  the demo app is rendered with the Flask test client into
  `freeze-site/` (gitignored, never committed), with forms
  disabled and a static-demo banner, for GitHub Pages. The
  freeze builds its own demo app and takes no credentials
  argument, so real data cannot be frozen by accident.
- Tests for the web app (demo flows, CSRF rejection, redacted
  preview, demo submit) and for the freeze (all pages, banner,
  disabled forms, no absolute paths, no leaked env secrets).

Not included, deliberately:

- No live Pages app: Pages is static and cannot hold the API
  key, upload files, or submit orders. The frozen site is a
  demo only.
- No public hosting or login for live mode. A publicly hosted
  ordering service would need auth, which is out of scope.

## 1.2.0 — 2026-10-31

Stage 3 of the staff review: architecture, with no behaviour
change for existing callers. Dict and attribute-style product
inputs still work; `ProductQty` is now the preferred form.

Added:

- `transport.py`: a `Transport` protocol plus a
  `RequestsTransport` implementation. `WalgreensClient` accepts
  `transport=...` (precedence over the legacy `session=...`),
  so the client is testable without subclassing a real
  `requests.Session`, and a future async transport is additive.
- `models.ProductQty`: typed coupon/store product input, with
  `to_payload()`. The CLI now parses product-details JSON into
  `ProductQty` objects, so the CLI, client, and tests share one
  typed shape instead of three dict parsers.
- `client.API_VERSION` and `client.ENDPOINTS`: the six paths
  are built from one version constant, so a v4 migration is a
  one-line change plus a changelog entry.
- Debug logging in `_post` (method, path, status only; payloads
  are never logged, since they contain the API key).

Changed:

- `RATE_LIMITS_PER_MINUTE` renamed to
  `DOCUMENTED_RATE_LIMITS_PER_MINUTE` to make clear the limits
  are documented, not enforced; the old name remains as an
  alias for backwards compatibility.

Not changed, deliberately:

- `Config` still requires HTTPS base URLs, so the local
  HTTP-server test exercises `RequestsTransport` directly
  rather than weakening the client to accept HTTP.
- No automatic retry: submit is not idempotent (see the client
  module docstring).

## 1.1.0 — 2026-10-31

Staff-review pass, applied in the review's suggested order (P0/P1
fixes first, then DRY/version/README cleanup). No live Walgreens run
yet; the sandbox gate from 1.0.0 is unchanged.

Fixed:

- `UploadCredentials` no longer leaks the SAS token through
  `repr`; `redacted_dict()` is the sanctioned serialised view, and
  the CLI uses it. (`asdict()` still ignores `repr=False` by
  design, which is now documented on the class.)
- `upload_image` closes a session it created, and never closes a
  caller's session. Content type is guessed from the file extension
  (overridable), and caller-supplied image names are validated to
  bare filenames.
- `OrderStatusEntry.status_label` now prefers the raw
  `orderStatus` string, as the reference's duplicated code `2`
  requires; the code map is only a fallback.
- Client validation moved into the client, matching the CLI:
  required submit fields non-empty, at least one product with at
  least one image, quantities are integers in 1..20 (floats,
  bools, 0, and negatives rejected, no silent truncation),
  coordinates validated to -90..90 / -180..180, coupon and store
  calls require product details, and distinct-image limits count
  distinct URLs across the order.
- HTTP errors now include a truncated response body, requests
  send a `walgreens-photo-prints/<version>` User-Agent, and
  `Retry-After` parses HTTP dates as well as seconds.
- `Config` normalises `platform`/`app_ver`/`dev_inf`, rejects a
  `None` timeout with `ConfigError` instead of `TypeError`,
  checks sandbox by hostname instead of substring, and
  `from_env` parses dotenv files without mutating
  `os.environ` (explicit mappings now see file values too).
- Money: `CouponResult` gains Decimal properties
  (`total_as_decimal`, `discount_as_decimal`,
  `new_subtotal_decimal`); float fields are kept for
  compatibility.

Changed:

- Single version source: `walgreens_photo_prints/_version.py`.
  `pyproject.toml` reads it dynamically, and the CLI imports it.
- Library dependency ranges (`requests>=2.32,<3`,
  `python-dotenv>=1.2,<2`) instead of exact pins; reproducibility
  moves to the CI install.
- CLI config overrides use `dataclasses.replace` instead of a
  field-by-field rebuild.
- README rewritten with Description, Prerequisites, Installation,
  Local Development, and Deployment sections, plus `.env.example`,
  `SECURITY.md`, `CONTRIBUTING.md`, and architecture/order-flow
  diagrams in `docs/assets/`. The CLI demo GIF and CI screenshot
  are deliberately not included: they may only be added from real
  runs (see `CONTRIBUTING.md`).
- CI now runs `ruff format --check` and caches pip installs.

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
