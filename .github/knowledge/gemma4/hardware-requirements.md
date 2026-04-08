# Gemma 4 - Exigences hardware

## VRAM / RAM par quantization

| Modele | Q4 (4-bit) | Q8 (8-bit) | BF16/FP16 |
|--------|-----------|-----------|-----------|
| **E2B** | ~4 Go | 5-8 Go | ~10 Go |
| **E4B** | ~6 Go | 9-12 Go | ~16 Go |
| **26B A4B (MoE)** | 16-18 Go | 28-30 Go | ~52 Go |
| **31B (Dense)** | 17-20 Go | 34-38 Go | ~62 Go |

Ajouter 1-3 Go pour le runtime, KV cache et contexte.

## Mapping GPU typique

| GPU | VRAM | Modele max recommande |
|-----|------|-----------------------|
| Pas de GPU (CPU only, 64 Go RAM) | - | 31B Q4 ou 26B A4B Q8 |
| RTX 3060 (12 Go) | 12 Go | E4B Q8 |
| RTX 4060 Ti 16 Go | 16 Go | 26B A4B Q4 |
| RTX 3090 / 4090 (24 Go) | 24 Go | 31B Q4 |
| A6000 (48 Go) | 48 Go | 31B Q8 |
| A100 / H100 (80 Go) | 80 Go | 31B BF16 |

## Quantization recommandee

- **E2B / E4B** : Q8_0 -- assez petit pour que le 8-bit ne coute rien en plus
- **26B A4B / 31B** : UD-Q4_K_XL (dynamic 4-bit) -- meilleur compromis qualite/memoire (~2-5% de degradation)
- **Alternative** : Q5_K_M -- bon milieu de gamme

## Notre machine (pseudo-copilot)

- **CPU** : AMD Ryzen 9 5900HX (8 coeurs / 16 threads, AVX2)
- **RAM** : 62 Go
- **GPU** : Radeon Vega integre uniquement (inutilisable pour l'inference LLM)
- **Mode** : CPU-only

### Ce qu'on peut faire tourner

| Modele | Quantization | RAM estimee | Faisable ? | Vitesse estimee |
|--------|-------------|-------------|------------|-----------------|
| E2B | Q4 | ~4 Go | Oui | 15-25 tok/s |
| E4B | Q4 | ~6 Go | Oui | 10-20 tok/s |
| E4B | Q8 | ~12 Go | Oui | 8-15 tok/s |
| 26B A4B | Q4 | ~18 Go | Oui | 5-10 tok/s (seulement 3.8B actifs) |
| 26B A4B | Q8 | ~30 Go | Oui | 3-7 tok/s |
| 31B | Q4 | ~20 Go | Oui | 3-6 tok/s |
| 31B | Q8 | ~38 Go | Oui (limite) | 1-3 tok/s |

**Recommandation pour cette machine** : Le **26B A4B en Q4** est le meilleur choix -- seulement 3.8B params actifs donc rapide en CPU, mais qualite proche du 31B. Excellente efficacite.
