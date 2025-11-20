import pytest
import utils.telegram_operations as telegram_ops


def test_get_client_uses_sqlite_session_timeout(monkeypatch, tmp_path):
    calls = {}
    
    class DummySession:
        def __init__(self, path, timeout):
            calls["path"] = path
            calls["timeout"] = timeout
    
    class DummyClient:
        def __init__(self, session_obj, api_id, api_hash):
            self.session = session_obj
            self.api_id = api_id
            self.api_hash = api_hash
            calls["api_id"] = api_id
            calls["api_hash"] = api_hash
            calls["session_obj"] = session_obj
    
    monkeypatch.setattr(telegram_ops, "SESSION_PATH", str(tmp_path / "session"))
    monkeypatch.setattr(telegram_ops, "TimeoutSQLiteSession", DummySession)
    monkeypatch.setattr(telegram_ops, "TelegramClient", DummyClient)
    monkeypatch.setattr(telegram_ops, "client", None)
    
    client = telegram_ops.get_client()
    
    assert isinstance(client, DummyClient)
    assert calls["path"] == str(tmp_path / "session")
    assert calls["timeout"] == 15
    assert calls["session_obj"] is client.session
    assert calls["api_id"] == telegram_ops.API_ID
    assert calls["api_hash"] == telegram_ops.API_HASH
