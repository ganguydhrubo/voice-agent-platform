# Third party notices

Our own source code is under the Apache License 2.0, in `LICENSE`. The items below keep their own licences. Read `docs/04_LICENSE_AUDIT.md`. This is not legal advice.

## GPL-3.0 parts used at run time

- **phonemizer** 3.6.0, https://github.com/bootphon/phonemizer
- **espeak-ng**, through espeakng-loader 0.2.4, https://github.com/espeak-ng/espeak-ng

They are not stored in this repository. `pip` downloads them. If you distribute a product that includes them, such as a Docker image, GPL-3.0 applies to that combined product. You must then offer its source code.

## Voices

- **Piper voices**, https://huggingface.co/rhasspy/piper-voices
  - `en_GB-alba-medium`: CC BY 4.0, Centre for Speech Technology Research, University of Edinburgh.
  - `en_GB-northern_english_male-medium`: CC BY-SA 4.0, OpenSLR SLR83.
  - `hi_IN-rohan-medium`: IITM IndicTTS licence. Keep its notices. Pass the same terms on resale.
  - `bn_BD-google-medium`: CC BY-SA 4.0, OpenSLR SLR37, plus CMU licence.
- **Kokoro** (optional): Apache-2.0, https://huggingface.co/hexgrad/Kokoro-82M

## Speech recognition

- **Bangla Zipformer**: CC BY-SA 4.0, Sayed Shaun, https://huggingface.co/SayedShaun/bangla-zipformer-onnx
- **Zipformer English**: Apache-2.0, k2-fsa, https://huggingface.co/csukuangfj/sherpa-onnx-zipformer-en-2023-06-26
- **IndicConformer**: MIT, AI4Bharat. ONNX export by OpenVoiceOS.
- **Hindi streaming CTC**: Apache-2.0, https://huggingface.co/mobilebytesensei/betterflow-hindi-streaming-ctc

## Other models

- **Qwen3.5-0.8B**: Apache-2.0, Alibaba Cloud. GGUF by Unsloth.
- **Multilingual E5 small**: MIT, Microsoft.
- **Silero VAD**: MIT, https://github.com/snakers4/silero-vad

## Libraries and tools

- llama.cpp: MIT
- sherpa-onnx: Apache-2.0. Its wheel embeds espeak-ng (GPL-3.0)
- onnxruntime: MIT
- onnx-asr: MIT
- FastAPI, uvicorn, Pydantic, httpx: MIT or BSD
- NumPy: BSD
- pypdf, python-docx, Beautiful Soup, prometheus-client, argon2-cffi: BSD, MIT or Apache-2.0
- React, React Router, Vite: MIT
- cloudflared: Apache-2.0
- Caddy: Apache-2.0
- Prometheus: Apache-2.0
- Grafana OSS: AGPL-3.0, optional monitoring only

The full list of Python packages and their licences comes from `pip-licenses`, and for the page from `frontend/bun.lock`.
