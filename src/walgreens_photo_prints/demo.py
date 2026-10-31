"""Demo data and a demo transport for the web front-end and its freeze.

Every value here is fictional (``example.test`` URLs, fake store
numbers, a ``DEMO`` SAS signature). The demo client goes through the
real ``WalgreensClient`` validation and parsing code, with only the
HTTP layer replaced, so the demo exercises the same code paths as
live use without ever touching the network or needing credentials.

The freeze script builds its demo app from here and takes no
credentials argument, so real data cannot be frozen by accident.
"""

from .client import WalgreensClient
from .config import Config

SAMPLE_CART_JSON = '[{"productId": "8420005", "qty": "10"}]'
SAMPLE_ORDER_JSON = (
    '[{"productId": "8420005", "imageDetails": '
    '[{"url": "https://example.test/blob/demo.jpg?sig=DEMO", "qty": "1"}]}]'
)
SAMPLE_LATITUDE = "38.0293"
SAMPLE_LONGITUDE = "-78.4767"
SAMPLE_COUPON_CODE = "DEMO10"
SAMPLE_ORDER_ID = "DEMO-0001"


class DemoResponse:
    def __init__(self, data):
        self._data = data
        self.status_code = 200
        self.headers = {}
        self.text = ""

    def json(self):
        return self._data


class DemoTransport:
    """A transport that answers every endpoint with fictional data."""

    def post(self, url, headers, json, timeout):
        if url.endswith("/creds/v3"):
            return DemoResponse(
                {
                    "uploadLimit": 5,
                    "template": "demo-template",
                    "landingUrl": "https://example.test/landing",
                    "cloud": [{"sasKeyToken": "https://example.test/blob?sig=DEMO"}],
                }
            )
        if url.endswith("/products/v3"):
            return DemoResponse(
                {
                    "products": [
                        {
                            "productId": "8420005",
                            "productDesc": "Demo 4x6 Print",
                            "productSize": "4x6",
                            "productGroupId": "STDPR",
                            "productPrice": "0.25",
                        },
                        {
                            "productId": "8420006",
                            "productDesc": "Demo 5x7 Print",
                            "productSize": "5x7",
                            "productGroupId": "STDPR",
                            "productPrice": "0.65",
                        },
                    ]
                }
            )
        if url.endswith("/coupon/v3"):
            return DemoResponse(
                {"status": "success", "orderTotalPrice": 10.00, "orderDiscountPrice": 2.00}
            )
        if url.endswith("/store/v3"):
            return DemoResponse(
                {
                    "photoStores": [
                        {
                            "photoStoreDetails": {
                                "storeNum": "211",
                                "promiseTime": "03-02-2020 5:15 PM",
                                "type": "Demo Store",
                                "zip": "22901",
                                "city": "Charlottesville",
                                "state": "VA",
                                "street": "1 Demo Way",
                                "latitude": SAMPLE_LATITUDE,
                                "longitude": SAMPLE_LONGITUDE,
                                "phone": "5555555555",
                                "distance": "1.2",
                                "distanceUnit": "mi",
                                "openTime": "8:00 AM",
                                "closeTime": "10:00 PM",
                                "storeName": "Demo Walgreens",
                            }
                        },
                        {
                            "photoStoreDetails": {
                                "storeNum": "212",
                                "promiseTime": "01-01-3000 00:00 AM",
                                "type": "Demo Store",
                                "zip": "22901",
                                "city": "Charlottesville",
                                "state": "VA",
                                "street": "2 Demo Way",
                                "latitude": SAMPLE_LATITUDE,
                                "longitude": SAMPLE_LONGITUDE,
                                "phone": "5555555555",
                                "distance": "2.4",
                                "distanceUnit": "mi",
                                "openTime": "8:00 AM",
                                "closeTime": "10:00 PM",
                                "storeName": "Demo Walgreens (no promise time)",
                            }
                        },
                    ]
                }
            )
        if url.endswith("/submit/v3"):
            return DemoResponse({"vendorOrderId": SAMPLE_ORDER_ID, "status": "success"})
        if url.endswith("/status/v3"):
            orders = (json or {}).get("orders") or [SAMPLE_ORDER_ID]
            return DemoResponse(
                {
                    "statuses": [
                        {
                            "orderId": str(order_id),
                            "valid": "true",
                            "code": "3",
                            "orderStatus": "Ready for Pickup",
                        }
                        for order_id in orders
                    ]
                }
            )
        return DemoResponse({})

    def close(self):
        pass


def create_demo_client():
    """A client wired to the demo transport, with placeholder config.

    The placeholder key is fictional and is never sent anywhere:
    the demo transport ignores request bodies entirely.
    """
    config = Config(
        api_key="demo-api-key",
        aff_id="demo-aff",
        app_ver="1.0",
        dev_inf="DemoDevice,1.0",
        base_url="https://example.test",
    )
    return WalgreensClient(config, transport=DemoTransport())
