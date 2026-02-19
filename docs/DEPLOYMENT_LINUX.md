# Linux Production Deployment (VPS)

This deploys the full SequoIA stack using Docker Compose on a Linux server. Everything runs in containers — no need to install Python or Node.js on the server itself.

---

## Prerequisites

You need:
- A Linux server (Ubuntu 22.04+ recommended) with:
  - At least **16 GB RAM** (Kafka, ClickHouse, and AI engine are memory-hungry)
  - At least **4 CPU cores**
  - At least **100 GB disk** (SSD preferred for ClickHouse)
  - NVIDIA GPU if running the AI engine (optional — the platform works without it)
- Root or sudo access
- A domain name pointing to your server's IP (optional but recommended for HTTPS)

---

## Step 1: Install Docker

SSH into your server:

```bash
ssh your-user@your-server-ip
```

Install Docker Engine (not Docker Desktop — there's no GUI on a server):

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install prerequisites
sudo apt install -y ca-certificates curl gnupg

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Let your user run Docker without sudo
sudo usermod -aG docker $USER

# IMPORTANT: Log out and back in for the group change to take effect
exit
```

SSH back in and verify:

```bash
docker --version          # Should print Docker version
docker compose version    # Should print Docker Compose version
```

### (Optional) Install NVIDIA Container Toolkit — for GPU / AI Engine

Only needed if your server has an NVIDIA GPU and you want vehicle detection:

```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Verify the GPU is visible to Docker:
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

If you do NOT have a GPU, just skip this. The platform will work fine — you just won't have the AI-powered vehicle detection. The processor service and platform still run normally.

---

## Step 2: Create Persistent Data Directories

In production, we store data in known paths instead of anonymous Docker volumes. This makes backups easy:

```bash
sudo mkdir -p /mnt/kafka-data /mnt/clickhouse-data /mnt/postgres-data /mnt/redis-data

# Set ownership to match the UID each container runs as
sudo chown -R 1001:1001 /mnt/kafka-data      # Kafka runs as uid 1001
sudo chown -R 101:101 /mnt/clickhouse-data    # ClickHouse runs as uid 101
sudo chown -R 999:999 /mnt/postgres-data      # PostgreSQL runs as uid 999
sudo chown -R 999:999 /mnt/redis-data         # Redis runs as uid 999
```

---

## Step 3: Get the Code

```bash
cd /opt
sudo git clone <your-repo-url> sequoia
sudo chown -R $USER:$USER /opt/sequoia
cd /opt/sequoia/Pipeline
```

---

## Step 4: Generate Secrets

Production needs real, random secrets. Generate them now.

### 4a. Django secret key

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the output (a ~64-character random string). You'll paste it into `.env` in Step 5.

### 4b. JWT RS256 key pair

SequoIA uses asymmetric RS256 tokens. Generate a fresh key pair:

```bash
# Generate private + public key
openssl genrsa 2048 > jwt_private.pem
openssl rsa -in jwt_private.pem -pubout > jwt_public.pem

# Convert to single-line format for the .env file
echo "JWT_SIGNING_KEY=$(cat jwt_private.pem | tr '\n' '\\' | sed 's/\\/\\n/g')"
echo "JWT_VERIFYING_KEY=$(cat jwt_public.pem | tr '\n' '\\' | sed 's/\\/\\n/g')"
```

Copy both output lines. You'll paste them into `.env` in Step 5.

### 4c. Database passwords

```bash
echo "POSTGRES_PASSWORD=$(openssl rand -base64 24)"
echo "CLICKHOUSE_PASSWORD=$(openssl rand -base64 24)"
echo "REDIS_PASSWORD=$(openssl rand -base64 24)"
```

Copy all three. Same deal — paste into `.env`.

---

## Step 5: Create the Environment File

```bash
cd /opt/sequoia/Pipeline
cp .env.example .env
nano .env       # or vim, whatever you prefer
```

Fill in every value. Here's a commented template explaining each section:

```env
# ---- Deployment ----
VERSION=v1.0.0
ENVIRONMENT=production

# ---- Persistent data paths (from Step 2) ----
KAFKA_DATA_PATH=/mnt/kafka-data
CLICKHOUSE_DATA_PATH=/mnt/clickhouse-data
POSTGRES_DATA_PATH=/mnt/postgres-data

# ---- Kafka ----
KAFKA_BOOTSTRAP_SERVERS=kafka:29092
SCHEMA_REGISTRY_URL=http://schema-registry:8081
# Set this to YOUR SERVER'S IP — the one DAS interrogators connect to.
# If only using simulation (no real DAS hardware), just use "localhost".
KAFKA_EXTERNAL_HOST=192.168.1.100

# ---- Telemetry ----
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-lgtm:4317
PYTHONUNBUFFERED=1

# ---- DAS Settings (defaults are fine for the Carros fiber) ----
DAS_FIBER_NAMES=carros
DAS_CHANNEL_COUNT=2829
DAS_SAMPLING_RATE_HZ=50
DAS_GENERATION_RATE_HZ=50
DAS_MEMORY_POOL_SIZE=10
DAS_CHANNEL_SLICE_STEP=2
DAS_FILTER_WARMUP_TIME_SECONDS=5.0
DAS_MAX_PROCESSING_RATE_HZ=50
DAS_PROCESSING_MEMORY_POOL_SIZE=5
DAS_STATE_CLEANUP_INTERVAL=300

# ---- AI Engine ----
AI_MAX_CONCURRENT=10
ENABLE_COUNTING=true
AI_CORRELATION_THRESHOLD=130

# ---- Databases (paste passwords from Step 4c) ----
CLICKHOUSE_HOST=clickhouse
CLICKHOUSE_PORT=9000
CLICKHOUSE_DATABASE=sequoia
CLICKHOUSE_USER=sequoia
CLICKHOUSE_PASSWORD=<paste here>

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=<paste here>

POSTGRES_DB=sequoia
POSTGRES_USER=sequoia
POSTGRES_PASSWORD=<paste here>

# ---- Django (paste secret from Step 4a) ----
DJANGO_SECRET_KEY=<paste your 64-char secret here>

# Replace with your actual domain or server IP
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
CORS_ALLOWED_ORIGINS=https://yourdomain.com
FRONTEND_URL=https://yourdomain.com

# Set to false if running WITHOUT HTTPS (e.g. internal network, VPN)
SECURE_SSL_REDIRECT=false

# ---- JWT Keys (paste from Step 4b) ----
JWT_SIGNING_KEY=-----BEGIN PRIVATE KEY-----\nMIIEvgIBA...\n-----END PRIVATE KEY-----
JWT_VERIFYING_KEY=-----BEGIN PUBLIC KEY-----\nMIIBIjANB...\n-----END PUBLIC KEY-----

# ---- Frontend ----
VITE_API_BASE_URL=http://yourdomain.com:8001
VITE_MAPBOX_TOKEN=pk.YOUR_MAPBOX_TOKEN

# ---- Proxy (only if behind a corporate proxy) ----
# HTTP_PROXY=http://proxy.example.com:8080
# HTTPS_PROXY=http://proxy.example.com:8080
# NO_PROXY=localhost,127.0.0.1,kafka,redis,clickhouse,schema-registry,otel-lgtm
```

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X` in nano).

**IMPORTANT** — protect this file, it contains all your secrets:

```bash
chmod 600 .env
```

---

## Step 6: Build and Start Everything

```bash
cd /opt/sequoia/Pipeline

# Build all Docker images (5-10 minutes the first time)
docker compose build

# Start all services in detached mode
docker compose up -d
```

**What this starts (12 containers):**

| Container | What it does | Port |
|-----------|-------------|------|
| `kafka` | Message broker for DAS data | 9092 (DAS machines connect here) |
| `kafka-setup` | Creates Kafka topics, then exits | — |
| `schema-registry` | Avro schema storage | (internal only) |
| `kafka-ui` | Kafka admin panel | 127.0.0.1:8080 (localhost only) |
| `processor` | DAS signal processing (bandpass, decimation, CMR) | (internal only) |
| `ai-engine` | DTAN vehicle detection + speed inference (GPU) | (internal only) |
| `postgres` | User/org/fiber PostgreSQL database | (internal only) |
| `redis` | WebSocket layer + cache | (internal only) |
| `clickhouse` | Analytics time-series database | 127.0.0.1:8123 (localhost only) |
| `otel-lgtm` | Grafana + Prometheus + Tempo + Loki | 127.0.0.1:3002 (localhost only) |
| `platform-backend` | Django API + WebSocket server | **8001** |
| `platform-frontend` | React app served by nginx | **3000** |

Wait 1-2 minutes for all health checks to pass, then verify:

```bash
docker compose ps
```

Every service should show `healthy` or `running`. The only exception is `kafka-setup` which will show `exited (0)` — that's correct, it's a one-shot job.

---

## Step 7: Create the First Admin User

Production does NOT auto-create users (unlike dev mode). Create one manually:

```bash
docker compose exec platform-backend python manage.py createsuperuser
```

It will ask for:
- **Username** (e.g. `admin`)
- **Email** (e.g. `admin@yourdomain.com`)
- **Password** (pick something strong)

This creates a Django superuser with access to everything. You can then:
1. Log in to the **Django admin** at `http://your-server:8001/admin/`
2. Create an **Organization** (e.g. "My Company")
3. Create **Fiber Assignments** to map fibers to the organization
4. Create **regular users** assigned to the organization

---

## Step 8: Access the Platform

| What | URL |
|------|-----|
| **Main app** | `http://your-server:3000` |
| **REST API health check** | `http://your-server:8001/api/health` |
| **Django Admin** | `http://your-server:8001/admin/` |
| **Grafana** (SSH tunnel or localhost) | `http://localhost:3002` |
| **Kafka UI** (SSH tunnel or localhost) | `http://localhost:8080` |

> Grafana and Kafka UI are bound to `127.0.0.1` only for security. To access them remotely, use an SSH tunnel: `ssh -L 3002:localhost:3002 user@server`

---

## Step 9: Set Up Data Flow

### Option A: Simulation Mode (no real DAS hardware)

Add this to your `.env` file:

```env
REALTIME_SOURCE=simulation
```

Then restart the backend:

```bash
docker compose restart platform-backend
```

The simulation engine will generate realistic fake vehicle detections on all configured fibers.

### Option B: Real DAS Data (Kafka)

Your DAS interrogators push raw data to Kafka at `your-server-ip:9092` on topics:
- `das.raw.carros`
- `das.raw.mathis`
- `das.raw.promenade`

The data flows automatically:
1. **Processor** consumes raw data, applies bandpass filter + decimation + common-mode removal, publishes to `das.processed`
2. **AI Engine** consumes processed data, runs DTAN neural network for vehicle detection, publishes speeds to `das.speeds` and counts to `das.counts`
3. **ClickHouse** ingests speeds/counts via Kafka table engine
4. **Backend** queries ClickHouse and broadcasts to browsers via WebSocket

---

## Step 10: (Optional) Set Up HTTPS with Nginx Reverse Proxy

For production, you should have HTTPS. Install Nginx on the host (not in Docker):

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

Create the Nginx config:

```bash
sudo nano /etc/nginx/sites-available/sequoia
```

Paste:

```nginx
server {
    server_name yourdomain.com;

    # Frontend (React SPA)
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Django Admin
    location /admin/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket (real-time data)
    location /ws/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;  # Keep WebSocket alive for 24h
    }
}
```

Enable the site and get a free SSL certificate:

```bash
sudo ln -s /etc/nginx/sites-available/sequoia /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t                          # Verify config is valid
sudo systemctl restart nginx

# Get SSL from Let's Encrypt (auto-configures nginx)
sudo certbot --nginx -d yourdomain.com
```

Update your `.env` to use HTTPS:

```env
VITE_API_BASE_URL=https://yourdomain.com
FRONTEND_URL=https://yourdomain.com
CORS_ALLOWED_ORIGINS=https://yourdomain.com
DJANGO_ALLOWED_HOSTS=yourdomain.com
SECURE_SSL_REDIRECT=true
```

Rebuild the frontend (it bakes the API URL at build time):

```bash
docker compose build platform-frontend
docker compose up -d platform-frontend
```

---

## Maintenance

### View Logs

```bash
# All services (follow mode)
docker compose logs -f

# Specific service
docker compose logs -f platform-backend
docker compose logs -f ai-engine
docker compose logs -f processor
```

### Update the Code

```bash
cd /opt/sequoia/Pipeline
git pull

# Rebuild and restart
docker compose build
docker compose up -d

# Run database migrations if there are schema changes
docker compose exec platform-backend python manage.py migrate --noinput
```

### Backup Databases

```bash
# PostgreSQL (users, orgs, fibers, reports)
docker compose exec postgres pg_dump -U sequoia sequoia > backup_pg_$(date +%Y%m%d).sql

# ClickHouse (time-series data — can be large)
sudo tar czf backup_ch_$(date +%Y%m%d).tar.gz /mnt/clickhouse-data
```

### Restart a Single Service

```bash
docker compose restart platform-backend
docker compose restart processor
```

### Check Resource Usage

```bash
docker stats
```

### Scale Down (save resources)

If you don't need certain services:

```bash
# Stop AI engine (saves ~8GB RAM, lose vehicle detection)
docker compose stop ai-engine

# Stop observability stack (saves ~3GB RAM, lose Grafana)
docker compose stop otel-lgtm

# Stop Kafka UI (saves a bit of memory)
docker compose stop kafka-ui
```

---

## Troubleshooting

**Container keeps restarting**
Check its logs: `docker compose logs platform-backend --tail 50`

**"ImproperlyConfigured: SECRET_KEY is too short"**
Your `DJANGO_SECRET_KEY` in `.env` must be at least 50 characters. See Step 4a.

**"ImproperlyConfigured: ALLOWED_HOSTS is empty"**
Set `DJANGO_ALLOWED_HOSTS=yourdomain.com` in `.env`.

**"JWT_SIGNING_KEY is not set"**
You need to set the JWT keys in `.env`. See Step 4b.

**No data on the map**
- Check backend health: `curl http://localhost:8001/api/health`
- If using simulation: set `REALTIME_SOURCE=simulation` in `.env` and restart
- If using real DAS: check Kafka UI at `http://localhost:8080` to see if data is arriving

**AI Engine crashes (GPU)**
- Verify GPU access: `docker compose exec ai-engine nvidia-smi`
- If no GPU available: just stop the ai-engine service (`docker compose stop ai-engine`). Everything else works.

**Out of memory**
- Check usage: `docker stats`
- Kafka and ClickHouse each want 2-8 GB. Minimum server RAM is 16 GB.
- Reduce resource limits in `docker-compose.yml` under `deploy.resources.limits`

**ClickHouse "too many parts" error**
Data accumulating without merges. Fix: `docker compose exec clickhouse clickhouse-client -q "OPTIMIZE TABLE sequoia.speed_hires FINAL"`

**Port conflicts**
- 9092 (Kafka): `sudo lsof -i :9092`
- 8001 (Backend): `sudo lsof -i :8001`
- 3000 (Frontend): `sudo lsof -i :3000`
Kill conflicting processes or change ports in `docker-compose.yml`.
