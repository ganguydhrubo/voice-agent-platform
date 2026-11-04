// The browser side of a conversation: microphone, WebSocket, playback and interruption.

import { AudioPlayer, parseAudioFrame } from "./player";

export type ConversationState =
  | "idle"
  | "connecting"
  | "listening"
  | "thinking"
  | "speaking"
  | "reconnecting"
  | "ended"
  | "error";

export type MicStatus = "unknown" | "requesting" | "granted" | "denied" | "missing" | "unsupported" | "off";

export interface TranscriptLine {
  id: string;
  role: "user" | "agent";
  text: string;
  turn: number;
  interrupted?: boolean;
  sources?: { title: string; section: string }[];
  confidence?: number;
}

export interface VoiceEvents {
  onState(state: ConversationState): void;
  onMic(status: MicStatus): void;
  onPartial(text: string): void;
  onLine(line: TranscriptLine): void;
  onInterrupted(turn: number): void;
  onError(message: string): void;
  onNotice(code: string): void;
  onEscalation(severity: string): void;
  onTimings(timings: Record<string, number | string | boolean>): void;
  onLanguage(language: string, voice: string | null): void;
}

export interface StartOptions {
  id: string;
  token: string;
  mode: "voice" | "text";
}

export function microphoneError(error: unknown): { status: MicStatus; message: string } {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return {
      status: "denied",
      message:
        "Microphone access is blocked. Select the lock icon in the address bar, allow the microphone, then try again. You can also type your question.",
    };
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return { status: "missing", message: "No microphone was found. Connect one and try again, or type your question." };
  }
  if (name === "NotReadableError") {
    return { status: "missing", message: "Another app is using the microphone. Close it and try again, or type your question." };
  }
  return { status: "unsupported", message: "The microphone could not be started. You can type your question instead." };
}

const MAX_RECONNECTS = 3;
const TYPED_TURN = -2;

export class VoiceClient {
  private socket: WebSocket | null = null;
  private context: AudioContext | null = null;
  private player: AudioPlayer | null = null;
  private stream: MediaStream | null = null;
  private capture: AudioWorkletNode | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private micAnalyser: AnalyserNode | null = null;
  private options: StartOptions | null = null;
  private speechEndAt = 0;
  private speechEndTurn = -1;
  // Frames of this turn or an older one may still be on the wire after a stop. They must stay silent.
  private flushedTurn = -1;
  private playbackTimer = 0;
  private reconnects = 0;
  private ended = false;
  private muted = false;
  private lineCounter = 0;
  private agentLine: TranscriptLine | null = null;
  private connected = false;
  state: ConversationState = "idle";

  constructor(private readonly events: VoiceEvents) {}

  get microphoneLevelNode(): AnalyserNode | null {
    return this.micAnalyser;
  }

  get speakerLevelNode(): AnalyserNode | null {
    return this.player?.output ?? null;
  }

  private setState(state: ConversationState): void {
    this.state = state;
    this.events.onState(state);
  }

  async start(options: StartOptions): Promise<void> {
    this.options = options;
    this.ended = false;
    this.setState("connecting");
    // Created inside the click that started the conversation, or browsers keep it suspended.
    this.context = new AudioContext({ latencyHint: "interactive" });
    await this.context.resume();
    this.player = new AudioPlayer(this.context);
    this.player.onFirstAudio = (turn, delayMs) => this.reportAudible(turn, delayMs);
    this.player.onDrained = (turn) => this.reportFinished(turn);
    if (options.mode === "voice") await this.startMicrophone();
    this.connect();
  }

