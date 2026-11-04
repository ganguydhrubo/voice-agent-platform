# Languages

English, Hindi and Bengali are supported in speech and text. Every number below comes from human recordings or real runs.

## Evidence

| Check | English | Hindi | Bengali |
| --- | --- | --- | --- |
| Word errors on 40 human clips, live path | 12.5% | 10.1% | 3.1%, overlap warning |
| Publisher's own Bengali test | | | 14.4% WER, 4.3% CER |
| Round-trip voice check, default voice | CER 0.036 | CER 0.023 | CER 0.037 |
| Browser journey with follow-up and interruption | Pass | Pass | Pass, awkward wording at times |
| First spoken reply, p50 | 1,998 ms | 2,483 ms | 2,461 ms |

Round trip means a recogniser listened to the voice and the text was compared. It shows the words are clear. **It does not show the voice sounds good. No person has judged that yet.**

## Language choice

1. The caller picks the language on the start page or during the call.
2. Typed text is detected from its script, so typing Hindi in an English session works.
3. Spoken language is not auto-detected. It was not measured, and a wrong guess would give a nonsense transcript, so we do not offer it.

Natural switching in speech means choosing the new language in the Settings box. The agent then answers in it.

## Details that matter

| Language | Note |
| --- | --- |
| English | British voice by default, alba. |
| Hindi | Rohan is the default. Numbers are read correctly in Hindi: 24 is heard as "चौबीस". |
| Bengali | Speaker 14 is the default, picked from 16 speakers. Numbers are read in Bengali: 24 is heard as "চব্বিশ". |
| All | Native digits are converted before speech. Telephone numbers are read digit by digit. |
| Mixed speech | Calling in a mix of Hindi and English is common. Clips in the test set are mostly single-language, so mixed speech is not measured. Expect more mistakes. |

## Known weak spots

1. **Bengali wording.** The small model at times gives odd phrases, such as calling a ground-floor pharmacy "একটি একতলা দোকান". A larger model should help, but it was not measured.
2. **Bengali scores** may be too good because of the overlap warning. Treat 3.1% as the best case and 14.4% as the safer guess.
3. **Regional accents** are limited to what Common Voice holds.

## Adding a language

1. Add a recogniser and a voice to `models/manifests/catalogue.json`.
2. Add the language to `voice_engine/tts/voices.py`, `backend/runtime.py` and the digit tables in `normalise.py`.
3. Add sample knowledge and greetings.
4. Measure with `benchmarks/live_path_stt.py` and `benchmarks/tts_candidates.py` on human speech.
5. Only then show it to callers.
