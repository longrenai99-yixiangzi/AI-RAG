from __future__ import annotations

from pathlib import Path
from typing import Sequence
from types import MethodType


class BGERerankerProvider:
    """Real bge-reranker-v2-m3 provider; it has no Qdrant or index write responsibility."""

    def __init__(self, model_path: Path | str, *, use_fp16: bool = False, max_length: int = 512) -> None:
        self.model_path = Path(model_path)
        self.use_fp16 = use_fp16
        self.max_length = max_length
        self.model: object | None = None

    @property
    def ready(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        if self.model is not None:
            return
        if not self.model_path.is_dir():
            raise FileNotFoundError(f"Reranker 本地模型目录不存在：{self.model_path}")
        from FlagEmbedding import FlagReranker

        self.model = FlagReranker(str(self.model_path), use_fp16=self.use_fp16)
        _ensure_prepare_for_model(self.model.tokenizer)  # type: ignore[attr-defined]

    def score(self, question: str, passages: Sequence[str]) -> list[float] | None:
        if not passages:
            return []
        self.load()
        assert self.model is not None
        raw_scores = self.model.compute_score(  # type: ignore[attr-defined]
            [[question, passage] for passage in passages],
            batch_size=2,
            max_length=self.max_length,
            normalize=False,
        )
        if isinstance(raw_scores, (int, float)):
            return [float(raw_scores)]
        return [float(score) for score in raw_scores]

    def close(self) -> None:
        self.model = None


def _ensure_prepare_for_model(tokenizer: object) -> None:
    """Bridge FlagEmbedding 1.4.0 to Transformers 5 tokenizer API without upgrades."""

    if hasattr(tokenizer, "prepare_for_model"):
        return

    def prepare_for_model(
        self: object,
        ids: list[int],
        pair_ids: list[int] | None = None,
        *,
        truncation: str = "only_second",
        max_length: int | None = None,
        padding: bool = False,
        **kwargs: object,
    ) -> object:
        first = list(ids)
        second = list(pair_ids or [])
        if max_length is not None:
            special_tokens = (
                self.num_special_tokens_to_add(pair=True)  # type: ignore[attr-defined]
                if hasattr(self, "num_special_tokens_to_add")
                else 4
            )
            while len(first) + len(second) + special_tokens > max_length:
                if truncation == "only_second" and second:
                    second.pop()
                elif second and len(second) >= len(first):
                    second.pop()
                elif first:
                    first.pop()
                else:
                    break
        if hasattr(self, "build_inputs_with_special_tokens"):
            input_ids = self.build_inputs_with_special_tokens(first, second)  # type: ignore[attr-defined]
        else:
            bos_id = getattr(self, "bos_token_id", 0)
            eos_id = getattr(self, "eos_token_id", 2)
            input_ids = [bos_id, *first, eos_id, eos_id, *second, eos_id]
        return {
            "input_ids": input_ids,
            "attention_mask": [1] * len(input_ids),
        }

    setattr(tokenizer, "prepare_for_model", MethodType(prepare_for_model, tokenizer))
