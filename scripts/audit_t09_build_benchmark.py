"""T09 - 建立真实业务问题 Benchmark（Development / Regression / Holdout 三层隔离）。

问题来源（按真实性优先级）：
    1. 内部试用真实提问       evaluation/v2_8010_trial/trial_audit.jsonl
    2. 业务验收题             tests/gold_questions/business_acceptance_10.yaml
    3. 已审核问题变体         data/shadow/knowledge_os/state.json -> question_variants
    4. 全库候选 Gold（需人工确认来源） tests/gold_questions/full_corpus_gold_questions.yaml

分层原则：
    Development  允许开发人员查看，用于定位问题
    Regression   用于持续回归
    Holdout      开发人员不得根据其答案调整规则；首次结果永久保留

输出：
    evaluation/knowledge_os_system_audit/t09/
        manifest.json
        development.json
        regression.json
        holdout.json
        holdout_first_run.json   （首次结果，一旦存在不再覆盖）
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_system_audit" / "t09"
TRIAL_AUDIT = ROOT / "evaluation" / "v2_8010_trial" / "trial_audit.jsonl"
STATE_PATH = ROOT / "data" / "shadow" / "knowledge_os" / "state.json"
FCQ_PATH = ROOT / "tests" / "gold_questions" / "full_corpus_gold_questions.yaml"
BA_PATH = ROOT / "tests" / "gold_questions" / "business_acceptance_10.yaml"
CONFIRMED_PATH = OUT / "recommended_22.json"

SEED = 20260909
SEALED_HOLDOUT_COUNT = 30
TRIAL_REGRESSION_COUNT = 47

TYPE_RULES: list[tuple[str, str]] = [
    ("数量题", r"(多少|几[个条项家份次人座]|总数|数量|合计)"),
    ("列举题", r"(哪些|列出|包含哪些|包括哪些|哪几)"),
    ("比较题", r"(比选|比较|区别|优缺点|差异|对比)"),
    ("判断题", r"(是否|能不能|有没有|可否|能否)"),
    ("总结题", r"(总结|概述|总体|归纳|复盘)"),
    ("组织题", r"(公司|部门|中心|组织|岗位|架构|层级)"),
    ("项目题", r"(项目)"),
    ("年份题", r"(20\d{2})"),
    ("制度题", r"(制度|规定|办法|要求|规范|流程|细则)"),
    ("关系题", r"(关系|隶属|归口|对接|接口)"),
]


def detect_types(question: str) -> list[str]:
    types = [name for name, pattern in TYPE_RULES if re.search(pattern, question)]
    return types or ["事实题"]


def load_trial_questions() -> list[dict]:
    """内部试用期间真实提问，并附带历史回答状态分布。"""
    if not TRIAL_AUDIT.exists():
        return []
    buckets: dict[str, dict] = {}
    for line in TRIAL_AUDIT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        q = str(row.get("question") or "").strip()
        if not q:
            continue
        item = buckets.setdefault(
            q,
            {
                "question": q,
                "source": "TRIAL_QUERY_LOG_UNVERIFIED",
                "run_count": 0,
                "answer_status_counts": Counter(),
                "had_failure": False,
            },
        )
        item["run_count"] += 1
        status = str(row.get("answer_status") or "")
        item["answer_status_counts"][status] += 1
        if status in {"SOURCE_SCOPE_MISSING", "INSUFFICIENT_EVIDENCE", "CONFLICTING_ANSWER", "PARTIAL_ANSWER"}:
            item["had_failure"] = True
    for item in buckets.values():
        item["answer_status_counts"] = dict(item["answer_status_counts"])
    return list(buckets.values())


def load_yaml_questions(path: Path, source: str) -> list[dict]:
    if not path.exists():
        return []
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = []
    for q in data.get("questions") or []:
        if not q.get("question"):
            continue
        rows.append(
            {
                "question": str(q["question"]).strip(),
                "source": source,
                "question_ref": q.get("id"),
                "topic": q.get("topic"),
                "expected_files": list(q.get("expected_files") or []),
                "difficulty": q.get("difficulty"),
                "run_count": 0,
                "had_failure": False,
            }
        )
    return rows


def load_variants() -> list[dict]:
    if not STATE_PATH.exists():
        return []
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    rows = []
    for vid, v in (state.get("question_variants") or {}).items():
        text = str(v.get("text") or "").strip()
        if not text:
            continue
        rows.append(
            {
                "question": text,
                "source": "APPROVED_QUESTION_VARIANT",
                "question_ref": vid,
                "usage": v.get("usage"),
                "knowledge_id": v.get("knowledge_id"),
                "run_count": 0,
                "had_failure": False,
            }
        )
    return rows


def load_owner_confirmed_candidates() -> list[dict]:
    if not CONFIRMED_PATH.exists():
        return []
    payload = json.loads(CONFIRMED_PATH.read_text(encoding="utf-8"))
    if not str(payload.get("status") or "").startswith("OWNER_CONFIRMED"):
        return []
    return [
        {
            **row,
            "source": "OWNER_CONFIRMED_DOCUMENT_SECTION",
            "question_ref": row.get("candidate_id"),
            "expected_files": [row.get("source_file")],
            "run_count": 0,
            "had_failure": False,
        }
        for row in payload.get("questions") or []
        if row.get("question") and row.get("source_file")
    ]


def load_sealed_holdout_questions() -> set[str]:
    path = OUT / "holdout_first_run.json"
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows") or payload.get("results") or payload.get("questions") or []
    return {re.sub(r"\s+", "", str(row.get("question") or row.get("query") or "")) for row in rows}


def load_knowledge_and_feedback() -> list[dict]:
    """已审核知识的标准问/相似问/反例，以及用户真实反馈问题。

    这些都是业务确认过的真实问题资产，不是开发人员临时编造。
    """
    if not STATE_PATH.exists():
        return []
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    rows: list[dict] = []

    def add(text: str, source: str, *, usage: str = "", ref: str = "") -> None:
        text = str(text or "").strip()
        if not text:
            return
        rows.append(
            {
                "question": text,
                "source": source,
                "question_ref": ref,
                "usage": usage,
                "run_count": 0,
                "had_failure": False,
            }
        )

    for kid, k in (state.get("knowledge") or {}).items():
        add(k.get("standard_question"), "APPROVED_KNOWLEDGE_STANDARD", usage="STANDARD", ref=kid)
        for item in k.get("similar_questions") or []:
            add(item, "APPROVED_KNOWLEDGE_SIMILAR", usage="SIMILAR", ref=kid)
        for item in k.get("negative_questions") or []:
            add(item, "APPROVED_KNOWLEDGE_NEGATIVE", usage="NEGATIVE", ref=kid)

    for fid, f in (state.get("feedback") or {}).items():
        add(f.get("question"), "USER_FEEDBACK_QUESTION", usage="FEEDBACK", ref=fid)
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    random.seed(SEED)

    trial = load_trial_questions()
    ba = load_yaml_questions(BA_PATH, "BUSINESS_ACCEPTANCE")
    fcq = load_yaml_questions(FCQ_PATH, "FULL_CORPUS_GOLD")
    variants = load_variants()
    approved = load_knowledge_and_feedback()
    confirmed = load_owner_confirmed_candidates()

    print(
        f"[T09] 真实提问 {len(trial)} / 业务验收 {len(ba)} / 全库 Gold {len(fcq)} / "
        f"变体 {len(variants)} / 已审核知识与反馈 {len(approved)}"
    )

    # 去重（按问题文本）
    seen: set[str] = set()
    pool: list[dict] = []
    for group in (trial, variants, approved, ba, fcq, confirmed):
        for item in group:
            key = re.sub(r"\s+", "", item["question"])
            if key in seen:
                continue
            seen.add(key)
            pool.append(item)

    for idx, item in enumerate(pool, start=1):
        item["question_id"] = f"Q{idx:03d}"
        item["types"] = detect_types(item["question"])

    # 分层：按题面保持首次运行已封存的 Holdout，不得重新随机切分。
    real_indices = [i for i, item in enumerate(pool) if item["source"] == "TRIAL_QUERY_LOG_UNVERIFIED"]
    sealed_questions = load_sealed_holdout_questions()
    holdout_set = {i for i in real_indices if re.sub(r"\s+", "", pool[i]["question"]) in sealed_questions}
    if not sealed_questions:
        random.shuffle(real_indices)
        holdout_set = set(real_indices[:SEALED_HOLDOUT_COUNT])
    regression_candidates = [i for i in real_indices if i not in holdout_set]
    random.shuffle(regression_candidates)
    regression_set = set(regression_candidates[:TRIAL_REGRESSION_COUNT])

    # 已审核的变体/标准问/反馈问题本身就是回归资产，放入 Regression
    regression_sources = {
        "APPROVED_QUESTION_VARIANT",
        "APPROVED_KNOWLEDGE_STANDARD",
        "APPROVED_KNOWLEDGE_SIMILAR",
        "APPROVED_KNOWLEDGE_NEGATIVE",
        "USER_FEEDBACK_QUESTION",
    }
    for i, item in enumerate(pool):
        if item["source"] in regression_sources:
            regression_set.add(i)

    development = [item for i, item in enumerate(pool) if i not in holdout_set and i not in regression_set]
    regression = [pool[i] for i in sorted(regression_set)]
    holdout = [pool[i] for i in sorted(holdout_set)]
    if sealed_questions:
        assert {re.sub(r"\s+", "", item["question"]) for item in holdout} == sealed_questions, "SEALED_HOLDOUT_DRIFT"

    # Holdout 不携带期望来源，避免开发期参照答案调整规则
    holdout_public = [
        {
            "question_id": item["question_id"],
            "question": item["question"],
            "source": item["source"],
            "types": item["types"],
            "expected_files": item.get("expected_files") or [],
        }
        for item in holdout
    ]

    manifest = {
        "task": "T09_BENCHMARK",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "seed": SEED,
        "total_questions": len(pool),
        "benchmark_status": "OWNER_CONFIRMED_200_QUESTIONS" if len(pool) == 200 and len(confirmed) == 22 else "PROVISIONAL_QUESTION_COUNT_OR_CONFIRMATION_INCOMPLETE",
        "development_count": len(development),
        "regression_count": len(regression),
        "holdout_count": len(holdout),
        "source_distribution": dict(Counter(item["source"] for item in pool)),
        "type_distribution": dict(Counter(t for item in pool for t in item["types"])),
        "holdout_policy": {
            "rule": "Holdout 结果不得用于调整规则；首次结果一旦写入 holdout_first_run.json 不再覆盖",
            "sealed": (OUT / "holdout_first_run.json").exists(),
        },
        "notes": [
            "8010 query log 混有用户提问、浏览器验收和开发探测，未完成来源确认前不得全部称为真实业务问题",
            "FULL_CORPUS_GOLD 为既有候选集，expected_files 需内容负责人确认后才可作为标准答案",
            "题型由规则自动标注，仅用于分层统计，不作为答案判据",
            "22道文档章节题已由内容负责人确认题目适合纳入；该确认不等于确认答案内容",
        ],
    }

    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "development.json").write_text(json.dumps(development, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "regression.json").write_text(json.dumps(regression, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "holdout.json").write_text(json.dumps(holdout_public, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[T09] 总计 {len(pool)} 题 -> Development {len(development)} / Regression {len(regression)} / Holdout {len(holdout)}")
    print(f"[T09] 来源分布: {manifest['source_distribution']}")
    print(f"[T09] 题型分布: {manifest['type_distribution']}")
    print(f"[T09] 输出目录: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
