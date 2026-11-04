"""Show what the running server retrieves for a question."""
import http.cookiejar
import json
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf8")
BASE = "http://localhost:8000"
env = dict(line.split("=", 1) for line in Path(".env").read_text().splitlines() if "=" in line)
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(path, body=None):
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Origin": BASE},
    )
    return json.loads(opener.open(request, timeout=30).read())


call("/api/auth/login", {"email": env["VAP_ADMIN_EMAIL"], "password": env["VAP_ADMIN_PASSWORD"]})
bases = call("/api/admin/knowledge-bases?page=1&size=100")["items"]
base = next(item for item in bases if item["name"] == sys.argv[1])
for language, question in zip(sys.argv[2::2], sys.argv[3::2]):
    found = call(f"/api/admin/knowledge-bases/{base['id']}/search", {"query": question, "language": language})
    print(language, question, "confidence", found["confidence"])
    for hit in found["hits"]:
        print("   ", hit.get("language"), hit.get("section"), "|", hit["text"][:300].replace("\n", " / "))
