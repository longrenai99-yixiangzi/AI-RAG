import hashlib
import json
from pathlib import Path

import pytest

from app.knowledge_contract import CONTRACT_REL, KnowledgeContract
from app.parsers import iter_source_files
from app.ingestion.pipeline import run_document_pipeline


def write(root: Path, name: str, text: str = '原文') -> Path:
    path = root/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def test_contract_excludes_navigation_candidates_and_unreviewed_notes(tmp_path):
    vault = tmp_path/'vault'
    contract = {'original_roots':['raw'], 'navigation_roots':['01_设计管理','06_索引','00_AI系统'], 'excluded_roots':['99_Archive','07_AI候选知识'], 'navigation_prefixes':['wiki/entities/'], 'excluded_roles':['classification_navigation'], 'reviewed_knowledge':{}}
    raw = write(vault,'raw/制度.pdf')
    nested_original = write(vault,'raw/06_索引/原文.pdf')
    original_note = write(vault,'raw/工作总结/年度.md')
    reviewed = write(vault,'02_正式知识/已审核.md', '---\ngenerated_by: assistant\n---\n\n逐条审核后的知识')
    contract['reviewed_knowledge'] = {'02_正式知识/已审核.md':{'sha256':hashlib.sha256(reviewed.read_bytes()).hexdigest()}}
    write(vault, str(CONTRACT_REL), json.dumps(contract))
    for name in ['99_Archive/备份.pdf','07_AI候选知识/候选.md','01_设计管理/导航.md','06_索引/清单.md','00_AI系统/问答规则.md','wiki/concepts/未经审核.md','wiki/entities/项目.md','02_正式知识/仅声明已入库.md']:
        write(vault,name)
    write(vault,'raw/生成清单.md','---\ngenerated_by: classify-vault-v1\n---\n\n自动生成')
    assert set(iter_source_files(vault)) == {raw,nested_original,original_note,reviewed}
    assert iter_source_files(vault/'06_索引') == []
    assert set(iter_source_files(vault/'raw')) == {raw,nested_original,original_note}
    result = run_document_pipeline(vault, files=[vault/'06_索引/清单.md',original_note])
    assert [document.path for document in result.documents] == [original_note]
    reviewed.write_text('原审核版本已改变',encoding='utf-8')
    assert not KnowledgeContract(vault).decision(reviewed)[0]
    assert not KnowledgeContract(vault).decision(write(tmp_path,'外部.pdf'))[0]
    assert not KnowledgeContract(vault).decision(write(vault,'raw/无结束标记.md','---\ntitle: example'))[0]
    assert KnowledgeContract(vault).decision(write(vault,'raw/合法属性.md','---\ntitle: pre---post\n---\n原始记录'))[0]


def test_invalid_contract_fails_closed_and_generic_fixture_scanning_survives(tmp_path):
    write(tmp_path,'普通.md')
    assert len(iter_source_files(tmp_path)) == 1
    write(tmp_path,str(CONTRACT_REL),'{}')
    with pytest.raises(ValueError):
        iter_source_files(tmp_path)
