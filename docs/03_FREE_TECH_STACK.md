# Free technology stack

## Classes

| Class | Meaning |
| --- | --- |
| FREE | No cost, no meaningful conditions beyond keeping the notice. |
| FREE WITH HARDWARE | No cost, but it needs your own computer. |
| RESTRICTED | No cost, but the licence adds conditions such as share-alike. Read `04_LICENSE_AUDIT.md`. |
| FREE TIER | Free up to a limit set by a company. The default never depends on one. |
| PAID | Costs money. Never used by default. |

## The default stack

| Job | Choice | Class | Version | CPU or GPU | Disk |
| --- | --- | --- | --- | --- | --- |
| Web page | React 18.3, Vite, TypeScript | FREE | In `frontend/package.json` | Browser | Small |
| Server | FastAPI, uvicorn | FREE | fastapi 0.115 or newer | CPU | Small |
| Turn detection | Silero VAD | FREE | v6.2 | CPU | 2.3 MB |
| Speech to text, English | Zipformer offline | FREE WITH HARDWARE | 2023-06-26 | CPU | Part of 335 MB |
| Speech to text, Hindi | IndicConformer int8 | FREE WITH HARDWARE | ONNX export | CPU | Part of 335 MB |
| Live Hindi words | Hindi streaming CTC | FREE WITH HARDWARE | int8 | CPU | Part of 335 MB |
| Speech to text, Bengali | Bangla Zipformer int8 | RESTRICTED (CC BY-SA 4.0) | Current | CPU | Part of 335 MB |
| Language model | Qwen3.5-0.8B Q4_K_M | FREE WITH HARDWARE | GGUF | CPU | 508 MB |
| Model server | llama.cpp llama-server | FREE | b12098 | CPU | Part of 114 MB |
| Embeddings | Multilingual E5 small | FREE WITH HARDWARE | ONNX | CPU | 130 MB |
| Search store | SQLite FTS5 and NumPy | FREE | With Python | CPU | Grows with documents |
| Voices | Piper voices on onnxruntime | RESTRICTED (see audit) | Per voice | CPU | 254 MB |
| Phonemes | phonemizer, espeak-ng | FREE, GPL-3.0 | 3.6.0, loader 0.2.4 | CPU | Small |
| Public link (optional) | cloudflared | FREE | Official release | CPU | Part of 114 MB |

No default part depends on a FREE TIER or PAID service. Total models on disk: about 1.3 GB.

Optional extra: `python scripts/fetch_models.py --profile natural-voices` adds Kokoro voices for English and Hindi, about 0.2 GB. They sound more natural by design, but take about 3 seconds to speak a sentence on this laptop.

## Hardware profiles

`backend/hardware.py` reads the machine at start-up and picks one.

| Profile | When | Language model slots | Callers at one time |
| --- | --- | --- | --- |
| A, CPU only | No usable GPU | 1 | 2 if 12 or more logical cores, else 1 |
| B, GPU | One usable GPU | 4 | 10, not measured |
| C, server | Large memory and a GPU | 8 | 40, not measured |

Only profile A has been run. Profiles B and C are planned settings until someone measures them.

## Minimum hardware for profile A

| Part | Minimum | Tested on |
| --- | --- | --- |
| Processor | 8 logical cores | i7-13620H, 10 cores, 16 threads |
| Memory | 8 GB, with 3 GB free for the agent | 15.7 GB usable |
| GPU | None | Intel UHD, not used |
| Disk | 3 GB | 477 GB SSD |
| Browser | Chrome, Edge or another browser with AudioWorklet | Chromium through Playwright |

The agent used about 521 MB for the server and 806 MB for the language model before speech models load, plus up to about 700 MB for three recognisers and voices. The 8 GB figure comes from those numbers and is not a separate test.

## Model report

| Model | Measured strength | Measured weakness |
| --- | --- | --- |
| Qwen3.5-0.8B | Fast, small, stays on facts when held by the guards. | Awkward Bengali wording at times, such as "একটি একতলা দোকান". |
| Zipformer English | 12% word errors on human speech. | Mishears unusual names, such as "OPD" heard as "op d". |
| IndicConformer Hindi | About 10% word errors on human speech. | About 1.1 seconds per clip. |
| Bangla Zipformer | 3.1% word errors, with the overlap warning. | No independent test set. |
