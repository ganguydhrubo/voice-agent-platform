"""The WebSocket from start to end, in text mode with the scripted model."""
import json

from starlette.websockets import WebSocketDisconnect

ORIGIN = {"origin": "http://localhost:8000"}


def start(client, agent="healthcare", language="en", keep_history=True):
    body = {"agent": agent, "language": language, "mode": "text", "keep_history": keep_history}
    response = client.post("/api/public/conversations", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def opening(conversation, resume=False):
    return json.dumps({"type": "start", "id": conversation["id"], "token": conversation["token"], "mode": "text", "resume": resume})


def read_until(socket, kind, limit=60):
    seen = []
    for _ in range(limit):
        event = json.loads(socket.receive_text())
        seen.append(event)
        if event["type"] == kind:
            return event, seen
    raise AssertionError(f"{kind} not seen in {[event['type'] for event in seen]}")


def test_a_typed_conversation(client):
    conversation = start(client)
    with client.websocket_connect("/ws/voice", headers=ORIGIN) as socket:
        socket.send_text(opening(conversation))
        read_until(socket, "turn_end")  # the greeting
        socket.send_text(json.dumps({"type": "text", "text": "My father has chest pain"}))
        event, seen = read_until(socket, "turn_end")
        assert event["outcome"] == "escalate"
        assert any(item["type"] == "escalation" for item in seen)
        socket.send_text(json.dumps({"type": "end"}))
        read_until(socket, "ended")
    headers = {"authorization": f"Bearer {conversation['token']}"}
    messages = client.get(f"/api/public/conversations/{conversation['id']}/messages", headers=headers)
    assert sorted(item["role"] for item in messages.json()["messages"]) == ["assistant", "assistant", "user"]
    assert client.app.state.runtime.db.scalar("SELECT COUNT(*) FROM escalations") == 1


def test_no_transcript_when_the_caller_says_no(client):
    conversation = start(client, keep_history=False)
    with client.websocket_connect("/ws/voice", headers=ORIGIN) as socket:
        socket.send_text(opening(conversation))
        read_until(socket, "turn_end")
        socket.send_text(json.dumps({"type": "end"}))
        read_until(socket, "ended")
    assert client.app.state.runtime.db.scalar("SELECT COUNT(*) FROM messages") == 0


def test_a_wrong_token_is_refused(client):
    conversation = start(client)
    conversation["token"] = "x" * 40
    with client.websocket_connect("/ws/voice", headers=ORIGIN) as socket:
        socket.send_text(opening(conversation))
        assert json.loads(socket.receive_text())["code"] == "denied"


def test_another_site_cannot_open_the_socket(client):
    try:
        with client.websocket_connect("/ws/voice", headers={"origin": "https://evil.example"}) as socket:
            socket.receive_text()
    except WebSocketDisconnect as closed:
        assert closed.code == 4403
    else:
        raise AssertionError("the socket stayed open")


def test_a_dropped_connection_can_resume_without_a_second_greeting(client):
    conversation = start(client)
    with client.websocket_connect("/ws/voice", headers=ORIGIN) as socket:
        socket.send_text(opening(conversation))
        read_until(socket, "turn_end")
    with client.websocket_connect("/ws/voice", headers=ORIGIN) as socket:
        socket.send_text(opening(conversation, resume=True))
        event, seen = read_until(socket, "state")
        assert event["state"] == "listening"
        assert not any(item["type"] == "agent_text" for item in seen)


def test_an_ended_conversation_stays_closed(client):
    conversation = start(client)
    with client.websocket_connect("/ws/voice", headers=ORIGIN) as socket:
        socket.send_text(opening(conversation))
        read_until(socket, "turn_end")
        socket.send_text(json.dumps({"type": "end"}))
        read_until(socket, "ended")
    with client.websocket_connect("/ws/voice", headers=ORIGIN) as socket:
        socket.send_text(opening(conversation))
        assert json.loads(socket.receive_text())["code"] == "denied"


def test_a_caller_can_delete_their_conversation(client):
    conversation = start(client)
    with client.websocket_connect("/ws/voice", headers=ORIGIN) as socket:
        socket.send_text(opening(conversation))
        read_until(socket, "turn_end")
    headers = {"authorization": f"Bearer {conversation['token']}"}
    assert client.delete(f"/api/public/conversations/{conversation['id']}", headers=headers).status_code == 200
    assert client.get(f"/api/public/conversations/{conversation['id']}/messages", headers=headers).status_code == 404


def test_a_language_the_agent_does_not_offer_is_refused(client):
    response = client.post("/api/public/conversations", json={"agent": "healthcare", "language": "fr"})
    assert response.status_code == 422


def test_an_unknown_agent_is_refused(client):
    assert client.post("/api/public/conversations", json={"agent": "nobody", "language": "en"}).status_code == 404


def test_no_audio_is_kept_by_default(client):
    runtime = client.app.state.runtime
    assert runtime.db.one("SELECT audio_retention FROM tenants LIMIT 1")["audio_retention"] == "none"


def test_metrics_stay_private_behind_a_proxy(client):
    assert client.get("/metrics", headers={"cf-connecting-ip": "203.0.113.9"}).status_code == 404
    assert client.get("/metrics", headers={"x-forwarded-for": "203.0.113.9"}).status_code == 404
