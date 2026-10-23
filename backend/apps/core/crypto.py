import hashlib
import hmac

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings


def _fernet():
    return MultiFernet([Fernet(k) for k in settings.FIELD_ENCRYPTION_KEYS])


def encrypt(text):
    return _fernet().encrypt(text.encode())


def decrypt(token):
    return _fernet().decrypt(bytes(token)).decode()


def phone_hmac(e164):
    return hmac.new(settings.PHONE_HMAC_KEY, e164.encode(), hashlib.sha256).digest()
