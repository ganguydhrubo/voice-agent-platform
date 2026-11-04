# Licence audit

This is an engineer's reading, not legal advice. Have a lawyer read it before you sell or resell this product.

## The short version

1. Our own source code is Apache-2.0.
2. **Two runtime packages are GPL-3.0: phonemizer and espeak-ng.** They are not stored in this repository. `pip install` fetches them. Apache-2.0 code can be combined with GPL-3.0 code, but anything you **distribute** with them, such as a Docker image or an installer, falls under GPL-3.0 terms as a whole. That means offering the source of the whole. Running the service on your own server without handing out copies is treated differently by the GPL. Get legal advice on your exact case.
3. **Two voices and one recogniser are share-alike (CC BY-SA 4.0).** If you change and share those weights, your changes carry the same licence. Credit the source.
4. Rohan, the Hindi voice, is under the IITM IndicTTS licence. Notices must stay. It allows resale, with the same terms passed on.

## Code and libraries

| Item | Licence | Commercial use | Conditions |
| --- | --- | --- | --- |
| llama.cpp b12098 | MIT | Yes | Keep notice |
| sherpa-onnx 2.0.1 | Apache-2.0 | Yes | Keep notice. Its wheel embeds espeak-ng (GPL), although we do not use its voice front end |
| onnxruntime | MIT | Yes | Keep notice |
| onnx-asr 0.12 | MIT | Yes | Keep notice |
| phonemizer 3.6.0 | GPL-3.0 | Yes | **Copyleft on distribution** |
| espeak-ng through espeakng-loader 0.2.4 | GPL-3.0 (loader itself MIT) | Yes | **Copyleft on distribution** |
| FastAPI, uvicorn, Pydantic, httpx, NumPy | MIT or BSD | Yes | Keep notice |
| pypdf, python-docx, Beautiful Soup, prometheus-client, argon2-cffi | BSD, MIT or Apache-2.0 | Yes | Keep notice |
| React, React Router, Vite | MIT | Yes | Keep notice |
| cloudflared | Apache-2.0 | Yes | Keep notice. The link itself runs on Cloudflare's service under its terms |

## Models and voices

| Item | Licence | Commercial use | Conditions |
| --- | --- | --- | --- |
| Qwen3.5-0.8B and 2B | Apache-2.0 | Yes | Keep notice |
| Multilingual E5 small | MIT | Yes | Keep notice |
| Silero VAD 6.2 | MIT | Yes | Keep notice |
| Zipformer English 2023-06-26 | Apache-2.0 | Yes | Keep notice |
| IndicConformer Hindi and Bengali | MIT | Yes | Keep notice |
| Hindi streaming CTC | Apache-2.0 | Yes | Keep notice |
| Bangla Zipformer | CC BY-SA 4.0 | Yes | Credit. Share changes alike |
| Piper en alba | CC BY 4.0 | Yes | Credit |
| Piper en northern English male | CC BY-SA 4.0 | Yes | Credit. Share changes alike |
| Piper hi rohan | IITM IndicTTS EULA | Yes: perpetual, worldwide, royalty-free, transferable, sublicensable | Keep notices. Pass the same terms on any resale. Read through the Web Archive copy, as the original page was unavailable |
| Piper bn google | CC BY-SA 4.0, with CMU licence | Yes | Credit. Share changes alike |
| Kokoro (optional) | Apache-2.0 | Yes | Keep notice |

## Rejected on licence

| Item | Why |
| --- | --- |
| TEN VAD | Licence is Apache-2.0 with extra conditions. GitHub reports `NOASSERTION`. |
| Piper Hindi pratham, priyamvada | CC BY-NC-SA. Non-commercial only. |
| Piper en hfc_female, hfc_male, ryan | CC BY-NC-SA. Non-commercial only. |

## Test data

Mozilla Common Voice 17.0 is CC0. The clips are not stored in this repository.

## Paid or free-tier services

None by default. The LLM setting accepts any OpenAI-compatible address, so a paid service could be added by someone who chooses to. It stays off unless that person sets it.
