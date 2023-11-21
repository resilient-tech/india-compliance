import hmac
from base64 import b64decode, b64encode
from hashlib import sha256

from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

import frappe
from frappe import _
from frappe.utils import now_datetime

BS = 16


def aes_encrypt_data(data: str, key: bytes | str) -> str:
    raw = pad(data.encode(), BS)

    if isinstance(key, str):
        key = key.encode()

    cipher = AES.new(key, AES.MODE_ECB)
    enc = cipher.encrypt(raw)

    return b64encode(enc).decode()


def aes_decrypt_data(encrypted: str, key: bytes | str) -> bytes:
    if isinstance(key, str):
        key = key.encode()

    encrypted = b64decode(encrypted)
    cipher = AES.new(key, AES.MODE_ECB)
    decrypted = unpad(cipher.decrypt(encrypted), BS)

    return decrypted


def hmac_sha256(data: str, key: bytes) -> str:
    hmac_value = hmac.new(key, data, sha256)
    return b64encode(hmac_value.digest()).decode()


def hash_sha256(data: bytes) -> str:
    return sha256(data).hexdigest()


def encrypt_using_public_key(data: str, certificate: bytes) -> str:
    if not data:
        return

    cert = x509.load_pem_x509_certificate(certificate, default_backend())

    valid_up_to = cert.not_valid_after
    if valid_up_to < now_datetime():
        frappe.throw(_("Public Certificate has expired"))

    public_key = cert.public_key()
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    key = RSA.importKey(pem)

    cipher = PKCS1_v1_5.new(key)
    if isinstance(data, str):
        data = data.encode()

    ciphertext = cipher.encrypt(data)

    return b64encode(ciphertext).decode()
