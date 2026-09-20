"""T09 补充 - 从业务文档真实章节生成候选问题（需人工确认后才入 Benchmark）。

原则：
    1. 只使用知识库中**真实存在**的文档标题与章节路径，不凭空编造业务事实；
    2. 生成结果标记为 CANDIDATE，未经确认不得进入 Development / Regression；
    3. 避免与已有 177 题重复。

输出：
    evaluation/knowledge_os_system_audit/t09/candidate_questions.json
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_system_audit" / "t09"
SECTION_PATH = (
    ROOT / "data" / "shadow" / "hierarchical_retrieval_v1_stabilization" / "section_index" / "records.jsonl"
)
EXISTING = [OUT / "development.json", OUT / "regression.json", OUT / "holdout.json"]
LIMIT = 120

# 章节标题中暗示"说明性内容"的词，适合生成"是什么/包含哪些"问题
DESCRIPTIVE_HINTS = (
    "要点", "要求", "内容", "职责", "流程", "标准", "管理", "措施", "规定",
    "方法", "原则", "依据", "范围", "定义", "清单", "制度", "计划", "机制",
)
NOISE_PATTERNS = (
    r"^\d+$", r"^第?[一二三四五六七八九十\d]+[章节]?$", r"^附?[录表图]\d*$",
    r"^[\s\-—_\.。、,，:：;；]+$", r"^目录$", r"^contents?$",
)


def is_meaningful(heading: str) -> bool:
    h = heading.strip()
    if not (4 <= len(h) <= 24):
        return False
    for pattern in NOISE_PATTERNS:
        if re.match(pattern, h, re.IGNORECASE):
            return False
    if not re.search(r"[\u4e00-\u9fff]", h):
        return False
    return True


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    existing: set[str] = set()
    for path in EXISTING:
        if not path.exists():
            continue
        for item in json.loads(path.read_text(encoding="utf-8")):
            existing.add(re.sub(r"\s+", "", str(item.get("question") or "")))

    records = [
        json.loads(line)
        for line in SECTION_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    # 按文件聚合章节，优先选择章节较多的文档（结构完整，问题更有意义）
    by_file: dict[str, list[str]] = defaultdict(list)
    for r in records:
        heading = str(r.get("heading_path") or r.get("heading") or "").strip()
        fname = str(r.get("file_name") or "").strip()
        if heading and fname:
            by_file[fname].append(heading)

    candidates: list[dict] = []
    seen_questions: set[str] = set()

    # 章节多的文档优先，保证候选问题有真实上下文支撑
    for fname, headings in sorted(by_file.items(), key=lambda x: -len(set(x[1]))):
        if len(candidates) >= LIMIT:
            break
        uniq = list(dict.fromkeys(headings))
        for heading in uniq:
            if len(candidates) >= LIMIT:
                break
            leaf = heading.split(">")[-1].strip()
            if not is_meaningful(leaf):
                continue
            # 只取含说明性语义的章节，避免生成无意义问题
            if not any(hint in leaf for hint in DESCRIPTIVE_HINTS):
                continue
            question = question_for(fname, leaf)
            key = re.sub(r"\s+", "", question)
            if key in existing or key in seen_questions:
                continue
            seen_questions.add(key)
            candidates.append(
                {
                    "candidate_id": f"C{len(candidates) + 1:03d}",
                    "question": question,
                    "source": "DOCUMENT_SECTION_CANDIDATE",
                    "source_file": fname,
                    "source_heading": heading,
                    "status": "PENDING_HUMAN_CONFIRM",
                    "types": ["事实题"],
                }
            )

    payload = {
        "task": "T09_CANDIDATE_GENERATION",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "policy": [
            "候选问题由真实文档标题与章节路径生成，不含编造的业务事实",
            "必须经业务负责人确认后才可进入 Benchmark",
            "未确认前不参与任何指标计算",
        ],
        "existing_question_count": len(existing),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    (OUT / "candidate_questions.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    review = ["# Benchmark 候选问题确认表", "", "> 候选均来自真实文档标题与章节，勾选仅表示问题适合纳入评估；不等于确认答案。", "", "| 选择 | ID | 问题 | 来源章节 |", "|---|---|---|---|"]
    review.extend(f"| [ ] | {item['candidate_id']} | {item['question']} | {item['source_file']} · {item['source_heading']} |" for item in candidates)
    (OUT / "candidate_review.md").write_text("\n".join(review) + "\n", encoding="utf-8")

    print(f"[T09-CANDIDATE] 已有问题 {len(existing)} 条，新增候选 {len(candidates)} 条")
    for c in candidates[:8]:
        print(f"  {c['candidate_id']}  {c['question']}")
    print(f"[T09-CANDIDATE] 输出: {OUT / 'candidate_questions.json'}")
    return 0


def question_for(file_name: str, heading: str) -> str:
    if "职责" in heading:
        return f"《{file_name}》中“{heading}”由谁负责，职责边界是什么？"
    if "流程" in heading:
        return f"《{file_name}》中“{heading}”应按什么流程执行？"
    if any(marker in heading for marker in ("要求", "标准", "规定")):
        return f"《{file_name}》中“{heading}”有哪些明确要求？"
    if "计划" in heading:
        return f"《{file_name}》中“{heading}”安排了哪些重点任务？"
    if any(marker in heading for marker in ("风险", "措施")):
        return f"《{file_name}》中“{heading}”识别了哪些风险及应对措施？"
    return f"《{file_name}》中“{heading}”包含哪些内容？"


if __name__ == "__main__":
    raise SystemExit(main())
