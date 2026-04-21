#!/usr/bin/env bash
# =============================================================================
# TicketInsight Pro — NLP Model Download Script
# =============================================================================
# Downloads all required NLP models and data:
#   - spaCy en_core_web_sm (English language model)
#   - NLTK punkt (sentence tokenizer)
#   - NLTK stopwords (stop word lists)
#   - NLTK wordnet (lexical database)
#   - NLTK averaged_perceptron_tagger (POS tagger)
#   - NLTK vader_lexicon (sentiment analysis)
#
# Each model is checked first to avoid redundant downloads.
#
# Usage:
#   bash scripts/download_models.sh
#   bash scripts/download_models.sh --force
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

FORCE=false
for arg in "$@"; do
    case "$arg" in
        --force|-f)
            FORCE=true
            ;;
        --help|-h)
            echo "Usage: bash scripts/download_models.sh [--force]"
            echo ""
            echo "Options:"
            echo "  --force, -f  Re-download models even if already present"
            echo "  --help, -h   Show this help message"
            exit 0
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Determine project root
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Activate venv if available
if [[ -d "${PROJECT_ROOT}/.venv/bin" ]]; then
    source "${PROJECT_ROOT}/.venv/bin/activate"
    info "Activated virtual environment"
fi

echo ""
echo -e "${BOLD}${CYAN}━━━ TicketInsight Pro — NLP Model Downloader ━━━${NC}"
echo ""

ERRORS=0
TOTAL=0
DOWNLOADED=0
SKIPPED=0

# ---------------------------------------------------------------------------
# Function: download a spaCy model
# ---------------------------------------------------------------------------
download_spacy_model() {
    local model="$1"
    TOTAL=$((TOTAL + 1))

    echo -e "${CYAN}[${TOTAL}] spaCy model: ${model}${NC}"

    # Check if model is already available
    if [[ "$FORCE" == false ]]; then
        if python -c "import spacy; spacy.load('${model}')" 2>/dev/null; then
            success "  ${model} — already installed"
            SKIPPED=$((SKIPPED + 1))
            return 0
        fi
    fi

    # Download
    info "  Downloading ${model}..."
    if python -m spacy download "${model}" 2>&1; then
        success "  ${model} — downloaded successfully"
        DOWNLOADED=$((DOWNLOADED + 1))
    else
        error "  Failed to download ${model}"
        ERRORS=$((ERRORS + 1))
    fi
}

# ---------------------------------------------------------------------------
# Function: download an NLTK data package
# ---------------------------------------------------------------------------
download_nltk_data() {
    local package="$1"
    TOTAL=$((TOTAL + 1))

    echo -e "${CYAN}[${TOTAL}] NLTK data: ${package}${NC}"

    # Check if already downloaded
    if [[ "$FORCE" == false ]]; then
        if python -c "
import nltk
try:
    nltk.data.find('tokenizers/${package}')
    print('found')
except LookupError:
    try:
        nltk.data.find('corpora/${package}')
        print('found')
    except LookupError:
        try:
            nltk.data.find('taggers/${package}')
            print('found')
        except LookupError:
            try:
                nltk.data.find('sentiment/${package}')
                print('found')
            except LookupError:
                print('missing')
" 2>/dev/null | grep -q "found"; then
            success "  ${package} — already downloaded"
            SKIPPED=$((SKIPPED + 1))
            return 0
        fi
    fi

    # Download
    info "  Downloading ${package}..."
    if python -c "import nltk; nltk.download('${package}', quiet=False)" 2>&1; then
        success "  ${package} — downloaded successfully"
        DOWNLOADED=$((DOWNLOADED + 1))
    else
        error "  Failed to download ${package}"
        ERRORS=$((ERRORS + 1))
    fi
}

# ===========================================================================
# spaCy Models
# ===========================================================================
echo -e "${BOLD}── spaCy Language Models ──${NC}"
echo ""

download_spacy_model "en_core_web_sm"

echo ""

# ===========================================================================
# NLTK Data
# ===========================================================================
echo -e "${BOLD}── NLTK Data Packages ──${NC}"
echo ""

download_nltk_data "punkt"
download_nltk_data "punkt_tab"
download_nltk_data "stopwords"
download_nltk_data "wordnet"
download_nltk_data "averaged_perceptron_tagger"
download_nltk_data "averaged_perceptron_tagger_eng"
download_nltk_data "vader_lexicon"

echo ""

# ===========================================================================
# Summary
# ===========================================================================
echo -e "${BOLD}${CYAN}━━━ Download Summary ━━━${NC}"
echo ""
echo -e "  Total models checked:  ${TOTAL}"
echo -e "  ${GREEN}Downloaded:             ${DOWNLOADED}${NC}"
echo -e "  ${YELLOW}Already present:        ${SKIPPED}${NC}"
if [[ "$ERRORS" -gt 0 ]]; then
    echo -e "  ${RED}Errors:                 ${ERRORS}${NC}"
else
    echo -e "  Errors:                 0"
fi
echo ""

if [[ "$ERRORS" -gt 0 ]]; then
    warn "Some models failed to download. Check the output above for details."
    warn "You may need to run: pip install spacy nltk"
    exit 1
else
    success "All NLP models and data are ready!"
fi
