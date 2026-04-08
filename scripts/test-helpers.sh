#!/usr/bin/env bash
# Helpers partagés entre verify et test:system.
# Sourced — ne pas exécuter directement.

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0
SKIP=0
TOTAL_START=$(date +%s)

section()  { echo -e "\n${BLUE}${BOLD}━━━ $1 ━━━${NC}"; }
ok()       { echo -e "  ${GREEN}✓${NC} $1"; PASS=$((PASS + 1)); }
fail()     { echo -e "  ${RED}✗${NC} $1"; FAIL=$((FAIL + 1)); }
warn()     { echo -e "  ${YELLOW}⚠${NC} $1"; WARN=$((WARN + 1)); }
skip()     { echo -e "  ${YELLOW}⊘${NC} $1 ${DIM}(skipped)${NC}"; SKIP=$((SKIP + 1)); }
info()     { echo -e "  ${DIM}$1${NC}"; }
detail()   { echo -e "    ${DIM}$1${NC}"; }

summary() {
    local elapsed=$(( $(date +%s) - TOTAL_START ))
    echo ""
    echo -e "${BOLD}━━━ Résumé ━━━${NC}"
    echo -e "  ${GREEN}✓ $PASS passed${NC}  ${RED}✗ $FAIL failed${NC}  ${YELLOW}⚠ $WARN warnings${NC}  ${YELLOW}⊘ $SKIP skipped${NC}  (${elapsed}s)"
    if [ "$FAIL" -gt 0 ]; then
        echo -e "\n  ${RED}${BOLD}FAIL${NC}"
        return 1
    fi
    echo -e "\n  ${GREEN}${BOLD}OK${NC}"
    return 0
}
