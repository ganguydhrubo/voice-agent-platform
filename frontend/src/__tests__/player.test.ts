import { describe, expect, it } from "vitest";
import { AudioPlayer } from "../voice/player";

class FakeNode {
  buffer: unknown = null;
  onended: (() => void) | null = null;
  started = 0;
  stopped = false;
  connect() { return this; }
  disconnect() {}
  start(at: number) { this.started = at; }
  stop() { this.stopped = true; }
}

function fakeContext() {
  const sources: FakeNode[] = [];
  const context = {
    currentTime: 1,
    baseLatency: 0,
    outputLatency: 0,
    sampleRate: 48000,
    destination: {},
    createBuffer: (_channels: number, length: number, rate: number) => ({ duration: length / rate, getChannelData: () => new Float32Array(length) }),
    createBufferSource: () => {
      const node = new FakeNode();
      sources.push(node);
      return node;
    },
    createGain: () => ({ gain: { value: 1 }, connect() { return this; } }),
    createAnalyser: () => ({ fftSize: 0, connect() { return this; } }),
  };
  return { context: context as unknown as AudioContext, sources };
}

const header = (turn: number, index: number) => ({ turn, index, rate: 16000 });
const pcm = () => new Int16Array(3200);

describe("AudioPlayer", () => {
  it("plays chunks one after another without overlap", () => {
    const { context, sources } = fakeContext();
    const player = new AudioPlayer(context);
    player.enqueue(header(1, 0), pcm());
    player.enqueue(header(1, 1), pcm());
    expect(sources[1].started).toBeGreaterThan(sources[0].started);
  });

  it("stops everything at once when interrupted", () => {
    const { context, sources } = fakeContext();
    const player = new AudioPlayer(context);
    player.enqueue(header(1, 0), pcm());
    player.enqueue(header(1, 1), pcm());
    player.flush();
    expect(sources.every((source) => source.stopped)).toBe(true);
  });

  it("clears the old turn when a new one starts", () => {
    const { context, sources } = fakeContext();
    const player = new AudioPlayer(context);
    player.enqueue(header(1, 0), pcm());
    player.enqueue(header(2, 0), pcm());
    expect(sources[0].stopped).toBe(true);
    expect(sources[1].stopped).toBe(false);
  });
});
