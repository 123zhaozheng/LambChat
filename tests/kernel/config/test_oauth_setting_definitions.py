from __future__ import annotations

from src.kernel.config.definitions import SETTING_DEFINITIONS


def test_github_oauth_secret_depends_on_github_enabled() -> None:
    assert SETTING_DEFINITIONS["OAUTH_GITHUB_CLIENT_SECRET"]["depends_on"] == "OAUTH_GITHUB_ENABLED"
