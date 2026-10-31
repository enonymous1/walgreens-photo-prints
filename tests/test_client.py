"""Client tests against mocked responses. No live Walgreens calls."""

import pytest
import requests

from conftest import FakeResponse, FakeSession
from walgreens_photo_prints.client import WalgreensClient
from walgreens_photo_prints.config import Config
from walgreens_photo_prints.errors import ConfigError, WalgreensApiError
from walgreens_photo_prints.models import ImageDetail, OrderProduct


def test_import_makes_no_request(make_client):
    client, session = make_client([])
    assert session.posts == []


def test_fetch_upload_credentials_payload(make_client):
    client, session = make_client(
        [
            FakeResponse(
                {
                    "uploadLimit": 200,
                    "template": "default",
                    "cloud": [{"sasKeyToken": "https://example.test/c?sig=abc"}],
                }
            )
        ]
    )
    creds = client.fetch_upload_credentials()
    assert creds.upload_limit == 200
    assert creds.sas_key_token == "https://example.test/c?sig=abc"
    payload = session.posts[0]["json"]
    assert session.posts[0]["url"] == "https://services-qa.walgreens.com/api/photo/creds/v3"
    assert payload == {
        "apiKey": "test-api-key",
        "affId": "test-aff",
        "platform": "ios",
        "transaction": "photocheckoutv2",
        "appVer": "1.0",
        "devInf": "TestDevice,1.0",
    }
    assert session.posts[0]["timeout"] == 30.0


def test_list_products_payload_and_order_preserved(make_client):
    client, session = make_client(
        [
            FakeResponse(
                {
                    "err": "",
                    "errDesc": "",
                    "products": [
                        {"productId": "2", "productDesc": "Second", "productPrice": "0.20"},
                        {"productId": "1", "productDesc": "First", "productPrice": "0.10"},
                    ],
                }
            )
        ]
    )
    products = client.list_products(product_group_id="STDPR")
    assert [p.product_id for p in products] == ["2", "1"]
    payload = session.posts[0]["json"]
    assert payload["act"] == "getphotoprods"
    assert payload["productGroupId"] == "STDPR"


def test_list_products_omits_optional_fields_when_unset(config):
    bare = Config(api_key="k", aff_id="a")
    session = FakeSession([FakeResponse({"products": []})])
    WalgreensClient(bare, session=session).list_products()
    payload = session.posts[0]["json"]
    assert "appVer" not in payload and "devInf" not in payload and "productGroupId" not in payload


def test_products_with_null_fields_are_filtered_by_id_only(make_client):
    client, _ = make_client(
        [
            FakeResponse(
                {
                    "products": [
                        {"productId": None, "productDesc": "No id"},
                        {"productId": "", "productDesc": "Blank id"},
                        {"productId": "7", "productDesc": None, "productPrice": None},
                        "not-a-dict",
                    ]
                }
            )
        ]
    )
    products = client.list_products()
    assert [p.product_id for p in products] == ["7"]
    assert products[0].product_desc is None
    assert products[0].price_as_decimal() is None


def test_validate_coupon_payload_and_subtotal(make_client):
    client, session = make_client(
        [
            FakeResponse(
                {
                    "err": "",
                    "errDesc": "",
                    "orderTotalPrice": 40.00,
                    "orderDiscountPrice": 8.00,
                    "status": "success",
                }
            )
        ]
    )
    result = client.validate_coupon("TESTFORALL", [{"productId": "0000001", "qty": "10"}])
    assert result.new_subtotal == 32.0
    payload = session.posts[0]["json"]
    assert payload["couponCode"] == "TESTFORALL"
    assert payload["act"] == "getdiscount"
    assert payload["productDetails"] == [{"productId": "0000001", "qty": "10"}]


def test_validate_coupon_requires_app_ver_and_dev_inf(config):
    bare = Config(api_key="k", aff_id="a")
    session = FakeSession([])
    with pytest.raises(ConfigError):
        WalgreensClient(bare, session=session).validate_coupon(
            "X", [{"productId": "1", "qty": "1"}]
        )
    assert session.posts == []


def test_find_stores_payload_and_no_promise_time(make_client):
    client, session = make_client(
        [
            FakeResponse(
                {
                    "status": "success",
                    "errCode": "",
                    "errDesc": "",
                    "photoStores": [
                        {
                            "photoStoreDetails": {
                                "storeNum": "211",
                                "promiseTime": "01-01-3000 00:00 AM",
                                "city": "Chicago",
                            }
                        },
                        {"photoStoreDetails": None},
                        {
                            "photoStoreDetails": {
                                "storeNum": "212",
                                "promiseTime": "03-02-2020 5:15 PM",
                            }
                        },
                    ],
                }
            )
        ]
    )
    stores = client.find_stores(41.88, -87.62, [{"productId": "1", "qty": "2"}])
    assert [s.store_num for s in stores] == ["211", "212"]
    assert stores[0].is_no_promise_time
    assert not stores[1].is_no_promise_time
    payload = session.posts[0]["json"]
    assert payload["latitude"] == "41.88" and payload["longitude"] == "-87.62"
    assert payload["act"] == "photoStores"


