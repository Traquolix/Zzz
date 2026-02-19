# IMREDD Deployment Guide

This guide covers deploying SequoIA on the IMREDD infrastructure.

---

## Architecture Overview

```
                           INTERNET
                              │
                              │ HTTPS (443)
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              IMREDD NETWORK                                  │
│                                                                              │
│  ┌──────────────────────┐                                                   │
│  │   FRONTEND SERVER    │                                                   │
│  │   134.59.98.100      │                                                   │
│  │                      │                                                   │
│  │  nginx + React       │                                                   │
│  │  Let's Encrypt TLS   │                                                   │
│  └──────────┬───────────┘                                                   │
│             │                                                               │
│             │ port 8001 (API)                                               │
│             ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         VPN IMREDD-GEOAZUR                           │   │
│  │                                                                      │   │
│  │  ┌──────────────────────┐          ┌──────────────────────┐         │   │
│  │  │   BACKEND SERVER     │◄─────────│      DAS HARDWARE    │         │   │
│  │  │   192.168.99.113     │  9092    │   192.168.99.110     │         │   │
│  │  │                      │  8081    │                      │         │   │
│  │  │  Docker services:    │          │  Produces Kafka      │         │   │
│  │  │  - Kafka             │          │  messages to topic   │         │   │
│  │  │  - Schema Registry   │          │                      │         │   │
│  │  │  - ClickHouse        │          └──────────────────────┘         │   │
│  │  │  - PostgreSQL        │                                           │   │
│  │  │  - Redis             │                                           │   │
│  │  │  - DAS Processor     │                                           │   │
│  │  │  - AI Engine (GPU)   │                                           │   │
│  │  │  - Platform Backend  │                                           │   │
│  │  │  - OTEL-LGTM         │                                           │   │
│  │  └──────────────────────┘                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: Backend Server Setup (192.168.99.113)

### 1.1 Prerequisites

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Log out and back in, then verify
docker --version
```

### 1.2 Install NVIDIA Container Toolkit

```bash
# Add NVIDIA repository
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit

# Configure Docker to use NVIDIA runtime
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Verify GPU access
docker run --rm --gpus all nvidia/cuda:12.2-base-ubuntu22.04 nvidia-smi
```

### 1.3 Create Data Directories

```bash
sudo mkdir -p /mnt/{kafka-data,clickhouse-data,postgres-data,redis-data}
sudo chown -R 1001:1001 /mnt/kafka-data      # Kafka user
sudo chown -R 101:101 /mnt/clickhouse-data   # ClickHouse user
sudo chown -R 999:999 /mnt/postgres-data     # PostgreSQL user
sudo chown -R 999:999 /mnt/redis-data        # Redis user
```

### 1.4 Deploy Application

```bash
# Clone or copy the repository
cd /opt
git clone <your-repo-url> sequoia
cd sequoia

# Or if transferring manually:
scp -r /path/to/Pipeline user@192.168.99.113:/opt/sequoia
```

### 1.5 Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with production values:

```bash
# Deployment
VERSION=v1.0.0
ENVIRONMENT=production
LOG_LEVEL=INFO

# Data paths
KAFKA_DATA_PATH=/mnt/kafka-data
CLICKHOUSE_DATA_PATH=/mnt/clickhouse-data
POSTGRES_DATA_PATH=/mnt/postgres-data
REDIS_DATA_PATH=/mnt/redis-data

# Kafka - expose to DAS hardware
KAFKA_BOOTSTRAP_SERVERS=kafka:29092
KAFKA_EXTERNAL_HOST=192.168.99.113
SCHEMA_REGISTRY_URL=http://schema-registry:8081

# Database credentials (use strong passwords)
POSTGRES_PASSWORD=<generate-strong-password>
CLICKHOUSE_PASSWORD=<generate-strong-password>
REDIS_PASSWORD=<generate-strong-password>

# Django
DJANGO_SECRET_KEY=<generate-64-char-secret>
DJANGO_ALLOWED_HOSTS=192.168.99.113,localhost
CORS_ALLOWED_ORIGINS=https://134.59.98.100,https://your-domain.com
FRONTEND_URL=https://134.59.98.100

# JWT keys (generate with commands below)
JWT_SIGNING_KEY=<paste-private-key-with-\n-for-newlines>
JWT_VERIFYING_KEY=<paste-public-key-with-\n-for-newlines>

# AI Engine
AI_MAX_CONCURRENT=10
ENABLE_COUNTING=true

# DAS settings (match your fiber configuration)
DAS_FIBER_NAMES=carros
DAS_CHANNEL_COUNT=2829
```

