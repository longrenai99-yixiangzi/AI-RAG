from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "knowledge_os_v2_2" / "retrieval_ab"


def main() -> int:
    try:
        nvidia = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=10, check=False)
        nvidia_text = nvidia.stdout
    except Exception as error:
        nvidia_text = f"{type(error).__name__}: {error}"
    import torch
    payload = {"schema_version": "knowledge_os_v2_2.cuda", "captured_at": datetime.now(timezone.utc).astimezone().isoformat(), "nvidia_smi": nvidia_text, "torch_version": torch.__version__, "torch_cuda_version": torch.version.cuda, "cuda_available": bool(torch.cuda.is_available()), "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None, "dense_status": "NOT_RUN_CUDA_FAILURE", "reason": "GPU hardware is present but the active Python environment has CPU-only PyTorch; task requires stopping instead of falling back to CPU.", "vectors_written": False}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dense_gpu_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "docs" / "CUDA_FAILURE_REPORT.md").write_text(f"# CUDA Failure Report\n\n- GPU hardware detected: RTX 4060 class device via `nvidia-smi`.\n- PyTorch: `{torch.__version__}`; CUDA build: `{torch.version.cuda}`; `torch.cuda.is_available()`: `{torch.cuda.is_available()}`.\n- Dense V2 status: `NOT_RUN_CUDA_FAILURE`.\n- No CPU fallback was started; no vectors were written.\n\nNext action: install/activate a CUDA-enabled PyTorch environment, then resume the checkpointable Dense V2 encoder.\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("torch_version", "torch_cuda_version", "cuda_available", "device", "dense_status")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
