# Benchmark gemma4:e4b (mode: all)

## Machine
- CPU: AMD Ryzen 9 5900HX with Radeon Graphics
- RAM: 55 Go disponibles / 62 Go total
- GPU: Aucun (CPU-only)
- Date: 2026-04-07 22:25

## Résultats détaillés

| Prompt | Catégorie | Temps | Tokens est. | Vitesse | Caractères |
|--------|-----------|-------|-------------|---------|------------|
| code_simple | coding | 100.6s | ~3496 | 34.7 tok/s | 13986 |
| code_debug | coding | 253.6s | ~3914 | 15.4 tok/s | 15656 |
| code_refactor | coding | 219.7s | ~3691 | 16.7 tok/s | 14765 |
| code_algo | coding | 280.0s | ~7276 | 25.9 tok/s | 29105 |
| code_archi | coding | 136.3s | ~5016 | 36.7 tok/s | 20065 |
| doc_api | doc | 105.5s | ~3096 | 29.3 tok/s | 12387 |
| doc_changelog | doc | 74.2s | ~2795 | 37.6 tok/s | 11181 |
| doc_technique | doc | 133.5s | ~4944 | 37.0 tok/s | 19779 |
| doc_tutorial | doc | 137.5s | ~4886 | 35.5 tok/s | 19544 |
| doc_readme | doc | 87.7s | ~3324 | 37.8 tok/s | 13296 |

## Scores UX

| Catégorie | Vitesse moy. | Score | Verdict |
|-----------|-------------|-------|---------|
| Coding | ~23.6 tok/s | 95/100 | Excellent |
| Documentation | ~35.3 tok/s | 95/100 | Excellent |
| **Global** | **~27.7 tok/s** | **95/100** | **Excellent** |

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
