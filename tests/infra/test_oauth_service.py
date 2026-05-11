from __future__ import annotations

import builtins
import importlib
import sys


def test_oauth_module_import_does_not_eagerly_load_authlib(monkeypatch) -> None:
    module_name = "src.infra.auth.oauth"
    sys.modules.pop(module_name, None)

    authlib_imports: list[str] = []
    original_import = builtins.__import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("authlib"):
            authlib_imports.append(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)

    oauth_module = importlib.import_module(module_name)

    assert oauth_module.OAuthService is not None
    assert authlib_imports == []


def test_apple_client_secret_is_generated_from_private_key_settings(monkeypatch) -> None:
    from src.infra.auth import oauth as oauth_module

    captured: dict[str, object] = {}

    def fake_encode(payload, key, algorithm=None, headers=None):
        captured["payload"] = payload
        captured["key"] = key
        captured["algorithm"] = algorithm
        captured["headers"] = headers
        return "apple-client-secret.jwt"

    monkeypatch.setattr(oauth_module.jwt, "encode", fake_encode)
    monkeypatch.setattr(oauth_module.settings, "OAUTH_APPLE_TEAM_ID", "TEAM123")
    monkeypatch.setattr(oauth_module.settings, "OAUTH_APPLE_KEY_ID", "KEY123")
    monkeypatch.setattr(oauth_module.settings, "OAUTH_APPLE_CLIENT_ID", "com.example.web")
    monkeypatch.setattr(
        oauth_module.settings,
        "OAUTH_APPLE_CLIENT_SECRET",
        "-----BEGIN PRIVATE KEY-----\\nkey\\n-----END PRIVATE KEY-----",
    )

    secret = oauth_module._build_apple_client_secret()

    assert secret == "apple-client-secret.jwt"
    assert captured["key"] == "-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----"
    assert captured["algorithm"] == "ES256"
    assert captured["headers"] == {"kid": "KEY123"}
    assert captured["payload"]["iss"] == "TEAM123"
    assert captured["payload"]["sub"] == "com.example.web"
    assert captured["payload"]["aud"] == "https://appleid.apple.com"
