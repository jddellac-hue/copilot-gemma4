#!/usr/bin/env bash
# Vérifie qu'ollama tourne, que le modèle est installé, le précharge en RAM.
# Usage: source ensure-model.sh <model>
# Retourne 0 si prêt, 1 si erreur.

_ensure_model() {
    local MODEL="$1"

    # 1. Ollama tourne ?
    if ! curl -sf http://localhost:11434/api/ps > /dev/null 2>&1; then
        echo "[...] Démarrage d'ollama..."
        sudo systemctl start ollama 2>/dev/null || nohup ollama serve &>/dev/null &
        sleep 3
        if ! curl -sf http://localhost:11434/api/ps > /dev/null 2>&1; then
            echo "[ERREUR] Impossible de démarrer ollama"
            return 1
        fi
        echo "[OK] ollama démarré"
    fi

    # 2. Modèle installé ? Sinon proposer le téléchargement.
    if ! ollama list 2>/dev/null | grep -q "$MODEL"; then
        echo "[!] $MODEL n'est pas installé"
        echo ""
        read -rp "Voulez-vous le télécharger maintenant ? [O/n] " REPLY
        REPLY="${REPLY:-O}"
        if [[ "$REPLY" =~ ^[OoYy]$ ]]; then
            echo "[...] Téléchargement de $MODEL (peut prendre plusieurs minutes)..."
            ollama pull "$MODEL" || {
                echo "[ERREUR] Échec du téléchargement de $MODEL"
                return 1
            }
            echo "[OK] $MODEL téléchargé"
        else
            echo "[ERREUR] $MODEL est requis pour ce profil"
            echo ""
            echo "Installez-le manuellement :"
            echo "  ollama pull $MODEL"
            echo "  mise run model:install -- $MODEL"
            return 1
        fi
    fi

    # 3. Décharger les autres modèles
    local LOADED
    LOADED=$(curl -sf http://localhost:11434/api/ps 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
for m in d.get('models',[]):
    if m['name'] != '$MODEL':
        print(m['name'])
" 2>/dev/null || true)

    for other in $LOADED; do
        echo "[...] Déchargement de $other..."
        curl -sf http://localhost:11434/api/generate \
            -d "{\"model\":\"$other\",\"keep_alive\":0}" > /dev/null 2>&1 || true
    done

    # 4. Précharger le modèle (si pas déjà en mémoire)
    local IS_LOADED
    IS_LOADED=$(curl -sf http://localhost:11434/api/ps 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
for m in d.get('models',[]):
    if m['name'] == '$MODEL': print('yes')
" 2>/dev/null || true)

    if [ "$IS_LOADED" != "yes" ]; then
        echo "[...] Chargement de $MODEL en mémoire (première fois, peut être long)..."
        curl -sf http://localhost:11434/api/generate \
            -d "{\"model\":\"$MODEL\",\"keep_alive\":\"10m\"}" \
            --max-time 300 > /dev/null 2>&1 || true

        # Vérifier que c'est chargé
        sleep 2
        IS_LOADED=$(curl -sf http://localhost:11434/api/ps 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
for m in d.get('models',[]):
    if m['name'] == '$MODEL': print('yes')
" 2>/dev/null || true)

        if [ "$IS_LOADED" != "yes" ]; then
            echo "[ERREUR] Impossible de charger $MODEL"
            echo "Vérifiez la RAM disponible (free -h)"
            return 1
        fi
    fi

    echo "[OK] $MODEL prêt"
    return 0
}
