import { useState } from "react";

const FAQS = [
  ["Do I need a phone number?", "No. You talk through your browser. There is no phone number, SIM or calling plan."],
  ["Is my voice recorded?", "No. Audio is used to understand you and is then discarded. It is never written to storage."],
  [
    "Are the agents real people?",
    "No. Each agent is an AI assistant. It answers from approved documents, and it says so when it does not know something.",
  ],
  [
    "Can the healthcare agent give medical advice?",
    "No. It gives hospital information only. It does not diagnose or prescribe. For an emergency, call 112 or go to the nearest emergency department.",
  ],
  ["Which languages can I use?", "English, Hindi and Bengali. You can change language during a conversation."],
  ["Why is the microphone blocked?", "Your browser needs your permission. Select the lock icon in the address bar and allow the microphone."],
  ["Can I delete my conversation?", "Yes. Choose Delete Transcript when the conversation ends. You can also turn off the transcript before you start."],
];

export function Faqs() {
  const [open, setOpen] = useState(0);
  return (
    <article className="accordion">
      <h1>FAQs</h1>
      {FAQS.map(([question, answer], index) => (
        <div key={question}>
          <button type="button" aria-expanded={open === index} onClick={() => setOpen(open === index ? -1 : index)}>
            {question}
            <span aria-hidden="true">{open === index ? "▲" : "▼"}</span>
          </button>
          {open === index ? <p className="answer">{answer}</p> : null}
        </div>
      ))}
    </article>
  );
}

export function Privacy() {
  return (
    <article className="legal card">
      <h1>Privacy Policy</h1>
      <p>This service runs on the organisation&apos;s own server. Speech, language and knowledge processing all happen there. No voice, text or document is sent to any outside service.</p>
      <h2>Audio</h2>
      <p>Your microphone audio is sent to the server over an encrypted connection when the service is used over HTTPS. It is held in memory only while your words are recognised, and it is then discarded. Audio is never written to storage.</p>
      <h2>Transcripts</h2>
      <p>If you leave Keep a transcript switched on, the text of the conversation is stored so that the organisation can improve its service. You can switch this off before you start. Transcripts are deleted automatically after the period set by the organisation, 30 days by default.</p>
      <h2>Your choices</h2>
      <p>When a conversation ends you can delete its transcript at once. Timing measurements are kept without any text, for capacity planning.</p>
      <h2>Sensitive information</h2>
      <p>Please do not share passwords, card numbers, one-time codes or medical records. The agents never need them.</p>
      <h2>Not for emergencies</h2>
      <p>This service gives general information. It does not replace a doctor, lawyer or other professional. In an emergency, call 112.</p>
    </article>
  );
}
