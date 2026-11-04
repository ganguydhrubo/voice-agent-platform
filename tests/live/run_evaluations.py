"""Run every agent's saved tests through the running server and print each failure."""
import http.cookiejar
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf8")
BASE = "http://localhost:8000"
env = dict(line.split("=", 1) for line in Path(".env").read_text().splitlines() if "=" in line)
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(path, body=None, method=None):
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None),
        headers={"Content-Type": "application/json", "Origin": BASE},
        method=method,
    )
    return json.loads(opener.open(request, timeout=300).read())


call("/api/auth/login", {"email": env["VAP_ADMIN_EMAIL"], "password": env["VAP_ADMIN_PASSWORD"]})
agents = call("/api/admin/agents?page=1&size=100")["items"]
report = []
passed = total = 0
started = time.perf_counter()
for agent in agents:
    result = call(f"/api/admin/agents/{agent['id']}/evaluate", method="POST")
    passed += result["passed"]
    total += result["total"]
    report.append({"agent": agent["slug"], **result})
    print(f"{agent['slug']}: {result['passed']}/{result['total']}", flush=True)
    for item in result["results"]:
        if not item["passed"]:
            print(f"   FAIL [{item['language']}] {item['question']}\n        reply: {item['reply'][:160]}\n        {item['failures']}", flush=True)
print(f"TOTAL {passed}/{total} in {time.perf_counter() - started:.0f}s")
Path("benchmarks/results/evaluations.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf8")
