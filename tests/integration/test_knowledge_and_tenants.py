"""Knowledge upload, search and the wall between customers."""
from backend.db import new_id, now_iso

GUIDE = b"Parking\nThe car park is in the basement."


def base(owner, name="Test Base"):
    response = owner.post("/api/admin/knowledge-bases", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def upload(owner, kb, name, data):
    return owner.post(f"/api/admin/knowledge-bases/{kb}/documents", files={"file": (name, data)})


def test_upload_then_search(owner):
    kb = base(owner)
    assert upload(owner, kb, "guide.txt", GUIDE).status_code == 200
    found = owner.post(f"/api/admin/knowledge-bases/{kb}/search", json={"query": "parking basement"}).json()
    assert "basement" in found["hits"][0]["text"]


def test_faq_upload(owner):
    kb = base(owner)
    pairs = [{"question": "Do you open on Sunday?", "answer": "No, we close on Sunday."}]
    response = owner.post(f"/api/admin/knowledge-bases/{kb}/faqs", json={"title": "FAQs", "pairs": pairs})
    assert response.status_code == 200, response.text
    assert owner.get(f"/api/admin/knowledge-bases/{kb}/documents").json()["total"] == 1


def test_a_bad_file_is_refused_with_a_clear_message(owner):
    response = upload(owner, base(owner), "fake.pdf", b"not a pdf")
    assert response.status_code in (400, 422)
    assert response.json()["detail"].endswith(".")


def test_a_private_address_cannot_be_fetched(owner):
    kb = base(owner)
    response = owner.post(f"/api/admin/knowledge-bases/{kb}/urls", json={"url": "http://127.0.0.1:8000/metrics"})
    assert response.status_code in (400, 422)


def test_deleting_a_document_removes_it_from_search(owner):
    kb = base(owner)
    document = upload(owner, kb, "guide.txt", GUIDE).json()
    assert owner.delete(f"/api/admin/documents/{document['id']}").status_code == 200
    found = owner.post(f"/api/admin/knowledge-bases/{kb}/search", json={"query": "parking basement"}).json()
    assert found["hits"] == []


def second_tenant(client) -> tuple[str, str]:
    runtime = client.app.state.runtime
    tenant = new_id()
    runtime.db.execute(
        "INSERT INTO tenants (id, slug, name, created_at) VALUES (?, ?, ?, ?)", (tenant, "other", "Other", now_iso())
    )
    kb = runtime.knowledge.create_base(tenant, "Secret")["id"]
    runtime.knowledge.ingest_file(tenant, kb, "secret.txt", b"Secret plan\nThe launch code word is mango.")
    return tenant, kb


def test_one_customer_cannot_search_another(owner):
    tenant, kb = second_tenant(owner)
    assert owner.post(f"/api/admin/knowledge-bases/{kb}/search", json={"query": "launch code"}).status_code == 404
    runtime = owner.app.state.runtime
    mine = runtime.db.one("SELECT id FROM tenants WHERE id != ?", (tenant,))["id"]
    assert runtime.knowledge.search(mine, [kb], "launch code mango", "en").hits == []
    assert runtime.knowledge.search(tenant, [kb], "launch code mango", "en").hits


def test_one_customer_cannot_read_or_delete_another(owner):
    _, kb = second_tenant(owner)
    assert owner.get(f"/api/admin/knowledge-bases/{kb}/documents").status_code == 404
    assert owner.delete(f"/api/admin/knowledge-bases/{kb}").status_code == 404
    names = [item["name"] for item in owner.get("/api/admin/knowledge-bases?size=100").json()["items"]]
    assert "Secret" not in names
