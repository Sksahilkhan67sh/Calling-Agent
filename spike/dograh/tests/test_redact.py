import json
from redact import (mask_phone, redact_url, redact_text, redact_headers, redact_obj,
                    redact_body, header_shape)

JWT_SAMPLE = "eyJ" + "a" * 10 + "." + "b" * 10 + "." + "c" * 10


def test_phone_keeps_cc_and_last_two():
    assert mask_phone("+919876543210") == "+91********10"
    assert mask_phone("+14155550123") == "+1********23"


def test_phone_in_text_and_non_phone_untouched():
    assert "+91********10" in redact_text("call +919876543210 now")
    assert redact_text("order 12345678 total 99") == "order 12345678 total 99"


def test_url_drops_query_and_token_segments():
    url = "https://h.example/api/v1/public/download/workflow/0f8fad5b-d9cb-469f-a165-70867728950e/recording?sig=abc&X-Amz-Signature=zzz"
    out = redact_url(url)
    assert out == "https://h.example/api/v1/public/download/workflow/<token>/recording"
    assert "sig" not in out and "Amz" not in out


def test_jwt_masked():
    assert JWT_SAMPLE not in redact_text(f"Bearer {JWT_SAMPLE}")


def test_headers_secret_masked_with_shape_only(monkeypatch):
    monkeypatch.setenv("DOGRAH_WEBHOOK_HEADER_NAME", "X-Dograh-Webhook-Secret")
    out = redact_headers({"Authorization": "Bearer abc", "X-Dograh-Webhook-Secret": "g" * 43,
                          "X-API-Key": "k", "User-Agent": "dograh/1"})
    assert out["Authorization"].startswith("***") and "abc" not in out["Authorization"]
    assert out["X-Dograh-Webhook-Secret"] == "*** (len=43 chars=base64url)"
    assert out["X-API-Key"].startswith("***")
    assert out["User-Agent"] == "dograh/1"


def test_obj_masks_sensitive_keys_and_nested_values():
    out = redact_obj({"public_access_token": "t", "n": {"phone": "+919876543210"}, "ok": 5})
    assert out["public_access_token"] == "***"
    assert out["n"]["phone"] == "+91********10"
    assert out["ok"] == 5


def test_body_json_and_non_json():
    assert json.loads(redact_body(b'{"secret":"x","a":"+919876543210"}'))["secret"] == "***"
    assert "+919876543210" not in redact_body(b"plain +919876543210")


def test_header_shape_hex_vs_mixed():
    assert header_shape("ab12") == "len=4 chars=hex"
    assert header_shape("a b") == "len=3 chars=mixed"
