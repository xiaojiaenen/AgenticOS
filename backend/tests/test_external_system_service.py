"""external_system_service 拆分后的单元测试。

覆盖：
- SecurityProcessor 的 HMAC/RSA 签名与 AES 加解密往返
- AuthInjector 的认证注入（api_key/bearer/basic/custom/jwt_login/oauth2 缓存路径）
- 路径模板解析（_resolve_path 的 {var} 替换）与参数类型转换（_cast_value）
- UserInputBlocker / ApprovalBlocker 阻塞协调器
- 门面兼容：``app.services.external_system_service`` re-export 的符号与子模块同源

所有用例均不发真实网络请求：OAuth/JWT 的网络刷新路径通过"缓存令牌仍有效"
短路，或用假对象替换。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac as hmac_mod
import json
from types import SimpleNamespace

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.core.encryption import encrypt
from app.services.external_system_service import (  # 门面兼容导入
    INTEGRATION_CATEGORIES,
    ApprovalBlocker,
    AuthInjector,
    ExternalSystemService,
    SecurityProcessor,
    UserInputBlocker,
    _cast_value,
    _current_session_id,
    _resolve_path,
    get_ext_user_id,
    register_external_tools,
    seed_preset_external_systems,
    set_ext_user_id,
)

# ── 测试夹具对象 ────────────────────────────────────────────────────────────


def make_system(**kw):
    """构建 AuthInjector/SecurityProcessor 所需的最小 system 假对象。"""
    defaults = dict(
        id=1,
        name="TestSystem",
        base_url="https://api.example.com",
        auth_type="bearer",
        headers_json="{}",
        advanced_auth_json="",
        jwt_login_url=None,
        jwt_refresh_url=None,
        jwt_request_body_template=None,
        jwt_refresh_body_template=None,
        jwt_response_token_path=None,
        jwt_response_expires_path=None,
        jwt_response_token_header=None,
        login_token_source=None,
        login_inject_mode=None,
        login_inject_header_name=None,
        oauth_token_url=None,
        oauth_client_id_encrypted=None,
        oauth_client_secret_encrypted=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def make_cred(**kw):
    """构建 AuthInjector 所需的最小凭据假对象。"""
    defaults = dict(
        id=1,
        user_id=1,
        system_id=1,
        connection_status="connected",
        credential_data_encrypted="",
        oauth_access_token_encrypted=None,
        oauth_refresh_token_encrypted=None,
        oauth_expires_at=None,
        cached_jwt_encrypted=None,
        jwt_expires_at=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def naive_utc_now_plus(seconds: int):
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=seconds)


# ── 门面兼容性：re-export 与子模块同源 ──────────────────────────────────────


def test_facade_reexports_are_submodule_objects():
    import app.services.external_systems.auth_injector as auth_injector_mod
    import app.services.external_systems.coordinators as coordinators_mod
    import app.services.external_systems.context as context_mod
    import app.services.external_systems.security_processor as security_mod
    import app.services.external_systems.service as service_mod
    import app.services.external_systems.tool_builder as tool_builder_mod

    assert AuthInjector is auth_injector_mod.AuthInjector
    assert SecurityProcessor is security_mod.SecurityProcessor
    assert ApprovalBlocker is coordinators_mod.ApprovalBlocker
    assert UserInputBlocker is coordinators_mod.UserInputBlocker
    assert set_ext_user_id is context_mod.set_ext_user_id
    assert get_ext_user_id is context_mod.get_ext_user_id
    assert _current_session_id is context_mod._current_session_id
    assert _resolve_path is tool_builder_mod._resolve_path
    assert _cast_value is tool_builder_mod._cast_value
    assert register_external_tools is tool_builder_mod.register_external_tools
    assert ExternalSystemService is service_mod.ExternalSystemService
    assert seed_preset_external_systems is __import__(
        "app.services.external_systems.presets", fromlist=["x"]
    ).seed_preset_external_systems


def test_facade_import_surface_matches_external_callers():
    """外部调用点（endpoints / agent 包 / db.session）使用的全部符号可从门面导入。"""
    from app.services.external_system_service import _current_session_id as _ctx
    from app.services.external_system_service import ApprovalBlocker as _ab
    from app.services.external_system_service import ExternalSystemService as _ess
    from app.services.external_system_service import UserInputBlocker as _uib
    from app.services.external_system_service import register_external_tools as _ret
    from app.services.external_system_service import seed_preset_external_systems as _seed
    from app.services.external_system_service import set_ext_user_id as _suid

    assert _ab is ApprovalBlocker and _uib is UserInputBlocker
    assert _ess is ExternalSystemService and _ret is register_external_tools
    assert _seed is seed_preset_external_systems and _suid is set_ext_user_id
    assert _ctx is _current_session_id
    assert isinstance(INTEGRATION_CATEGORIES, list) and len(INTEGRATION_CATEGORIES) == 10
    assert all({"key", "label", "icon"} == set(c) for c in INTEGRATION_CATEGORIES)


def test_context_user_id_roundtrip():
    set_ext_user_id(42)
    try:
        assert get_ext_user_id() == 42
    finally:
        set_ext_user_id(0)
    assert get_ext_user_id() == 0


# ── SecurityProcessor：HMAC / RSA / AES ─────────────────────────────────────


class TestSecurityProcessorHmac:
    def test_sign_hmac_sha256_matches_stdlib(self):
        expected = hmac_mod.new(b"s3cret", b"payload", hashlib.sha256).digest()
        assert SecurityProcessor.sign_hmac("payload", "s3cret", "hmac_sha256") == expected

    def test_sign_hmac_sha512(self):
        expected = hmac_mod.new(b"k", b"d", hashlib.sha512).digest()
        assert SecurityProcessor.sign_hmac("d", "k", "hmac_sha512") == expected

    def test_sign_hmac_md5(self):
        expected = hmac_mod.new(b"k", b"d", hashlib.md5).digest()
        assert SecurityProcessor.sign_hmac("d", "k", "hmac_md5") == expected

    def test_sign_hmac_unknown_algorithm_falls_back_to_sha256(self):
        expected = hmac_mod.new(b"k", b"d", hashlib.sha256).digest()
        assert SecurityProcessor.sign_hmac("d", "k", "hmac_unknown") == expected

    def test_sign_hmac_unicode_input(self):
        expected = hmac_mod.new("密钥".encode(), "数据".encode(), hashlib.sha256).digest()
        assert SecurityProcessor.sign_hmac("数据", "密钥", "hmac_sha256") == expected


class TestSecurityProcessorRsa:
    def _gen_private_pem(self) -> str:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        return key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("ascii")

    def _public_key(self, pem: str):
        return serialization.load_pem_private_key(pem.encode(), password=None).public_key()

    @pytest.mark.parametrize("algorithm,digest", [
        ("sha256_with_rsa", hashes.SHA256()),
        ("sha1_with_rsa", hashes.SHA1()),
        ("md5_with_rsa", hashes.MD5()),
    ])
    def test_sign_rsa_verify_roundtrip(self, algorithm, digest):
        pem = self._gen_private_pem()
        sig = SecurityProcessor.sign_rsa("hello", pem, algorithm)
        assert isinstance(sig, bytes)
        # 正确签名验证通过
        self._public_key(pem).verify(sig, b"hello", padding.PKCS1v15(), digest)

    def test_sign_rsa_unknown_algorithm_falls_back_to_sha256(self):
        pem = self._gen_private_pem()
        sig_default = SecurityProcessor.sign_rsa("hello", pem, "sha256_with_rsa")
        sig_unknown = SecurityProcessor.sign_rsa("hello", pem, "bogus_with_rsa")
        assert sig_default == sig_unknown

    def test_sign_rsa_rejects_tampered_data(self):
        pem = self._gen_private_pem()
        sig = SecurityProcessor.sign_rsa("hello", pem, "sha256_with_rsa")
        with pytest.raises(Exception):
            self._public_key(pem).verify(sig, b"tampered", padding.PKCS1v15(), hashes.SHA256())


class TestSecurityProcessorAes:
    @pytest.mark.parametrize("algorithm,key_len", [
        ("aes_128_cbc", 16),
        ("aes_256_cbc", 32),
        ("aes_ecb", 32),
        ("aes_128_ecb", 16),
        ("aes_256_gcm", 32),
    ])
    def test_aes_roundtrip(self, algorithm, key_len):
        key = "k" * key_len
        iv = "i" * 16
        plaintext = "你好，AgenticOS！hello world — roundtrip 测试"
        ct = SecurityProcessor.encrypt_aes(plaintext, key, iv, algorithm)
        assert isinstance(ct, bytes)
        assert SecurityProcessor.decrypt_aes(ct, key, iv, algorithm) == plaintext

    def test_aes_unknown_algorithm_uses_cbc(self):
        key = "k" * 16
        iv = "i" * 16
        ct_unknown = SecurityProcessor.encrypt_aes("data", key, iv, "aes_999_cbc")
        ct_cbc = SecurityProcessor.encrypt_aes("data", key, iv, "aes_128_cbc")
        assert ct_unknown == ct_cbc

    def test_aes_gcm_ciphertext_contains_tag(self):
        key = "k" * 32
        iv = "i" * 16
        ct = SecurityProcessor.encrypt_aes("data", key, iv, "aes_256_gcm")
        assert len(ct) > 16  # ciphertext + 16-byte tag

    def test_aes_cbc_tampered_ciphertext_fails(self):
        key = "k" * 16
        iv = "i" * 16
        ct = bytearray(SecurityProcessor.encrypt_aes("data", key, iv, "aes_128_cbc"))
        ct[0] ^= 0xFF
        with pytest.raises(Exception):
            SecurityProcessor.decrypt_aes(bytes(ct), key, iv, "aes_128_cbc")


# ── SecurityProcessor.process_request / process_response ───────────────────


class TestProcessRequest:
    def _sign_config(self, **over):
        cfg = {
            "sign": {
                "algorithm": "hmac_sha256",
                "secret": encrypt("topsecret"),
                "placement": "header",
                "field_name": "X-Signature",
                "content_template": "{timestamp}|{nonce}|{body}",
                "encoding": "base64",
            },
            "common": {
                "timestamp_field": "X-Ts",
                "timestamp_format": "epoch",
                "nonce_field": "X-Nonce",
                "nonce_length": 16,
            },
        }
        cfg.update(over)
        return cfg

    @pytest.mark.anyio
    async def test_hmac_header_signature_and_common_fields(self):
        system = make_system(advanced_auth_json=json.dumps(self._sign_config()))
        request = httpx.Request("POST", "https://api.example.com/x", content=b'{"a":1}')

        await SecurityProcessor.process_request(system, request)

        ts = request.headers["X-Ts"]
        nonce = request.headers["X-Nonce"]
        body_text = '{"a":1}'
        assert len(nonce) == 16  # nonce_length=16 → token_hex(8)
        expected_content = f"{ts}|{nonce}|{body_text}"
        expected_sig = base64.b64encode(
            hmac_mod.new(b"topsecret", expected_content.encode(), hashlib.sha256).digest()
        ).decode("ascii")
        assert request.headers["X-Signature"] == expected_sig
        assert request.content == b'{"a":1}'  # 未配置加密时 body 不变

    @pytest.mark.anyio
    async def test_hex_encoding_and_query_placement(self):
        cfg = self._sign_config()
        cfg["sign"]["encoding"] = "hex"
        cfg["sign"]["placement"] = "query"
        system = make_system(advanced_auth_json=json.dumps(cfg))
        request = httpx.Request("GET", "https://api.example.com/x")

        await SecurityProcessor.process_request(system, request)

        sig = request.url.params["X-Signature"]
        expected_content = f"{request.headers['X-Ts']}|{request.headers['X-Nonce']}|"
        expected = hmac_mod.new(
            b"topsecret", expected_content.encode(), hashlib.sha256
        ).hexdigest()
        assert sig == expected

    @pytest.mark.anyio
    async def test_no_advanced_auth_leaves_request_untouched(self):
        system = make_system(advanced_auth_json="")
        request = httpx.Request("GET", "https://api.example.com/x")
        await SecurityProcessor.process_request(system, request)
        assert "X-Signature" not in request.headers

    @pytest.mark.anyio
    async def test_body_encryption_roundtrip_via_process_response(self):
        key, iv = "k" * 16, "i" * 16
        cfg = {
            "request_encrypt": {
                "algorithm": "aes_128_cbc",
                "key": encrypt(key),
                "iv": encrypt(iv),
                "encoding": "base64",
                "scope": "body",
            },
        }
        system = make_system(advanced_auth_json=json.dumps(cfg))
        request = httpx.Request(
            "POST", "https://api.example.com/x",
            content=json.dumps({"msg": "机密"}).encode(),
        )

        await SecurityProcessor.process_request(system, request)

        assert request.headers["Content-Type"] == "application/json"
        # httpx.Request.content 只读，实际发送的 body 在替换后的 stream 里
        sent_body = b"".join(request.stream)
        wrapped = json.loads(sent_body)
        assert set(wrapped) == {"encrypted"}
        # 解密往返：还原出原始 body
        pt = SecurityProcessor.decrypt_aes(
            base64.b64decode(wrapped["encrypted"]), key, iv, "aes_128_cbc"
        )
        assert json.loads(pt) == {"msg": "机密"}


class TestProcessResponse:
    def test_decrypt_response_field(self):
        key, iv = "k" * 16, "i" * 16
        plaintext = json.dumps({"ok": True, "items": [1, 2]})
        ct_b64 = base64.b64encode(
            SecurityProcessor.encrypt_aes(plaintext, key, iv, "aes_128_cbc")
        ).decode("ascii")
        system = make_system(advanced_auth_json=json.dumps({
            "response_decrypt": {
                "algorithm": "aes_128_cbc",
                "key": encrypt(key),
                "iv": encrypt(iv),
                "encoding": "base64",
                "path": "data.payload",
            },
        }))
        response_text = json.dumps({"code": 0, "data": {"payload": ct_b64}})

        result = asyncio.run(SecurityProcessor.process_response(system, response_text))

        parsed = json.loads(result)
        assert parsed["code"] == 0  # 外层字段保留
        assert parsed["data"]["payload"] == {"ok": True, "items": [1, 2]}  # 密文字段被解密替换

    def test_no_decrypt_config_returns_text_unchanged(self):
        system = make_system(advanced_auth_json="")
        assert asyncio.run(SecurityProcessor.process_response(system, "plain")) == "plain"

    def test_non_json_response_returns_unchanged(self):
        system = make_system(advanced_auth_json=json.dumps({
            "response_decrypt": {"algorithm": "aes_128_cbc", "key": encrypt("k" * 16), "iv": encrypt("i" * 16), "path": "a"},
        }))
        assert asyncio.run(SecurityProcessor.process_response(system, "not-json")) == "not-json"

    def test_hex_encoding_decrypt(self):
        key, iv = "k" * 32, "i" * 16
        plaintext = '{"status":"done"}'
        ct_hex = SecurityProcessor.encrypt_aes(plaintext, key, iv, "aes_256_cbc").hex()
        system = make_system(advanced_auth_json=json.dumps({
            "response_decrypt": {
                "algorithm": "aes_256_cbc",
                "key": encrypt(key),
                "iv": encrypt(iv),
                "encoding": "hex",
                "path": "payload",
            },
        }))
        result = asyncio.run(SecurityProcessor.process_response(system, json.dumps({"payload": ct_hex})))
        assert json.loads(result)["payload"] == {"status": "done"}


# ── 路径模板解析与参数转换 ───────────────────────────────────────────────────


class TestResolvePath:
    def test_simple_var_substitution(self):
        assert _resolve_path("/spiders/{spider_id}/start", {"spider_id": 7}) == "/spiders/7/start"

    def test_multiple_vars(self):
        tpl = "/ws/v1/cluster/apps/{appId}/appattempts/{appAttemptId}/containers/{containerId}"
        params = {"appId": "app_1", "appAttemptId": "att_2", "containerId": "c_3"}
        assert _resolve_path(tpl, params) == "/ws/v1/cluster/apps/app_1/appattempts/att_2/containers/c_3"

    def test_missing_var_kept_as_is(self):
        assert _resolve_path("/users/{id}/posts/{post_id}", {"id": 9}) == "/users/9/posts/{post_id}"

    def test_no_template_vars(self):
        assert _resolve_path("/static/path", {}) == "/static/path"

    def test_non_string_values_are_cast_to_str(self):
        assert _resolve_path("/items/{n}", {"n": True}) == "/items/True"


class TestCastValue:
    @pytest.mark.parametrize("raw,expected", [("3", 3), (7, 7), ("0", 0)])
    def test_integer(self, raw, expected):
        assert _cast_value(raw, "integer") == expected

    @pytest.mark.parametrize("raw,expected", [
        ("true", True), ("1", True), ("yes", True), (True, True),
        ("false", False), ("0", False), ("no", False), ("", False),
    ])
    def test_boolean(self, raw, expected):
        assert _cast_value(raw, "boolean") is expected

    def test_object_from_json_string(self):
        assert _cast_value('{"a": 1}', "object") == {"a": 1}

    def test_object_passthrough(self):
        assert _cast_value({"a": 1}, "object") == {"a": 1}

    def test_string_default(self):
        assert _cast_value(12, "string") == "12"

    def test_none_passthrough(self):
        assert _cast_value(None, "integer") is None


# ── AuthInjector ────────────────────────────────────────────────────────────


class TestAuthInjectorGuards:
    @pytest.mark.anyio
    async def test_missing_credential_raises(self):
        system = make_system(name="OpenSpider")
        with pytest.raises(ValueError, match="请先连接"):
            await AuthInjector.inject(system, None, httpx.Request("GET", "https://x"))

    @pytest.mark.anyio
    async def test_expired_credential_raises(self):
        system = make_system(name="OpenSpider")
        cred = make_cred(connection_status="expired")
        with pytest.raises(ValueError, match="连接已过期"):
            await AuthInjector.inject(system, cred, httpx.Request("GET", "https://x"))

    @pytest.mark.anyio
    async def test_auth_error_credential_raises(self):
        system = make_system(name="OpenSpider")
        cred = make_cred(connection_status="auth_error")
        with pytest.raises(ValueError, match="凭据无效"):
            await AuthInjector.inject(system, cred, httpx.Request("GET", "https://x"))


class TestAuthInjectorStaticAuth:
    @pytest.mark.anyio
    async def test_api_key_header_injection(self):
        system = make_system(auth_type="api_key")
        cred = make_cred(credential_data_encrypted=encrypt(json.dumps({
            "key": "k-123", "inject_in": "header", "header_name": "X-API-Key",
        })))
        request = httpx.Request("GET", "https://api.example.com/x")
        await AuthInjector.inject(system, cred, request)
        assert request.headers["X-API-Key"] == "k-123"

    @pytest.mark.anyio
    async def test_api_key_query_injection(self):
        system = make_system(auth_type="api_key")
        cred = make_cred(credential_data_encrypted=encrypt(json.dumps({
            "key": "k-123", "inject_in": "query", "param_name": "api_key",
        })))
        request = httpx.Request("GET", "https://api.example.com/x")
        await AuthInjector.inject(system, cred, request)
        assert request.url.params["api_key"] == "k-123"

    @pytest.mark.anyio
    async def test_bearer_injection(self):
        system = make_system(auth_type="bearer")
        cred = make_cred(credential_data_encrypted=encrypt(json.dumps({"token": "tok-1"})))
        request = httpx.Request("GET", "https://api.example.com/x")
        await AuthInjector.inject(system, cred, request)
        assert request.headers["Authorization"] == "Bearer tok-1"

    @pytest.mark.anyio
    async def test_basic_injection(self):
        system = make_system(auth_type="basic")
        cred = make_cred(credential_data_encrypted=encrypt(json.dumps(
            {"username": "u", "password": "p"}
        )))
        request = httpx.Request("GET", "https://api.example.com/x")
        await AuthInjector.inject(system, cred, request)
        assert request.headers["Authorization"] == "Basic " + base64.b64encode(b"u:p").decode()

    @pytest.mark.anyio
    async def test_custom_headers_injection(self):
        system = make_system(auth_type="custom")
        cred = make_cred(credential_data_encrypted=encrypt(json.dumps({
            "headers": {"X-One": "1", "X-Two": "2"},
        })))
        request = httpx.Request("GET", "https://api.example.com/x")
        await AuthInjector.inject(system, cred, request)
        assert request.headers["X-One"] == "1"
        assert request.headers["X-Two"] == "2"

    @pytest.mark.anyio
    async def test_system_fixed_headers_always_injected(self):
        system = make_system(auth_type="bearer", headers_json=json.dumps({"X-Tenant": "acme"}))
        cred = make_cred(credential_data_encrypted=encrypt(json.dumps({"token": "t"})))
        request = httpx.Request("GET", "https://api.example.com/x")
        await AuthInjector.inject(system, cred, request)
        assert request.headers["X-Tenant"] == "acme"
        assert request.headers["Authorization"] == "Bearer t"


class TestAuthInjectorJwtLogin:
    @pytest.mark.anyio
    async def test_cached_jwt_with_explicit_header_inject_mode(self):
        """缓存 JWT 仍有效 → 直接注入，不发网络请求。"""
        system = make_system(
            auth_type="jwt_login",
            login_inject_mode="header",
            login_inject_header_name="X-Auth-Token",
        )
        cred = make_cred(cached_jwt_encrypted=encrypt("jwt-tok"), jwt_expires_at=naive_utc_now_plus(3600))
        request = httpx.Request("GET", "https://api.example.com/x")
        await AuthInjector.inject(system, cred, request)
        assert request.headers["X-Auth-Token"] == "jwt-tok"

    @pytest.mark.anyio
    async def test_cached_jwt_default_bearer_inject_mode(self):
        """未配置 login_inject_mode 且无 jwt_response_token_header → 默认 Bearer。"""
        system = make_system(auth_type="jwt_login")
        cred = make_cred(cached_jwt_encrypted=encrypt("jwt-tok"), jwt_expires_at=naive_utc_now_plus(3600))
        request = httpx.Request("GET", "https://api.example.com/x")
        await AuthInjector.inject(system, cred, request)
        assert request.headers["Authorization"] == "Bearer jwt-tok"

    @pytest.mark.anyio
    async def test_legacy_jwt_response_token_header_implies_header_mode(self):
        """仅配置了 jwt_response_token_header（无 login_inject_mode）→ header 模式。"""
        system = make_system(auth_type="jwt_login", jwt_response_token_header="X-Token")
        cred = make_cred(cached_jwt_encrypted=encrypt("legacy-tok"), jwt_expires_at=naive_utc_now_plus(3600))
        request = httpx.Request("GET", "https://api.example.com/x")
        await AuthInjector.inject(system, cred, request)
        assert request.headers["X-Token"] == "legacy-tok"


class TestAuthInjectorOAuth2:
    @pytest.mark.anyio
    async def test_cached_access_token_used_without_network(self):
        """缓存 access token 仍在有效期（60s buffer 之外）→ 不发起刷新请求。"""
        system = make_system(auth_type="oauth2")
        cred = make_cred(
            oauth_access_token_encrypted=encrypt("oa-tok"),
            oauth_expires_at=naive_utc_now_plus(3600),
        )
        request = httpx.Request("GET", "https://api.example.com/x")
        await AuthInjector.inject(system, cred, request)
        assert request.headers["Authorization"] == "Bearer oa-tok"

    @pytest.mark.anyio
    async def test_expired_without_refresh_token_marks_credential_expired(self):
        system = make_system(auth_type="oauth2", name="Dinky")
        cred = make_cred(
            oauth_access_token_encrypted=None,
            oauth_expires_at=naive_utc_now_plus(-7200),  # 已过期
            oauth_refresh_token_encrypted="",            # 无 refresh token
        )
        request = httpx.Request("GET", "https://api.example.com/x")
        with pytest.raises(ValueError, match="连接已过期"):
            await AuthInjector.inject(system, cred, request)
        assert cred.connection_status == "expired"


# ── 阻塞协调器 ──────────────────────────────────────────────────────────────


class TestUserInputBlocker:
    @pytest.mark.anyio
    async def test_request_input_resolved_by_user_values(self):
        q = UserInputBlocker.subscribe("sess-ui-1")
        try:
            task = asyncio.create_task(
                UserInputBlocker.request_input("sess-ui-1", {"type": "user_input_required"})
            )
            payload = await asyncio.wait_for(q.get(), timeout=2)
            assert payload["type"] == "user_input_required"
            UserInputBlocker.resolve("sess-ui-1", {"token": "abc"})
            assert await asyncio.wait_for(task, timeout=2) == {"token": "abc"}
        finally:
            UserInputBlocker.unsubscribe("sess-ui-1")

    def test_resolve_without_pending_request_is_noop(self):
        UserInputBlocker.resolve("sess-ui-none", {"a": 1})  # 不应抛异常

    @pytest.mark.anyio
    async def test_unsubscribe_cleans_state(self):
        q = UserInputBlocker.subscribe("sess-ui-2")
        UserInputBlocker.unsubscribe("sess-ui-2")
        assert "sess-ui-2" not in UserInputBlocker._queues
        assert "sess-ui-2" not in UserInputBlocker._futures


class TestApprovalBlocker:
    @pytest.mark.anyio
    async def test_approval_approved(self):
        q = ApprovalBlocker.subscribe("sess-ap-1")
        try:
            task = asyncio.create_task(
                ApprovalBlocker.request_approval("sess-ap-1", {"system_name": "Sys", "api_name": "op"})
            )
            await asyncio.wait_for(q.get(), timeout=2)
            ApprovalBlocker.resolve("sess-ap-1", {"approved": True})
            assert await asyncio.wait_for(task, timeout=2) is True
        finally:
            ApprovalBlocker.unsubscribe("sess-ap-1")

    @pytest.mark.anyio
    async def test_approval_rejected(self):
        q = ApprovalBlocker.subscribe("sess-ap-2")
        try:
            task = asyncio.create_task(
                ApprovalBlocker.request_approval("sess-ap-2", {"system_name": "Sys"})
            )
            await asyncio.wait_for(q.get(), timeout=2)
            ApprovalBlocker.resolve("sess-ap-2", {"approved": False})
            assert await asyncio.wait_for(task, timeout=2) is False
        finally:
            ApprovalBlocker.unsubscribe("sess-ap-2")

    @pytest.mark.anyio
    async def test_allow_all_skips_future_approval(self):
        try:
            assert ApprovalBlocker.is_allowed("sess-ap-3", "Sys") is False
            ApprovalBlocker.allow_all("sess-ap-3", "Sys")
            # 已全部允许 → 不再阻塞，直接返回 True
            assert await asyncio.wait_for(
                ApprovalBlocker.request_approval("sess-ap-3", {"system_name": "Sys"}), timeout=2
            ) is True
            assert ApprovalBlocker.is_allowed("sess-ap-3", "Sys") is True
        finally:
            ApprovalBlocker.unsubscribe("sess-ap-3")

    @pytest.mark.anyio
    async def test_allow_all_scoped_per_system(self):
        """allow_all 只对 (session, system) 生效：未允许的系统仍走正常审批队列。"""
        q = ApprovalBlocker.subscribe("sess-ap-4")
        try:
            ApprovalBlocker.allow_all("sess-ap-4", "SysA")
            assert ApprovalBlocker.is_allowed("sess-ap-4", "SysB") is False
            task = asyncio.create_task(
                ApprovalBlocker.request_approval("sess-ap-4", {"system_name": "SysB"})
            )
            await asyncio.wait_for(q.get(), timeout=2)  # SysB 进入审批等待，而非直接放行
            ApprovalBlocker.resolve("sess-ap-4", {"approved": False})
            assert await asyncio.wait_for(task, timeout=2) is False
        finally:
            ApprovalBlocker.unsubscribe("sess-ap-4")


# ── Redis 缓存序列化（不依赖真实 Redis） ────────────────────────────────────


class TestCacheSerialization:
    def _fake_system(self):
        from app.services.external_systems.cache import _CACHE_FIELDS

        data = {f: "" for f in _CACHE_FIELDS}
        data.update({
            "id": 7,
            "name": "HDFS",
            "base_url": "http://nn:9870",
            "auth_type": "bearer",
            "headers_json": "{}",
            "default_credential_data_encrypted": "enc",
        })
        return SimpleNamespace(**data)

    def test_cache_key_format(self):
        from app.services.external_systems.cache import _system_cache_key

        assert _system_cache_key(7) == "agenticos:ext_system:7"
        assert _system_cache_key(42) == "agenticos:ext_system:42"

    def test_serialize_and_cached_proxy_roundtrip(self):
        from app.services.external_systems.cache import (
            _CACHE_FIELDS,
            _CachedSystem,
            _serialize_system_for_cache,
        )

        sys = self._fake_system()
        data = _serialize_system_for_cache(sys)
        assert set(data) == set(_CACHE_FIELDS)
        cached = _CachedSystem(data)
        assert cached.id == 7  # id 恢复为 int
        assert cached.name == "HDFS"
        assert cached.headers_json == "{}"  # 非空字符串保留
        for f in _CACHE_FIELDS:
            if f == "id":
                continue
            expected = str(getattr(sys, f)) if getattr(sys, f) is not None else ""
            assert (getattr(cached, f) or "") == expected

    def test_cached_system_empty_field_becomes_none(self):
        from app.services.external_systems.cache import _CachedSystem

        cached = _CachedSystem({"id": "3"})
        assert cached.id == 3
        assert cached.name is None  # 空字符串恢复为 None
