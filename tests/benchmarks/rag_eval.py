"""Calibrate retrieval confidence on answerable and unanswerable questions, on the running server.

The knowledge is the Sample City Hospital guide. Results go to benchmarks/results/rag_eval.json.
"""
import http.cookiejar
import json
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf8")
BASE = "http://localhost:8000"
env = dict(line.split("=", 1) for line in Path(".env").read_text().splitlines() if "=" in line)
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

ANSWERABLE = [
    ("en", "What are the visiting hours?", "4 pm"),
    ("en", "Where is the pharmacy?", "pharmacy"),
    ("en", "What are the OPD timings?", "9 am"),
    ("en", "How do I book an appointment?", "5550 1234"),
    ("en", "Is the outpatient department open on Sunday?", "Sundays"),
    ("en", "Do you take credit cards?", "credit"),
    ("en", "Is there parking?", "Parking"),
    ("en", "Can I get a wheelchair?", "wheelchair"),
    ("en", "Where is the emergency entrance?", "east"),
    ("en", "What departments do you have?", "cardiology"),
    ("hi", "मरीज़ों से मिलने का समय क्या है?", "4 बजे"),
    ("hi", "फार्मेसी कहाँ है?", "फार्मेसी"),
    ("hi", "ओपीडी कब खुलती है?", "9 बजे"),
    ("hi", "अपॉइंटमेंट कैसे लें?", "5550 1234"),
    ("hi", "क्या पार्किंग है?", "पार्किंग"),
    ("hi", "बिल कहाँ भरें?", "बिलिंग"),
    ("bn", "রোগী দেখার সময় কখন?", "4টা"),
    ("bn", "ফার্মেসি কোথায়?", "ফার্মেসি"),
    ("bn", "আউটডোর কখন খোলা থাকে?", "9টা"),
    ("bn", "অ্যাপয়েন্টমেন্ট কীভাবে নেব?", "5550 1234"),
    ("bn", "পার্কিং আছে কি?", "পার্কিং"),
    ("bn", "বিলিং কাউন্টার কোথায়?", "বিলিং"),
]
UNANSWERABLE = [
    ("en", "What is the price of a flight to Paris?"),
    ("en", "Who is the Prime Minister of Australia?"),
    ("en", "How do I bake a chocolate cake?"),
    ("en", "What is the capital of Japan?"),
    ("en", "Do you sell car insurance?"),
    ("en", "What is the weather tomorrow?"),
    ("en", "Who won the cricket match last night?"),
    ("en", "Can you write a poem about the sea?"),
    ("hi", "पेरिस की फ्लाइट कितने की है?"),
    ("hi", "जापान की राजधानी क्या है?"),
    ("hi", "कल मौसम कैसा रहेगा?"),
    ("hi", "केक कैसे बनाते हैं?"),
    ("bn", "প্যারিসের বিমানের ভাড়া কত?"),
    ("bn", "জাপানের রাজধানী কী?"),
    ("bn", "আগামীকাল আবহাওয়া কেমন থাকবে?"),
    ("bn", "কেক কীভাবে বানায়?"),
]


def call(path, body=None):
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Origin": BASE},
    )
    return json.loads(opener.open(request, timeout=30).read())


def main() -> None:
    call("/api/auth/login", {"email": env["VAP_ADMIN_EMAIL"], "password": env["VAP_ADMIN_PASSWORD"]})
    base = next(item for item in call("/api/admin/knowledge-bases?page=1&size=100")["items"] if item["name"] == "healthcare")
    rows = []
    for language, question, expected in ANSWERABLE:
        found = call(f"/api/admin/knowledge-bases/{base['id']}/search", {"query": question, "language": language})
        top = found["hits"][0]
        hit_top1 = expected in top["text"]
        hit_any = any(expected in hit["text"] for hit in found["hits"])
        rows.append({"kind": "answerable", "language": language, "question": question, "confidence": found["confidence"],
                     "cosine": round(top["cosine"], 3), "coverage": round(top["coverage"], 3), "top1": hit_top1, "top3": hit_any})
    for language, question in UNANSWERABLE:
        found = call(f"/api/admin/knowledge-bases/{base['id']}/search", {"query": question, "language": language})
        top = found["hits"][0] if found["hits"] else {"cosine": 0, "coverage": 0}
        rows.append({"kind": "unanswerable", "language": language, "question": question, "confidence": found["confidence"],
                     "cosine": round(top["cosine"], 3), "coverage": round(top["coverage"], 3)})
    for row in rows:
        print(row["kind"][:4], row["language"], f"conf {row['confidence']:.3f} cos {row['cosine']:.3f} cov {row['coverage']:.2f}", row.get("top1", ""), row.get("top3", ""), row["question"][:44])
    good = [row for row in rows if row["kind"] == "answerable"]
    print("top-1", sum(row["top1"] for row in good), "/", len(good), "top-3", sum(row["top3"] for row in good), "/", len(good))
    Path("benchmarks/results/rag_eval.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf8")


if __name__ == "__main__":
    main()
