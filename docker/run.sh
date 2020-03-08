#!/bin/bash

set -e
set -u

cd /opt/meshping

if [ -n "${REDIS_HOST:-}" ]; then
    exec /usr/bin/python3 -- /opt/meshping/src/meshping.py -r "$REDIS_HOST" "$@"
else
    exec /usr/bin/python3 -- /opt/meshping/src/meshping.py "$@"
fi
