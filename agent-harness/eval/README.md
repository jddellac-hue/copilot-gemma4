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
ollama pull gemma:2b-instruct      # smaller model = faster eval
harness eval --profile config/profiles/ci.yaml
```

The runner produces `eval/report.json` and exits non-zero if any task
fails. CI uses the artifact for gating.

## Adding a task

1. Create `tasks/NN-name.yaml` following the existing schema.
2. Make the success criterion **objective** — no LLM-judged grading.
3. Keep the fixture small (< 1 KB total). Eval tasks must be fast.
4. Run locally to validate.
5. Add a one-line entry under "Categories" above.
6. Open PR.
