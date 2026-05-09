import sys
import types
from datetime import timezone


def test_mongo_client_reads_datetimes_as_utc_aware(monkeypatch):
    from src.infra.storage import mongodb

    captured: dict[str, object] = {}

    class FakeAsyncIOMotorClient:
        def __init__(self, connection_string: str, **kwargs: object) -> None:
            captured["connection_string"] = connection_string
            captured.update(kwargs)

    fake_motor = types.ModuleType("motor")
    fake_motor_asyncio = types.ModuleType("motor.motor_asyncio")
    fake_motor_asyncio.AsyncIOMotorClient = FakeAsyncIOMotorClient
    monkeypatch.setitem(sys.modules, "motor", fake_motor)
    monkeypatch.setitem(sys.modules, "motor.motor_asyncio", fake_motor_asyncio)
    monkeypatch.setattr(mongodb.settings, "MONGODB_URL", "mongodb://localhost:27017")
    monkeypatch.setattr(mongodb.settings, "MONGODB_USERNAME", "")
    monkeypatch.setattr(mongodb.settings, "MONGODB_PASSWORD", "")
    mongodb.get_mongo_client.cache_clear()

    try:
        mongodb.get_mongo_client()
    finally:
        mongodb.get_mongo_client.cache_clear()

    assert captured["tz_aware"] is True
    assert captured["tzinfo"] is timezone.utc
