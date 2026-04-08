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

_ensure_skills_index() {
    local SKILLS_DIR="$REPO_DIR/skills"
    local PERSIST_DIR="$HOME/.local/share/agent-harness/chroma"
    local STAMP_FILE="$PERSIST_DIR/.skills_indexed_at"
    local VENV_PYTHON="$HARNESS_DIR/.venv/bin/python3"

    # Pas de dossier skills → rien à indexer
    [ -d "$SKILLS_DIR" ] || return 0

    # Chroma DB absente ou cassée ?
    local needs_reindex=false
    if [ ! -f "$PERSIST_DIR/chroma.sqlite3" ]; then
        echo "    [i] Base vectorielle Chroma absente — indexation requise"
        needs_reindex=true
    elif [ ! -f "$STAMP_FILE" ]; then
        echo "    [i] Première indexation des skills"
        needs_reindex=true
    else
        # Comparer le dernier commit sur skills/ avec le stamp
        local last_commit_ts
        last_commit_ts=$(git -C "$REPO_DIR" log -1 --format=%ct -- skills/ 2>/dev/null || echo 0)
        local stamp_ts
        stamp_ts=$(stat -c %Y "$STAMP_FILE" 2>/dev/null || echo 0)
        if [ "$last_commit_ts" -gt "$stamp_ts" ] 2>/dev/null; then
            echo "    [i] Skills modifiés depuis le dernier index (commit plus récent)"
            needs_reindex=true
        fi
    fi

    if [ "$needs_reindex" = true ]; then
        echo "    [i] Reindexation automatique des skills..."
        PYTHONUNBUFFERED=1 "$VENV_PYTHON" -c "
import sys, os, time, hashlib
from pathlib import Path

sys.path.insert(0, '$HARNESS_DIR/src')
from harness.tools.runbooks import _split_markdown
import chromadb

skills_path = Path('$SKILLS_DIR')
persist_dir = Path('$PERSIST_DIR')
persist_dir.mkdir(parents=True, exist_ok=True)

client = chromadb.PersistentClient(path=str(persist_dir))
collection = client.get_or_create_collection(name='agent_skills')

domains = sorted([d.name for d in skills_path.iterdir()
                  if d.is_dir() and (d / 'SKILL.md').exists()])

t0 = time.time()
total = 0
for i, domain in enumerate(domains, 1):
    n = 0
    for f in sorted((skills_path / domain).rglob('*.md')):
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        fh = hashlib.sha256(text.encode('utf-8')).hexdigest()
        rel = f.relative_to(skills_path).as_posix()
        for idx, (sec, body) in enumerate(_split_markdown(text, 800, 100)):
            collection.upsert(
                ids=[f'{fh}:{idx}'],
                documents=[body],
                metadatas=[{'file': rel, 'section': sec, 'domain': domain, 'chunk_index': str(idx)}],
            )
            n += 1
    total += n
    print(f'    [{i:2d}/{len(domains)}] {domain:<14s} {n:4d} chunks  ({time.time()-t0:.0f}s)', flush=True)

print(f'    [OK] {total} chunks en {time.time()-t0:.0f}s')
" || {
            echo "    [!] Reindexation échouée — l'agent fonctionnera sans skills RAG"
            return 0
        }
        # Mettre à jour le timestamp
        mkdir -p "$PERSIST_DIR"
        touch "$STAMP_FILE"
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
    _ensure_skills_index
    _check_env "$profile_name"
    _ensure_local_model "$profile_path"

    exec "$HARNESS_DIR/.venv/bin/harness" run \
        --profile "$profile_path" \
        --workspace "$workspace" \
        "$task"
}
