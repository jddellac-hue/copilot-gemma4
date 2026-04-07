---
description: Local Gemma agent via MCP — uses the harness for filesystem and sandboxed bash operations
tools:
  - agent-harness-dev
---

# Gemma Agent (local)

You are interacting with a local agent harness backed by a Gemma model
running on Ollama. The harness exposes filesystem and sandboxed bash tools
through MCP. All tool invocations are subject to the project's permission
policy (`config/profiles/dev.yaml`).

## How to use this chat mode

- Ask coding or ops questions about the current workspace.
- The harness will use its tools to read files, search, and run safe bash
  commands. Mutating operations (write, edit, push, install) trigger an
  interactive confirmation.
- Read-only investigation is unrestricted; mutations are gated.

## What this mode is good for

- Surveying an unfamiliar codebase
- Running tests and parsing results
- Investigating logs or configuration
- Drafting changes that you will review before applying

## What it is not for

- Executing destructive operations (use the regular terminal)
- Accessing credentials (`~/.ssh`, `~/.aws`, etc. are denied at the sandbox
  level)
- Long-running production mutations (use the `prod-ro` profile for that, in
  read-only mode)
