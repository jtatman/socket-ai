"""Bulk-seed remaining environments with prompts and YAML configs.

Safe to run multiple times: skips existing files. Only fills missing bots for:
- philosophy (Confucius)
- marketing (BrandDesigner)
- saas (GrowthHacker, CustomerSuccess, PricingAnalyst)
- product_development (ProductManager, UXResearcher, TechLead)
- planning (RoadmapStrategist, OKRCoach, RiskAnalyst)

After running, every env will have at least 3 bots.
"""
import os
import textwrap
import yaml

ROOT = os.path.dirname(os.path.dirname(__file__))
PROMPTS_DIR = os.path.join(ROOT, "prompts")
ENVS_DIR = os.path.join(ROOT, "environments")
LLM_NODE = "10.209.1.96"
MODEL = "llama3.2:3b"
HOST = "localhost"
PORT = 6667
TLS = False

data = {
    "philosophy": [
        {
            "nick": "Confucius",
            "temperature": 0.3,
            "prompt": "You are Confucius. Speak with wisdom using concise Analects-style aphorisms focusing on virtue and harmony.",
        },
    ],
    "marketing": [
        {
            "nick": "BrandDesigner",
            "temperature": 0.5,
            "prompt": "You are a brand designer focused on visual identity and narrative consistency. Give creative yet practical advice on brand assets.",
        },
    ],
    "saas": [
        {
            "nick": "CustomerSuccess",
            "temperature": 0.4,
            "prompt": "You are a customer success leader prioritizing retention and adoption. Provide playbooks for onboarding, QBRs, and churn mitigation.",
        },
        {
            "nick": "PricingAnalyst",
            "temperature": 0.2,
            "prompt": "You are a SaaS pricing analyst specializing in tiered and usage-based models. Recommend data-driven pricing strategies.",
        },
    ],
    "product_development": [
        {
            "nick": "ProductManager",
            "temperature": 0.35,
            "prompt": "You are a pragmatic product manager. Focus on user stories, prioritization frameworks, and stakeholder alignment.",
        },
        {
            "nick": "UXResearcher",
            "temperature": 0.45,
            "prompt": "You are a UX researcher who values empathy and data. Suggest research methods and synthesize findings clearly.",
        },
        {
            "nick": "TechLead",
            "temperature": 0.25,
            "prompt": "You are a tech lead balancing architecture and delivery. Provide guidance on technical trade-offs and team mentoring.",
        },
    ],
    "planning": [
        {
            "nick": "RoadmapStrategist",
            "temperature": 0.3,
            "prompt": "You are a roadmap strategist mapping quarterly objectives to business impact. Speak in milestones and deliverables.",
        },
        {
            "nick": "OKRCoach",
            "temperature": 0.4,
            "prompt": "You are an OKR coach helping teams craft measurable objectives and key results. Offer clear examples and pitfalls to avoid.",
        },
        {
            "nick": "RiskAnalyst",
            "temperature": 0.25,
            "prompt": "You are a risk analyst identifying and mitigating project risks with probability-impact matrices.",
        },
    ],
}

CHANNEL_MAP = {
    env: f"#{env}"
    for env in data.keys()
}


def ensure_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path)


def write_prompt(env: str, nick: str, prompt_text: str):
    path_dir = os.path.join(PROMPTS_DIR, env)
    ensure_dir(path_dir)
    fname = os.path.join(path_dir, f"{nick}.md")
    if os.path.exists(fname):
        return
    with open(fname, "w", encoding="utf-8") as fp:
        fp.write(prompt_text.strip() + "\n")


def write_yaml(env: str, nick: str, temperature: float):
    path_dir = os.path.join(ENVS_DIR, env)
    ensure_dir(path_dir)
    fname = os.path.join(path_dir, f"{nick}.yml")
    if os.path.exists(fname):
        return
    ydata = {
        "nick": nick,
        "channel": CHANNEL_MAP.get(env, f"#{env}"),
        "host": HOST,
        "port": PORT,
        "tls": TLS,
        "model": MODEL,
        "temperature": temperature,
        "prompt": os.path.relpath(os.path.join(PROMPTS_DIR, env, f"{nick}.md"), start=path_dir).replace("\\", "/"),
        "llm_node": LLM_NODE,
    }
    with open(fname, "w", encoding="utf-8") as fp:
        yaml.dump(ydata, fp, sort_keys=False)


for env, bots in data.items():
    for bot in bots:
        write_prompt(env, bot["nick"], bot["prompt"])
        write_yaml(env, bot["nick"], bot["temperature"])

print("Bulk seeding complete.")
