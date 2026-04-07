#!/usr/bin/env python3
"""Chat interactif avec un modèle Gemma 4 local via Ollama."""

import json
import sys
import os
import urllib.request
import urllib.error
import readline  # pour l'historique des commandes en input

OLLAMA_API = os.environ.get("OLLAMA_API", "http://localhost:11434")

# Couleurs ANSI
RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
CYAN    = "\033[36m"
RED     = "\033[31m"

ROLES = {
    "coding": {
        "model": os.environ.get("GEMMA4_CODING_MODEL", "gemma4:26b-a4b-it-q8_0"),
        "system": (
            "Tu es un agent de développement expert. Tu écris du code Python, "
            "TypeScript, Bash, et tu maîtrises les architectures logicielles. "
            "Tu es concis et pragmatique. Tu donnes du code fonctionnel, testé "
            "mentalement, avec le bon niveau d'abstraction. "
            "Quand tu écris du code, tu utilises les bonnes pratiques et les "
            "patterns idiomatiques du langage. Tu ne sur-ingénierises pas. "
            "Tu expliques tes choix quand c'est pertinent."
        ),
        "color": BLUE,
        "label": "CODING",
    },
    "doc": {
        "model": os.environ.get("GEMMA4_DOC_MODEL", "gemma4:26b-a4b-it-q8_0"),
        "system": (
            "Tu es un agent de documentation technique expert. Tu rédiges des "
            "documentations claires, structurées et complètes : README, API docs, "
            "tutoriels, changelogs, guides d'architecture. "
            "Tu utilises le Markdown. Tu adaptes le niveau de détail au public "
            "cible. Tu es précis sur les exemples de code. "
            "Tu structures avec des titres, listes, tableaux quand c'est pertinent. "
            "Tu écris en français sauf si on te demande l'anglais."
        ),
        "color": MAGENTA,
        "label": "DOC",
    },
    "general": {
        "model": os.environ.get("GEMMA4_GENERAL_MODEL", "gemma4:26b"),
        "system": (
            "Tu es un assistant technique polyvalent. Tu aides avec le code, "
            "la documentation, l'architecture, le DevOps, et les questions "
            "techniques en général. Tu es concis et direct."
        ),
        "color": CYAN,
        "label": "GENERAL",
    },
}


def stream_chat(model, messages):
    """Appelle l'API Ollama en streaming et yield chaque morceau de texte."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_API}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            full_response = ""
            for line in resp:
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                    if "message" in chunk and "content" in chunk["message"]:
                        text = chunk["message"]["content"]
                        full_response += text
                        sys.stdout.write(text)
                        sys.stdout.flush()
                    if chunk.get("done"):
                        # Stats
                        total_duration = chunk.get("total_duration", 0)
                        eval_count = chunk.get("eval_count", 0)
                        eval_duration = chunk.get("eval_duration", 0)
                        return full_response, {
                            "total_s": total_duration / 1e9 if total_duration else 0,
                            "tokens": eval_count,
                            "tok_s": eval_count / (eval_duration / 1e9) if eval_duration else 0,
                        }
                except json.JSONDecodeError:
                    continue
            return full_response, {}
    except urllib.error.URLError as e:
        print(f"\n{RED}Erreur de connexion à Ollama : {e}{RESET}")
        return "", {}
    except Exception as e:
        print(f"\n{RED}Erreur : {e}{RESET}")
        return "", {}


def unload_other_models(keep_model):
    """Décharge les modèles en mémoire sauf celui qu'on utilise."""
    try:
        req = urllib.request.Request(f"{OLLAMA_API}/api/ps")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        for m in data.get("models", []):
            if m["name"] != keep_model:
                payload = json.dumps({"model": m["name"], "keep_alive": 0}).encode()
                req = urllib.request.Request(
                    f"{OLLAMA_API}/api/generate",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=10)
    except:
        pass


