from __future__ import annotations

import pytest

from src.infra.storage.s3.service import get_or_init_storage, get_storage_service, init_storage
from src.infra.storage.s3.types import S3Config, S3Provider
from src.kernel.config import settings


class _FakeBackend:
    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_get_or_init_storage_switches_to_local_when_s3_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    await init_storage(
        S3Config(
            provider=S3Provider.MINIO,
            endpoint_url="http://minio.example.test:9000",
            bucket_name="old-bucket",
        )
    )
    existing = get_storage_service()
    existing._backend = _FakeBackend()

    monkeypatch.setattr(settings, "S3_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path / "uploads"), raising=False)

    storage = await get_or_init_storage()

    assert storage.is_local
    assert storage._config.storage_path == str(tmp_path / "uploads")


@pytest.mark.asyncio
async def test_get_or_init_storage_treats_string_false_as_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    await init_storage(
        S3Config(
            provider=S3Provider.MINIO,
            endpoint_url="http://minio.example.test:9000",
            bucket_name="old-bucket",
        )
    )

    monkeypatch.setattr(settings, "S3_ENABLED", "false", raising=False)
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path / "uploads"), raising=False)

    storage = await get_or_init_storage()

    assert storage.is_local
