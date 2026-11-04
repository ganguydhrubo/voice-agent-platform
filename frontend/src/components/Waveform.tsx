import { useEffect, useRef } from "react";

// Draws whichever audio is live: the caller's microphone or the agent's voice.
export function Waveform({ getNode, active }: { getNode: () => AnalyserNode | null; active: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return undefined;
    let frame = 0;
    const samples = new Uint8Array(256);
    const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#0f766e";

    const draw = () => {
      const scale = window.devicePixelRatio || 1;
      const width = element.clientWidth * scale;
      const height = element.clientHeight * scale;
      if (element.width !== width || element.height !== height) {
        element.width = width;
        element.height = height;
      }
      context.clearRect(0, 0, width, height);
      const node = active ? getNode() : null;
      const bars = 48;
      const gap = 3 * scale;
      const barWidth = (width - gap * (bars - 1)) / bars;
      if (node) node.getByteTimeDomainData(samples);
      context.fillStyle = accent;
      for (let index = 0; index < bars; index += 1) {
        const sample = node ? samples[Math.floor((index / bars) * samples.length)] : 128;
        const level = Math.abs(sample - 128) / 128;
        const barHeight = Math.max(3 * scale, Math.min(1, level * 2.4) * height * 0.9);
        const x = index * (barWidth + gap);
        context.fillRect(x, (height - barHeight) / 2, barWidth, barHeight);
      }
      frame = window.requestAnimationFrame(draw);
    };
    draw();
    return () => window.cancelAnimationFrame(frame);
  }, [getNode, active]);

  return <canvas ref={canvas} className="waveform" role="img" aria-label="Live audio level" />;
}
