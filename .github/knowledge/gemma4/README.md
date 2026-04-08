# Gemma 4 - Knowledge Base

## Vue d'ensemble

**Gemma 4** est la dernière famille de modèles open-source de Google DeepMind, sortie le **2 avril 2026**.
Basée sur la meme fondation que Gemini 3, sous licence **Apache 2.0** (usage commercial libre).

## Variantes

| Variante | Params totaux | Params actifs | Couches | Contexte | Modalites |
|----------|--------------|---------------|---------|----------|-----------|
| **E2B** | 5.1B | 2.3B | 35 | 128K | Texte, Image, Video, Audio |
| **E4B** | 8B | 4.5B | 42 | 128K | Texte, Image, Video, Audio |
| **26B A4B (MoE)** | 25.2B | 3.8B actifs | 30 | 256K | Texte, Image, Video |
| **31B (Dense)** | 30.7B | 30.7B | 60 | 256K | Texte, Image, Video |

Chaque variante existe en **base** (pre-trained) et **instruction-tuned (IT)**.

## Architecture

- **Attention hybride** : alternance sliding-window local + attention globale full-context
- **Sliding window** : 512 tokens (E2B/E4B), 1024 tokens (26B/31B)
- **Dual RoPE** : RoPE standard (sliding) + Proportional RoPE (global, pour le long contexte)
- **Per-Layer Embeddings (PLE)** : signal residuel a chaque couche (E2B/E4B)
- **Shared KV Cache** : les N dernieres couches reutilisent le KV cache des couches precedentes
- **Vision encoder** : ~150M params (E2B/E4B), ~550M params (26B/31B)
- **Audio encoder** : USM conformer ~300M params (E2B/E4B uniquement, max 30s audio)
- **MoE (26B A4B)** : 128 experts, 8 actifs par token

## Capacites cles

- Mode thinking configurable (`<|think|>`)
- Function calling natif / tool use (workflows agentiques)
- Support role systeme natif
- Multilingue : 140+ langues
- Vision : OCR, detection objets, GUI, captioning, comprehension video
- Audio : ASR, traduction vocale (E2B/E4B uniquement)

## Benchmarks (IT, thinking mode)

| Benchmark | 31B | 26B A4B | E4B | E2B |
|-----------|-----|---------|-----|-----|
| MMLU Pro | 85.2% | 82.6% | 69.4% | 60.0% |
| AIME 2026 | 89.2% | 88.3% | 42.5% | 37.5% |
| GPQA Diamond | 84.3% | 82.3% | 58.6% | 43.4% |
| LiveCodeBench v6 | 80.0% | 77.1% | 52.0% | 44.0% |

## Licence

**Apache 2.0** - Changement majeur par rapport aux versions precedentes de Gemma.
Usage commercial, modification et redistribution libres, sans restrictions.
