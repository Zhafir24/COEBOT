# COEBOT models directory

Drop a GGUF-format LLM file into this folder and COEBOT will use it
automatically on the next launch. No code changes required.

## Requirements

- Format: **GGUF** (single file, `.gguf` extension)
- Quantization: any (Q4_K_M recommended as the best speed/quality
  tradeoff on CPU)
- Chat-tuned: the model must be an "Instruct" / "Chat" variant, NOT a
  base completion model. RAG requires instruction following.
- Size: fits in RAM alongside the rest of the app (~24 GB free budget
  on a 32 GB machine, so keep model + KV cache under ~20 GB)

## Where to download GGUF files

Any of these HuggingFace publishers ship well-tested Q4_K_M builds:

- `bartowski/...` — most popular, keeps every model up to date
- `lmstudio-community/...` — curated, only well-behaved models
- `unsloth/...` — publisher of many models, active

Example search on HuggingFace: `<model-name> GGUF Q4_K_M`

## How COEBOT picks which file to load

1. If the `MODEL_FILENAME` environment variable is set (or in `.env`),
   it must name a `.gguf` file inside this folder — COEBOT uses that.
2. Otherwise, COEBOT loads the **first `.gguf` file it finds** in this
   folder (alphabetical order).
3. If no `.gguf` file exists, COEBOT shows a clear error at chat time
   telling you to place a model file here.

## Multi-model setups

If you want more than one model in this folder and pick which to load,
set `MODEL_FILENAME` in `.env` at the project root:

```
MODEL_FILENAME=qwen2.5-7b-instruct-q4_k_m.gguf
```

Then to switch models: change that one line, restart COEBOT.

## Files in this folder are gitignored

Model files are typically 3-20+ GB and don't belong in version control.
The project's `.gitignore` excludes `*.gguf` in this folder.
