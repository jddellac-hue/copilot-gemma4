# Eval suite

7 reproducible tasks gating CI merges. Each task is a YAML file under
`tasks/` describing a fixture workspace, a user prompt, and a verification
criterion (`contains`, `exact`, or a `bash` command).

## Categories

| Category       | Tasks                                              |
|----------------|----------------------------------------------------|
| `fundamentals` | 01 read-and-report, 02 search-by-pattern           |
| `coding`       | 03 edit-file, 04 run-tests, 05 fix-failing-test    |
| `ops`          | 06 ops-log-investigation                           |
| `security`     | 07 redteam-prompt-injection                        |

## Run locally

```bash
# Via mise (recommandé — gère les prérequis automatiquement)
mise run agent:eval -- gemma4          # Gemma 4 26B MoE (~5 min)
mise run agent:eval -- gemma4-light    # Gemma 4 E4B (~10 min)
mise run agent:eval -- claude          # Claude Sonnet (~2 min, ANTHROPIC_API_KEY)
mise run agent:eval -- copilot         # GitHub Copilot (~2 min, GITHUB_TOKEN)

# Ou directement
cd agent-harness
PYTHONPATH=. harness eval --profile config/profiles/ci-gemma4.yaml
```

The runner produces `eval/report.json` and exits non-zero if any task
fails. CI uses the artifact for gating.

Profiles with `eval.budget_multiplier` (e.g. `ci-gemma4.yaml: 3.0`)
scale task budgets for verbose models that need more tokens per step.

## Adding a task

1. Create `tasks/NN-name.yaml` following the existing schema.
2. Make the success criterion **objective** — no LLM-judged grading.
3. Keep the fixture small (< 1 KB total). Eval tasks must be fast.
4. Run locally to validate.
5. Add a one-line entry under "Categories" above.
6. Open PR.
