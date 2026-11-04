# Performance

All numbers were measured on 4 November 2026 on one laptop: Lenovo 83K1, i7-13620H, 10 cores, 16 threads, 15.7 GB memory, no GPU. Raw results are in `benchmarks/results/`. Another machine will differ, so run the benchmarks there.

## First spoken reply

Time from the `speech_end` event to the first audio frame leaving for the browser, over a real WebSocket, with the Healthcare agent and machine-voice questions.

| Run | Turns | Free memory | p50 | p95 | p99 | Max |
| --- | --- | --- | --- | --- | --- | --- |
| Final code, one caller | 60 | About 0.6 GB | 2,139 ms | 3,326 ms | 3,688 ms | 3,899 ms |
| Earlier code, one caller | 60 | About 2 to 3 GB | 1,896 ms | 2,758 ms | 2,880 ms | 2,925 ms |
| Final code, two callers talking at once | 16 | About 1 GB | 2,875 ms | 3,563 ms | 4,169 ms | 4,320 ms |

The final run had other apps holding most of the memory. That probably explains most of the gap, but it was not tested on its own, so read 1.9 to 2.1 seconds as the honest typical figure.

**Add these when reading the numbers:**

1. The caller must stop talking for 450 ms before the timer starts.
2. Browser playback delay is not included.
3. With 20 turns per language, p99 is close to the maximum. It is not a true 99th percentile.
4. Two-caller test: each caller keeps talking without a pause, which is harder than a real call.

## By language, final code, one caller

| Language | First audio p50 | p95 | p99 | Turns |
| --- | --- | --- | --- | --- |
| English | 1,998 ms | 2,252 ms | 2,399 ms | 20 |
| Hindi | 2,483 ms | 2,768 ms | 2,809 ms | 20 |
| Bengali | 2,461 ms | 3,559 ms | 3,831 ms | 20 |

## By stage, final code, one caller

| Stage | English p50 / p95 | Hindi p50 / p95 | Bengali p50 / p95 |
| --- | --- | --- | --- |
| Final text | 50 / 64 ms | 551 / 664 ms | 53 / 75 ms |
| Retrieval | 2 / 3 ms | 2 / 8 ms | 3 / 4 ms |
| Model first token | 960 / 1,254 ms | 964 / 1,086 ms | 943 / 1,961 ms |
| First audio | 1,990 / 2,243 ms | 2,475 / 2,761 ms | 2,452 / 3,541 ms |

The gap between the first token and first audio is mostly the model finishing its first sentence, because each sentence is checked before it is spoken. This is the price of the safety checks.

## Speech to text

40 human clips per language, 4 threads, whole clips. Lower is better for WER and CER. RTF under 1 is faster than speech.

| Model | Language | WER | CER | RTF | p50 | p95 | Memory |
| --- | --- | --- | --- | --- | --- | --- | --- |
| zipformer-en-offline | English | 0.120 | 0.050 | 0.028 | 130 ms | 307 ms | 242 MB |
| indicconformer-hi | Hindi | 0.105 | 0.035 | 0.253 | 1,135 ms | 1,860 ms | 353 MB |
| bangla-zipformer | Bengali | 0.031 | 0.007 | 0.026 | 142 ms | 244 ms | 259 MB |
| indicconformer-bn | Bengali | 0.107 | 0.020 | 0.252 | 1,361 ms | 2,422 ms | 381 MB |
| faster-whisper small | English | 0.051 | 0.022 | 0.563 | 3,038 ms | 3,258 ms | 320 MB |
| faster-whisper small | Hindi | 0.990 | 0.524 | | | | |
| faster-whisper small | Bengali | 1.123 | 1.259 | | | | |
| faster-whisper base | English | 0.105 | 0.053 | 0.181 | 938 ms | 1,307 ms | 167 MB |
| faster-whisper base | Hindi | 1.647 | 1.341 | | | | |
| faster-whisper base | Bengali | 1.451 | 1.074 | | | | |
| zipformer-en-streaming-large | English | 0.164 | 0.082 | 0.084 | 434 ms | 717 ms | 118 MB |
| zipformer-en-streaming 20M | English | 0.478 | 0.362 | 0.043 | 218 ms | 360 ms | 67 MB |
| hindi-streaming-ctc | Hindi | 0.392 | 0.175 | 0.163 | 720 ms | 1,159 ms | 128 MB |

Bengali warning: bangla-zipformer may have trained on some of these clips. The publisher reports WER 14.4%, CER 4.3% on its own test. Report both.

## The live path

Same clips, sent through the detector and then the recogniser, as a real call does. Final code.

| Language | Whole clip WER | Live path WER | Clips cut in two |
| --- | --- | --- | --- |
| English | 0.120 | 0.125 | 5 of 40 |
| Hindi | 0.094 | 0.101 | 4 of 40 |
| Bengali | 0.031 | 0.031 | 0 of 40 |

## Language model

| Setting | Load | Idle | Peak | First token | Speed | Facts right |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen3.5-0.8B, context 4,096, old prompt | 1.4 s | 831 MB | 1,486 MB | 1,759 ms | 23.3 tokens/s | 11 of 12 |
| Qwen3.5-0.8B, context 2,048, final prompt | 2.0 s | 806 MB | 1,188 MB | 1,318 ms | 32.1 tokens/s | 12 of 12 |

Both used 6 threads. The 2B model test was stopped on this laptop for memory, so there is no result.

## Text to speech

See `VOICE_QUALITY_REPORT.md`.

## Interruption

Flush was sent about 230 to 250 ms after the caller began to talk, in two runs. No more frames from the old turn came after it.

## Memory while running

Server 521 MB, llama-server 806 MB, before speech models load. Models on disk 1.3 GB.

## How to repeat

```bash
python benchmarks/fetch_eval_audio.py
python benchmarks/stt_candidates.py
python benchmarks/live_path_stt.py
python benchmarks/tts_candidates.py
python benchmarks/llm_candidates.py
python tests/benchmarks/rag_eval.py
python tests/benchmarks/latency.py --turns 20
python tests/benchmarks/latency.py --turns 8 --concurrent 2
```

The last three need the server running.
