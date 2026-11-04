// Runs on the browser's audio thread. Turns microphone audio into 16 kHz, 16-bit mono frames of 20 ms.
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.step = sampleRate / 16000;
    this.position = 0;
    this.total = 0;
    this.count = 0;
    this.frame = new Int16Array(320);
    this.filled = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i += 1) {
      // Averaging across each output sample is a simple low-pass filter, which stops aliasing.
      this.total += channel[i];
      this.count += 1;
      this.position += 1;
      if (this.position >= this.step) {
        this.position -= this.step;
        const value = Math.max(-1, Math.min(1, this.total / this.count));
        this.frame[this.filled] = value * 32767;
        this.filled += 1;
        this.total = 0;
        this.count = 0;
        if (this.filled === this.frame.length) {
          const out = this.frame.slice(0);
          this.port.postMessage(out.buffer, [out.buffer]);
          this.filled = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("capture-processor", CaptureProcessor);
