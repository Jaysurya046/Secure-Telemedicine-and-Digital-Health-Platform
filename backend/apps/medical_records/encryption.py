"""Small encryption helpers for medical file workflows."""
import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet_key():
    digest = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_bytes(payload):
    return Fernet(_fernet_key()).encrypt(payload)


def decrypt_bytes(payload):
    return Fernet(_fernet_key()).decrypt(payload)


def sha256_file(file_obj):
    position = file_obj.tell()
    file_obj.seek(0)
    digest = hashlib.sha256()
    for chunk in iter(lambda: file_obj.read(8192), b''):
        digest.update(chunk)
    file_obj.seek(position)
    return digest.hexdigest()
