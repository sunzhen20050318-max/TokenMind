from datetime import datetime

from sun_agent.session.manager import Session, SessionManager


def test_session_manager_roundtrip_preserves_timeline_events(tmp_path):
    manager = SessionManager(tmp_path)
    session = Session(
        key="web:test",
        messages=[
            {
                "role": "user",
                "content": "hello",
                "timestamp": datetime.now().isoformat(),
            }
        ],
        timeline_events=[
            {
                "id": "trace-1",
                "type": "progress",
                "content": "Thinking",
                "timestamp": datetime.now().isoformat(),
                "turnId": "turn-1",
            }
        ],
    )

    manager.save(session)
    manager.invalidate("web:test")

    loaded = manager.get_or_create("web:test")
    assert loaded.timeline_events == session.timeline_events


def test_session_clear_removes_timeline_events():
    session = Session(
        key="web:test",
        messages=[{"role": "user", "content": "hello"}],
        timeline_events=[{"id": "trace-1", "type": "progress", "content": "Thinking", "turnId": "turn-1"}],
    )

    session.clear()

    assert session.messages == []
    assert session.timeline_events == []
