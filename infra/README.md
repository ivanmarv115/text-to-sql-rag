# LLM infrastructure (real / GPU mode)

The app talks to two OpenAI-compatible [vLLM](https://github.com/vllm-project/vllm)
servers — a **big brain** (large dense model, used for SQL generation) and a
**small brain** (small quantized model, used for formatting / chat). This folder
holds genericized compose files to stand them up on GPU hosts.

> You only need this for `LLM_MODE=vllm`. The default demo runs in mock mode and
> needs none of it.

## Quick start

```bash
cp .env.example .env          # set your model ids + HF token
docker compose -f docker-compose.big-brain.yaml up -d     # serves on :8000
docker compose -f docker-compose.small-brain.yaml up -d   # serves on :8001
```

Then point the app at them (in the project root `.env`):

```env
LLM_MODE=vllm
VLLM_BIG_BRAIN_BASE_URL=http://<host>:8000/v1
VLLM_SMALL_BRAIN_BASE_URL=http://<host>:8001/v1
```

## Notes

- `--served-model-name` must match `VLLM_BIG_BRAIN_MODEL` / `VLLM_SMALL_BRAIN_MODEL`.
- Pick quantization to fit your GPUs (e.g. FP8 for the big model, INT4/GPTQ for
  the small one). Set `--max-model-len` to your context budget.
- Set `--api-key` and pass the same value via `VLLM_*_API_KEY` to the app.
- Pin the `vllm/vllm-openai` image tag for reproducibility.
