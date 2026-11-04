# Voice quality report

**No person has listened to these voices yet.** Everything here is measured by machine. Good clarity numbers do not prove a voice is pleasant. A listening test by native speakers is the next step.

## Method

The voice speaks a set of sentences, the best recogniser for that language listens, and the two texts are compared with CER (character error rate). Lower is clearer. RTF is time to make the audio divided by its length, so under 1 is faster than speech. The test used 2 threads and 4 to 7 sentences.

## Results

| Voice | Language | RTF | Time for a sentence | CER | Status |
| --- | --- | --- | --- | --- | --- |
| Piper alba | English | 0.122 | 390 ms | 0.036 | **Default** |
| Piper northern English male | English | 0.093 | 301 ms | 0.036 | Available |
| Kokoro bf_emma | English | 0.640 | 2,547 ms | 0.036 | Optional download |
| Piper rohan | Hindi | 0.113 | 483 ms | 0.023 | **Default** |
| Kokoro hf_alpha | Hindi | 0.715 | 3,615 ms | 0.005 | Optional download |
| Kokoro hf_beta | Hindi | 0.712 | 3,026 ms | 0.016 | Optional download |
| Kokoro hm_omega | Hindi | 0.681 | 3,363 ms | 0.009 | Optional download |
| Piper Bengali speaker 14 | Bengali | 0.136 | | 0.037 | **Default** |
| Piper Bengali speaker 13 | Bengali | 0.081 | | 0.047 | Available |
| Kokoro hf_alpha, Bengali text | Bengali | 0.959 | 5,416 ms | 0.025 | Rejected, too slow |
| Coqui Bengali female | Bengali | 1.114 | 4,223 ms | 0.071 | Rejected, slower than speech |

Bengali speakers were picked from all 16 with `benchmarks/bn_speaker_scan.py`, on 7 sentences. CER ranged from 0.037 to 0.078 and the recogniser made the judgement, so with so few sentences the order is a guide only.

## Numbers and special words

Checked by round trip on the final code.

| Input | Heard as |
| --- | --- |
| Hindi "24 घंटे" | चौबीस घंटे |
| Hindi "₹200" | दो सौ रुपये |
| Hindi "₹1,500" | एक हज़ार पाँच सौ रुपये |
| Bengali "২৪ ঘণ্টা" | চব্বিশ ঘন্টা |
| Bengali "₹২০০" | দুশো টাকা |
| Telephone numbers | Digit by digit, in the language of the call |
| English "OPD" | O P D |

## Listening test still to do

Ask three native speakers per language to score these on a 1 to 5 scale:

1. Can you understand every word?
2. Does it sound natural?
3. Would you be happy to hear this from a hospital?
4. Are numbers, dates and times read properly?

Test on a phone speaker and on headphones. Replace any default voice that scores under 3.

## Sample audio

`python benchmarks/tts_candidates.py` writes samples to `benchmarks/results/tts_samples/`.
