# Benchmark gemma4:26b (mode: all)

## Machine
- CPU: AMD Ryzen 9 5900HX with Radeon Graphics
- RAM: 55 Go disponibles / 62 Go total
- GPU: Aucun (CPU-only)
- Date: 2026-04-07 22:00

## Résultats détaillés

| Prompt | Catégorie | Temps | Tokens est. | Vitesse | Caractères |
|--------|-----------|-------|-------------|---------|------------|
| code_simple | coding | 66.7s | ~2322 | 34.7 tok/s | 9290 |
| code_debug | coding | 89.0s | ~2717 | 30.5 tok/s | 10870 |
| code_refactor | coding | 300.0s | TIMEOUT | >300s | - |
| code_algo | coding | 144.3s | ~5307 | 36.7 tok/s | 21231 |
| code_archi | coding | 224.8s | ~7417 | 32.9 tok/s | 29668 |
| doc_api | doc | 176.5s | ~5744 | 32.5 tok/s | 22977 |
| doc_changelog | doc | 79.5s | ~2665 | 33.4 tok/s | 10663 |
| doc_technique | doc | 145.0s | ~5508 | 37.9 tok/s | 22035 |
| doc_tutorial | doc | 147.8s | ~5008 | 33.8 tok/s | 20034 |
| doc_readme | doc | 137.2s | ~4705 | 34.2 tok/s | 18821 |

## Scores UX

| Catégorie | Vitesse moy. | Score | Verdict |
|-----------|-------------|-------|---------|
| Coding | ~33.8 tok/s | 95/100 | Excellent |
| Documentation | ~34.4 tok/s | 95/100 | Excellent |
| **Global** | **~34.1 tok/s** | **95/100** | **Excellent** |

### Barème UX

**Coding** (tolérance vitesse plus haute, qualité prime) :
- 95+ : Excellent (>15 tok/s) — réponse fluide
- 70-94 : Bon (8-15 tok/s) — attente raisonnable
- 40-69 : Acceptable (3-8 tok/s) — utilisable pour des tâches ponctuelles
- <40 : Lent (<3 tok/s) — pénible pour un usage interactif

**Documentation** (besoin de fluidité pour le volume) :
- 95+ : Excellent (>25 tok/s) — génération fluide de longs documents
- 70-94 : Bon (15-25 tok/s) — confortable
- 40-69 : Acceptable (8-15 tok/s) — utilisable avec patience
- <40 : Lent (<8 tok/s) — inadapté pour de la documentation longue
