from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from collections import Counter
from pathlib import Path

from qdrant_client import QdrantClient

from app.document_intelligence.profile_builder import (
    DocumentProfile,
    build_profile,
    link_related_documents,
)
from app.domain import Chunk
from app.evaluation.gold_dataset_loader import load_gold_questions
from app.ingestion.metadata.governance import GovernanceClassifier
from app.parsers import iter_source_files
from scripts.evaluate_shadow_retrieval import (
    COLLECTION_NAME,
    GOLD_PATH,
    SHADOW_DIR,
    _load_shadow_chunks,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Shadow Document Profiles from the persisted Shadow corpus.")
    parser.add_argument("--shadow-dir", type=Path, default=SHADOW_DIR)
    parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    parser.add_argument("--vault", type=Path, default=Path(r"D:\设计管理"))
    args = parser.parse_args()

    client = QdrantClient(path=str(args.shadow_dir))
    collection_count = client.count(COLLECTION_NAME, exact=True).count
    chunks, metadata_by_chunk = _load_shadow_chunks(client)
    client.close()

    grouped: dict[str, list] = {}
    for chunk in chunks:
        grouped.setdefault(chunk.document_id, []).append(chunk)
    shadow_paths = {chunk.source_path for chunk in chunks}
    for path in iter_source_files(args.vault):
        if str(path) in shadow_paths:
            continue
        document_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(path.resolve()).lower()))
        text = _read_file_preview(path)
        chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}|profile-only"))
        grouped[document_id] = [
            Chunk(
                chunk_id=chunk_id,
                document_id=document_id,
                ordinal=0,
                source_path=str(path),
                file_name=path.name,
                text=text,
                heading_path="",
                location={"file_level_only": True},
            )
        ]
        metadata_by_chunk[chunk_id] = {
            "file_type": path.suffix.lower(),
            "file_name": path.name,
            "source_path": str(path),
            "sha256": _sha256(path),
            "parse_status": "profile_only",
        }
    classifier = GovernanceClassifier()
    profiles: list[DocumentProfile] = []
    for document_id, document_chunks in sorted(grouped.items()):
        first = document_chunks[0]
        metadata = _merge_metadata(
            [metadata_by_chunk.get(chunk.chunk_id, {}) for chunk in document_chunks]
        )
        governance = classifier.classify(
            file_name=first.file_name,
            source_path=first.source_path,
            heading_path=" > ".join(
                dict.fromkeys(chunk.heading_path for chunk in document_chunks if chunk.heading_path)
            ),
            text="\n".join(chunk.text[:4_000] for chunk in document_chunks[:8]),
            metadata=metadata,
        )
        profiles.append(
            build_profile(
                document_id=document_id,
                document_name=first.file_name,
                source_path=first.source_path,
                file_type=str(metadata.get("file_type") or Path(first.file_name).suffix.lower()),
                sha256=str(metadata.get("sha256") or ""),
                chunks=document_chunks,
                metadata=metadata,
                governance=governance,
            )
        )
    profiles = link_related_documents(profiles)

    output_path = args.shadow_dir / "document_profiles.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(profile.to_dict(), ensure_ascii=False) + "\n" for profile in profiles),
        encoding="utf-8",
    )

    questions = load_gold_questions(args.gold, minimum=100)
    by_name = {profile.document_name.casefold(): profile for profile in profiles}
    expected_present = 0
    expected_role_match = 0
    expected_authority_match = 0
    expected_scene_match = 0
    for question in questions:
        matches = [
            by_name.get(expected.casefold())
            for expected in question.expected_files
            if by_name.get(expected.casefold()) is not None
        ]
        expected_present += int(bool(matches))
        expected_role_match += int(
            any(profile.document_role == question.expected_document_role for profile in matches)
        )
        expected_authority_match += int(
            any(profile.authority_level == question.expected_authority_level for profile in matches)
        )
        expected_scene_match += int(
            any(profile.usage_scene == question.expected_usage_scene for profile in matches)
        )

    low_confidence = [
        profile
        for profile in profiles
        if profile.profile_confidence < 0.8
    ]
    report = {
        "summary": {
            "collection_points": collection_count,
            "profile_count": len(profiles),
            "role_counts": dict(Counter(profile.document_role for profile in profiles)),
            "authority_counts": dict(Counter(profile.authority_level for profile in profiles)),
            "project_stage_counts": dict(Counter(
                profile.scope.get("project_stage", ["未识别"])[0]
                for profile in profiles
            )),
            "needs_review_count": sum(
                profile.profile_review_status == "NEEDS_REVIEW" for profile in profiles
            ),
            "low_confidence_count": len(low_confidence),
            "scope_present_count": sum(bool(profile.scope) for profile in profiles),
            "topics_present_count": sum(bool(profile.contains_topics) for profile in profiles),
            "related_link_count": sum(len(profile.related_documents) for profile in profiles),
            "gold_questions": len(questions),
            "gold_expected_file_present": expected_present,
            "gold_expected_role_match": expected_role_match,
            "gold_expected_authority_match": expected_authority_match,
            "gold_expected_scene_match": expected_scene_match,
            "profile_output": str(output_path.resolve()),
        },
        "low_confidence": [
            {
                "document_name": profile.document_name,
                "source_path": profile.source_path,
                "document_role": profile.document_role,
                "authority_level": profile.authority_level,
                "confidence": profile.profile_confidence,
                "review_status": profile.profile_review_status,
            }
            for profile in low_confidence
        ],
    }
    report_path = Path("docs") / "DOCUMENT_PROFILE_SHADOW_BUILD_REPORT.md"
    report_path.write_text(_render_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report={report_path.resolve()}")
    return 0


def _merge_metadata(values: list[dict]) -> dict:
    merged: dict = {}
    for value in values:
        for key, item in value.items():
            if item not in (None, "", [], {}):
                merged.setdefault(key, item)
    return merged


def _read_file_preview(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="strict")[:32_000]
    except (OSError, UnicodeError):
        return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1_048_576), b""):
                digest.update(block)
    except OSError:
        return ""
    return digest.hexdigest()


