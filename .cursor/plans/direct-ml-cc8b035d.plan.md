<!-- cc8b035d-4639-41b3-ad31-a1aadf2ffa82 950a679e-bc10-4ce2-ae84-531c4b95816d -->
# Add Optional DirectML Backend With CUDA-First Fallback

## Goal

Introduce a tiny abstraction that selects the best available backend at runtime:
1) CUDA if available, else 2) DirectML on Windows, else 3) CPU. Apply it in `SentenceTransformer` embedder and CrossEncoder reranker with minimal edits. Keep behavior unchanged on CUDA systems.

## Files to Add/Change

- Add: `rag_engine/utils/device.py` (backend detection helper)
- Edit: `rag_engine/retrieval/embedder.py` (move model to selected device)
- Edit: `rag_engine/retrieval/reranker.py` (move model to selected device)
- Optional docs: `README.md` (usage notes and install variants)
- Optional requirements note: do not hard-pin `torch-directml`; document install instead

## Key Implementation Details

- `rag_engine/utils/device.py`:
- `detect_torch_device() -> tuple[Literal["cuda","directml","cpu"], Optional[object]]`
- Prefers `torch.cuda.is_available()`
- Else tries `import torch_directml; torch_directml.device()`
- Else CPU via `torch.device("cpu")`
- `get_onnx_providers() -> list[str]`
- Returns providers in priority order among those installed: `CUDAExecutionProvider`, `DmlExecutionProvider`, `CPUExecutionProvider`
- In `embedder.py` and `reranker.py`:
- Import `detect_torch_device`
- After model init, if device is not None: `model.to(device)`
- No behavioral change for CPUs/CUDA; new path enables DirectML seamlessly when available
- Keep try/except style consistent with existing `reranker.py` import guards
- Avoid adding hard dependencies; prefer docs instructing `pip install torch-directml` or `onnxruntime-directml` when needed

## Testing

- Unit smoke: existing tests (no GPU assumptions) should pass
- Local validation (manual):
- CPU-only env: models load on CPU
- NVIDIA+CUDA: stays on `cuda:0`
- Intel/AMD on Windows with `torch-directml`: uses DirectML device
- Optional tiny runtime probe in a dev script to print selected backend (not added to repo)

## Linting

- Run Ruff only on modified files; ensure no new warnings beyond project standards

## Documentation

- In `README.md`: short section “GPU Backends”: CUDA (default if present), DirectML (Windows; install `torch-directml`), ONNX Runtime provider names (`CUDAExecutionProvider`, `DmlExecutionProvider`).

## Backout

- Remove `device.py` import lines and calls; no storage or schema changes, fully reversible.

### To-dos

- [ ] Add backend helper `rag_engine/utils/device.py` for CUDA/DirectML/CPU
- [ ] Use helper to move SentenceTransformer to selected device
- [ ] Use helper to move CrossEncoder to selected device
- [ ] Document CUDA/DirectML usage and installs in README
- [ ] Run Ruff on changed files and fix actionable issues
- [ ] Manual smoke on CPU, CUDA, and DirectML environments