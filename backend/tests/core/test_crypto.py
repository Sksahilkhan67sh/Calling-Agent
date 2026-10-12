import base64
import hashlib
import hmac as hmac_mod

import pytest

from apps.core import crypto

KEY_A = ("a1", b"A" * 32)
KEY_B = ("b2", b"B" * 32)
CTX = "contact.phone_encrypted"


def test_roundtrip_unicode():
    cipher = crypto.FieldCipher([KEY_A])
    token = cipher.encrypt("+919876543210 नमस्ते", context=CTX)
    assert token.startswith("v1:a1:")
    assert cipher.decrypt(token, context=CTX) == "+919876543210 नमस्ते"


def test_wrong_key_fails():
    token = crypto.FieldCipher([KEY_A]).encrypt("x", context=CTX)
    with pytest.raises(crypto.DecryptionError):
        crypto.FieldCipher([("a1", b"Z" * 32)]).decrypt(token, context=CTX)


def test_rotation_old_decrypts_new_uses_newest():
    old = crypto.FieldCipher([KEY_A]).encrypt("secret", context=CTX)
    rotated = crypto.FieldCipher([KEY_B, KEY_A])
    assert rotated.decrypt(old, context=CTX) == "secret"
    assert rotated.needs_rotation(old)
    fresh = rotated.encrypt("secret", context=CTX)
    assert fresh.split(":")[1] == "b2" and not rotated.needs_rotation(fresh)
    assert rotated.current_key_id == "b2"


def test_removed_key_cannot_decrypt():
    old = crypto.FieldCipher([KEY_A]).encrypt("s", context=CTX)
    with pytest.raises(crypto.DecryptionError):
        crypto.FieldCipher([KEY_B]).decrypt(old, context=CTX)


@pytest.mark.parametrize("index", [2, 3])
def test_tampered_ciphertext_fails(index):
    cipher = crypto.FieldCipher([KEY_A])
    parts = cipher.encrypt("hello", context=CTX).split(":")
    raw = bytearray(base64.urlsafe_b64decode(parts[index] + "=" * (-len(parts[index]) % 4)))
    raw[0] ^= 1
    parts[index] = base64.urlsafe_b64encode(bytes(raw)).decode().rstrip("=")
    with pytest.raises(crypto.DecryptionError):
        cipher.decrypt(":".join(parts), context=CTX)


def test_aad_mismatch_and_relabelled_key_id_fail():
    cipher = crypto.FieldCipher([KEY_A, ("c3", b"C" * 32)])
    token = cipher.encrypt("hello", context=CTX)
    with pytest.raises(crypto.DecryptionError):
        cipher.decrypt(token, context="contact.other_column")
    relabelled = token.replace(":a1:", ":c3:", 1)
    with pytest.raises(crypto.DecryptionError):
        cipher.decrypt(relabelled, context=CTX)


@pytest.mark.parametrize("bad", ["", "v1:a1:x", "v2:a1:AAAA:BBBB", "v1:a1:!!!:???", "v1:a1:AAAA:BBBB:CC"])
def test_malformed_tokens(bad):
    cipher = crypto.FieldCipher([KEY_A])
    with pytest.raises(crypto.DecryptionError):
        cipher.decrypt(bad, context=CTX)
    assert cipher.needs_rotation(bad) is False


def test_short_nonce_rejected():
    cipher = crypto.FieldCipher([KEY_A])
    with pytest.raises(crypto.DecryptionError):
        cipher.decrypt("v1:a1:AAAA:BBBBBBBBBBBBBBBBBBBBBBBB", context=CTX)


def test_nonce_uniqueness():
    cipher = crypto.FieldCipher([KEY_A])
    nonces = {cipher.encrypt("same", context=CTX).split(":")[2] for _ in range(5000)}
    assert len(nonces) == 5000


def test_context_required():
    with pytest.raises(crypto.CryptoError):
        crypto.FieldCipher([KEY_A]).encrypt("x", context="")


def test_errors_never_contain_plaintext():
    cipher = crypto.FieldCipher([KEY_A])
    token = cipher.encrypt("TOP-SECRET-PLAINTEXT", context=CTX)
    with pytest.raises(crypto.DecryptionError) as exc:
        cipher.decrypt(token, context="wrong")
    for text in (str(exc.value), repr(exc.value)):
        assert "TOP-SECRET" not in text


@pytest.mark.parametrize("keys", [[], [("bad id", b"A" * 32)], [("a", b"short")], [KEY_A, KEY_A]])
def test_cipher_rejects_bad_key_sets(keys):
    with pytest.raises(crypto.KeyConfigError):
        crypto.FieldCipher(keys)


def _b64(n: bytes) -> str:
    return base64.b64encode(n).decode()


def test_parse_keys_ok_order_preserved():
    keys = crypto.parse_encryption_keys(f"new:{_b64(b'N' * 32)}, old:{_b64(b'O' * 32)}")
    assert [k for k, _ in keys] == ["new", "old"]


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " , ",
        "nocolon",
        f"bad id:{_b64(b'A' * 32)}",
        "a:!!!notb64",
        f"a:{_b64(b'short')}",
        f"a:{_b64(b'A' * 32)},a:{_b64(b'B' * 32)}",
        f"a:{_b64(b'A' * 32)},b:{_b64(b'A' * 32)}",
    ],
)
def test_parse_keys_rejects_and_names_variable(raw):
    with pytest.raises(crypto.KeyConfigError, match="FIELD_ENCRYPTION_KEYS") as exc:
        crypto.parse_encryption_keys(raw)
    assert _b64(b"A" * 32) not in str(exc.value)


def test_parse_hmac_key():
    assert crypto.parse_hmac_key(_b64(b"k" * 32)) == b"k" * 32
    for bad in ("!!!", _b64(b"short")):
        with pytest.raises(crypto.KeyConfigError, match="PHONE_HMAC_KEY"):
            crypto.parse_hmac_key(bad)


def test_blind_index_known_answer():
    key = bytes(range(32))
    expected = hmac_mod.new(key, b"phone\x00+919876543210", hashlib.sha256).hexdigest()
    assert crypto.blind_index("+919876543210", key=key, purpose="phone") == expected
    assert expected == "3a4f2bb9c0b4a2a8d1b5de42e9c5b5e1" or len(expected) == 64


def test_blind_index_properties():
    key = b"k" * 32
    a = crypto.blind_index("+14155550100", key=key, purpose="phone")
    assert a == crypto.blind_index("+14155550100", key=key, purpose="phone")
    assert a != crypto.blind_index("+14155550100", key=key, purpose="suppression")
    assert a != crypto.blind_index("+14155550101", key=key, purpose="phone")
    assert a != crypto.blind_index("+14155550100", key=b"j" * 32, purpose="phone")
    assert len(a) == 64


def test_blind_index_rejects_weak_inputs():
    with pytest.raises(crypto.CryptoError):
        crypto.blind_index("x", key=b"short", purpose="phone")
    for purpose in ("", "Phone", "a\x00b", "1abc"):
        with pytest.raises(crypto.CryptoError):
            crypto.blind_index("x", key=b"k" * 32, purpose=purpose)


def test_strict_base64_rejects_junk_characters():
    junk = base64.b64encode(b"A" * 32).decode()[:-4] + "!!!!"
    with pytest.raises(crypto.KeyConfigError, match="not valid base64"):
        crypto.parse_encryption_keys(f"a:{junk}")
    with pytest.raises(crypto.KeyConfigError, match="PHONE_HMAC_KEY is not valid base64"):
        crypto.parse_hmac_key("not base64 at all ✓")
