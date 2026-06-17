#!/bin/bash
# OC-specific wrapper for herd_mail.py
# Sources OC environment before executing herd_mail commands

set -e

# Hardcoded for OC agent
AGENT_ID="oc"

# Source agent-specific .env
AGENT_ENV="$HOME/.openclaw-primary/agents/$AGENT_ID/agent/.env"
if [[ -f "$AGENT_ENV" ]]; then
  set -a
  source "$AGENT_ENV"
  set +a
else
  echo "ERROR: Agent .env not found: $AGENT_ENV" >&2
  exit 1
fi

# Global connection settings should come from gateway process env
# If not, try loading from openclaw.json env section (fallback)

# Execute herd_mail.py with all arguments passed through
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/herd_mail.py" "$@"
