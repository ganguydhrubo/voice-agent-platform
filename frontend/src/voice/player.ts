// Plays the server's audio chunks without gaps, and can stop instantly when the caller interrupts.

export interface ChunkHeader {
  turn: number;
  index: number;
  rate: number;
}

export const HEADER_BYTES = 12;

export function parseAudioFrame(data: ArrayBuffer): { header: ChunkHeader; pcm: Int16Array } {
  const view = new DataView(data);
  const header = {
    turn: view.getUint32(0, true),
    index: view.getUint32(4, true),
    rate: view.getUint32(8, true),
  };
  // Copy, because the sample data may not start on a two-byte boundary.
  const pcm = new Int16Array(data.slice(HEADER_BYTES));
  return { header, pcm };
}

export class AudioPlayer {
  readonly context: AudioContext;
  readonly output: AnalyserNode;
  private sources = new Set<AudioBufferSourceNode>();
  private nextStart = 0;
  private firstStart: number | null = null;
  private scheduledSeconds = 0;
  turn = -1;
  onFirstAudio: ((turn: number, delayMs: number) => void) | null = null;
  onDrained: ((turn: number) => void) | null = null;

  constructor(context: AudioContext) {
    this.context = context;
    this.output = context.createAnalyser();
    this.output.fftSize = 512;
    this.output.connect(context.destination);
  }

  enqueue(header: ChunkHeader, pcm: Int16Array): void {
    if (header.turn !== this.turn) {
      this.startTurn(header.turn);
    }
    const buffer = this.context.createBuffer(1, pcm.length, header.rate);
    const samples = buffer.getChannelData(0);
    for (let i = 0; i < pcm.length; i += 1) samples[i] = pcm[i] / 32768;

    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.output);
    const now = this.context.currentTime;
    const start = Math.max(now + 0.03, this.nextStart);
    source.start(start);
    source.onended = () => {
      this.sources.delete(source);
      if (this.sources.size === 0 && this.turn === header.turn) this.onDrained?.(header.turn);
    };
    this.sources.add(source);
    this.nextStart = start + buffer.duration;
    this.scheduledSeconds += buffer.duration;
    if (this.firstStart === null) {
      this.firstStart = start;
      const latency = (this.context.outputLatency || this.context.baseLatency || 0) * 1000;
      this.onFirstAudio?.(header.turn, (start - now) * 1000 + latency);
    }
  }

  private startTurn(turn: number): void {
    this.flush();
    this.turn = turn;
  }

  /** How much of the current turn has reached the speaker. */
  playedMs(): number {
    if (this.firstStart === null) return 0;
    const elapsed = this.context.currentTime - this.firstStart;
    return Math.max(0, Math.min(elapsed, this.scheduledSeconds)) * 1000;
  }

  get isPlaying(): boolean {
    return this.sources.size > 0;
  }

  flush(): void {
    for (const source of this.sources) {
      source.onended = null;
      try {
        source.stop();
      } catch {
        // Already finished.
      }
      source.disconnect();
    }
    this.sources.clear();
    this.nextStart = 0;
    this.firstStart = null;
    this.scheduledSeconds = 0;
  }
}
