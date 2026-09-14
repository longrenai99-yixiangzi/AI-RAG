from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "evaluation" / "knowledge_os_v2_6"


def citation_lines(citations: list[dict]) -> list[str]:
    lines = []
    for index, citation in enumerate(citations, start=1):
        location = citation.get("display_location") or citation.get("location") or citation.get("heading_path") or "位置未记录"
        excerpt = str(citation.get("excerpt") or "").replace("\n", " ")[:320]
        lines.append(f"- [{index}] `{citation.get('file_name') or '文件名未记录'}`；位置：`{location}`；路径：`{citation.get('source_path') or '路径未记录'}`" + (f"；摘录：{excerpt}" if excerpt else ""))
    return lines or ["- 无引用"]


def main() -> int:
    payload = json.loads((V26 / "live_shadow_manual_review.json").read_text(encoding="utf-8"))
    lines = ["# V2.6 Live Shadow 人工核验表", "", "> 这是对既有真实请求的只读重放，答案来自当前 Primary/V2.5 代码，不修改原始 Live Shadow 记录。请核对答案事实、项目/年份范围、来源定位和 Citation 是否支持。", "", f"- 待核验：{payload['review_count']} 条（New Hit {payload['new_hit_count']}，Lost Hit {payload['lost_hit_count']}）", "- 当前决策：`PENDING_OWNER_REVIEW`", ""]
    for row in payload.get("records") or []:
        primary = row.get("replayed_primary") or {}
        shadow = row.get("replayed_v2_5") or {}
        lines += [f"## {row['review_id']} · {row['candidate_type']}", "", f"**问题**：{row['question']}", "", f"**历史候选**：V1 `{row['historical'].get('v1_status_at_request')}` → V2.5 `{row['historical'].get('v2_status_at_request')}`", "", "### 当前 Primary 重放答案", "", f"状态：`{primary.get('status', '重放失败')}`", "", str(primary.get("answer") or "（无答案正文）"), "", "引用：", *citation_lines(primary.get("citations") or []), "", "### V2.5 重放答案", "", f"状态：`{shadow.get('status', '重放失败')}`；Bundle：`{shadow.get('bundle_status', '未知')}`", "", str(shadow.get("answer") or "（无答案正文）"), "", "引用：", *citation_lines(shadow.get("citations") or []), "", "### 人工核验结果", "", f"**已确认决定：`{row.get('manual_decision') or 'PENDING'}`**", f"核验人：{row.get('reviewer') or '未记录'}；时间：{row.get('reviewed_at') or '未记录'}", "", "- 备注：", row.get("review_note") or "", "", "---", ""]
    (ROOT / "docs" / "LIVE_SHADOW_MANUAL_REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"review_count": payload["review_count"], "output": str(ROOT / "docs" / "LIVE_SHADOW_MANUAL_REVIEW.md")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
