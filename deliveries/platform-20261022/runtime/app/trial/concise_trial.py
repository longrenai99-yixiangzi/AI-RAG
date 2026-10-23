"""Separate local retrieval trial; daily generation requires an explicitly approved bounded policy."""
from pathlib import Path
import json

from app.config import Settings
from .platform_app import create_app
from .platform_existing import ExistingKnowledge

FOLDER = Path(__file__).resolve().parents[2]/'evaluation/concise_trial_20261022'


def trial_app():
    if not (FOLDER/'prepared.json').is_file():
        raise RuntimeError('独立试用尚未完成准备，未启动空白替代入口。')
    policy_path=FOLDER/'daily_policy.json'
    policy=json.loads(policy_path.read_text(encoding='utf-8')) if policy_path.exists() else None
    return create_app(FOLDER/'state.json', FOLDER/'platform-dist',
                      Settings.load().vault_root/'.ai-growth/config/knowledge-platform-contract-v1.json',
                      ExistingKnowledge(), generation_execution_enabled=False,daily_policy=policy)
