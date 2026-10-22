from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RRFCandidate:
    chunk_id: str
    score: float
    ranks: dict[str, int]


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[str]], rank_constant: int = 60
) -> list[RRFCandidate]:
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    for source, ranked in ranked_lists.items():
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (rank_constant + rank)
            ranks.setdefault(chunk_id, {})[source] = rank
    return [
        RRFCandidate(chunk_id=chunk_id, score=score, ranks=ranks[chunk_id])
        for chunk_id, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ]
