"""Separate local trial using existing read-only retrieval, with model execution disabled."""
from pathlib import Path

from app.config import Settings
from .platform_app import create_app
from .platform_existing import ExistingKnowledge

FOLDER = Path(__file__).resolve().parents[2]/'evaluation/concise_trial_20261022'


def trial_app():
    if not (FOLDER/'prepared.json').is_file():
        raise RuntimeError('独立试用尚未完成准备，未启动空白替代入口。')
    return create_app(FOLDER/'state.json', FOLDER/'platform-dist',
                      Settings.load().vault_root/'.ai-growth/config/knowledge-platform-contract-v1.json',
                      ExistingKnowledge(), generation_execution_enabled=False)
