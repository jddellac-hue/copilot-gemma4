"""Eval suite for the agent harness.

Each task in `eval/tasks/` is a YAML file describing:
- a fixture workspace to set up
- a user prompt
- a verification command (exit 0 = pass)

The runner orchestrates them and produces a JSON report consumed by CI.
"""
