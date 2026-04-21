#!/usr/bin/env bash
# =============================================================================
# TicketInsight Pro — Setup Script
# =============================================================================
# Automated setup for local development:
#   1. Check Python version (>= 3.9)
#   2. Create virtual environment
#   3. Install requirements
#   4. Copy .env.example to .env if needed
#   5. Download NLP models (spaCy, NLTK)
#   6. Initialize database
#   7. Seed sample data
#
# Usage:
#   bash scripts/setup.sh
#   bash scripts/setup.sh --skip-models
#   bash scripts/setup.sh --skip-db
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'  # No Color

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
header()  { echo -e "\n${BOLD}${BLUE}━━━ $* ━━━${NC}\n"; }

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
SKIP_MODELS=false
SKIP_DB=false

for arg in "$@"; do
    case "$arg" in
        --skip-models)
            SKIP_MODELS=true
            ;;
        --skip-db)
            SKIP_DB=true
            ;;
        --help|-h)
            echo "Usage: bash scripts/setup.sh [--skip-models] [--skip-db]"
            echo ""
            echo "Options:"
            echo "  --skip-models  Skip NLP model downloads"
            echo "  --skip-db      Skip database initialization and seeding"
            echo "  --help, -h     Show this help message"
            exit 0
            ;;
        *)
            warn "Unknown argument: $arg"
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Determine project root
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_ROOT"

header "TicketInsight Pro — Development Setup"
info "Project root: ${PROJECT_ROOT}"

# ---------------------------------------------------------------------------
# 1. Check Python version
# ---------------------------------------------------------------------------
header "Step 1/7: Checking Python version"

PYTHON_CMD=""
for cmd in python3.11 python3.10 python3.9 python3; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if (( major == 3 && minor >= 9 )); then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    error "Python 3.9+ is required but not found on PATH."
    error "Please install Python 3.9, 3.10, or 3.11 and try again."
    exit 1
fi

