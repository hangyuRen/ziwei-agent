#!/bin/sh
set -eu
cd /home/ziwei-agent

# Serialize manual and timer invocations. Nginx stays up during HTTP-01 checks.
exec 9>/run/lock/ziwei-certbot.lock
flock -n 9 || exit 0
docker compose --profile tools run --rm --no-deps certbot renew --non-interactive "$@"
# Reload only after successful renewal/check; keep existing workers if config fails.
docker compose exec -T nginx nginx -t
docker compose exec -T nginx nginx -s reload
