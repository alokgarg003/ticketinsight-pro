# =============================================================================
# TicketInsight Pro — Multi-stage Dockerfile
# =============================================================================
# Builds a production-ready container for the ticket analytics platform.
# Uses a two-stage approach to minimise final image size.
#
# Build:   docker build -f docker/Dockerfile -t ticketinsight-pro .
# Run:     docker run -p 5000:5000 --env-file .env ticketinsight-pro
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder — install Python dependencies into an isolated prefix
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies required for some Python packages (e.g. psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install Python packages into /install prefix
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: Runtime — lean production image
# ---------------------------------------------------------------------------
FROM python:3.11-slim

LABEL maintainer="TicketInsight Team <team@ticketinsight.dev>"
LABEL description="TicketInsight Pro — Open Source Ticket Analytics Platform"
LABEL version="1.0.0"

WORKDIR /app

# Install minimal runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder stage
COPY --from=builder /install /usr/local

# Copy project source code and configuration
COPY src/ ./src/
COPY setup.py .
COPY config.yaml* ./

# Copy web assets (templates and static files)
COPY web/ ./web/

# Create application directories
RUN mkdir -p data data/samples logs

# Download spaCy English model
RUN python -m spacy download en_core_web_sm

# Create non-root user for security
RUN useradd -m -u 1000 ticketinsight && \
    chown -R ticketinsight:ticketinsight /app

USER ticketinsight

# Environment variables
ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    TICKETINSIGHT_CONFIG=/app/config.yaml

# Expose application port
EXPOSE 5000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/v1/health')"]

# Run with gunicorn for production
CMD ["gunicorn", \
     "-w", "4", \
     "-b", "0.0.0.0:5000", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "src.ticketinsight.main:create_app()"]
