#!/usr/bin/env bash
# Helper commun pour les tasks agent:*.
# Sourced par chaque task — ne pas exécuter directement.
#
# Usage depuis une task mise :
#   source "$REPO_DIR/scripts/harness-run.sh"
#   harness_run "$PROFILE_NAME" "$TASK" "$WORKSPACE"

set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HARNESS_DIR="$REPO_DIR/agent-harness"

# --- Profile mapping ---------------------------------------------------
_resolve_profile() {
    local name="$1"
    case "$name" in
        coding)  echo "$HARNESS_DIR/config/profiles/gemma4-coding.yaml" ;;
        doc)     echo "$HARNESS_DIR/config/profiles/gemma4-doc.yaml" ;;
        dev)     echo "$HARNESS_DIR/config/profiles/dev.yaml" ;;
        claude)  echo "$HARNESS_DIR/config/profiles/claude-online.yaml" ;;
        copilot) echo "$HARNESS_DIR/config/profiles/copilot.yaml" ;;
        ops)     echo "$HARNESS_DIR/config/profiles/ops.yaml" ;;
        *)       echo "" ;;
    esac
}

# --- Checks -------------------------------------------------------------
_check_harness() {
    if [ ! -f "$HARNESS_DIR/.venv/bin/harness" ]; then
        echo "[ERREUR] agent-harness non installé"
        echo "  → mise run agent:setup"
        exit 1
    fi
}

_check_chromadb() {
    if ! "$HARNESS_DIR/.venv/bin/python3" -c "import chromadb" 2>/dev/null; then
        echo "[ERREUR] chromadb non installé (requis pour les skills RAG)"
        echo "  → mise run agent:setup -- --force"
        echo "  ou : $HARNESS_DIR/.venv/bin/pip install chromadb"
        exit 1
    fi
}

_check_env() {
    local profile_name="$1"
    case "$profile_name" in
        claude)
            if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
                echo "[ERREUR] ANTHROPIC_API_KEY non définie"
                echo "  export ANTHROPIC_API_KEY=sk-ant-..."
                exit 1
            fi
            ;;
        copilot)
            if [ -z "${GITHUB_TOKEN:-}" ]; then
                echo "[ERREUR] GITHUB_TOKEN non défini"
                echo "  export GITHUB_TOKEN=ghp_..."
                exit 1
            fi
            ;;
    esac
}

_ensure_local_model() {
    local profile_path="$1"
    local provider
    provider=$(grep -E '^\s+provider:' "$profile_path" 2>/dev/null | awk '{print $2}' | head -1)
    if [ "${provider:-ollama}" = "ollama" ]; then
        local model
        model=$(grep -E '^\s+name:' "$profile_path" 2>/dev/null | awk '{print $2}' | head -1)
        source "$REPO_DIR/scripts/ensure-model.sh"
        _ensure_model "$model" || exit 1
    fi
}

# --- Main entry point ----------------------------------------------------
harness_run() {
    local profile_name="$1"
    local task="$2"
    local workspace="${3:-.}"

    local profile_path
    profile_path=$(_resolve_profile "$profile_name")
    if [ -z "$profile_path" ]; then
        echo "[ERREUR] Profil inconnu : $profile_name"
        echo "  Profils : coding, doc, dev, claude, copilot, ops"
        exit 1
    fi

    _check_harness
    _check_chromadb
    _check_env "$profile_name"
    _ensure_local_model "$profile_path"

    exec "$HARNESS_DIR/.venv/bin/harness" run \
        --profile "$profile_path" \
        --workspace "$workspace" \
        "$task"
}