  private async startMicrophone(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) {
      this.events.onMic("unsupported");
      this.events.onError("This page needs HTTPS for the microphone, or a browser that supports it. You can type your question instead.");
      return;
    }
    this.events.onMic("requesting");
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (error) {
      const problem = microphoneError(error);
      this.events.onMic(problem.status);
      this.events.onError(problem.message);
      return;
    }
    const context = this.context as AudioContext;
    await context.audioWorklet.addModule("/audio-capture-worklet.js");
    this.sourceNode = context.createMediaStreamSource(this.stream);
    this.micAnalyser = context.createAnalyser();
    this.micAnalyser.fftSize = 512;
    this.capture = new AudioWorkletNode(context, "capture-processor", { numberOfOutputs: 0 });
    this.capture.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      const listening = !this.muted && this.options?.mode === "voice";
      if (listening && this.socket?.readyState === WebSocket.OPEN) this.socket.send(event.data);
    };
    this.sourceNode.connect(this.micAnalyser);
    this.sourceNode.connect(this.capture);
    this.events.onMic("granted");
  }

  private connect(): void {
    const options = this.options as StartOptions;
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${scheme}://${location.host}/ws/voice`);
    socket.binaryType = "arraybuffer";
    this.socket = socket;
    this.flushedTurn = -1;
    socket.onopen = () => {
      socket.send(JSON.stringify({ type: "start", id: options.id, token: options.token, mode: options.mode, resume: this.connected }));
      this.connected = true;
    };
    socket.onmessage = (event) => {
      if (typeof event.data === "string") this.onMessage(JSON.parse(event.data));
      else this.onAudio(event.data as ArrayBuffer);
    };
    socket.onclose = (event) => this.onClose(event.code);
  }

  private onClose(code: number): void {
    window.clearInterval(this.playbackTimer);
    this.playbackTimer = 0;
    if (this.ended) return;
    const refused = code === 4401 || code === 4403 || code === 4503;
    if (refused || this.reconnects >= MAX_RECONNECTS) {
      this.setState("error");
      if (!refused) this.events.onError("The connection was lost. Please start the conversation again.");
      return;
    }
    this.reconnects += 1;
    this.setState("reconnecting");
    window.setTimeout(() => this.connect(), 800 * this.reconnects);
  }

  private onAudio(data: ArrayBuffer): void {
    const { header, pcm } = parseAudioFrame(data);
    if (header.turn <= this.flushedTurn) return;
    this.player?.enqueue(header, pcm);
    if (!this.playbackTimer) {
      this.playbackTimer = window.setInterval(() => this.reportPlayback(), 250);
    }
  }

  private stopPlayback(turn: number = this.player?.turn ?? -1): void {
    this.flushedTurn = Math.max(this.flushedTurn, turn);
    this.player?.flush();
  }

  private reportPlayback(): void {
    if (!this.player) return;
    this.send({ type: "playback", turn: this.player.turn, played_ms: Math.round(this.player.playedMs()) });
  }

  private reportFinished(turn: number): void {
    window.clearInterval(this.playbackTimer);
    this.playbackTimer = 0;
    this.send({ type: "playback", turn, played_ms: Math.round(this.player?.playedMs() ?? 0), finished: true });
  }

  private reportAudible(turn: number, delayMs: number): void {
    if (turn !== this.speechEndTurn) return;
    const after = performance.now() - this.speechEndAt + delayMs;
    this.send({ type: "audible", turn, after_speech_end_ms: Math.round(after) });
  }

  private send(payload: object): void {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(payload));
  }

  private nextId(): string {
    this.lineCounter += 1;
    return `line-${this.lineCounter}`;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private onMessage(message: any): void {
    switch (message.type) {
      case "ready":
        this.reconnects = 0;
        break;
      case "state":
        this.setState(message.state);
        break;
      case "partial":
        this.events.onPartial(message.text);
        break;
      case "speech_start":
        this.events.onPartial("");
        break;
      case "speech_end":
        this.speechEndAt = performance.now();
        this.speechEndTurn = message.turn;
        break;
      case "final":
        this.events.onPartial("");
        if (this.speechEndTurn === TYPED_TURN) this.speechEndTurn = message.turn;
        if (message.text) {
          this.agentLine = null;
          this.events.onLine({ id: this.nextId(), role: "user", text: message.text, turn: message.turn });
        }
        break;
      case "agent_text":
        this.appendAgentText(message.turn, message.text);
        break;
      case "sources":
        this.pendingSources = message.sources;
        this.pendingConfidence = message.confidence;
        break;
      case "flush":
        this.stopPlayback(message.turn);
        this.markInterrupted(message.turn);
        break;
      case "turn_end":
        if (message.timings) this.events.onTimings(message.timings);
        break;
      case "language":
        this.events.onLanguage(message.language, message.voice);
        break;
      case "escalation":
        this.events.onEscalation(message.severity);
        break;
      case "notice":
        this.events.onNotice(message.code);
        break;
      case "error":
        this.events.onError(message.message);
        break;
      case "ended":
        this.finish();
        break;
      default:
        break;
    }
  }

  private pendingSources: { title: string; section: string }[] | undefined;
  private pendingConfidence: number | undefined;

  private appendAgentText(turn: number, text: string): void {
    if (this.agentLine && this.agentLine.turn === turn) {
      this.agentLine = { ...this.agentLine, text: `${this.agentLine.text} ${text}` };
    } else {
      this.agentLine = {
        id: this.nextId(),
        role: "agent",
        text,
        turn,
        sources: this.pendingSources,
        confidence: this.pendingConfidence,
      };
      this.pendingSources = undefined;
      this.pendingConfidence = undefined;
    }
    this.events.onLine(this.agentLine);
  }

  private markInterrupted(turn: number): void {
    if (this.agentLine && this.agentLine.turn === turn) {
      this.agentLine = { ...this.agentLine, interrupted: true };
      this.events.onLine(this.agentLine);
    }
    this.events.onInterrupted(turn);
  }

  interrupt(): void {
    this.stopPlayback();
    this.send({ type: "interrupt" });
  }

  sendText(text: string): void {
    this.stopPlayback();
    this.agentLine = null;
    this.speechEndAt = performance.now();
    this.speechEndTurn = TYPED_TURN;
    // The server sends the text back, joined to any words it is still holding.
    this.send({ type: "text", text });
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    this.events.onMic(muted ? "off" : "granted");
  }

  setLanguage(language: string): void {
    this.send({ type: "language", language });
  }

  setVoice(voice: string): void {
    this.send({ type: "voice", voice });
  }

  async setMode(mode: "voice" | "text"): Promise<void> {
    if (this.options) this.options.mode = mode;
    this.send({ type: "mode", mode });
    if (mode === "text") {
      this.stopPlayback();
      this.events.onMic("off");
    } else if (this.stream) {
      this.events.onMic(this.muted ? "off" : "granted");
    } else {
      await this.startMicrophone();
    }
  }

  private finish(): void {
    this.ended = true;
    this.setState("ended");
    this.release();
  }

  end(): void {
    this.send({ type: "end" });
    this.finish();
  }

  release(): void {
    this.ended = true;
    this.socket?.close();
    window.clearInterval(this.playbackTimer);
    this.playbackTimer = 0;
    this.player?.flush();
    this.capture?.disconnect();
    this.sourceNode?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    void this.context?.close();
    this.context = null;
  }
}