### 1.6 Generate Secrets

```bash
# Django secret key
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# Database passwords
openssl rand -base64 24

# JWT RS256 keys
openssl genrsa 2048 > jwt_private.pem
openssl rsa -in jwt_private.pem -pubout > jwt_public.pem

# View keys (copy to .env, replace newlines with \n)
cat jwt_private.pem
cat jwt_public.pem
```

### 1.7 Create Backend-Only Compose Override

Create `docker-compose.override.yml` to disable the frontend container:

```yaml
# docker-compose.override.yml
# Disables frontend - served from separate server

services:
  platform-frontend:
    deploy:
      replicas: 0
```

### 1.8 Start Services

```bash
# Start all backend services with GPU support
docker compose --profile gpu up -d

# Verify all services are running
docker compose ps

# Check logs
docker compose logs -f platform-backend
docker compose logs -f ai-engine
```

### 1.9 Initialize Database

```bash
# Run Django migrations
docker compose exec platform-backend python manage.py migrate

# Create superuser
docker compose exec platform-backend python manage.py createsuperuser
```

### 1.10 Configure Firewall

```bash
# Allow Kafka from DAS hardware
sudo ufw allow from 192.168.99.110 to any port 9092
sudo ufw allow from 192.168.99.110 to any port 8081

# Allow API from frontend server
sudo ufw allow from 134.59.98.100 to any port 8001

# Allow SSH/NoMachine
sudo ufw allow 22
sudo ufw allow 4000

# Enable firewall
sudo ufw enable
```

### 1.11 Verify Backend

```bash
# Test API
curl http://localhost:8001/api/health/

# Test Kafka is accessible from DAS IP
# (run from DAS machine)
nc -zv 192.168.99.113 9092
nc -zv 192.168.99.113 8081

# Check Grafana dashboards
# Access at http://192.168.99.113:3002
```

---

## Part 2: Frontend Server Setup (134.59.98.100)

> **Note:** The frontend server does NOT need the full repository. You only deploy
> the built static files (~5MB) from `dist/`. No Node.js, no source code.

### 2.1 Install Dependencies (on frontend server)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y nginx certbot python3-certbot-nginx
```

### 2.2 Build Frontend (on your development machine)

```bash
# Clone repo (if not already)
git clone <your-repo> sequoia
cd sequoia/services/platform/frontend

# Install dependencies
npm install

# Build with production settings (uses values from .env.example)
VITE_API_BASE_URL=http://192.168.99.113:8001 \
VITE_MAPBOX_TOKEN=pk.eyJ1Ijoic3lwaGVyciIsImEiOiJjbWcwOGZodHEwMnJyMmxzNnBveDdidWxsIn0.db7Lk0ON4mG1zqMVUZXMYg \
npm run build