def print_help(role_config):
    print(f"""
{BOLD}Commandes :{RESET}
  {YELLOW}/help{RESET}       Afficher cette aide
  {YELLOW}/clear{RESET}      Effacer l'historique de conversation
  {YELLOW}/system{RESET}     Voir le prompt système actuel
  {YELLOW}/model{RESET}      Voir le modèle utilisé
  {YELLOW}/stats{RESET}      Voir les stats de la dernière réponse
  {YELLOW}/save{RESET}       Sauvegarder la conversation dans un fichier
  {YELLOW}/quit{RESET}       Quitter (ou Ctrl+D)
""")


def print_banner(role_config):
    color = role_config["color"]
    label = role_config["label"]
    model = role_config["model"]

    print(f"""
{BOLD}{color}╔══════════════════════════════════════════════════╗
║  GEMMA 4 CHAT — {label:<33}║
╠══════════════════════════════════════════════════╣
║  Modèle : {model:<39}║
║  /help pour les commandes                        ║
╚══════════════════════════════════════════════════╝{RESET}
""")


def save_conversation(messages, role_name):
    from datetime import datetime
    filename = f"chat_{role_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(filename, "w") as f:
        f.write(f"# Conversation {role_name} — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        for msg in messages:
            if msg["role"] == "system":
                continue
            role = "**Vous**" if msg["role"] == "user" else "**Gemma 4**"
            f.write(f"{role} :\n\n{msg['content']}\n\n---\n\n")
    print(f"{GREEN}Conversation sauvegardée dans {filename}{RESET}")


def main():
    role = sys.argv[1] if len(sys.argv) > 1 else "general"

    if role not in ROLES:
        print(f"{RED}Rôle inconnu : {role}{RESET}")
        print(f"Rôles disponibles : {', '.join(ROLES.keys())}")
        sys.exit(1)

    role_config = ROLES[role]
    model = role_config["model"]
    color = role_config["color"]

    print_banner(role_config)

    # Décharger les autres modèles
    print(f"{DIM}Libération de la mémoire...{RESET}", end=" ", flush=True)
    unload_other_models(model)
    print(f"{DIM}OK{RESET}")
    print()

    # Historique de conversation
    messages = [{"role": "system", "content": role_config["system"]}]
    last_stats = {}

    try:
        while True:
            try:
                user_input = input(f"{BOLD}{GREEN}vous >{RESET} ").strip()
            except EOFError:
                print()
                break

            if not user_input:
                continue

            # Commandes
            if user_input.startswith("/"):
                cmd = user_input.lower().split()[0]
                if cmd in ("/quit", "/exit", "/q"):
                    break
                elif cmd == "/help":
                    print_help(role_config)
                elif cmd == "/clear":
                    messages = [{"role": "system", "content": role_config["system"]}]
                    print(f"{DIM}Historique effacé.{RESET}")
                elif cmd == "/system":
                    print(f"{DIM}{role_config['system']}{RESET}")
                elif cmd == "/model":
                    print(f"{DIM}Modèle : {model}{RESET}")
                elif cmd == "/stats":
                    if last_stats:
                        print(f"{DIM}Tokens: {last_stats.get('tokens', '?')} | "
                              f"Vitesse: {last_stats.get('tok_s', 0):.1f} tok/s | "
                              f"Temps: {last_stats.get('total_s', 0):.1f}s{RESET}")
                    else:
                        print(f"{DIM}Pas encore de stats.{RESET}")
                elif cmd == "/save":
                    save_conversation(messages, role)
                else:
                    print(f"{DIM}Commande inconnue. /help pour l'aide.{RESET}")
                continue

            # Ajouter le message utilisateur
            messages.append({"role": "user", "content": user_input})

            # Réponse du modèle (streaming)
            print(f"\n{BOLD}{color}gemma4 >{RESET} ", end="", flush=True)
            response, stats = stream_chat(model, messages)
            last_stats = stats
            print()

            if stats:
                print(f"{DIM}({stats.get('tokens', '?')} tokens, "
                      f"{stats.get('tok_s', 0):.1f} tok/s, "
                      f"{stats.get('total_s', 0):.1f}s){RESET}")

            print()

            # Ajouter la réponse à l'historique
            if response:
                messages.append({"role": "assistant", "content": response})

    except KeyboardInterrupt:
        print()

    print(f"\n{DIM}Chat terminé.{RESET}")


if __name__ == "__main__":
    main()
