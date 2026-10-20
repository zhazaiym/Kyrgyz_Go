from mysite.database.chat_models import ChatSession
from mysite.database.db import SessionLocal


def test_session_creation_respects_foreign_keys(client):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from main import app
    from mysite.database.db import Base, get_db

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def isolated_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = isolated_db
    try:
        token = register(client, "chat_foreign_keys")
        response = client.post("/chat/session", headers=bearer(token))
        assert response.status_code == 200
        history = client.get(
            f"/chat/history/{response.json()['session_id']}", headers=bearer(token)
        )
        assert history.status_code == 200
        assert [message["role"] for message in history.json()] == ["assistant"]
        assert history.json()[0]["content"] == response.json()["welcome"]
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def register(client, username):
    response = client.post(
        "/chat/auth/register",
        json={"username": username, "password": "StrongPassword123!"},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_chat_sessions_are_owned_by_the_authenticated_client(client):
    first_token = register(client, "chat_owner")
    second_token = register(client, "chat_other")

    created = client.post("/chat/session", headers=bearer(first_token))
    assert created.status_code == 200, created.text
    session_id = created.json()["session_id"]

    assert client.get(
        f"/chat/history/{session_id}", headers=bearer(first_token)
    ).status_code == 200
    assert client.get(
        f"/chat/history/{session_id}", headers=bearer(second_token)
    ).status_code == 404


def test_chat_logout_revokes_the_login_token(client):
    token = register(client, "chat_logout")
    assert client.get("/chat/auth/me", headers=bearer(token)).status_code == 200
    assert client.post("/chat/auth/logout", headers=bearer(token)).status_code == 200
    assert client.get("/chat/auth/me", headers=bearer(token)).status_code == 401


def test_booking_confirmation_is_idempotent(client):
    token = register(client, "chat_booking")
    session_response = client.post("/chat/session", headers=bearer(token))
    session_id = session_response.json()["session_id"]

    with SessionLocal() as db:
        session = db.get(ChatSession, session_id)
        session.state = {
            "client_name": "Booking User",
            "phone": "+996700000002",
            "people_count": 2,
            "travel_date": "2099-06-01",
            "destination": "Иссык-Куль",
        }
        session.stage = "awaiting_confirmation"
        session.revision = 1
        db.commit()

    payload = {"session_id": session_id, "revision": 1, "confirmed": True}
    first = client.post("/booking/confirm", json=payload, headers=bearer(token))
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "submitted"

    second = client.post("/booking/confirm", json=payload, headers=bearer(token))
    assert second.status_code == 200, second.text
    assert second.json() == {
        "status": "already_submitted",
        "request_id": first.json()["request_id"],
        "client_code": first.json()["client_code"],
    }


def test_websocket_authentication_accepts_owned_session(client):
    token = register(client, "chat_socket")
    created = client.post("/chat/session", headers=bearer(token))
    session_id = created.json()["session_id"]

    with client.websocket_connect(
        f"/ws/chat/{session_id}",
        headers={"origin": "http://localhost:3000"},
    ) as websocket:
        websocket.send_json({"type": "auth", "token": token})
        assert websocket.receive_json() == {
            "type": "connected",
            "session_id": session_id,
        }
