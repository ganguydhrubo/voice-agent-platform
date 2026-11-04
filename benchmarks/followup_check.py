"""Compare ways of giving the small model the previous turn, on real follow-up questions."""
import sys
import time

import httpx

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf8")

from agent_engine.config.loader import bundled_agent
from agent_engine.orchestration.prompt import system_prompt

DOCS = {
    "en": "Departments and services: The pathology laboratory is on the ground floor. The pharmacy is on the ground floor near the main entrance and is open 24 hours a day.\nBilling and insurance: The billing counter is next to the main reception and is open from 8 am to 8 pm.",
    "hi": "विभाग और सेवाएँ: पैथोलॉजी लैब भूतल पर है। फार्मेसी (दवाई की दुकान) मुख्य द्वार के पास भूतल पर है और 24 घंटे खुली रहती है।\nबिल और बीमा: बिलिंग काउंटर मुख्य रिसेप्शन के पास है और सुबह 8 बजे से रात 8 बजे तक खुला रहता है।",
    "bn": "বিভাগ ও পরিষেবা: প্যাথলজি ল্যাব একতলায় আছে। ফার্মেসি (ওষুধের দোকান) মূল প্রবেশপথের কাছে একতলায় আছে এবং 24 ঘণ্টা খোলা থাকে।\nবিল ও বিমা: বিলিং কাউন্টার মূল রিসেপশনের পাশে এবং সকাল 8টা থেকে রাত 8টা পর্যন্ত খোলা থাকে।",
}
CASES = [
    ("en", "English", "Where is the pharmacy?", "The pharmacy is on the ground floor near the main entrance.", "When does it open?", ["24"]),
    ("en", "English", "Where is the billing counter?", "The billing counter is next to the main reception.", "What are its hours?", ["8"]),
    ("hi", "Hindi", "फार्मेसी कहाँ है?", "फार्मेसी मुख्य द्वार के पास है।", "वह कितने बजे खुलती है?", ["24"]),
    ("hi", "Hindi", "बिलिंग काउंटर कहाँ है?", "बिलिंग काउंटर मुख्य रिसेप्शन के पास है।", "वह कब तक खुला रहता है?", ["8"]),
    ("bn", "Bengali", "ফার্মেসি কোথায়?", "ফার্মেসি মূল প্রবেশপথের কাছে আছে।", "এটা কখন খোলে?", ["24"]),
    ("bn", "Bengali", "বিলিং কাউন্টার কোথায়?", "বিলিং কাউন্টার মূল রিসেপশনের পাশে আছে।", "এটা কখন খোলা থাকে?", ["8"]),
]


def history_variant(system, name, docs, q1, a1, q2):
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": q1},
        {"role": "assistant", "content": a1},
        {"role": "user", "content": f"DOCUMENTS:\n{docs}\n\nQUESTION: {q2}\nReply in {name} only."},
    ]


def earlier_question(system, name, docs, q1, a1, q2):
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"DOCUMENTS:\n{docs}\n\nEARLIER QUESTION: {q1}\nNEW QUESTION: {q2}\nAnswer the new question. Reply in {name} only."},
    ]


def joined_question(system, name, docs, q1, a1, q2):
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"DOCUMENTS:\n{docs}\n\nQUESTION: {q1} {q2}\nReply in {name} only."},
    ]


def topic_note(system, name, docs, q1, a1, q2):
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"DOCUMENTS:\n{docs}\n\nThe caller is asking about: {q1}\nQUESTION: {q2}\nGive a new fact from the DOCUMENTS. Reply in {name} only."},
    ]


VARIANTS = {"history": history_variant, "earlier": earlier_question, "joined": joined_question, "topic": topic_note}


def main() -> None:
    agent = bundled_agent("healthcare").config
    system = system_prompt(agent)
    with httpx.Client(timeout=60) as client:
        for key, build in VARIANTS.items():
            score = 0
            lines = []
            started = time.perf_counter()
            for language, name, q1, a1, q2, expect in CASES:
                body = {"messages": build(system, name, DOCS[language], q1, a1, q2), "max_tokens": 60, "temperature": 0.1, "cache_prompt": True}
                reply = client.post("http://127.0.0.1:8081/v1/chat/completions", json=body).json()["choices"][0]["message"]["content"].strip()
                good = all(item in reply or item.translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")) in reply or item.translate(str.maketrans("0123456789", "०१२३४५६७८९")) in reply for item in expect)
                score += good
                lines.append(f"   {'ok ' if good else 'NO '} [{language}] {reply[:110]}")
            print(f"{key}: {score}/{len(CASES)} in {time.perf_counter() - started:.1f}s")
            print("\n".join(lines))


if __name__ == "__main__":
    main()
