#!/bin/sh
# COEBOT container entrypoint.
#
# Runs as the non-root `coebot` user (see Dockerfile). Its only job is
# to fix ownership on the bind-mounted /app/data and /app/models
# directories when the host owns them as a different UID/GID (very
# common on Linux hosts). On Docker Desktop for Windows/macOS the
# bind mount already appears with the container user's permissions,
# so this step is a no-op there.
#
# Any failure to chown is non-fatal — the app will fall back to
# whatever permissions the mount arrived with and log an error later
# if it truly can't write.
set -e

# Only try to fix perms if the process is somehow root (e.g. someone
# ran `docker run --user 0`); the default USER coebot cannot chown
# files it does not own and shouldn't try.
if [ "$(id -u)" = "0" ]; then
    chown -R coebot:coebot /app/data /app/models 2>/dev/null || true
    exec runuser -u coebot -- "$@"
fi

exec "$@"
