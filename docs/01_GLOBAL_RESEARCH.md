# Global research

Research date: November 2026. This records what was looked at and why each piece was kept or dropped. Numbers come from `benchmarks/results/` on the test laptop. Where a result is not measured, this document says so.

## The question

Can one web page give a natural voice conversation in English, Hindi and Bengali, with no phone line, no paid service and no data leaving the server, on ordinary hardware?

Yes, with limits. A 10-core laptop with 16 GB of memory gave a first spoken reply in about 1.9 seconds for one caller. The limits are in section 6.

## 1. Speech to text

| Candidate | Result | Decision |
| --- | --- | --- |
| faster-whisper base and small | Good English. Hindi and Bengali on human speech were very poor: WER 0.99 to 1.65. | Rejected as default. It would have failed Hindi and Bengali quietly. |
| Sherpa streaming Zipformer English 20M | WER 0.478 on human speech. | Rejected. |
| Sherpa streaming Zipformer English large | WER 0.164. | Rejected for final text. Offline model was better and faster. |
| Sherpa offline Zipformer English | WER 0.120, 130 ms for a clip. | **Chosen for English.** |
| AI4Bharat IndicConformer Hindi | WER 0.105, 1135 ms for a clip. | **Chosen for Hindi.** |
| AI4Bharat IndicConformer Bengali | WER 0.107, 1361 ms for a clip. | Accurate, slower. Kept as a fallback in the catalogue. |
| Bangla Zipformer | WER 0.031, 142 ms, on Common Voice clips. Possible overlap with its training data. The publisher's own figures are WER 14.4%, CER 4.3%. | **Chosen for Bengali.** Both numbers must be reported together. |
| Hindi streaming CTC | WER 0.392 on human speech. | Used only for live words on screen in Hindi, never for the final text. |

Lesson: test on human recordings. A model that looks fine on clean machine voices can fail on people.

## 2. Language model

| Candidate | Result | Decision |
| --- | --- | --- |
| Qwen3.5-0.8B Q4_K_M on llama.cpp | 806 MB idle, 1188 MB peak, 1318 ms first token, 32 tokens a second, 12 of 12 facts right. | **Chosen.** Fits beside the speech models on 16 GB. |
| Qwen3.5-2B Q4_K_M | Test stopped on this laptop for lack of memory. No result. | Offered on machines with more memory. Not measured here. |
| Ollama | MIT licence and easy to use, but not installed here, and llama-server gives the same OpenAI-compatible interface directly. | Not needed. Any OpenAI-compatible server can be swapped in by configuration. |

## 3. Text to speech

| Candidate | Result | Decision |
| --- | --- | --- |
| Piper English alba, northern English male | RTF about 0.1, round-trip CER 0.036. | **Chosen.** |
| Piper Hindi rohan | RTF 0.113, CER 0.023. | **Chosen.** Licence note in `04_LICENSE_AUDIT.md`. |
| Piper Hindi pratham, priyamvada | Non-commercial licence. | Rejected. |
| Piper Bengali google, 16 speakers | Speaker 14 best at CER 0.037 on 7 sentences. | **Chosen**, speakers 14 and 13. |
| Kokoro int8, English and Hindi | Natural sounding, but RTF 0.64 to 0.72, about 3 seconds for a sentence. | Optional download, not default. |
| Kokoro with Bengali | RTF 0.959, 5.4 seconds a sentence. | Rejected. |
| Coqui Bengali female | RTF 1.114, slower than speech. | Rejected. |

## 4. Turn detection and interruption

| Candidate | Result | Decision |
| --- | --- | --- |
| Silero VAD 6.2 | MIT. Fine on all three languages. | **Chosen.** |
| TEN VAD | Licence adds conditions on top of Apache-2.0. GitHub reports `NOASSERTION`. | Rejected. |

## 5. Frameworks that were read and not used

Pipecat (BSD-2-Clause) and LiveKit Agents (Apache-2.0) are strong projects. Both are mostly used with paid or cloud parts, and LiveKit adds a media server. This product needs one small WebSocket between one page and one server, so a framework would add more than it saves. TEN Framework has the same licence question as TEN VAD.

## 6. What this research cannot claim

1. No person has listened to the voices. Quality is measured by machine only, so `VOICE_QUALITY_REPORT.md` lists a listening test as still to do.
2. A real microphone in a real room has not been tested. The browser test uses a fake microphone device that plays recordings.
3. Spoken language detection is not measured, so the caller picks the language. Typed text is detected from its script.
4. Bengali accuracy has no independent test set. See section 1.
5. Multi-server use was not built or measured. See `12_COST_ANALYSIS.md`.

## Sources

Repository facts: `02_GITHUB_AUDIT.md`. Licences: `04_LICENSE_AUDIT.md`. Test speech: Mozilla Common Voice 17.0 (CC0), through `fsicoli/common_voice_17_0`.

Hosting sources:

- https://huggingface.co/docs/hub/en/spaces-overview
- https://discuss.huggingface.co/t/free-cpu-basic-quota-is-0-on-new-account/180764
- https://flaviocopes.com/cloudflare-quick-tunnels/
- https://www.issoh.co.jp/md/tech/8634
