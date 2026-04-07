# Benchmark gemma4:31b (mode: all)

## Machine
- CPU: AMD Ryzen 9 5900HX with Radeon Graphics
- RAM: 53 Go disponibles / 62 Go total
- GPU: Aucun (CPU-only)
- Date: 2026-04-07 22:51

## Résultats détaillés

| Prompt | Catégorie | Temps | Tokens est. | Vitesse | Caractères |
|--------|-----------|-------|-------------|---------|------------|
| code_simple | coding | 300.0s | TIMEOUT | >300s | - |
| code_debug | coding | 300.0s | TIMEOUT | >300s | - |
| code_refactor | coding | 300.0s | TIMEOUT | >300s | - |
| code_algo | coding | 300.0s | TIMEOUT | >300s | - |
| code_archi | coding | 300.0s | TIMEOUT | >300s | - |
| doc_api | doc | 180.0s | TIMEOUT | >180s | - |
| doc_changelog | doc | 180.0s | TIMEOUT | >180s | - |
| doc_technique | doc | 180.0s | TIMEOUT | >180s | - |
| doc_tutorial | doc | 180.0s | TIMEOUT | >180s | - |
| doc_readme | doc | 180.0s | TIMEOUT | >180s | - |

## Scores UX

| Catégorie | Vitesse moy. | Score | Verdict |
|-----------|-------------|-------|---------|


| **Global** | **~0 tok/s** | **0/100** | **Pénible** |

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
