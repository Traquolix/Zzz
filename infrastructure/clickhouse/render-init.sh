#!/usr/bin/env bash
# Render ClickHouse init SQL templates with environment variables.
# CH_DATABASE, CH_KAFKA_TOPIC, CH_KAFKA_GROUP are expanded via envsubst.
# Defaults (sequoia / das.detections / clickhouse_detection_consumer) are set
# below when the env vars are unset.  SQL files use bare ${CH_DATABASE} etc.
set -euo pipefail

: "${CH_DATABASE:=sequoia}"
: "${CH_KAFKA_TOPIC:=prod.detections}"
: "${CH_KAFKA_GROUP:=clickhouse_detection_consumer}"
export CH_DATABASE CH_KAFKA_TOPIC CH_KAFKA_GROUP

SRC_DIR="${1:?Usage: render-init.sh <src-dir> <dest-dir>}"
DEST_DIR="${2:?Usage: render-init.sh <src-dir> <dest-dir>}"

mkdir -p "$DEST_DIR"
for f in "$SRC_DIR"/*.sql; do
    [ -f "$f" ] || continue
    envsubst '${CH_DATABASE} ${CH_KAFKA_TOPIC} ${CH_KAFKA_GROUP}' < "$f" > "$DEST_DIR/$(basename "$f")"
done

echo "Rendered $(ls "$DEST_DIR"/*.sql 2>/dev/null | wc -l) SQL files to $DEST_DIR"
