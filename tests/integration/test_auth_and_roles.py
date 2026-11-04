"""Sessions, lockout, roles and validation."""
from tests.conftest import OWNER


def login(client, email=OWNER["email"], password=OWNER["password"]):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_wrong_password_is_a_plain_refusal(client):
    response = login(client, password="Wrong-Pass-2026")
    assert response.status_code == 401
    assert response.json()["detail"].endswith(".")


def test_an_unknown_user_gets_the_same_answer(client):
    known = login(client, password="Wrong-Pass-2026")
    unknown = login(client, email="nobody@example.test", password="Wrong-Pass-2026")
    assert known.status_code == unknown.status_code
    assert known.json() == unknown.json()


def test_repeated_failures_lock_the_account(client):
    for _ in range(5):
        login(client, password="Wrong-Pass-2026")
    assert login(client).status_code == 423


def test_me_is_empty_for_a_visitor_and_filled_after_log_in(client):
    assert client.get("/api/auth/me").json() == {"user": None}
    login(client)
    assert client.get("/api/auth/me").json()["user"]["role"] == "owner"


def test_log_out_ends_the_session(owner):
    assert owner.post("/api/auth/logout").status_code == 200
    assert owner.get("/api/admin/overview").status_code == 401


def test_session_cookie_is_protected(client):
    cookie = login(client).headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie


def test_new_password_must_differ(owner):
    body = {"current_password": OWNER["password"], "new_password": OWNER["password"]}
    assert owner.post("/api/auth/change-password", json=body).status_code in (400, 422)


def test_weak_passwords_are_refused(owner):
    body = {"current_password": OWNER["password"], "new_password": "short"}
    response = owner.post("/api/auth/change-password", json=body)
    assert response.status_code == 422
    assert response.json()["detail"].endswith(".")


def make_user(owner, role):
    email = f"{role}@example.test"
    password = "Fixture-Pass-2026!"
    body = {"full_name": f"{role} user", "email": email, "role": role, "password": password}
    response = owner.post("/api/admin/users", json=body)
    assert response.status_code == 200, response.text
    return email, password


def test_a_viewer_can_read_but_not_change(owner):
    email, password = make_user(owner, "viewer")
    owner.post("/api/auth/logout")
    assert login(owner, email, password).status_code == 200
    assert owner.get("/api/admin/conversations").status_code == 200
    assert owner.post("/api/admin/knowledge-bases", json={"name": "Nope"}).status_code == 403
    assert owner.get("/api/admin/users").status_code == 403


def test_an_editor_cannot_publish_or_manage_users(owner):
    email, password = make_user(owner, "editor")
    agent = owner.get("/api/admin/agents?size=100").json()["items"][0]
    owner.post("/api/auth/logout")
    assert login(owner, email, password).status_code == 200
    assert owner.post(f"/api/admin/agents/{agent['id']}/publish?published=false").status_code == 403
    assert owner.get("/api/admin/users").status_code == 403


def test_nobody_can_create_a_second_owner(owner):
    body = {"full_name": "Second", "email": "o2@example.test", "role": "owner", "password": "Fixture-Pass-2026!"}
    assert owner.post("/api/admin/users", json=body).status_code == 422


def test_a_duplicate_email_id_is_refused(owner):
    make_user(owner, "viewer")
    body = {"full_name": "Copy", "email": "viewer@example.test", "role": "viewer", "password": "Fixture-Pass-2026!"}
    assert owner.post("/api/admin/users", json=body).status_code == 409


def test_a_cross_site_write_is_refused(client):
    headers = {"origin": "https://evil.example"}
    assert client.post("/api/auth/login", json=OWNER, headers=headers).status_code == 403


def test_security_headers_are_set(client):
    headers = client.get("/api/health").headers
    assert "script-src 'self'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"


def test_the_password_never_appears_in_user_rows(owner):
    assert "password" not in owner.get("/api/admin/users").text.lower()
