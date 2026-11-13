# Local Lingala model

Source: `Congo-digital-service/Llama-3.1-8B-Instruct-Lingala-QLoRA-merged-v2`.

Files are stored under `D:/AI-models/lingala-llama3.1-8b` because C: has little free space.
The original weights and license files are retained. Hugging Face credentials are not saved by the installer.

The downloaded `tokenizer_config.json` omits `tokenizer_class`. For llama.cpp conversion,
the local copy specifies `PreTrainedTokenizerFast`, using the unchanged `tokenizer.json` vocabulary.
Its original configuration is retained as `tokenizer_config.original.json`.

Conversion uses official llama.cpp release `b12110`:

```powershell
python D:/AI-models/tools/llama.cpp-b12110/convert_hf_to_gguf.py D:/AI-models/lingala-llama3.1-8b --outfile D:/AI-models/lingala-llama3.1-8b/lingala-f16.gguf --outtype f16
D:/AI-models/tools/bin/llama-quantize.exe D:/AI-models/lingala-llama3.1-8b/lingala-f16.gguf D:/AI-models/lingala-llama3.1-8b/lingala-Q4_K_M.gguf Q4_K_M
python scripts/install_lingala_ollama.py D:/AI-models/lingala-llama3.1-8b --gguf D:/AI-models/lingala-llama3.1-8b/lingala-Q4_K_M.gguf
```

The installer imports the quantized GGUF as `congo-lingala:8b` and tests generation.
Only after successful generation does it set `OLLAMA_LINGALA_MODEL` in `.env`.
Restart Django after activation. Requests with language `ln` then use the Lingala model;
Swahili and other languages continue using `OLLAMA_MODEL` (Qwen2.5 7B).

The smoke test verifies that inference works; it does not establish language quality or factual accuracy.
Review real Lingala answers before relying on this model for public service guidance.
