import { describe, expect, it, vi } from "vitest";
import { VoiceClient } from "../voice/client";

function frame(turn: number, index = 0): ArrayBuffer {
  const data = new ArrayBuffer(12 + 4);
  const view = new DataView(data);
  view.setUint32(0, turn, true);
  view.setUint32(4, index, true);
  view.setUint32(8, 16000, true);
  return data;
}

function makeClient() {
  const events = {
    onState: vi.fn(),
    onMic: vi.fn(),
    onPartial: vi.fn(),
    onLine: vi.fn(),
    onInterrupted: vi.fn(),
    onError: vi.fn(),
    onNotice: vi.fn(),
    onEscalation: vi.fn(),
    onTimings: vi.fn(),
    onLanguage: vi.fn(),
  };
  const player = { turn: 5, enqueue: vi.fn(), flush: vi.fn(), playedMs: () => 0 };
  const client = new VoiceClient(events);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const inside = client as any;
  inside.player = player;
  return { inside, player };
}

describe("audio that arrives after a stop", () => {
  it("plays normally before any stop", () => {
    const { inside, player } = makeClient();
    inside.onAudio(frame(5));
    expect(player.enqueue).toHaveBeenCalledTimes(1);
  });

  it("stays silent when the frame was already on the wire at the flush", () => {
    const { inside, player } = makeClient();
    inside.onMessage({ type: "flush", turn: 5 });
    inside.onAudio(frame(5, 7));
    expect(player.flush).toHaveBeenCalled();
    expect(player.enqueue).not.toHaveBeenCalled();
  });

  it("stays silent after the caller stops it by hand", () => {
    const { inside, player } = makeClient();
    inside.interrupt();
    inside.onAudio(frame(5, 8));
    expect(player.enqueue).not.toHaveBeenCalled();
  });

  it("plays the next answer", () => {
    const { inside, player } = makeClient();
    inside.onMessage({ type: "flush", turn: 5 });
    inside.onAudio(frame(6));
    expect(player.enqueue).toHaveBeenCalledTimes(1);
  });
});
