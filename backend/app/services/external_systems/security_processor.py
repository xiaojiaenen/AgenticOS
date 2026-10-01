"""SecurityProcessor：请求签名（HMAC/RSA）、请求加密与响应解密（AES）。"""

from __future__ import annotations

import base64
import hmac
import json

import httpx

from app.core.encryption import decrypt_safe
from app.db.models import ExternalSystemModel
from app.services.external_systems.serializers import _extract_nested, _naive_utc_now

# ── Security Processor (signing / encryption) ──────────────────────────────


class SecurityProcessor:
    """Handle request signing, request encryption, and response decryption."""

    @staticmethod
    def sign_hmac(data: str, secret: str, algorithm: str) -> str:
        """HMAC signing: hmac_sha256, hmac_sha512, hmac_md5."""
        algo_map = {"hmac_sha256": "sha256", "hmac_sha512": "sha512", "hmac_md5": "md5"}
        hash_name = algo_map.get(algorithm, "sha256")
        sig = hmac.new(secret.encode("utf-8"), data.encode("utf-8"), getattr(__import__("hashlib", fromlist=[hash_name]), hash_name)).digest()
        return sig

    @staticmethod
    def sign_rsa(data: str, private_key_pem: str, algorithm: str) -> bytes:
        """RSA signing: sha256_with_rsa, sha1_with_rsa, md5_with_rsa."""
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        hash_algo_map = {
            "sha256_with_rsa": hashes.SHA256(),
            "sha1_with_rsa": hashes.SHA1(),
            "md5_with_rsa": hashes.MD5(),
        }
        hash_algo = hash_algo_map.get(algorithm, hashes.SHA256())

        key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
        sig = key.sign(data.encode("utf-8"), padding.PKCS1v15(), hash_algo)
        return sig

    @staticmethod
    def encrypt_aes(plaintext: str, key: str, iv: str, algorithm: str) -> bytes:
        """AES encryption: aes_128_cbc, aes_256_cbc, aes_256_gcm, aes_ecb."""
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as sym_padding

        key_bytes = key.encode("utf-8")
        data = plaintext.encode("utf-8")

        if algorithm == "aes_ecb" or algorithm == "aes_128_ecb":
            cipher = Cipher(algorithms.AES(key_bytes), modes.ECB())
            padder = sym_padding.PKCS7(128).padder()
            data = padder.update(data) + padder.finalize()
        elif algorithm == "aes_256_gcm":
            iv_bytes = iv.encode("utf-8")[:12]
            cipher = Cipher(algorithms.AES(key_bytes), modes.GCM(iv_bytes))
            encryptor = cipher.encryptor()
            return encryptor.update(data) + encryptor.finalize() + encryptor.tag
        else:
            iv_bytes = iv.encode("utf-8")[:16]
            cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes))
            padder = sym_padding.PKCS7(128).padder()
            data = padder.update(data) + padder.finalize()

        encryptor = cipher.encryptor()
        return encryptor.update(data) + encryptor.finalize()

    @staticmethod
    def decrypt_aes(ciphertext: bytes, key: str, iv: str, algorithm: str) -> str:
        """AES decryption."""
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as sym_padding

        key_bytes = key.encode("utf-8")

        if algorithm == "aes_ecb" or algorithm == "aes_128_ecb":
            cipher = Cipher(algorithms.AES(key_bytes), modes.ECB())
            decryptor = cipher.decryptor()
            data = decryptor.update(ciphertext) + decryptor.finalize()
            unpadder = sym_padding.PKCS7(128).unpadder()
            data = unpadder.update(data) + unpadder.finalize()
            return data.decode("utf-8")
        elif algorithm == "aes_256_gcm":
            iv_bytes = iv.encode("utf-8")[:12]
            tag = ciphertext[-16:]
            ct = ciphertext[:-16]
            cipher = Cipher(algorithms.AES(key_bytes), modes.GCM(iv_bytes, tag))
            decryptor = cipher.decryptor()
            return (decryptor.update(ct) + decryptor.finalize()).decode("utf-8")
        else:
            iv_bytes = iv.encode("utf-8")[:16]
            cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes))
            decryptor = cipher.decryptor()
            data = decryptor.update(ciphertext) + decryptor.finalize()
            unpadder = sym_padding.PKCS7(128).unpadder()
            data = unpadder.update(data) + unpadder.finalize()
            return data.decode("utf-8")

    @classmethod
    async def process_request(cls, system: ExternalSystemModel, request: httpx.Request) -> None:
        """Apply signing and encryption to the outgoing request."""
        try:
            aa = json.loads(system.advanced_auth_json) if system.advanced_auth_json else {}
        except (json.JSONDecodeError, TypeError):
            return

        sign_cfg = aa.get("sign", {})
        enc_cfg = aa.get("request_encrypt", {})
        common_cfg = aa.get("common", {})

        algorithm = sign_cfg.get("algorithm", "none")
        if algorithm == "none" and enc_cfg.get("algorithm", "none") == "none":
            return

        # Generate timestamp + nonce
        now = _naive_utc_now()
        timestamp = ""
        nonce = ""
        ts_field = common_cfg.get("timestamp_field", "")
        nonce_field = common_cfg.get("nonce_field", "")

        if ts_field:
            if common_cfg.get("timestamp_format") == "iso8601":
                timestamp = now.isoformat()
            else:
                timestamp = str(int(now.timestamp()))

        if nonce_field:
            import secrets
            length = common_cfg.get("nonce_length", 16)
            nonce = secrets.token_hex(length // 2)

        # ── Signing ──
        if algorithm != "none":
            secret = decrypt_safe(sign_cfg.get("secret", ""))
            placement = sign_cfg.get("placement", "header")
            field_name = sign_cfg.get("field_name", "X-Signature")
            content_template = sign_cfg.get("content_template", "{body}")
            encoding = sign_cfg.get("encoding", "base64")

            body_text = ""
            if request.content:
                body_text = request.content.decode("utf-8", errors="replace")

            sign_content = content_template.replace("{timestamp}", timestamp).replace("{nonce}", nonce).replace("{body}", body_text)

            if algorithm.startswith("hmac"):
                raw_sig = cls.sign_hmac(sign_content, secret, algorithm)
            else:
                raw_sig = cls.sign_rsa(sign_content, secret, algorithm)

            if encoding == "hex":
                sig_str = raw_sig.hex()
            else:
                sig_str = base64.b64encode(raw_sig).decode("ascii")

            if placement == "header":
                request.headers[field_name] = sig_str
            elif placement == "query":
                url = str(request.url)
                sep = "&" if "?" in url else "?"
                request.url = httpx.URL(f"{url}{sep}{field_name}={sig_str}")
            elif placement == "body":
                # For body placement, we'd need to modify the body — skip for now
                pass

        # ── Request Encryption ──
        enc_algorithm = enc_cfg.get("algorithm", "none")
        if enc_algorithm != "none" and request.content:
            enc_key = decrypt_safe(enc_cfg.get("key", ""))
            enc_iv = decrypt_safe(enc_cfg.get("iv", ""))
            encoding = enc_cfg.get("encoding", "base64")

            plaintext = request.content.decode("utf-8", errors="replace")
            encrypted = cls.encrypt_aes(plaintext, enc_key, enc_iv, enc_algorithm)

            if encoding == "hex":
                result = encrypted.hex()
            else:
                result = base64.b64encode(encrypted).decode("ascii")

            scope = enc_cfg.get("scope", "body")
            if scope == "body":
                # httpx.Request.content 是只读属性，直接赋值会抛 AttributeError；
                # 替换请求体的正确方式是重建 stream（借一个新 Request 的流）
                request.headers["Content-Type"] = "application/json"
                rebuilt = httpx.Request(
                    method=request.method,
                    url=request.url,
                    headers=request.headers,
                    content=json.dumps({"encrypted": result}).encode("utf-8"),
                )
                request.stream = rebuilt.stream

        # Add common fields to headers
        if ts_field and timestamp:
            request.headers[ts_field] = timestamp
        if nonce_field and nonce:
            request.headers[nonce_field] = nonce

    @classmethod
    async def process_response(cls, system: ExternalSystemModel, response_text: str) -> str:
        """Decrypt response if configured."""
        try:
            aa = json.loads(system.advanced_auth_json) if system.advanced_auth_json else {}
        except (json.JSONDecodeError, TypeError):
            return response_text

        dec_cfg = aa.get("response_decrypt", {})
        dec_algorithm = dec_cfg.get("algorithm", "none")
        if dec_algorithm == "none":
            return response_text

        try:
            resp_json = json.loads(response_text)
        except (json.JSONDecodeError, TypeError):
            return response_text

        path = dec_cfg.get("path", "")
        if not path:
            return response_text

        ciphertext_b64 = _extract_nested(resp_json, path)
        if not ciphertext_b64:
            return response_text

        dec_key = decrypt_safe(dec_cfg.get("key", ""))
        dec_iv = decrypt_safe(dec_cfg.get("iv", ""))
        encoding = dec_cfg.get("encoding", "base64")

        try:
            if encoding == "hex":
                ct_bytes = bytes.fromhex(str(ciphertext_b64))
            else:
                ct_bytes = base64.b64decode(str(ciphertext_b64))

            plaintext = cls.decrypt_aes(ct_bytes, dec_key, dec_iv, dec_algorithm)

            # Replace the encrypted field with decrypted content
            keys = path.split(".")
            current = resp_json
            for key in keys[:-1]:
                current = current.get(key, {})
            current[keys[-1]] = json.loads(plaintext) if plaintext.startswith(("{", "[")) else plaintext
            return json.dumps(resp_json, ensure_ascii=False)
        except Exception:
            return response_text
