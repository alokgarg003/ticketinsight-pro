# Deployment Guide

> Comprehensive deployment instructions for TicketInsight Pro.
> Covers Docker, Kubernetes, systemd, cloud platforms, and production hardening.

## Table of Contents

- [Deployment Overview](#deployment-overview)
- [Prerequisites](#prerequisites)
- [Quick Start (Docker Compose)](#quick-start-docker-compose)
- [Docker Deployment](#docker-deployment)
- [Standalone Python Deployment](#standalone-python-deployment)
- [Systemd Service (Linux)](#systemd-service-linux)
- [Reverse Proxy Setup (Nginx)](#reverse-proxy-setup-nginx)
- [SSL/TLS Configuration](#ssltls-configuration)
- [PostgreSQL Setup](#postgresql-setup)
- [Redis Setup](#redis-setup)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Cloud Platform Deployment](#cloud-platform-deployment)
- [Production Hardening](#production-hardening)
- [Monitoring & Observability](#monitoring--observability)
- [Backup & Recovery](#backup--recovery)
- [Troubleshooting](#troubleshooting)
- [Upgrade Guide](#upgrade-guide)

---

## Deployment Overview

TicketInsight Pro can be deployed in several configurations depending on your
infrastructure, scale requirements, and operational preferences.

### Deployment Options Matrix

| Option | Complexity | Scalability | Best For |
|--------|-----------|-------------|----------|
| **Docker Compose** | Low | Low-Medium | Small teams, evaluation, development |
| **Standalone Python** | Low | Low | Simple setups, single-server deployments |
| **Systemd + Nginx** | Medium | Medium | On-premises Linux servers |
| **Kubernetes** | High | High | Enterprise, multi-team, cloud-native |
| **Cloud Managed** | Medium | High | AWS/GCP/Azure deployments |

### Architecture Diagrams

#### Simple Deployment (Docker Compose)

```
┌─────────────────────────────────────────────┐
│              Docker Host                     │
│                                              │
│  ┌──────────────┐  ┌──────────────────┐     │
│  │  TicketInsight│  │   PostgreSQL     │     │
│  │  Pro (App)   │──│   (Database)     │     │
│  │  :8000       │  │   :5432          │     │
│  └──────────────┘  └──────────────────┘     │
│         │                                    │
│  ┌──────────────┐  ┌──────────────────┐     │
│  │    Redis     │  │  Nginx (Proxy)   │     │
│  │  :6379       │  │  :80 / :443      │     │
│  └──────────────┘  └──────────────────┘     │
│                                              │
└─────────────────────────────────────────────┘
```

#### Production Deployment

```
                    Internet
                       │
                  ┌────▼─────┐
                  │  CloudFlare │  (DDoS protection, CDN)
                  └────┬─────┘
                       │
                  ┌────▼─────┐
                  │  Nginx /  │  (Reverse proxy, TLS termination)
                  │  HAProxy  │
                  └────┬─────┘
                       │
              ┌────────┼────────┐
              │        │        │
         ┌────▼───┐ ┌─▼────┐ ┌▼──────┐
         │Worker 1│ │Worker2│ │Worker3│
         │ (API)  │ │ (API) │ │ (API) │
         └────┬───┘ └──┬────┘ └──┬────┘
              │        │        │
              └────────┼────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
    ┌────▼────┐  ┌────▼────┐  ┌───▼─────┐
    │PostgreSQL│  │  Redis  │  │  S3/    │
    │ Primary  │  │ Cluster │  │  MinIO  │
    └────┬────┘  └─────────┘  └─────────┘
         │
    ┌────▼────┐
    │PostgreSQL│
    │ Replica  │  (Read replicas for analytics queries)
    └─────────┘
```

---

## Prerequisites

### System Requirements

| Resource | Minimum | Recommended | High Volume |
|----------|---------|-------------|-------------|
| **CPU** | 2 cores | 4 cores | 8+ cores |
| **Memory** | 2 GB | 4 GB | 8+ GB |
| **Disk** | 10 GB SSD | 50 GB SSD | 200+ GB SSD |
| **Network** | 1 Mbps | 100 Mbps | 1 Gbps |
| **OS** | Linux, macOS, Windows | Ubuntu 22.04 / RHEL 9 | Ubuntu 22.04 LTS |

### Software Dependencies

| Software | Version | Required | Purpose |
|----------|---------|----------|---------|
| **Python** | 3.9+ | Standalone only | Runtime |
| **Docker** | 20.10+ | Docker deployment | Container runtime |
| **Docker Compose** | 2.0+ | Docker deployment | Container orchestration |
| **PostgreSQL** | 14+ | Production DB | Data storage |
| **Redis** | 7.0+ | Production cache | Caching layer |
| **Nginx** | 1.20+ | Production proxy | Reverse proxy, TLS |
| **kubectl** | 1.27+ | K8s deployment | Cluster management |
| **certbot** | 2.0+ | SSL certificates | Let's Encrypt |

### Network Requirements

| Source | Destination | Port | Protocol | Purpose |
|--------|-------------|------|----------|---------|
| TicketInsight | ServiceNow | 443 | HTTPS | Ticket sync |
| TicketInsight | Jira Cloud | 443 | HTTPS | Ticket sync |
| TicketInsight | PostgreSQL | 5432 | TCP | Database |
| TicketInsight | Redis | 6379 | TCP | Cache |
| Clients | TicketInsight | 8000 | HTTP | API access |
| Clients | Nginx | 80, 443 | HTTP/HTTPS | API access (proxied) |

---

## Quick Start (Docker Compose)

The fastest way to get TicketInsight Pro running.

### Step 1: Clone and Configure

```bash
# Clone the repository
git clone https://github.com/yourorg/ticketinsight-pro.git
cd ticketinsight-pro

# Copy the example configuration
cp config.example.yaml config.yaml
cp .env.example .env

# Edit the environment file with your secrets
nano .env
```

### Step 2: Configure Environment

```bash
# .env file - set these values
DB_PASSWORD=<generate-a-strong-password>
ADMIN_API_KEY=<generate-a-random-api-key>
ADMIN_PASSWORD=<set-admin-password>
JWT_SECRET=<generate-a-64-char-random-string>
```

Generate strong passwords:

```bash
# Generate a strong password
openssl rand -base64 32

# Generate a 64-character JWT secret
openssl rand -hex 32

# Generate an API key
echo "tkp_admin_$(openssl rand -hex 16)"
```

### Step 3: Start Services

```bash
# Start all services in detached mode
docker compose up -d

# Check that all services are running
docker compose ps

# View logs
docker compose logs -f ticketinsight
```

### Step 4: Verify Deployment

```bash
# Health check
curl http://localhost:8000/health | jq

# Initialize database (first time only)
docker compose exec ticketinsight ticketinsight db init

# Trigger initial sync
curl -X POST -H "X-API-Key: $ADMIN_API_KEY" \
    http://localhost:8000/api/v1/sync/all | jq

# Check ticket count
curl -H "X-API-Key: $ADMIN_API_KEY" \
    http://localhost:8000/api/v1/analytics/summary?period=30d | jq '.kpis.total_tickets'
```

### Step 5: Stop and Clean Up

```bash
# Stop services (preserves data)
docker compose down

# Stop and remove volumes (deletes all data)
docker compose down -v

# View resource usage
docker stats ticketinsight-pro ticketinsight-db ticketinsight-redis
```

---

## Docker Deployment

### Production Docker Compose

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  app:
    image: ticketinsight/ticketinsight-pro:latest
    container_name: ticketinsight-pro
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"  # Bind to localhost only (Nginx proxies)
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - app-data:/app/data
      - app-logs:/app/logs
      - app-reports:/app/reports
      - app-models:/app/models
    environment:
      - TIP_SERVER__HOST=0.0.0.0
      - TIP_SERVER__PORT=8000
      - TIP_SERVER__WORKERS=4
      - TIP_SERVER__DEBUG=false
      - TIP_DATABASE__TYPE=postgresql
      - TIP_DATABASE__POSTGRESQL__HOST=db
      - TIP_DATABASE__POSTGRESQL__PORT=5432
      - TIP_DATABASE__POSTGRESQL__DATABASE=ticketinsight
      - TIP_DATABASE__POSTGRESQL__USERNAME=tip
      - TIP_DATABASE__POSTGRESQL__PASSWORD=${DB_PASSWORD}
      - TIP_DATABASE__POSTGRESQL__POOL_SIZE=20
      - TIP_DATABASE__POSTGRESQL__SSL_MODE=require
      - TIP_CACHE__TYPE=redis
      - TIP_CACHE__REDIS__URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - TIP_LOGGING__LEVEL=INFO
      - TIP_LOGGING__FORMAT=json
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '4.0'
        reservations:
          memory: 1G
          cpus: '1.0'
    logging:
      driver: json-file
      options:
        max-size: "100m"
        max-file: "5"
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp

  db:
    image: postgres:15-alpine
    container_name: ticketinsight-db
    restart: unless-stopped
    volumes:
      - postgres-data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: ticketinsight
      POSTGRES_USER: tip
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    # Do not expose port externally
    # ports:
    #   - "127.0.0.1:5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tip -d ticketinsight"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "3"
    security_opt:
      - no-new-privileges:true

  redis:
    image: redis:7-alpine
    container_name: ticketinsight-redis
    restart: unless-stopped
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD}
      --maxmemory 512mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
    volumes:
      - redis-data:/data
    # Do not expose port externally
    # ports:
    #   - "127.0.0.1:6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 768M
          cpus: '1.0'
    logging:
      driver: json-file
      options:
        max-size: "20m"
        max-file: "3"
    security_opt:
      - no-new-privileges:true

volumes:
  postgres-data:
    driver: local
  redis-data:
    driver: local
  app-data:
    driver: local
  app-logs:
    driver: local
  app-reports:
    driver: local
  app-models:
    driver: local
```

### Building Custom Docker Images

```dockerfile
# Dockerfile
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim AS production

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r tip && useradd -r -g tip -d /app tip

# Copy installed packages from builder
COPY --from=builder /root/.local /home/tip/.local
ENV PATH=/home/tip/.local/bin:$PATH

# Copy application code
COPY --chown=tip:tip . .

# Create required directories
RUN mkdir -p /app/data /app/logs /app/reports /app/models \
    && chown -R tip:tip /app

# Switch to non-root user
USER tip

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
    CMD curl -f http://localhost:8000/health || exit 1

# Use tini as init system
ENTRYPOINT ["tini", "--"]

# Start the application
CMD ["ticketinsight", "serve", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

```bash
# Build the image
docker build -t ticketinsight-pro:custom .

# Build with build args
docker build \
    --build-arg PYTHON_VERSION=3.11 \
    -t ticketinsight-pro:v1.0.0 \
    .

# Push to a registry
docker tag ticketinsight-pro:v1.0.0 registry.example.com/ticketinsight-pro:v1.0.0
docker push registry.example.com/ticketinsight-pro:v1.0.0
```

---

## Standalone Python Deployment

For deployments without Docker, install directly on the host system.

### Step 1: Install Python Dependencies

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip \
    build-essential libffi-dev libssl-dev

# RHEL/CentOS
sudo dnf install -y python3.11 python3.11-pip gcc \
    libffi-devel openssl-devel

# Verify Python version
python3.11 --version
```

### Step 2: Install TicketInsight Pro

```bash
# Create application user
sudo useradd -r -m -s /bin/bash tip
sudo su - tip

# Create virtual environment
python3.11 -m venv /opt/ticketinsight/venv
source /opt/ticketinsight/venv/bin/activate

# Install the application
pip install --upgrade pip wheel setuptools
pip install ticketinsight-pro

# Or install from source
git clone https://github.com/yourorg/ticketinsight-pro.git /opt/ticketinsight/src
cd /opt/ticketinsight/src
pip install -e .

# Install with optional dependencies
pip install "ticketinsight-pro[postgres,redis,dev]"
```

### Step 3: Configure

```bash
# Copy configuration
sudo mkdir -p /etc/ticketinsight
sudo cp config.example.yaml /etc/ticketinsight/config.yaml
sudo chown tip:tip /etc/ticketinsight/config.yaml

# Create data directories
sudo mkdir -p /var/lib/ticketinsight/{data,logs,reports,models}
sudo chown -R tip:tip /var/lib/ticketinsight

# Set environment variables
sudo tee /etc/default/ticketinsight << 'EOF'
TIP_CONFIG_PATH=/etc/ticketinsight/config.yaml
TIP_DATABASE__TYPE=postgresql
TIP_DATABASE__POSTGRESQL__HOST=localhost
TIP_DATABASE__POSTGRESQL__PORT=5432
TIP_DATABASE__POSTGRESQL__DATABASE=ticketinsight
TIP_DATABASE__POSTGRESQL__USERNAME=tip
TIP_DATABASE__POSTGRESQL__PASSWORD=your_password_here
TIP_CACHE__TYPE=redis
TIP_CACHE__REDIS__URL=redis://localhost:6379/0
ADMIN_API_KEY=tkp_admin_your_key_here
JWT_SECRET=your_64_char_random_string_here
EOF
```

### Step 4: Initialize and Start

```bash
# Initialize database
source /opt/ticketinsight/venv/bin/activate
ticketinsight --config /etc/ticketinsight/config.yaml db init

# Verify configuration
ticketinsight config validate

# Test server
ticketinsight serve --host 127.0.0.1 --port 8000
```

---

## Systemd Service (Linux)

Create a systemd service to manage TicketInsight Pro as a background service.

### Service File

```ini
# /etc/systemd/system/ticketinsight.service
[Unit]
Description=TicketInsight Pro - Ticket Analytics Platform
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=notify
User=tip
Group=tip
EnvironmentFile=/etc/default/ticketinsight
ExecStart=/opt/ticketinsight/venv/bin/ticketinsight serve \
    --config /etc/ticketinsight/config.yaml \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 4
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60
TimeoutStartSec=60
TimeoutStopSec=30
WorkingDirectory=/opt/ticketinsight

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/ticketinsight
ReadOnlyPaths=/etc/ticketinsight

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096
MemoryMax=4G
CPUQuota=400%

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ticketinsight

[Install]
WantedBy=multi-user.target
```

### Management Commands

```bash
# Reload systemd
sudo systemctl daemon-reload

# Start the service
sudo systemctl start ticketinsight

# Enable on boot
sudo systemctl enable ticketinsight

# Check status
sudo systemctl status ticketinsight

# View logs
sudo journalctl -u ticketinsight -f

# View logs since yesterday
sudo journalctl -u ticketinsight --since yesterday

# Restart
sudo systemctl restart ticketinsight

# Stop
sudo systemctl stop ticketinsight
```

---

## Reverse Proxy Setup (Nginx)

### Install Nginx

```bash
# Ubuntu/Debian
sudo apt install -y nginx

# RHEL/CentOS
sudo dnf install -y nginx
```

### Nginx Configuration

```nginx
# /etc/nginx/sites-available/ticketinsight
upstream ticketinsight_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name ticketinsight.yourcompany.com;

    # Let's Encrypt challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ticketinsight.yourcompany.com;

    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/ticketinsight.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ticketinsight.yourcompany.com/privkey.pem;

    # SSL settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Gzip compression
    gzip on;
    gzip_types application/json text/plain text/html;
    gzip_min_length 1000;

    # Request size limits
    client_max_body_size 50M;

    # Proxy settings
    location / {
        proxy_pass http://ticketinsight_backend;
        proxy_http_version 1.1;

        # Header forwarding
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 30s;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;

        # Buffering
        proxy_buffering on;
        proxy_buffer_size 16k;
        proxy_buffers 4 32k;
    }

    # Health check endpoint (no auth required)
    location /health {
        proxy_pass http://ticketinsight_backend/health;
        access_log off;
    }

    # API documentation (restrict access)
    location /docs {
        proxy_pass http://ticketinsight_backend/docs;
        allow 10.0.0.0/8;  # Internal network only
        deny all;
    }

    # Block sensitive paths
    location ~ /\.(?!well-known) {
        deny all;
        return 404;
    }

    # Access and error logs
    access_log /var/log/nginx/ticketinsight_access.log;
    error_log /var/log/nginx/ticketinsight_error.log;
}
```

### Enable the Configuration

```bash
# Create symlink
sudo ln -sf /etc/nginx/sites-available/ticketinsight /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

---

## SSL/TLS Configuration

### Let's Encrypt with Certbot

```bash
# Install certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain certificate (first time)
sudo certbot certonly --nginx \
    -d ticketinsight.yourcompany.com \
    --email admin@yourcompany.com \
    --agree-tos \
    --no-eff-email

# Test automatic renewal
sudo certbot renew --dry-run

# Set up automatic renewal (cron)
sudo tee /etc/cron.d/certbot << 'EOF'
0 */12 * * * root certbot renew --quiet --deploy-hook "systemctl reload nginx"
EOF
```

### Self-Signed Certificate (Development Only)

```bash
# Generate self-signed certificate
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/ssl/private/ticketinsight.key \
    -out /etc/ssl/certs/ticketinsight.crt \
    -subj "/CN=ticketinsight.yourcompany.com"

# Update Nginx to use self-signed certs
# ssl_certificate /etc/ssl/certs/ticketinsight.crt;
# ssl_certificate_key /etc/ssl/private/ticketinsight.key;
```

---

## PostgreSQL Setup

### Installation

```bash
# Ubuntu/Debian
sudo apt install -y postgresql-15 postgresql-15-contrib

# Start and enable
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### Database Creation

```sql
-- Connect as postgres user
sudo -u postgres psql

-- Create database and user
CREATE DATABASE ticketinsight;
CREATE USER tip WITH ENCRYPTED PASSWORD 'your_strong_password_here';
GRANT ALL PRIVILEGES ON DATABASE ticketinsight TO tip;

-- Connect to the database
\c ticketinsight

-- Grant schema permissions
GRANT ALL ON SCHEMA public TO tip;

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- Fuzzy text matching
CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; -- UUID generation
```

### Configuration Tuning

```ini
# /etc/postgresql/15/main/postgresql.conf

# Connection settings
max_connections = 100
superuser_reserved_connections = 3

# Memory settings (adjust based on available RAM)
shared_buffers = 1GB
effective_cache_size = 3GB
maintenance_work_mem = 512MB
work_mem = 32MB

# WAL settings
wal_level = replica
max_wal_size = 2GB
min_wal_size = 512MB
checkpoint_completion_target = 0.9

# Query tuning
random_page_cost = 1.1
effective_io_concurrency = 200
default_statistics_target = 100

# Logging
log_min_duration_statement = 500  # Log slow queries (>500ms)
log_checkpoints = on
log_connections = on
log_disconnections = on
log_lock_waits = on
```

### Backup Configuration

```bash
# Create backup script
sudo tee /opt/ticketinsight/scripts/backup-db.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/var/backups/ticketinsight"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
KEEP_DAYS=30

mkdir -p "$BACKUP_DIR"

# Create backup
pg_dump -U tip -h localhost -d ticketinsight \
    | gzip > "$BACKUP_DIR/ticketinsight_$TIMESTAMP.sql.gz"

# Remove old backups
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$KEEP_DAYS -delete

echo "Backup completed: ticketinsight_$TIMESTAMP.sql.gz"
SCRIPT

sudo chmod +x /opt/ticketinsight/scripts/backup-db.sh

# Schedule daily backup at 2 AM
echo "0 2 * * * tip /opt/ticketinsight/scripts/backup-db.sh" | \
    sudo tee /etc/cron.d/ticketinsight-backup
```

---

## Redis Setup

### Installation

```bash
# Ubuntu/Debian
sudo apt install -y redis-server

# Start and enable
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### Configuration

```ini
# /etc/redis/redis.conf

# Network
bind 127.0.0.1
port 6379
protected-mode yes

# Authentication
requirepass your_redis_password_here

# Memory management
maxmemory 512mb
maxmemory-policy allkeys-lru

# Persistence
appendonly yes
appendfsync everysec
save 900 1
save 300 10
save 60 10000

# Logging
loglevel notice
logfile /var/log/redis/redis.log
```

### Connection Testing

```bash
# Test connection
redis-cli -a your_redis_password_here ping
# Expected: PONG

# Monitor commands
redis-cli -a your_redis_password_here monitor

# Check memory usage
redis-cli -a your_redis_password_here info memory
```

---

## Kubernetes Deployment

### Namespace and Secrets

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: ticketinsight
  labels:
    app: ticketinsight
---
# secrets.yaml (create with: kubectl create secret generic ...)
apiVersion: v1
kind: Secret
metadata:
  name: ticketinsight-secrets
  namespace: ticketinsight
type: Opaque
stringData:
  db-password: <your-db-password>
  redis-password: <your-redis-password>
  admin-api-key: <your-api-key>
  jwt-secret: <your-jwt-secret>
  admin-password: <your-admin-password>
  snow-user: <servicenow-user>
  snow-pass: <servicenow-password>
```

### ConfigMap

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ticketinsight-config
  namespace: ticketinsight
data:
  config.yaml: |
    server:
      host: "0.0.0.0"
      port: 8000
      workers: 4
      debug: false
    database:
      type: postgresql
      postgresql:
        host: ticketinsight-db
        port: 5432
        database: ticketinsight
        username: tip
    cache:
      type: redis
      redis:
        url: "redis://:${REDIS_PASSWORD}@ticketinsight-redis:6379/0"
    nlp:
      categorizer:
        model: tfidf_nb
    ml:
      priority_predictor:
        enabled: true
```

### Deployment

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ticketinsight
  namespace: ticketinsight
  labels:
    app: ticketinsight
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ticketinsight
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: ticketinsight
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/api/v1/system/metrics"
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
        - name: ticketinsight
          image: ticketinsight/ticketinsight-pro:latest
          ports:
            - containerPort: 8000
              protocol: TCP
          env:
            - name: TIP_CONFIG_PATH
              value: /app/config/config.yaml
            - name: TIP_DATABASE__POSTGRESQL__PASSWORD
              valueFrom:
                secretKeyRef:
                  name: ticketinsight-secrets
                  key: db-password
            - name: TIP_CACHE__REDIS__URL
              value: "redis://:$(REDIS_PASSWORD)@ticketinsight-redis:6379/0"
            - name: REDIS_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: ticketinsight-secrets
                  key: redis-password
            - name: ADMIN_API_KEY
              valueFrom:
                secretKeyRef:
                  name: ticketinsight-secrets
                  key: admin-api-key
          volumeMounts:
            - name: config
              mountPath: /app/config
              readOnly: true
            - name: data
              mountPath: /app/data
            - name: models
              mountPath: /app/models
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "2Gi"
              cpu: "2000m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 30
            timeoutSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
      volumes:
        - name: config
          configMap:
            name: ticketinsight-config
        - name: data
          persistentVolumeClaim:
            claimName: ticketinsight-data
        - name: models
          persistentVolumeClaim:
            claimName: ticketinsight-models
```

### Service and Ingress

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: ticketinsight
  namespace: ticketinsight
spec:
  type: ClusterIP
  ports:
    - port: 80
      targetPort: 8000
      protocol: TCP
  selector:
    app: ticketinsight
---
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ticketinsight
  namespace: ticketinsight
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/rate-limit: "60"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
    - hosts:
        - ticketinsight.yourcompany.com
      secretName: ticketinsight-tls
  rules:
    - host: ticketinsight.yourcompany.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: ticketinsight
                port:
                  number: 80
```

### Deploy to Cluster

```bash
# Create namespace
kubectl apply -f namespace.yaml

# Create secrets
kubectl create secret generic ticketinsight-secrets \
    --from-literal=db-password=$DB_PASSWORD \
    --from-literal=redis-password=$REDIS_PASSWORD \
    --from-literal=admin-api-key=$ADMIN_API_KEY \
    --from-literal=jwt-secret=$JWT_SECRET \
    -n ticketinsight

# Apply all resources
kubectl apply -f configmap.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml

# Check deployment status
kubectl -n ticketinsight get pods
kubectl -n ticketinsight logs -f deployment/ticketinsight

# Scale up
kubectl -n ticketinsight scale deployment ticketinsight --replicas=5
```

---

## Cloud Platform Deployment

### AWS (ECS Fargate)

```bash
# Using AWS CLI and CloudFormation
aws cloudformation deploy \
    --template-file infra/aws/cloudformation.yaml \
    --stack-name ticketinsight-pro \
    --parameter-overrides \
        Environment=production \
        DBInstanceClass=db.t3.medium \
        RedisNodeType=cache.t3.medium \
    --capabilities CAPABILITY_IAM
```

### Google Cloud (Cloud Run)

```bash
# Build and push container
gcloud builds submit --tag gcr.io/PROJECT_ID/ticketinsight-pro

# Deploy to Cloud Run
gcloud run deploy ticketinsight-pro \
    --image gcr.io/PROJECT_ID/ticketinsight-pro \
    --platform managed \
    --region us-central1 \
    --memory 2Gi \
    --cpu 2 \
    --min-instances 1 \
    --max-instances 10 \
    --set-env-vars TIP_DATABASE__TYPE=postgresql \
    --set-secrets DB_PASSWORD=ticketinsight-db-password:latest \
    --allow-unauthenticated
```

### Azure (Container Apps)

```bash
# Create resource group
az group create --name ticketinsight-rg --location eastus

# Deploy container app
az containerapp up \
    --name ticketinsight-pro \
    --resource-group ticketinsight-rg \
    --image ticketinsight/ticketinsight-pro:latest \
    --environment ticketinsight-env \
    --target-port 8000 \
    --ingress external \
    --min-replicas 1 \
    --max-replicas 10 \
    --cpu 2 \
    --memory 4Gi \
    --env-vars TIP_SERVER__WORKERS=4
```

---

## Production Hardening

### Security Checklist

- [ ] Run as non-root user (user `tip`, UID 1000)
- [ ] Use HTTPS/TLS everywhere (no HTTP access)
- [ ] Set strong, unique passwords for all services
- [ ] Use environment variables or secret management for sensitive values
- [ ] Enable rate limiting on the API
- [ ] Restrict CORS origins to known domains
- [ ] Enable audit logging for admin actions
- [ ] Rotate API keys and JWT secrets periodically
- [ ] Keep Docker images and dependencies up to date
- [ ] Enable container image scanning (Trivy, Grype)
- [ ] Use network policies to restrict pod communication (Kubernetes)
- [ ] Enable database SSL connections
- [ ] Configure Redis with password authentication
- [ ] Restrict file system permissions (read-only where possible)
- [ ] Set up firewall rules to limit inbound access

### Performance Tuning

| Component | Setting | Recommendation |
|-----------|---------|---------------|
| **Workers** | `server.workers` | `(CPU cores * 2) + 1` |
| **DB Pool** | `database.pool_size` | `workers * 5` |
| **DB Pool Overflow** | `database.max_overflow` | `pool_size` |
| **Cache TTL** | `cache.ttl_seconds` | 300-1800 (by data type) |
| **Batch Size** | `sync.batch_size` | 500 (adjust per adapter) |
| **Log Level** | `logging.level` | `INFO` (use `DEBUG` only for troubleshooting) |

---

## Monitoring & Observability

### Health Check Script

```bash
#!/bin/bash
# /opt/ticketinsight/scripts/health-check.sh

HEALTH_URL="http://localhost:8000/health"
ALERT_EMAIL="ops@yourcompany.com"

response=$(curl -sf "$HEALTH_URL" 2>/dev/null)

if [ $? -ne 0 ]; then
    echo "CRITICAL: TicketInsight Pro is not responding"
    # Send alert (mail, slack webhook, etc.)
    exit 2
fi

status=$(echo "$response" | jq -r '.status')
if [ "$status" != "healthy" ]; then
    echo "WARNING: TicketInsight Pro status: $status"
    exit 1
fi

echo "OK: TicketInsight Pro is healthy"
exit 0
```

### Prometheus Integration

```yaml
# prometheus.yml scrape config
scrape_configs:
  - job_name: 'ticketinsight'
    scrape_interval: 30s
    metrics_path: '/api/v1/system/metrics'
    static_configs:
      - targets: ['ticketinsight:8000']
    bearer_token: 'your-api-key'
```

### Log Aggregation

Configure structured JSON logging for integration with log aggregation systems:

```yaml
# config.yaml
logging:
  level: INFO
  format: json
  output: stdout
```

Sample log output:
```json
{
    "timestamp": "2024-01-15T10:30:00.123Z",
    "level": "INFO",
    "logger": "ticketinsight.api.tickets",
    "message": "Ticket list retrieved",
    "request_id": "req_abc123",
    "user": "admin",
    "duration_ms": 45,
    "filters": {"status": "open", "limit": 50}
}
```

---

## Backup & Recovery

### Backup Strategy

| Component | Method | Frequency | Retention |
|-----------|--------|-----------|-----------|
| **Database** | `pg_dump` | Daily | 30 days |
| **Database** | WAL archiving | Continuous | 7 days |
| **ML Models** | File copy | Weekly | 90 days |
| **Configuration** | Git | On change | Indefinite |
| **Reports** | File copy | Daily | 90 days |

### Full Backup Script

```bash
#!/bin/bash
# /opt/ticketinsight/scripts/full-backup.sh
set -euo pipefail

BACKUP_DIR="/var/backups/ticketinsight"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
APP_DIR="/var/lib/ticketinsight"
KEEP_DAYS=30

mkdir -p "$BACKUP_DIR/$TIMESTAMP"

# 1. Database backup
echo "Backing up database..."
pg_dump -U tip -h localhost -d ticketinsight \
    | gzip > "$BACKUP_DIR/$TIMESTAMP/database.sql.gz"

# 2. ML models backup
echo "Backing up ML models..."
tar czf "$BACKUP_DIR/$TIMESTAMP/models.tar.gz" \
    -C "$APP_DIR" models/ 2>/dev/null || echo "No models to backup"

# 3. Configuration backup
echo "Backing up configuration..."
cp /etc/ticketinsight/config.yaml "$BACKUP_DIR/$TIMESTAMP/"
cp /etc/default/ticketinsight "$BACKUP_DIR/$TIMESTAMP/" 2>/dev/null || true

# 4. Generate checksum
echo "Generating checksums..."
sha256sum "$BACKUP_DIR/$TIMESTAMP"/* > "$BACKUP_DIR/$TIMESTAMP/checksums.sha256"

# 5. Cleanup old backups
echo "Cleaning up old backups..."
find "$BACKUP_DIR" -maxdepth 1 -type d -mtime +$KEEP_DAYS -exec rm -rf {} +

echo "Backup completed: $BACKUP_DIR/$TIMESTAMP"
ls -lh "$BACKUP_DIR/$TIMESTAMP/"
```

### Recovery Procedure

```bash
# 1. Stop the service
sudo systemctl stop ticketinsight

# 2. Restore database
gunzip < /var/backups/ticketinsight/20240115/database.sql.gz | \
    psql -U tip -h localhost -d ticketinsight

# 3. Restore models
tar xzf /var/backups/ticketinsight/20240115/models.tar.gz \
    -C /var/lib/ticketinsight/

# 4. Restore configuration
cp /var/backups/ticketinsight/20240115/config.yaml /etc/ticketinsight/
sudo chown tip:tip /etc/ticketinsight/config.yaml

# 5. Start the service
sudo systemctl start ticketinsight

# 6. Verify
curl -s http://localhost:8000/health | jq
```

---

## Troubleshooting

### Common Issues

#### Service Won't Start

```bash
# Check logs
sudo journalctl -u ticketinsight -n 100 --no-pager

# Common causes:
# 1. Database connection failed → Check DB is running and credentials
# 2. Port already in use → Check with: ss -tlnp | grep 8000
# 3. Config file not found → Verify path in service file
# 4. Permission denied → Check file ownership: ls -la /var/lib/ticketinsight/
```

#### Database Connection Errors

```bash
# Test database connectivity
psql -U tip -h localhost -d ticketinsight -c "SELECT 1;"

# Check PostgreSQL is running
sudo systemctl status postgresql

# Check connection limits
psql -U tip -d ticketinsight -c "SELECT count(*) FROM pg_stat_activity;"

# Reset connection pool
sudo systemctl restart ticketinsight
```

#### Sync Failures

```bash
# Check adapter connection
curl -X POST -H "X-API-Key: $API_KEY" \
    http://localhost:8000/api/v1/adapters/servicenow/test | jq

# Check sync logs
curl -H "X-API-Key: $API_KEY" \
    http://localhost:8000/api/v1/sync/servicenow/logs | jq '.logs[0]'

# Trigger manual sync with verbose logging
TIP_LOGGING__LEVEL=DEBUG ticketinsight sync servicenow --verbose
```

#### High Memory Usage

```bash
# Check process memory
ps aux | grep ticketinsight

# Check database memory
psql -U tip -d ticketinsight -c "SELECT * FROM pg_stat_user_tables ORDER BY n_live_tup DESC;"

# Reduce worker count in config
# server.workers: 2

# Clear Redis cache
redis-cli -a $REDIS_PASSWORD FLUSHDB
```

---

## Upgrade Guide

### Standard Upgrade

```bash
# 1. Backup current state
sudo /opt/ticketinsight/scripts/full-backup.sh

# 2. Pull latest version
cd /opt/ticketinsight/src
git pull origin main

# 3. Update dependencies
source /opt/ticketinsight/venv/bin/activate
pip install -e .

# 4. Run database migrations
ticketinsight db migrate

# 5. Restart service
sudo systemctl restart ticketinsight

# 6. Verify health
curl -s http://localhost:8000/health | jq

# 7. Check version
curl -s http://localhost:8000/api/v1/system/version | jq
```

### Docker Upgrade

```bash
# 1. Pull latest image
docker compose pull

# 2. Run database migrations
docker compose exec ticketinsight ticketinsight db migrate

# 3. Restart services
docker compose up -d

# 4. Verify
curl -s http://localhost:8000/health | jq
```

### Rollback Procedure

```bash
# Revert to previous version
cd /opt/ticketinsight/src
git checkout v1.0.0  # or previous tag

# Reinstall
pip install -e .

# Restore database from backup
gunzip < /var/backups/ticketinsight/PREVIOUS/database.sql.gz | \
    psql -U tip -h localhost -d ticketinsight

# Restart
sudo systemctl restart ticketinsight
```
