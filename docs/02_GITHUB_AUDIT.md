# GitHub audit

Pulled from the GitHub API on 4 November 2026. The raw output is in `github_audit.tsv`. Stars are only a rough sign of use. "Last push" shows the project is alive, not that it is good.

| Repository | Stars | Licence on GitHub | Last push | Used here |
| --- | --- | --- | --- | --- |
| ggml-org/llama.cpp | 133,326 | MIT | 04/11/2026 | **Yes**, build b12098, language model server |
| k2-fsa/sherpa-onnx | 15,730 | Apache-2.0 | 04/11/2026 | **Yes**, version 2.0.1, offline Zipformer recognisers |
| microsoft/onnxruntime | 22,219 | MIT | 04/11/2026 | **Yes**, runs VAD, Piper and embeddings |
| snakers4/silero-vad | 10,594 | MIT | 22/10/2026 | **Yes**, pinned to v6.2 |
| istupakov/onnx-asr | 387 | MIT | 21/10/2026 | **Yes**, version 0.12, IndicConformer and Hindi live words |
| bootphon/phonemizer | 1,577 | GPL-3.0 | 02/11/2026 | **Yes**, turns text into phonemes. See licence audit |
| espeak-ng/espeak-ng | 6,995 | GPL-3.0 | 03/11/2026 | **Yes**, through the loader below. See licence audit |
| thewh1teagle/espeakng-loader | 10 | MIT | 01/11/2025 | **Yes**, version 0.2.4. Very small project, so a risk to watch |
| fastapi/fastapi | 104,395 | MIT | 02/11/2026 | **Yes** |
| cloudflare/cloudflared | 16,431 | Apache-2.0 | 30/10/2026 | **Yes**, optional public link only |
| caddyserver/caddy | 78,741 | Apache-2.0 | 04/11/2026 | Optional HTTPS in Docker |
| OHF-Voice/piper1-gpl | 6,156 | GPL-3.0 | 02/11/2026 | **No**. Its code is not used |
| rhasspy/piper | 11,316 | MIT | 26/08/2025 | **No**. Archived. Only its voice weights are used, through rhasspy/piper-voices |
| hexgrad/kokoro | 9,905 | Apache-2.0 | 06/08/2025 | Weights are an optional download |
| SYSTRAN/faster-whisper | 26,468 | MIT | 02/11/2026 | **No**. Tested, then rejected as default |
| ggml-org/whisper.cpp | 54,908 | MIT | 03/11/2026 | **No**. Read only |
| AI4Bharat/IndicConformerASR | 106 | MIT | 20/06/2025 | Source of the Hindi weights |
| AI4Bharat/NeMo | 28 | Apache-2.0 | 05/06/2025 | Read only |
| pipecat-ai/pipecat | 17,049 | BSD-2-Clause | 04/11/2026 | **No**. Read for design ideas |
| livekit/agents | 15,079 | Apache-2.0 | 04/11/2026 | **No**. Read for design ideas |
| TEN-framework/ten-framework | 11,219 | NOASSERTION | 04/11/2026 | **No**. Licence needs legal reading |
| TEN-framework/ten-vad | 2,302 | NOASSERTION | 04/11/2026 | **No**. Rejected on licence |
| coqui-ai/TTS | 46,175 | MPL-2.0 | 16/08/2024 | **No**. No push since 2024 |
| ollama/ollama | 185,868 | MIT | 04/11/2026 | **No**. Works as an alternative server |

## Model sources

| Model | Source | Licence recorded |
| --- | --- | --- |
| Qwen3.5-0.8B Q4_K_M | unsloth/Qwen3.5-0.8B-GGUF | Apache-2.0 |
| Multilingual E5 small | Xenova/multilingual-e5-small | MIT |
| Zipformer English offline | csukuangfj/sherpa-onnx-zipformer-en-2023-06-26 | Apache-2.0 |
| IndicConformer Hindi | OpenVoiceOS/ai4bharat-indicconformer-hi-onnx | MIT |
| Hindi streaming CTC | mobilebytesensei/betterflow-hindi-streaming-ctc | Apache-2.0 |
| Bangla Zipformer | SayedShaun/bangla-zipformer-onnx | CC BY-SA 4.0 |
| Piper voices | rhasspy/piper-voices | Per voice, see licence audit |
| Kokoro int8 (optional) | csukuangfj/kokoro-int8-multi-lang-v1_0 | Apache-2.0 |
| Silero VAD | snakers4/silero-vad v6.2 | MIT |

Every downloaded file is recorded by SHA-256 in `models/manifests/lock.json`, and `scripts/fetch_models.py` refuses a later download that does not match.