PYTHON_VERSION=$("$PYTHON_CMD" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
success "Found Python ${PYTHON_VERSION} at $(command -v "$PYTHON_CMD")"

# ---------------------------------------------------------------------------
# 2. Create virtual environment
# ---------------------------------------------------------------------------
header "Step 2/7: Creating virtual environment"

VENV_DIR="${PROJECT_ROOT}/.venv"

if [[ -d "$VENV_DIR" ]]; then
    success "Virtual environment already exists at ${VENV_DIR}"
else
    info "Creating virtual environment at ${VENV_DIR}..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    success "Virtual environment created"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"
success "Virtual environment activated"

# Verify we're using the venv Python
VENV_PYTHON=$(command -v python)
info "Using Python: ${VENV_PYTHON}"

# Upgrade pip
info "Upgrading pip..."
pip install --quiet --upgrade pip
success "Pip upgraded to $(pip --version | awk '{print $2}')"

# ---------------------------------------------------------------------------
# 3. Install requirements
# ---------------------------------------------------------------------------
header "Step 3/7: Installing Python dependencies"

if [[ -f "${PROJECT_ROOT}/requirements.txt" ]]; then
    info "Installing from requirements.txt..."
    pip install -r "${PROJECT_ROOT}/requirements.txt"
    success "All Python dependencies installed"
else
    warn "requirements.txt not found — installing package in development mode"
    pip install -e "${PROJECT_ROOT}[dev]"
    success "Package installed in development mode"
fi

# ---------------------------------------------------------------------------
# 4. Copy .env.example to .env
# ---------------------------------------------------------------------------
header "Step 4/7: Setting up environment variables"

ENV_FILE="${PROJECT_ROOT}/.env"
ENV_EXAMPLE="${PROJECT_ROOT}/.env.example"

if [[ -f "$ENV_FILE" ]]; then
    success ".env file already exists"
else
    if [[ -f "$ENV_EXAMPLE" ]]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        success "Copied .env.example to .env"
        warn "Review and update ${ENV_FILE} with your settings"
    else
        # Create a minimal .env file
        cat > "$ENV_FILE" << 'ENVEOF'
# =============================================================================
# TicketInsight Pro — Environment Variables
# =============================================================================
APP_ENV=development
APP_DEBUG=true
SECRET_KEY=dev-secret-change-me-in-production
DATABASE_URL=sqlite:///data/ticketinsight.db
REDIS_URL=redis://localhost:6379/0

# PostgreSQL (uncomment to use instead of SQLite)
# POSTGRES_USER=ticketinsight
# POSTGRES_PASSWORD=ticketinsight_secret
# POSTGRES_DB=ticketinsight

# Adapter configuration
ADAPTER_TYPE=csv
CSV_FILE_PATH=data/samples/tickets_sample.csv

# Metabase
# METABASE_URL=http://localhost:3000
# METABASE_API_KEY=your-metabase-api-key
ENVEOF
        success "Created default .env file"
        warn "Review and update ${ENV_FILE} with your settings"
    fi
fi

# ---------------------------------------------------------------------------
# 5. Download NLP models
# ---------------------------------------------------------------------------
if [[ "$SKIP_MODELS" == false ]]; then
    header "Step 5/7: Downloading NLP models"

    # Run the dedicated download script
    SETUP_SCRIPT="${PROJECT_ROOT}/scripts/download_models.sh"
    if [[ -f "$SETUP_SCRIPT" ]]; then
        bash "$SETUP_SCRIPT"
    else
        warn "download_models.sh not found — downloading models inline..."

        # spaCy
        info "Downloading spaCy model (en_core_web_sm)..."
        if python -c "import spacy; spacy.load('en_core_web_sm')" 2>/dev/null; then
            success "spaCy en_core_web_sm already installed"
        else
            python -m spacy download en_core_web_sm
            success "spaCy model downloaded"
        fi

        # NLTK
        info "Downloading NLTK data..."
        python -c "
import nltk
packages = ['punkt', 'punkt_tab', 'stopwords', 'wordnet', 'averaged_perceptron_tagger', 'vader_lexicon']
for pkg in packages:
    try:
        nltk.download(pkg, quiet=True)
    except Exception:
        pass
print('NLTK data ready')
"
        success "NLTK data downloaded"
    fi
else
    header "Step 5/7: Skipping NLP model downloads (--skip-models)"
fi

# ---------------------------------------------------------------------------
# 6. Initialize database
# ---------------------------------------------------------------------------
if [[ "$SKIP_DB" == false ]]; then
    header "Step 6/7: Initializing database"

    # Create data directory
    mkdir -p "${PROJECT_ROOT}/data" "${PROJECT_ROOT}/data/samples" "${PROJECT_ROOT}/logs"

    info "Initializing database..."
    python -m ticketinsight.main db init
    success "Database initialized"
else
    header "Step 6/7: Skipping database initialization (--skip-db)"
fi

# ---------------------------------------------------------------------------
# 7. Seed sample data
# ---------------------------------------------------------------------------
if [[ "$SKIP_DB" == false ]]; then
    header "Step 7/7: Seeding sample data"

    info "Seeding database with sample tickets..."
    python -m ticketinsight.main db seed
    success "Sample data seeded"
else
    header "Step 7/7: Skipping sample data seeding (--skip-db)"
fi

# ---------------------------------------------------------------------------
# Done!
# ---------------------------------------------------------------------------
header "Setup Complete!"

echo -e "${GREEN}${BOLD}  ✓  Virtual environment:  ${VENV_DIR}${NC}"
echo -e "${GREEN}${BOLD}  ✓  Python:               ${PYTHON_VERSION}${NC}"
echo -e "${GREEN}${BOLD}  ✓  Dependencies:         Installed${NC}"
echo -e "${GREEN}${BOLD}  ✓  Environment:          ${ENV_FILE}${NC}"
echo -e "${GREEN}${BOLD}  ✓  Database:             Initialized${NC}"
echo -e "${GREEN}${BOLD}  ✓  Sample data:          Loaded${NC}"
echo ""
echo -e "${CYAN}${BOLD}  Next Steps:${NC}"
echo ""
echo -e "  1. Activate the virtual environment:"
echo -e "     ${YELLOW}source .venv/bin/activate${NC}"
echo ""
echo -e "  2. Start the development server:"
echo -e "     ${YELLOW}python -m ticketinsight.main run${NC}"
echo ""
echo -e "  3. Or run the demo pipeline:"
echo -e "     ${YELLOW}python scripts/run_demo.py${NC}"
echo ""
echo -e "  4. Open in your browser:"
echo -e "     ${BLUE}http://localhost:5000/${NC}         (Dashboard)"
echo -e "     ${BLUE}http://localhost:5000/api/v1/health${NC}  (Health Check)"
echo ""
echo -e "  5. Run the setup wizard for adapter configuration:"
echo -e "     ${YELLOW}python -m ticketinsight.main setup --adapter-type csv${NC}"
echo ""
