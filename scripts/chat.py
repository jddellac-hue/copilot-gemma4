#!/usr/bin/env python3
"""Chat interactif avec un modèle Gemma 4 local via Ollama.

Si chromadb et le harness sont installés, le chat enrichit chaque message
avec du contexte issu des skills RAG (search_skills). Sinon le chat
fonctionne normalement sans RAG.
"""

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
        "model": os.environ.get("GEMMA4_GENERAL_MODEL", "gemma4:26b-a4b-it-q8_0"),
        "system": (
            "Tu es un assistant technique polyvalent. Tu aides avec le code, "
            "la documentation, l'architecture, le DevOps, et les questions "
            "techniques en général. Tu es concis et direct."
        ),
        "color": CYAN,
        "label": "GENERAL",
    },
}


# ---------------------------------------------------------------------------
# RAG skills (opt-in, graceful degradation)
# ---------------------------------------------------------------------------
_skills_tool = None
_rag_enabled = False
_skill_domains = []  # populated by _init_rag


def _init_rag():
    """Try to load skills RAG. Returns True if available."""
    global _skills_tool, _rag_enabled, _skill_domains
    try:
        # Find the repo root (scripts/ is one level below)
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        harness_src = os.path.join(repo_root, "agent-harness", "src")
        skills_dir = os.path.join(repo_root, "skills")

        if not os.path.isdir(skills_dir):
            return False

        # Add harness source to path so we can import
        if harness_src not in sys.path:
            sys.path.insert(0, harness_src)

        from harness.tools.skills import SkillsConfig, build_skills_tools

        config = SkillsConfig(
            enabled=True,
            path=__import__("pathlib").Path(skills_dir),
            collection_name="chat_skills",
            persist_dir=__import__("pathlib").Path(
                os.path.expanduser("~/.local/share/agent-harness/chroma")
            ),
            chunk_size=800,
            chunk_overlap=100,
            max_results=5,
        )
        tools = build_skills_tools(config)
        if tools:
            _skills_tool = tools[0]
            _rag_enabled = True
            # Collect domain names for keyword matching
            _skill_domains = sorted([
                d for d in os.listdir(skills_dir)
                if os.path.isdir(os.path.join(skills_dir, d))
                and os.path.isfile(os.path.join(skills_dir, d, "SKILL.md"))
            ])
            return True
    except Exception:
        pass
    return False


def _search_skills(query):
    """Search skills and return context string, or empty string.

    Two-pass strategy:
    1. Detect domain names mentioned in the query → targeted search per domain
    2. General search across all domains to fill remaining slots
    Dedup by chunk content.
    """
    if not _skills_tool:
        return ""
    try:
        results = []
        seen = set()
        query_lower = query.lower()

        # Pass 1: targeted search for explicitly mentioned domains
        for domain in _skill_domains:
            if domain in query_lower:
                r = _skills_tool.invoke({"query": query, "domain": domain, "top_k": 2})
                if r.ok and "no skill matched" not in r.content:
                    for chunk in r.content.split("\n\n--- ["):
                        if chunk not in seen:
                            seen.add(chunk)
                            results.append(chunk if chunk.startswith("--- [") else "--- [" + chunk)

        # Pass 2: general search to fill up to 5 results
        remaining = 5 - len(results)
        if remaining > 0:
            r = _skills_tool.invoke({"query": query, "top_k": remaining + 2})
            if r.ok and "no skill matched" not in r.content:
                for chunk in r.content.split("\n\n--- ["):
                    clean = chunk if chunk.startswith("--- [") else "--- [" + chunk
                    if clean not in seen and len(results) < 5:
                        seen.add(clean)
                        results.append(clean)

        if results:
            return "\n\n".join(results)
    except Exception:
        pass
    return ""


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
    except Exception:
        pass


def print_help(role_config):
    rag_status = f"{GREEN}activé{RESET}" if _rag_enabled else f"{DIM}indisponible{RESET}"
    print(f"""
{BOLD}Commandes :{RESET}
  {YELLOW}/help{RESET}       Afficher cette aide
  {YELLOW}/clear{RESET}      Effacer l'historique de conversation
  {YELLOW}/system{RESET}     Voir le prompt système actuel
  {YELLOW}/model{RESET}      Voir le modèle utilisé
  {YELLOW}/stats{RESET}      Voir les stats de la dernière réponse
  {YELLOW}/rag{RESET}        Activer/désactiver le RAG skills ({rag_status})
  {YELLOW}/skills{RESET}     Rechercher manuellement dans les skills
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

    # Initialiser le RAG skills
    global _rag_enabled
    print(f"{DIM}Skills RAG...{RESET}", end=" ", flush=True)
    if _init_rag():
        print(f"{GREEN}activé{RESET} {DIM}(5 chunks par requête, /rag off pour désactiver){RESET}")
    else:
        print(f"{RED}désactivé{RESET}")
        print(f"  {YELLOW}→ chromadb non installé. Installez avec : mise run agent:setup -- --force{RESET}")
        print(f"  {DIM}Le chat fonctionne sans RAG mais sans expertise domaine.{RESET}")
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
                elif cmd == "/rag":
                    parts = user_input.lower().split()
                    if len(parts) > 1 and parts[1] in ("on", "off"):
                        if parts[1] == "on" and _skills_tool:
                            _rag_enabled = True
                            print(f"{GREEN}RAG activé{RESET}")
                        elif parts[1] == "off":
                            _rag_enabled = False
                            print(f"{DIM}RAG désactivé{RESET}")
                        else:
                            print(f"{RED}RAG indisponible (chromadb non installé){RESET}")
                    else:
                        status = f"{GREEN}activé{RESET}" if _rag_enabled else f"{DIM}désactivé{RESET}"
                        print(f"RAG skills : {status}")
                        print(f"{DIM}/rag on | /rag off{RESET}")
                elif cmd == "/skills":
                    query = user_input[len("/skills"):].strip()
                    if not query:
                        print(f"{DIM}Usage : /skills <recherche>{RESET}")
                        print(f"{DIM}Ex : /skills Kafka consumer strategy{RESET}")
                    elif _skills_tool:
                        ctx = _search_skills(query)
                        if ctx:
                            print(f"\n{DIM}{ctx}{RESET}\n")
                        else:
                            print(f"{DIM}Aucun résultat.{RESET}")
                    else:
                        print(f"{RED}RAG indisponible.{RESET}")
                elif cmd == "/save":
                    save_conversation(messages, role)
                else:
                    print(f"{DIM}Commande inconnue. /help pour l'aide.{RESET}")
                continue

            # RAG : enrichir avec le contexte des skills
            rag_context = ""
            if _rag_enabled:
                rag_context = _search_skills(user_input)

            if rag_context:
                # Injecter le contexte comme message système temporaire
                augmented = user_input + (
                    "\n\n---\n"
                    "Contexte pertinent issu des skills de référence "
                    "(utilise ces informations pour enrichir ta réponse) :\n\n"
                    + rag_context
                )
                messages.append({"role": "user", "content": augmented})
                # Afficher les domaines trouvés
                domains = set()
                for line in rag_context.split("\n"):
                    if line.startswith("--- ["):
                        d = line.split("[")[1].split("]")[0]
                        domains.add(d)
                if domains:
                    print(f"{DIM}(skills: {', '.join(sorted(domains))}){RESET}")
            else:
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