def test_submit_order_payload_and_terms_gate(make_client):
    client, session = make_client(
        [
            FakeResponse(
                {"vendorOrderId": "0000000001", "err": "", "errDesc": "", "status": "success"}
            )
        ]
    )
    with pytest.raises(ValueError, match="terms_accepted"):
        client.submit_order(
            first_name="A",
            last_name="B",
            phone="5555555555",
            email="a@example.test",
            store_num="211",
            promise_time="03-02-2020 5:15 PM",
            product_details=[
                OrderProduct("8420005", [ImageDetail("https://example.test/x.jpg", "1")])
            ],
        )
    assert session.posts == []
    result = client.submit_order(
        first_name="A",
        last_name="B",
        phone="5555555555",
        email="a@example.test",
        store_num="211",
        promise_time="03-02-2020 5:15 PM",
        product_details=[
            {
                "productId": "8420005",
                "imageDetails": [{"url": "https://example.test/x.jpg", "qty": "1"}],
            }
        ],
        coupon_code="TESTFORALL",
        terms_accepted=True,
    )
    assert result.vendor_order_id == "0000000001"
    payload = session.posts[0]["json"]
    assert payload["act"] == "submitphotoorder"
    assert payload["couponCode"] == "TESTFORALL"
    assert payload["productDetails"] == [
        {
            "productId": "8420005",
            "imageDetails": [{"qty": "1", "url": "https://example.test/x.jpg"}],
        }
    ]


def test_build_submit_payload_sends_nothing(make_client):
    client, session = make_client([])
    payload = client.build_submit_payload(
        first_name="A",
        last_name="B",
        phone="555",
        email="a@example.test",
        store_num="1",
        promise_time="03-02-2020 5:15 PM",
        product_details=[OrderProduct("1", [ImageDetail("https://example.test/x.jpg", "1")])],
    )
    assert payload["act"] == "submitphotoorder"
    assert session.posts == []


def test_submit_order_enforces_image_limits(make_client):
    client, session = make_client([])
    too_many = OrderProduct(
        "1", [ImageDetail(f"https://example.test/{i}.jpg", "1") for i in range(201)]
    )
    with pytest.raises(ValueError, match="at most 200"):
        client.submit_order(
            first_name="A",
            last_name="B",
            phone="555",
            email="a@example.test",
            store_num="1",
            promise_time="x",
            product_details=[too_many],
            terms_accepted=True,
        )
    too_many_qty = OrderProduct("1", [ImageDetail("https://example.test/x.jpg", "21")])
    with pytest.raises(ValueError, match="outside the API range"):
        client.submit_order(
            first_name="A",
            last_name="B",
            phone="555",
            email="a@example.test",
            store_num="1",
            promise_time="x",
            product_details=[too_many_qty],
            terms_accepted=True,
        )
    assert session.posts == []


def test_get_order_status_and_code_two_ambiguity(make_client):
    client, _ = make_client(
        [
            FakeResponse(
                {
                    "err": "",
                    "errDesc": "",
                    "statuses": [
                        {
                            "valid": "true",
                            "code": "2",
                            "orderId": "0000000001",
                            "orderStatus": "Downloaded",
                        },
                        {"valid": "false", "code": "", "orderId": "0000000003", "orderStatus": ""},
                    ],
                }
            )
        ]
    )
    entries = client.get_order_status(["0000000001", "0000000003"])
    assert entries[0].valid and entries[0].code == "2"
    # The raw orderStatus string is authoritative for code 2, which
    # the reference lists twice; it is not replaced by the combined map label.
    assert entries[0].status_label == "Downloaded"
    assert entries[0].order_status == "Downloaded"
    assert not entries[1].valid


def test_status_label_falls_back_to_code_map_when_no_string(make_client):
    client, _ = make_client(
        [
            FakeResponse(
                {"statuses": [{"valid": "true", "code": "3", "orderId": "1", "orderStatus": ""}]}
            )
        ]
    )
    assert client.get_order_status(["1"])[0].status_label == "Ready for Pickup"


def test_get_order_status_requires_ids(make_client):
    client, session = make_client([])
    with pytest.raises(ValueError):
        client.get_order_status([])
    assert session.posts == []


def test_api_error_fields_raise(make_client):
    client, _ = make_client([FakeResponse({"err": "E1", "errDesc": "Bad key", "status": "error"})])
    with pytest.raises(WalgreensApiError) as excinfo:
        client.list_products()
    assert excinfo.value.err_code == "E1"
    assert "Bad key" in str(excinfo.value)


def test_http_error_raises(make_client):
    client, _ = make_client([FakeResponse({"x": 1}, status_code=500)])
    with pytest.raises(WalgreensApiError) as excinfo:
        client.list_products()
    assert excinfo.value.status_code == 500


def test_rate_limit_is_flagged_throttled(make_client):
    client, _ = make_client([FakeResponse(None, status_code=429, headers={"Retry-After": "60"})])
    with pytest.raises(WalgreensApiError) as excinfo:
        client.list_products()
    assert excinfo.value.throttled
    assert excinfo.value.retry_after == 60


def test_non_json_and_non_object_raise(make_client):
    client, _ = make_client([FakeResponse(json_error=True)])
    with pytest.raises(WalgreensApiError, match="non-JSON"):
        client.list_products()
    client2, _ = make_client([FakeResponse(["not", "an", "object"])])
    with pytest.raises(WalgreensApiError, match="non-object"):
        client2.list_products()


def test_transport_error_wrapped(make_client, monkeypatch):
    client, session = make_client([])

    def boom(*args, **kwargs):
        raise requests.ConnectionError("down")

    session.post = boom
    with pytest.raises(WalgreensApiError, match="Request to"):
        client.list_products()


def test_context_manager_does_not_close_injected_session(config):
    session = FakeSession([FakeResponse({"products": []})])
    # Injected sessions belong to the caller; the client must not close them.
    client = WalgreensClient(config, session=session)
    with client:
        client.list_products()
    assert not session.closed
