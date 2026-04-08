# Gemma 4 - Deploiement local (Linux)

## A. Ollama (le plus simple)

Necessite Ollama v0.20.0+.

```bash
# Installation
curl -fsSL https://ollama.com/install.sh | sh

# Lancer un modele
ollama run gemma4           # defaut E4B (~9.6 Go download)
ollama run gemma4:e2b       # plus petit (~7.2 Go)
ollama run gemma4:e4b       # edge (~9.6 Go)
ollama run gemma4:26b       # MoE (~18 Go)
ollama run gemma4:31b       # plus capable (~20 Go)
```

Sampling recommande : `temperature=1.0, top_p=0.95, top_k=64`

## B. llama.cpp (CPU/GPU, flexibilite max)

```bash
# Build CPU-only (notre cas)
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build -DGGML_CUDA=OFF
cmake --build build --config Release

# Telecharger un GGUF quantize
huggingface-cli download unsloth/gemma-4-26B-A4B-it-GGUF \
  gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf \
  --local-dir ./models

# Inference directe
./build/bin/llama-cli \
  -m ./models/gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf \
  -p "Ton prompt ici"

# Serveur OpenAI-compatible
./build/bin/llama-server \
  -m ./models/gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf \
  --host 0.0.0.0 --port 8080
```

## C. vLLM (serving haute performance, necessite GPU)

```bash
uv venv && source .venv/bin/activate
uv pip install -U vllm --pre \
  --extra-index-url https://wheels.vllm.ai/nightly/cu129 \
  --extra-index-url https://download.pytorch.org/whl/cu129 \
  --index-strategy unsafe-best-match
uv pip install transformers==5.5.0

# Servir E4B
vllm serve google/gemma-4-E4B-it --max-model-len 131072

# Servir 31B avec tensor parallelism (2x GPU)
vllm serve google/gemma-4-31B-it \
  --tensor-parallel-size 2 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90
```

## D. Hugging Face Transformers

```bash
pip install -U transformers
```

```python
from transformers import pipeline

pipe = pipeline("any-to-any", model="google/gemma-4-e4b-it", device_map="auto")
messages = [{"role": "user", "content": [{"type": "text", "text": "Hello"}]}]
output = pipe(messages, max_new_tokens=512, return_full_text=False)
print(output[0]["generated_text"])
```

## E. LM Studio (GUI)

Tailles de telechargement GGUF : E2B = 4.2 Go, E4B = 5.9 Go, 26B A4B = 17 Go, 31B = 19 Go.

## Recommandation pour notre machine (CPU-only, 62 Go RAM)

**Methode 1 (simple)** : Ollama
```bash
ollama run gemma4:26b
```

**Methode 2 (controle fin)** : llama.cpp avec GGUF Q4_K_XL
- Permet de configurer le nombre de threads, le batch size, etc.
- Plus rapide qu'Ollama dans certains cas

## Notes importantes

- **Thinking mode** : activer avec `<|think|>` dans le system prompt
- **Token EOS** : utiliser `<turn|>`
- **Audio** : seulement E2B et E4B (max 30s audio, max 60s video)
- **26B A4B** : tres efficace en CPU car seulement 3.8B params actifs malgre 25.2B total
