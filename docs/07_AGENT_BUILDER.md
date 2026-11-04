# Agent builder

Each agent is one YAML file in `agent_engine/config/agents/`, and `_common.yaml` holds what all share. Agents can also be created and edited on the Agents page. At start-up, the files are loaded into the database once.

## The 16 agents

Healthcare, Hospitals, Clinics, Real Estate, Education, Banking, Insurance, Retail, E-commerce, Hospitality, Logistics, Manufacturing, Legal Services, Customer Support, HR, SaaS.

Each has identity, name, role, personality, instructions, languages, its own sample knowledge, allowed tools, restricted actions, policies, escalation rules, memory settings and evaluation tests.

All organisations and facts are invented, marked "Sample". Replace them before real use.

## Fields

```yaml
slug: healthcare
industry: Healthcare
name: Asha
role: patient information assistant
organisation: Sample City Hospital
personality: Calm, kind and clear.
system_instructions: >-
  Help patients and visitors ...
greeting:
  en: "Hello, I am Asha ..."
restricted_topics: [...]
escalation_rules: [...]
evaluation_tests:
  - question: ...
    expect: ...
```

Read `healthcare.yaml` for the full example.

## Safety order

Checks before the model, strongest first:

1. **Emergency:** chest pain, heavy bleeding and the like. The agent gives the emergency line and records an urgent escalation.
2. **Restricted action:** for healthcare, diagnosis, medicine and dose questions. A fixed polite refusal, then a pointer to a doctor.
3. **Prompt injection:** "ignore your instructions", attempts to read the prompt and the like. A fixed refusal.

Checks on each sentence from the model:

| Check | Catches |
| --- | --- |
| Number grounding | A number not in the passages |
| Leak marker | Text from the system prompt |
| Medical claim | A diagnosis or dose in a healthcare reply |
| Wrong script | English in a Hindi reply and the like |
| Word grounding | Under 34% of the new words are in the passages |
| Repeat | The same answer as last time |

A failed check gives the approved sentence from the document instead, and a `notice` event records why.

## Tools

`allowed_tools` is `knowledge_search` and `escalate_to_human`. There are no tools that change outside systems: no booking, no payment, no CRM. An agent that says it will book something would be lying, so restricted actions and the no-answer line send people to staff instead.

## Testing an agent

The Agents page has a Test button that runs the evaluation tests. `tests/live/run_evaluations.py` runs all of them: 55 of 55 passed on the final code.

## Memory

Each agent keeps a set number of recent turns. There is no long-term memory across conversations.
