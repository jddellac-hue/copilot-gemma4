# Benchmark gemma4:26b-a4b-it-q8_0 (mode: all)

## Machine
- CPU: AMD Ryzen 9 5900HX with Radeon Graphics
- RAM: 25 Go disponibles / 62 Go total
- GPU: Aucun (CPU-only)
- Date: 2026-04-07 23:31

## Résultats détaillés

| Prompt | Catégorie | Temps | Tokens est. | Vitesse | Caractères |
|--------|-----------|-------|-------------|---------|------------|
| code_simple | coding | 151.6s | ~9025 | 59.5 tok/s | 36103 |
| code_debug | coding | 300.0s | TIMEOUT | >300s | - |
| code_refactor | coding | 300.0s | TIMEOUT | >300s | - |
| code_algo | coding | 197.0s | ~5182 | 26.2 tok/s | 20729 |
| code_archi | coding | 261.3s | ~6465 | 24.7 tok/s | 25860 |
| doc_api | doc | 180.0s | TIMEOUT | >180s | - |
| doc_changelog | doc | 104.4s | ~2802 | 26.8 tok/s | 11210 |
| doc_technique | doc | 163.0s | ~4245 | 26.0 tok/s | 16983 |
| doc_tutorial | doc | 180.0s | TIMEOUT | >180s | - |
| doc_readme | doc | 180.0s | TIMEOUT | >180s | - |

## Scores UX

| Catégorie | Vitesse moy. | Score | Verdict |
|-----------|-------------|-------|---------|
| Coding | ~33.8 tok/s | 95/100 | Excellent |
| Documentation | ~26.3 tok/s | 95/100 | Excellent |
| **Global** | **~31.5 tok/s** | **95/100** | **Excellent** |

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
