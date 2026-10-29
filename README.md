# walgreens-photo-prints

A Python client and CLI for the Walgreens Native Photo Prints API v3: fetch upload credentials, list products and prices, validate coupons, find photo stores, submit orders, and check order status. Uploads go to Walgreens cloud storage via a short-lived SAS token, for same-day pickup at a Walgreens store.

This is a standalone modernization of a small March 2024 client (`ss-walgreens`) that covered only three of the six endpoints and made network calls on import. It is not affiliated with or endorsed by Walgreens. You need your own API key and affiliate ID from the [Walgreens Developer Portal](https://developer.walgreens.com/apis).

## Install

Requires Python 3.10+.

```powershell
pip install -e .
```

## Configure

Credentials come from the environment or a `.env` file. Never commit a `.env` file, and never hardcode a key in source. Copy the example values, not a real key:

```env
WALGREENS_API_KEY=your-api-key
WALGREENS_AFF_ID=your-affiliate-id
WALGREENS_BASE_URL=https://services-qa.walgreens.com
WALGREENS_APP_VER=1.0
WALGREENS_DEV_INF=YourDevice,1.0
```

Defaults: the sandbox base URL above, platform `ios`, 30-second timeout. Set `WALGREENS_BASE_URL=https://services.walgreens.com` for production. `WALGREENS_APP_VER` and `WALGREENS_DEV_INF` are optional for credentials and products, required by the API for coupon, store, and submit calls.

If you are migrating from the 2024 original: the old `config.py` hardcoded an API key. Treat any key that was ever committed as compromised, rotate or revoke it in the developer portal, and put the replacement in the environment only. The old `production_url` value was actually the credentials endpoint, not a base URL; this package uses a single base URL for all six endpoints.

## CLI

```powershell
walgreens-prints creds
walgreens-prints products --product-group-id STDPR
walgreens-prints coupon --code TESTFORALL --product-details cart.json
walgreens-prints stores --latitude 41.880977 --longitude -87.626481 --product-details cart.json
walgreens-prints status 0000000001 0000000002
walgreens-prints upload-url
walgreens-prints upload photo.jpg
```

`cart.json` for coupon and stores:

```json
[{"productId": "0000001", "qty": "10"}]
```

`submit` places a real order. Without `--confirm` it only prints the redacted payload and exits with status 2. With `--confirm` you must also pass `--accept-terms`, asserting the customer took the required action on the terms element for this order:

```powershell
walgreens-prints submit --first-name "Jane" --last-name "Doe" --phone "5555555555" --email "jane@example.com" --store-num "211" --promise-time "03-02-2020 5:15 PM" --product-details order.json --confirm --accept-terms
```

`order.json` for submit:

```json
[{"productId": "8420005", "imageDetails": [{"url": "UPLOAD_URL", "qty": "1"}]}]
```

Every command also accepts `--api-key`, `--aff-id`, `--base-url`, `--app-ver`, `--dev-inf`, `--platform`, `--timeout`, and `--env-file` flags, which override the environment for that run. `creds` output redacts the SAS token; `upload-url` and `upload` print a signed upload URL, so do not share that output.

## Library

```python
from walgreens_photo_prints import Config, WalgreensClient, upload_image_for_credentials

config = Config.from_env()
with WalgreensClient(config) as client:
    products = client.list_products()
    stores = client.find_stores("41.880977", "-87.626481", [{"productId": "1", "qty": "1"}])
    upload_url, status = upload_image_for_credentials(client, "photo.jpg")
```

Importing the package makes no network calls. Fetch credentials once and reuse them; `upload_image_for_credentials` does exactly one credentials fetch per upload.

```python
from walgreens_photo_prints import ImageDetail, OrderProduct

result = client.submit_order(
    first_name="Jane", last_name="Doe", phone="5555555555",
    email="jane@example.com", store_num="211",
    promise_time="03-02-2020 5:15 PM",
    product_details=[OrderProduct("8420005", [ImageDetail(upload_url, "1")])],
    terms_accepted=True,
)
print(result.vendor_order_id)
```

## Endpoints

| Method | Endpoint | Rate limit |
|---|---|---|
| `fetch_upload_credentials` | `POST /api/photo/creds/v3` | 300/min |
| `list_products` | `POST /api/photo/products/v3` | 300/min |
| `validate_coupon` | `POST /api/photo/order/coupon/v3` | 100/min |
| `find_stores` | `POST /api/photo/store/v3` | 300/min |
| `submit_order` | `POST /api/photo/order/submit/v3` | 300/min |
| `get_order_status` | `POST /api/photo/order/status/v3` | 300/min |

Call `list_products` every time products or prices are shown; the API states prices and products can change at any time. Validate a coupon before adding it to a submit request. The discount is subtracted from the total: `new_subtotal = order_total_price - order_discount_price`. Fetch a fresh promise time from `find_stores` for every order, and never submit to a store reporting the no-promise-time sentinel (`01-01-3000 00:00 AM`, exposed as `PhotoStore.is_no_promise_time`).

Order limits enforced client-side before any request is sent: at most 200 distinct images, at most 20 prints per image URL. The post-coupon price limit (under $998) cannot be checked by this client; validate the coupon and check the total before submitting. The client does not retry or pace requests. A 429 raises `WalgreensApiError` with `throttled=True` and the `Retry-After` value when present; wait and re-run, and do not treat a throttled result as a measurement.

## Response shapes and documentation notes

Responses are JSON objects with `err`/`errCode` and `errDesc` fields; any non-empty error, or a `status` of `error`/`failure`, raises `WalgreensApiError`. Lists are returned in the order the API returned them and are never sorted. Fields may be absent or null; list parsers drop only entries missing the one usable identifier (`productId` for products, `photoStoreDetails` for stores) and keep everything else, nulls included.

The API reference contains two conflicting submit-order examples. This client implements the first, canonical shape (`act: submitphotoorder`, `publisherId`/`couponCode`/`affNotes` optional, `productDetails` of `productId` + `imageDetails`). The second example uses different field names (`currencyType`, `sdkVer`, `act: storenumber`, lowercase `apikey`/`devinf`/`appver`) and sets `affId` to an API-key placeholder. That shape is not implemented and must be resolved by a live sandbox run before relying on it. The reference also lists status code `2` twice ("Downloaded" and "Received at Store"); `OrderStatusEntry.status_label` reports both, and the raw `orderStatus` string is authoritative. The terms-and-conditions copy the reference requires in the app UI is not quoted in the reference excerpt this was built from; the client enforces that the caller collected the terms action (`terms_accepted=True` / `--accept-terms`) but does not supply the copy.

No live Walgreens run has been performed with this package. All tests use mocked responses modeled on the reference examples. A sandbox run with a fresh key is the remaining gate: credentials, products, and store search first, then a sandbox submit and status check. See `CHANGELOG.md` for what changed from the 2024 original.

## Development

```powershell
pip install -e ".[dev]"
pytest
ruff check src tests
```
