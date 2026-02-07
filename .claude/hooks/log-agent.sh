#!/bin/bash
# Log agent usage to .claude/agent-usage.log
set -euo pipefail

INPUT=$(cat)
EVENT=$(echo "$INPUT" | jq -r '.hook_event_name // "unknown"')
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
LOG_FILE="${CLAUDE_PROJECT_DIR:-.}/.claude/agent-usage.log"

case "$EVENT" in
  PreToolUse)
    TOOL=$(echo "$INPUT" | jq -r '.tool_name // ""')
    if [ "$TOOL" = "Task" ]; then
      TYPE=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // "unknown"')
      DESC=$(echo "$INPUT" | jq -r '.tool_input.description // ""')
      echo "[$TIMESTAMP] SPAWN $TYPE — $DESC" >> "$LOG_FILE"
    fi
    ;;
  SubagentStop)
    TYPE=$(echo "$INPUT" | jq -r '.agent_type // "unknown"')
    ID=$(echo "$INPUT" | jq -r '.agent_id // "?"')
    echo "[$TIMESTAMP] DONE  $TYPE ($ID)" >> "$LOG_FILE"
    ;;
esac

exit 0
