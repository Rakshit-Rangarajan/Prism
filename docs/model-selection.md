# Local model selection — 27 November 2026

The selected first model is **Qwen3-4B-Instruct-2507**, served as Q4_K_M GGUF by a portable CUDA llama.cpp server. It is a non-thinking 4B instruction model, with an Apache-2.0 license and upstream coding/tool-use capability. PRISM bounds context to 4,096 tokens instead of allocating its much larger advertised context. Hugging Face FP16/BF16 weights are retained separately for QLoRA; GGUF inference weights are not training inputs.

| Candidate | License / size | Fit for this task | Hardware evidence |
| --- | --- | --- | --- |
| [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | Apache-2.0; 4B | Selected: instruction, coding and tool use; suitable size for local inference and QLoRA | Tested on this RTX 3060 |
| [Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct) | MIT; 3.8B | Strong compact alternative for reasoning; requires the same PRISM schema/semantic evaluation | Not downloaded or benchmarked |
| [Gemma-3-4b-it](https://huggingface.co/google/gemma-3-4b-it) | Gemma custom terms; 4B | Open weights with custom conditions and access acceptance; multimodal capability is unnecessary here | Not downloaded or benchmarked |
| [Qwen2.5-Coder-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct) | Apache-2.0; 7B | SQL/code-oriented alternative; more memory and training pressure than 4B | Not downloaded or benchmarked |

A 4-bit 3–4B model should have more headroom than a 7B model within 12 GB, but total memory includes KV cache, compute buffers and the Windows desktop. This is a sizing inference, not a benchmark of the untested candidates. None of these pretrained models should be assumed to know company rules or safely execute transformations. Constrained JSON generation and deterministic validation remain mandatory.

## Measured locally

- Q4_K_M artifact: approximately 2.32 GiB; source [Unsloth's Qwen GGUF conversion](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF), retaining upstream licensing.
- llama.cpp CUDA 12.4 portable release b12774; NVIDIA driver 610.88.
- Total GPU memory while inference was loaded: approximately 4.75 GB, including roughly 1.6 GB desktop baseline.
- Initial real MySQL recommendation: 5.562 seconds; 1,522 prompt tokens and 395 output tokens.
- Second dataset with approved evidence: 6.585 seconds; 3,315 prompt tokens and 426 output tokens, before subsequent prompt compaction.
- Runtime generation logs in longer diagnostic calls: approximately 83–85 tokens/second. End-to-end request time includes prompt evaluation and JSON constraints.
- Actual NF4 QLoRA: 20 steps in 94.56 seconds including held-out evaluation; peak PyTorch allocation 7,376.77 MiB. Base held-out loss 1.9703 → adapter held-out loss 0.8221. Candidate saved, not promoted.

These measurements cover synthetic ERP quality analysis and finite rule selection, not a broad SQL benchmark. The first unconstrained transformation-language response suggested unsafe mappings; PRISM rejected it. The validated integration now lets the model select from useful, validated rule candidates, while human reviewers can correct bounded plans. This materially improves reliability without pretending that schema-constrained JSON guarantees semantic correctness.

## Runtime and training references

- [llama.cpp server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server): local OpenAI-compatible endpoint, GPU layers and schema-constrained responses.
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs): a viable alternate runtime; not benchmarked here. llama.cpp was chosen to keep this setup portable and avoid a system-level installation.
- [PEFT quantization guide](https://huggingface.co/docs/peft/main/en/developer_guides/quantization): NF4 quantization and preparation for adapter training.

After setup, inference and training use local files. No paid API key, cloud inference or internet access is required for the local migration workflow. Dependency installation/model acquisition and pushing Git/deploying still require internet access.
