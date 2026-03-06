# Rollback Procedure

## Automated Rollback (CI/CD)

The GitHub Actions deploy workflow (`.github/workflows/deploy.yml`) includes automatic
rollback. After deploying, it health-checks `platform-backend`, `processor-carros`,
and `ai-engine-carros`. If any are unhealthy, it rolls back to the previous commit
and rebuilds. No manual intervention needed.

## Manual Rollback — Backend

When something breaks after a deploy and you need to roll back manually.

### Quick rollback (< 2 minutes)

```bash
ssh beaujoin@192.168.99.113
cd /opt/Sequoia

# See recent deploy history
git log --oneline -10

# Roll back to the previous commit
git reset --hard HEAD~1
docker compose up -d --build --force-recreate

# Verify
docker compose ps
curl -f http://localhost:8001/api/health
```

### Roll back to a specific commit

```bash
git reset --hard <commit-sha>
docker compose up -d --build --force-recreate
```

### Roll back a single service

If only one service is broken, rebuild just that one:

```bash
# Example: only the backend is broken
docker compose up -d --build --force-recreate platform-backend

# Example: only the AI engine is broken
docker compose up -d --build --force-recreate ai-engine-carros
```

## Manual Rollback — Frontend

The frontend is static files served by nginx. Rolling back means replacing the files.

```bash
ssh frontend@134.59.98.100

# The previous build is still in git, rebuild from the last known good commit:
cd /tmp
git clone --depth 1 --branch <tag-or-sha> https://github.com/Traquolix/Sequoia.git sequoia-rollback
cd sequoia-rollback/services/platform/frontend
npm ci && npm run build
sudo cp -r dist/* /var/www/sequoia/
rm -rf /tmp/sequoia-rollback
```

Or from your local machine, if you have the last good build locally:

```bash
cd services/platform/frontend
git checkout <good-commit> -- .
npm ci && npm run build
scp -r dist/* frontend@134.59.98.100:/var/www/sequoia/
git checkout HEAD -- .
```

## Database Rollback

### Restore from backup

If a migration or data change broke something:

```bash
ssh beaujoin@192.168.99.113
cd /opt/Sequoia

# List available backups
./scripts/restore.sh --list

# Restore the latest backup
./scripts/restore.sh --latest

# Or a specific one
./scripts/restore.sh backups/2026-03-06_0300
```

### Reverse a Django migration

If the issue is a specific migration:

```bash
# Check what's applied
docker compose exec platform-backend python manage.py showmigrations <app>

# Reverse to a specific migration
docker compose exec platform-backend python manage.py migrate <app> <migration_number>

# Example: reverse monitoring to migration 0005
docker compose exec platform-backend python manage.py migrate monitoring 0005
```

## Nuclear Option — Full Rebuild

If everything is broken and you need a clean slate (data preserved):

```bash
ssh beaujoin@192.168.99.113
cd /opt/Sequoia

# Take a backup first
./scripts/backup.sh

# Tear down everything
docker compose down

# Clean Docker build cache
docker system prune -f

# Rebuild from scratch
git fetch origin main && git reset --hard origin/main
docker compose build --no-cache --parallel
docker compose up -d

# Restore data if needed
./scripts/restore.sh --latest
```

## Checklist After Rollback

1. Verify all services are healthy: `docker compose ps`
2. Check backend health: `curl -f http://localhost:8001/api/health`
3. Check frontend loads: `curl -f http://<frontend-ip>/`
4. Check Grafana dashboards for anomalies: `http://localhost:3002`
5. Verify WebSocket is streaming: open the frontend, check live map updates
6. Check logs for errors: `docker compose logs --tail=50 <service>`