def _render_report(report: dict) -> str:
    summary = report["summary"]
    gold_total = summary["gold_questions"]
    lines = [
        "# Document Profile Shadow Build Report",
        "",
        "> 本报告基于 Shadow Qdrant 的 Chunk、Metadata、Governance Metadata 和文档结构生成 Document Profile。",
        "> 不调用 LLM，不修改正式 Retriever、8000 服务或正式 Qdrant。",
        "",
        "## 1. 构建范围",
        "",
        f"- Shadow Collection 点数：{summary['collection_points']}。",
        f"- Profile 生成数量：{summary['profile_count']}。",
        f"- Profile 输出：{summary['profile_output']}。",
        "- 生成来源：文件名、路径、标题/章节、已有 Metadata、Governance Metadata 和规则化关键词。",
        "",
        "## 2. Profile 字段",
        "",
        "每个 Profile 包含：document_id、document_name、document_role、authority_level、scope、contains_topics、not_for、related_documents、profile_source、profile_confidence、profile_review_status。",
        "",
        "## 3. 统计结果",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| Profile 数量 | {summary['profile_count']} |",
        f"| NEEDS_REVIEW 数量 | {summary['needs_review_count']} |",
        f"| 低置信度文件（<0.8） | {summary['low_confidence_count']} |",
        f"| 包含 scope 的文件 | {summary['scope_present_count']} |",
        f"| 包含 contains_topics 的文件 | {summary['topics_present_count']} |",
        f"| related_documents 关系数 | {summary['related_link_count']} |",
        "",
        f"- document_role 分布：{json.dumps(summary['role_counts'], ensure_ascii=False)}。",
        f"- authority_level 分布：{json.dumps(summary['authority_counts'], ensure_ascii=False)}。",
        f"- scope.project_stage 分布：{json.dumps(summary['project_stage_counts'], ensure_ascii=False)}。",
        "",
        "## 4. 100题 Gold expected_files 对账",
        "",
        "| 指标 | 数量 | 比例 |",
        "|---|---:|---:|",
        f"| Gold Questions | {gold_total} | 100.00% |",
        f"| expected_files 可找到 Profile | {summary['gold_expected_file_present']} | {summary['gold_expected_file_present'] / gold_total:.2%} |",
        f"| expected_document_role 匹配 | {summary['gold_expected_role_match']} | {summary['gold_expected_role_match'] / gold_total:.2%} |",
        f"| expected_authority_level 匹配 | {summary['gold_expected_authority_match']} | {summary['gold_expected_authority_match'] / gold_total:.2%} |",
        f"| expected_usage_scene 匹配 | {summary['gold_expected_scene_match']} | {summary['gold_expected_scene_match'] / gold_total:.2%} |",
        "",
        "该对账只验证 Profile 是否覆盖 Gold 指向的文件和治理字段，不代表文件内容已经被人工确认。",
        "",
        "## 5. 低置信度文件",
        "",
        "| 文件 | 角色 | 权威等级 | 置信度 | 状态 |",
        "|---|---|---|---:|---|",
    ]
    for item in report["low_confidence"][:100]:
        lines.append(
            f"| {item['document_name']} | {item['document_role']} | "
            f"{item['authority_level']} | {item['confidence']:.3f} | "
            f"{item['review_status']} |"
        )
    if not report["low_confidence"]:
        lines.append("| 无 | - | - | - | - |")
    lines.extend(
        [
            "",
            "## 6. 质量边界与后续",
            "",
            "1. 当前 Profile 为规则化 Shadow Profile，不调用 LLM，不自动写入正式索引。",
            "2. contains_topics 是可解释关键词候选，不是经过语义模型确认的完整主题摘要。",
            "3. not_for 仅来自明确限制语句或确定性角色边界；低置信度限制不应直接作为硬过滤条件。",
            "4. related_documents 当前只建立有共同项目范围证据的 related_to 关系，不自动推断 supersedes。",
            "5. 下一步应使用 Profile 做 Document-level Retrieval，并与 Chunk-only Retrieval 对比 Expected File Hit Rate。",
            "",
            "## 7. TASK-014E 边界确认",
            "",
            "| 验收项 | 结果 |",
            "|---|---|",
            "| 真实知识库 Shadow Document Profile | 已生成 |",
            "| Profile 字段完整 | 已生成 |",
            "| 角色和 authority 分布统计 | 已完成 |",
            "| NEEDS_REVIEW 和低置信度统计 | 已完成 |",
            "| 100题 expected_files 对账 | 已完成 |",
            "| 调用 LLM | 否 |",
            "| 修改正式 Retriever | 否 |",
            "| 修改 8000 服务 | 否 |",
            "| 修改正式 Qdrant | 否 |",
            "",
            "**TASK-014E：Document Profile Shadow Build 完成。**",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
