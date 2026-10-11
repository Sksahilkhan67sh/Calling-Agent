#!/bin/sh
# Migrations are a deploy step (Deployment-Guide §5) and never run here.
set -eu
exec "$@"
