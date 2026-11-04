# Knowledge and retrieval

## Flow

Upload → check type and size → parse → clean → split by heading → chunk → embed → store → search → rerank → answer with sources.

| Step | Detail |
| --- | --- |
| Types | PDF, DOCX, TXT, MD, CSV, JSON, web addresses, FAQs |
| Upload limit | 25 MB by default |
| Web addresses | HTTPS only. Private network addresses refused, checked again on redirects |
| Chunks | Split by real headings, then by size. Each chunk starts with its heading |
| Embedding | Multilingual E5 small through onnxruntime |
| Word search | SQLite FTS5 on a folded form of the text |
| Vector search | NumPy brute force, kept in memory per tenant |
| Merge | Reciprocal rank fusion, then a deterministic rerank |
| Confidence | `min(1, 0.75 × cosine + 0.45 × word coverage)` of the top result |
| Cut-off | 0.62. Lower gives the no-answer line |
| Context | The three best sentences across hits, at most 1,000 characters |

## Folding

Hindi and Bengali spellings differ a lot, and speech recognisers often pick another spelling. `knowledge_engine/text.py` folds both the document and the question: nukta, virama, anusvara and candrabindu are dropped and candra vowels mapped. So "फ़ारमेसी" and "फार्मेसी" meet.

## Follow-up questions

"What are its timings?" has no subject. Questions with referring words use the previous question too, and the best passage of the topic is merged in. Other questions search alone, so a new topic never drags the old one along.

Measured on 6 follow-ups with `benchmarks/followup_check.py`: history only 6, earlier question 4, joined 6, topic note 6.

## Measured results

`tests/benchmarks/rag_eval.py`, on the Healthcare sample, final code:

| Test | Result |
| --- | --- |
| Answerable questions, 3 languages | 22 |
| Right document first | 22 of 22 |
| Right document in top three | 22 of 22 |
| Lowest confidence, answerable | 0.84 |
| Unanswerable questions | 16 |
| Unanswerable over the 0.62 cut-off | 2: "Do you sell car insurance?" at 0.891, Hindi weather at 0.694 |

Those two pass the cut-off because a word matches. The word grounding check still protects the reply, but the risk is real and a caller may get a passage that does not fit. These figures are from one small sample, so re-test with your own documents.

## Limits

1. Brute-force search is fine for thousands of chunks, not millions.
2. There is no OCR, so a scanned PDF gives no text and the upload says so.
3. A document in one language does not answer in another unless the model translates it. Keep documents in each language.
4. One sample set is too small to prove the cut-off. Check the Knowledge page's search on real documents.

## Isolation

Every query names the tenant and the agent's knowledge bases. Tests in `tests/integration/test_knowledge_and_tenants.py` prove one tenant cannot read another's documents.
