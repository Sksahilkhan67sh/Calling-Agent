from cryptography.fernet import Fernet
from django.test import override_settings

from apps.core.crypto import decrypt, encrypt, phone_hmac


def test_roundtrip_and_ciphertext_hides_plaintext():
    token = encrypt("+14155550100")
    assert b"4155550100" not in token and decrypt(token) == "+14155550100"


def test_hmac_is_deterministic_and_keyed():
    assert phone_hmac("+14155550100") == phone_hmac("+14155550100") != phone_hmac("+14155550101")
    with override_settings(PHONE_HMAC_KEY=b"another-key"):
        other = phone_hmac("+14155550100")
    assert other != phone_hmac("+14155550100")


def test_key_rotation_old_tokens_still_decrypt():
    old = encrypt("secret")
    from django.conf import settings

    with override_settings(FIELD_ENCRYPTION_KEYS=[Fernet.generate_key().decode(), *settings.FIELD_ENCRYPTION_KEYS]):
        assert decrypt(old) == "secret"
        assert decrypt(encrypt("new")) == "new"
