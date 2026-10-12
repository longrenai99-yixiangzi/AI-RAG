"""Version-bound project navigation; source ownership is explicitly reviewed."""
import json
import re
from functools import lru_cache
from pathlib import Path
from fastapi import HTTPException


@lru_cache(maxsize=2)
def load_navigation(root: Path, candidate_hash: str) -> dict:
    path = root/'project_navigation.json'
    if not path.is_file():
        return {'projects': [], 'periods': []}
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('candidate_hash') != candidate_hash:
        raise RuntimeError('NAVIGATION_CANDIDATE_VERSION_MISMATCH')
    return data


def question_project(question: str, navigation: dict) -> dict | None:
    matches = [p for p in navigation['projects'] if any(alias in question for alias in p['aliases'])]
    return matches[0] if len(matches)==1 else None


def record_in_project(record: dict, project: dict) -> bool:
    identities = {(s['source_id'],s['source_version']) for s in project['sources']}
    if (record.get('source_id'),record.get('source_version')) in identities:
        return True
    card = record.get('knowledge_card') or {}
    versions = {s['source_version'] for s in project['sources']}
    return card.get('approval_status')=='OWNER_CONFIRMED' and any(r.get('sha256') in versions for r in card.get('primary_sources') or [])


def resolve_project_question(question: str, project_id: str, navigation: dict, plan: dict) -> str:
    project = next((p for p in navigation['projects'] if p['id']==project_id),None)
    if not project:
        raise HTTPException(400,'请选择已核对资料归属的项目。')
    if any(p['id']!=project_id and any(alias in question for alias in p['aliases']) for p in navigation['projects']):
        raise HTTPException(400,'问题中的项目与当前选择不同，请先切换项目；跨项目比较请退出单项目范围。')
    if any(not any(alias in value for alias in project['aliases']) for value in plan.get('project') or []):
        raise HTTPException(400,'问题中的项目与当前选择不同，请先切换项目。')
    return question if any(alias in question for alias in project['aliases']) else project['name']+'：'+question


def page_number(record: dict) -> int | None:
    heading = str(record.get('heading_path') or record.get('section_path') or '')
    match = re.search(r'(?:Slide\s*|第\s*)(\d+)',heading,re.I)
    return int(match[1]) if match else None


def subject_records(records: list[dict], project: dict, subject: dict) -> list[dict]:
    pages = set(subject['pages'])
    results=[]
    seen=set()
    for record in records:
        prefixes = subject.get('section_prefixes') or []
        position_match = str(record.get('heading_path') or '').startswith(tuple(prefixes)) if prefixes else page_number(record) in pages
        if not record_in_project(record,project) or not position_match:
            continue
        body = str(record.get('raw_text') or '')
        if len(body.strip())<15 or body in seen:
            continue
        seen.add(body);results.append(record)
    return sorted(results,key=lambda r:(0 if str(r.get('file_name','')).endswith('.pptx') else 1,page_number(r) or 0))
