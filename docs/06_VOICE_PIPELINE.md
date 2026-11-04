# Voice pipeline

## Stages and settings

| Stage | What runs | Setting |
| --- | --- | --- |
| Capture | AudioWorklet, 16 kHz, mono, 16-bit, 20 ms frames. Echo cancellation, noise suppression and gain control are asked of the browser. | |
| Turn detection | Silero VAD on the server | Threshold 0.5, end of speech after 450 ms of silence, minimum speech 160 ms, maximum utterance 20 seconds |
| Live words | English and Bengali: the final model re-run every 600 ms. Hindi: separate streaming CTC model. | Off when the machine has under 8 logical cores |
| Final text | Offline model for the chosen language | Hindi audio gets 300 ms of silence added at both ends |
| Guards and retrieval | See `07_AGENT_BUILDER.md`, `08_RAG.md` | |
| Language model | llama-server, one slot on profile A | Context 2,048, temperature 0.1, at most 160 tokens |
| Text clean-up | `voice_engine/tts/normalise.py`: rupees, percent, telephone numbers digit by digit, clock times, acronyms | The stored text stays exact; only the spoken form changes |
| Speech | Piper through onnxruntime, sentence at a time | |
| Delivery | 12-byte header plus PCM, 200 ms chunks | |
| Playback | `AudioPlayer` schedules chunks one after another | |

## Why Hindi audio is padded

Without padding, human Hindi WER rose from 0.105 to 0.315 on the live path. The detector trims close to the speech and IndicConformer loses the first and last sounds. Measured with `benchmarks/live_path_stt.py`:

| Padding | Hindi WER |
| --- | --- |
| None | 0.315 |
| 100 ms | 0.105 |
| 300 ms | 0.098 |
| 500 ms | 0.094 |

300 ms was chosen. Final run with the padding in place: Hindi 0.101, English 0.125, Bengali 0.031.

## Barge-in

1. While the agent speaks, a higher speech bar and a minimum of 240 ms of speech are used, so its own voice leaking into the microphone does not count as the caller.
2. When the caller breaks in, the server sends `flush` and cancels the model by closing its stream.
3. The server stops making audio for that turn.
4. The browser stops all scheduled audio at once and remembers the turn number. Any frame of that turn still on the wire is dropped. `frontend/src/__tests__/client.test.ts` covers this.
5. The part of the reply that was actually played stays in the history, and the transcript line is marked Interrupted.

Measured in two runs: the flush came 907 and 927 ms after sending of the audio began. Speech started 676 ms into that recording, so about 230 to 250 ms after talking began. No more frames of the old turn arrived.

A real room may behave differently. Echo from speakers on a real laptop has not been tested. Headphones are the safe advice until it is.

## Failure paths

| Failure | What the caller gets |
| --- | --- |
| Microphone blocked | Clear steps to allow it, and text mode |
| No microphone, or another app using it | A message, and text mode |
| Page not on HTTPS | A message, and text mode |
| Socket drops | Up to the set number of reconnects, then a message |
| All places taken | "All our lines are busy." Close code 4503 |
| Model not running | The no-answer path or approved text; health page shows the fault |
| Memory too low | New callers refused, and new work degraded |
