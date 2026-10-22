"""Shared vault contract; classification is separate from evidence eligibility."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

CONTRACT_REL = Path('.ai-growth/config/knowledge-platform-contract-v1.json')


class KnowledgeContract:
    def __init__(self, vault: Path):
        self.vault = vault.resolve()
        self.path = self.vault / CONTRACT_REL
        self.data = json.loads(self.path.read_text(encoding='utf-8'))
        for key in ('original_roots', 'navigation_roots', 'excluded_roots', 'navigation_prefixes', 'excluded_roles'):
            if not isinstance(self.data.get(key), list):
                raise ValueError('Invalid knowledge contract: ' + key)
        if not isinstance(self.data.get('reviewed_knowledge'), dict):
            raise ValueError('Invalid reviewed knowledge registry')

    def decision(self, path: Path) -> tuple[bool, str]:
        try:
            relative = path.resolve().relative_to(self.vault).as_posix()
        except ValueError:
            return False, 'outside_vault'
        root = relative.split('/')[0]
        if any(part.startswith('.') for part in Path(relative).parts):
            return False, 'system_file'
        if root in self.data['excluded_roots']:
            return False, 'excluded_root'
        if root in self.data['navigation_roots'] or any(relative.startswith(p) for p in self.data['navigation_prefixes']):
            return False, 'navigation_only'
        if not path.is_file() or path.is_symlink():
            return False, 'missing_or_symlink'
        approved = self.data['reviewed_knowledge'].get(relative)
        reviewed = bool(approved and approved.get('sha256') == hashlib.sha256(path.read_bytes()).hexdigest())
        if path.suffix.lower() in {'.md', '.markdown'}:
            text = path.read_text(encoding='utf-8-sig', errors='replace')
            meta = {}
            if text.startswith('---\n'):
                lines = text.splitlines()
                closing = next((i for i in range(1,len(lines)) if lines[i].strip() == '---'), None)
                if closing is None:
                    return False, 'invalid_frontmatter'
                try:
                    meta = yaml.safe_load('\n'.join(lines[1:closing])) or {}
                except yaml.YAMLError:
                    return False, 'invalid_frontmatter'
                if not isinstance(meta, dict):
                    return False, 'invalid_frontmatter'
            if meta.get('type') in self.data['excluded_roles']:
                return False, 'generated_or_navigation_note'
            if meta.get('generated_by') and not reviewed:
                return False, 'generated_or_navigation_note'
        if root in self.data['original_roots']:
            return True, 'original_material_unverified_facts'
        if reviewed:
            return True, 'reviewed_knowledge_hash_verified'
        return False, 'knowledge_review_pending'


def load_contract(vault: Path) -> KnowledgeContract | None:
    for folder in (vault.resolve(), *vault.resolve().parents):
        if (folder / CONTRACT_REL).is_file():
            return KnowledgeContract(folder)
    return None
