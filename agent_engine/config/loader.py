"""Read the bundled agent files. Adding an industry means adding a YAML file, not code."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from agent_engine.config.schema import AgentConfig

AGENTS_DIR = Path(__file__).parent / "agents"
SAMPLE_KNOWLEDGE_DIR = Path(__file__).parent / "sample_knowledge"
# These lists add to the shared file. Every other key in an industry file replaces the shared one.
ADDITIVE_KEYS = ("business_policies", "escalation_rules", "restricted_actions")


@dataclass(frozen=True)
class BundledAgent:
    config: AgentConfig
    sample_faq: list[dict[str, str]]
    sample_files: list[Path]


def merge(common: dict, industry: dict) -> dict:
    merged = {**common, **industry}
    for key in ADDITIVE_KEYS:
        # The industry's own rules come first: an emergency must win over "talk to a person".
        merged[key] = [*(industry.get(key) or []), *(common.get(key) or [])]
    return merged


def parse_agent(raw: dict, common: dict) -> BundledAgent:
    data = merge(common, raw)
    faq = data.pop("sample_faq", [])
    config = AgentConfig.model_validate(data)
    problems = config.missing_translations()
    if problems:
        raise ValueError(f"{config.slug}: {' '.join(problems)}")
    folder = SAMPLE_KNOWLEDGE_DIR / config.slug
    files = sorted(folder.glob("*")) if folder.is_dir() else []
    return BundledAgent(config, faq, files)


def load_bundled_agents(folder: Path = AGENTS_DIR) -> list[BundledAgent]:
    common = yaml.safe_load((folder / "_common.yaml").read_text(encoding="utf-8"))
    agents = []
    for path in sorted(folder.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        agents.append(parse_agent(yaml.safe_load(path.read_text(encoding="utf-8")), common))
    return agents


def bundled_agent(slug: str) -> BundledAgent:
    for agent in load_bundled_agents():
        if agent.config.slug == slug:
            return agent
    raise KeyError(slug)
