"""一次性修复：把 models/bge-m3/pytorch_model.bin 转为 safetensors 到独立目录。

背景（审计发现）：
    torch 2.13.0+cpu 在 Windows 上使用默认的 `weights_only=True` 反序列化路径读取
    BGE-M3 的旧格式 pytorch_model.bin（2.27GB / 391 tensors）时，会在真正读取张量数据
    阶段抛出 "Windows fatal exception: access violation"（段错误，EXIT=139）。
    已验证的排除项：文件未损坏（2,271,145,830 字节全量可读、sha256 正常）、
    F.embedding 算子正常、1GB 与 2.19GB 随机 checkpoint roundtrip 均正常、
    与 OMP 线程数（1/2/4/8）无关、与 Qdrant 客户端无关。
    可用路径：`torch.load(..., weights_only=False, mmap=False)` 可正常加载。

修复策略（不修改原始模型目录）：
    读旧 checkpoint -> 检出共享存储并克隆 -> 保存为 safetensors 到 models/bge-m3-st/
    后续 transformers / FlagEmbedding 优先读 safetensors，绕开有缺陷的反序列化路径。
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import torch  # noqa: E402

SRC = ROOT / "models" / "bge-m3"
DST = ROOT / "models" / "bge-m3-st"
SKIP_FILES = {"pytorch_model.bin", ".cache"}
SKIP_DIRS = {".cache", "onnx"}


def main() -> int:
    if not (SRC / "pytorch_model.bin").is_file():
        print(f"ERROR: source checkpoint missing: {SRC / 'pytorch_model.bin'}")
        return 2
    started = time.perf_counter()

    print(f"[fix] loading {SRC / 'pytorch_model.bin'} with weights_only=False ...", flush=True)
    state = torch.load(str(SRC / "pytorch_model.bin"), map_location="cpu", weights_only=False, mmap=False)
    print(f"[fix] loaded {len(state)} tensors in {time.perf_counter() - started:.1f}s", flush=True)

    # safetensors 不允许共享存储，检出并克隆
    seen: dict[int, str] = {}
    shared: list[tuple[str, str]] = []
    tensors: dict[str, torch.Tensor] = {}
    for key, value in state.items():
        if not isinstance(value, torch.Tensor):
            print(f"[fix] skip non-tensor key: {key}")
            continue
        tensor = value.detach().contiguous()
        try:
            ptr = tensor.untyped_storage().data_ptr()
        except Exception:  # noqa: BLE001
            ptr = id(tensor)
        if ptr in seen:
            shared.append((key, seen[ptr]))
        else:
            seen[ptr] = key
        tensors[key] = tensor
    for key, _origin in shared:
        tensors[key] = tensors[key].clone()
    print(f"[fix] tensors={len(tensors)} shared_cloned={len(shared)}", flush=True)

    DST.mkdir(parents=True, exist_ok=True)
    try:
        from safetensors.torch import save_file

        out_path = DST / "model.safetensors"
        save_file(tensors, str(out_path), metadata={"format": "pt", "source": "bge-m3/pytorch_model.bin"})
        print(f"[fix] wrote {out_path} ({out_path.stat().st_size / 1024**3:.2f} GB)", flush=True)
    except ImportError:
        out_path = DST / "pytorch_model.bin"
        torch.save(tensors, str(out_path))
        print(f"[fix] safetensors unavailable; wrote {out_path} instead", flush=True)

    # 复制其余模型文件（配置 / 分词器 / pooling）
    copied = []
    for item in sorted(SRC.iterdir()):
        if item.name in SKIP_FILES or (item.is_dir() and item.name in SKIP_DIRS):
            continue
        target = DST / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
        copied.append(item.name)
    print(f"[fix] copied {len(copied)} files: {', '.join(copied)}", flush=True)

    report = {
        "source": str(SRC),
        "destination": str(DST),
        "tensors": len(tensors),
        "shared_cloned": [{"key": k, "shares_with": o} for k, o in shared],
        "output_file": out_path.name,
        "output_gb": round(out_path.stat().st_size / 1024**3, 2),
        "elapsed_seconds": round(time.perf_counter() - started, 1),
    }
    (ROOT / "evaluation" / "knowledge_os_system_audit" / "t11_pilot").mkdir(parents=True, exist_ok=True)
    (ROOT / "evaluation" / "knowledge_os_system_audit" / "t11_pilot" / "bge_m3_checkpoint_fix.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