# Result: dist/ folder (~5MB of static files)
ls -la dist/
```

### 2.3 Transfer Build to Frontend Server

```bash
# From your development machine - only copy the dist folder
scp -r dist/* user@134.59.98.100:/tmp/sequoia-frontend/

# That's it - no need to clone the repo on the frontend server
```

### 2.4 Deploy Static Files

```bash
# On frontend server
sudo mkdir -p /var/www/sequoia
sudo cp -r /tmp/sequoia-frontend/* /var/www/sequoia/
sudo chown -R www-data:www-data /var/www/sequoia
```

### 2.5 Configure nginx

Create `/etc/nginx/sites-available/sequoia`:

```nginx
server {
    listen 80;
    server_name 134.59.98.100;  # Or your domain name

    root /var/www/sequoia;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Serve static files with caching
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # SPA routing - serve index.html for all routes
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Health check endpoint
    location /health {
        return 200 'OK';
        add_header Content-Type text/plain;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/sequoia /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default  # Remove default site
sudo nginx -t
sudo systemctl reload nginx
```

### 2.6 Configure Let's Encrypt TLS

If you have a domain name pointing to 134.59.98.100:

```bash
sudo certbot --nginx -d your-domain.com
```

If using IP only (self-signed certificate):

```bash
# Generate self-signed certificate
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/sequoia.key \
  -out /etc/ssl/certs/sequoia.crt \
  -subj "/CN=134.59.98.100"
```

Update nginx config for HTTPS:

```nginx
server {
    listen 80;
    server_name 134.59.98.100;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name 134.59.98.100;

    ssl_certificate /etc/ssl/certs/sequoia.crt;
    ssl_certificate_key /etc/ssl/private/sequoia.key;

    # Or with Let's Encrypt:
    # ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    add_header Strict-Transport-Security "max-age=63072000" always;

    root /var/www/sequoia;
    index index.html;

    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 2.7 Configure Firewall

```bash
sudo ufw allow 80
sudo ufw allow 443
sudo ufw allow 22
sudo ufw allow 4000
sudo ufw enable
```

---

## Part 3: DAS Hardware Configuration (192.168.99.110)

The DAS hardware should be configured to send Kafka messages to:

- **Kafka Bootstrap**: `192.168.99.113:9092`
- **Schema Registry**: `http://192.168.99.113:8081`
- **Topic**: `das-raw` (or as configured in your fiber config)

Verify connectivity:

```bash
# From DAS machine
nc -zv 192.168.99.113 9092
nc -zv 192.168.99.113 8081
```

---

## Part 4: Verification Checklist

### Backend Server (192.168.99.113)

- [ ] `docker compose ps` shows all services healthy
- [ ] `curl http://localhost:8001/api/health/` returns 200
- [ ] Grafana accessible at http://192.168.99.113:3002
- [ ] GPU visible: `docker compose exec ai-engine nvidia-smi`
- [ ] Kafka accepting connections on port 9092
- [ ] Schema Registry accessible on port 8081

### Frontend Server (134.59.98.100)

- [ ] https://134.59.98.100 loads the dashboard
- [ ] Login form appears
- [ ] No browser console errors about API connection

### DAS Hardware (192.168.99.110)

- [ ] Can reach Kafka at 192.168.99.113:9092
- [ ] Can reach Schema Registry at 192.168.99.113:8081
- [ ] Messages appearing in Kafka topic

### End-to-End

- [ ] Login works on dashboard
- [ ] Data appears on map after DAS starts sending
- [ ] Real-time updates visible (with ~25s latency)
- [ ] Speed/count graphs populated

---

## Part 5: Troubleshooting

### API Connection Failed (CORS errors)

1. Check `CORS_ALLOWED_ORIGINS` in backend `.env` includes frontend URL
2. Ensure protocol matches (https vs http)
3. Restart backend: `docker compose restart platform-backend`

### No Data Appearing

1. Check DAS is sending to Kafka:
   ```bash
   docker compose exec kafka kafka-console-consumer \
     --bootstrap-server localhost:9092 \
     --topic das-raw --from-beginning --max-messages 5
   ```

2. Check processor is consuming:
   ```bash
   docker compose logs -f das-processor | grep -i "processing"
   ```

3. Check AI engine is running:
   ```bash
   docker compose logs -f ai-engine | grep -i "inference"
   ```

### GPU Not Detected

```bash
# Check NVIDIA driver
nvidia-smi

# Check Docker GPU access
docker run --rm --gpus all nvidia/cuda:12.2-base-ubuntu22.04 nvidia-smi

# Check AI engine sees GPU
docker compose logs ai-engine | grep -i "cuda\|gpu"
```

### High Latency

1. Check consumer lag in Grafana
2. Check AI inference times: should be < 5s per window
3. Consider reducing `AI_MAX_CONCURRENT` if GPU memory constrained

---

## Part 6: Maintenance

### Backups

See [BACKUP_STRATEGY.md](./BACKUP_STRATEGY.md) for backup procedures.

### Updates

```bash
cd /opt/sequoia
git pull
docker compose pull
docker compose up -d
```

### Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f ai-engine

# Last 100 lines
docker compose logs --tail=100 platform-backend
```

### Restart Services

```bash
# Single service
docker compose restart ai-engine

# All services
docker compose restart

# Full recreation
docker compose down && docker compose up -d
```
