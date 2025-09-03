#!/bin/bash

# Configuration
ROUND=1
MAX_ROUNDS=3
PROJECT="orchestration"
CONTEXT_FILE="review/round-1/context.md"
ROUND_DIR="review/round-1"
SESSION="review-orchestration"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Send text to a specific pane using tmux
send_to_pane() {
    local pane_index=$1
    shift
    local text="$*"
    
    # Map logical index to tmux pane
    case $pane_index in
        1) pane="0.0" ;;  # Claude
        2) pane="0.1" ;;  # Codex
        3) pane="0.2" ;;  # Gemini
    esac
    
    # Send text to pane
    tmux send-keys -t "$SESSION:$pane" "$text" C-m
}

# Send to all LLMs
send_all() {
    local text="$*"
    send_to_pane 1 "$text"
    send_to_pane 2 "$text"
    send_to_pane 3 "$text"
}

# Show help
show_help() {
    echo -e "${CYAN}═══ Commands ═══${NC}"
    echo -e "${GREEN}all <text>${NC}     - Send text to all LLMs"
    echo -e "${GREEN}claude <text>${NC}  - Send to Claude only"
    echo -e "${GREEN}codex <text>${NC}   - Send to Codex only"
    echo -e "${GREEN}context${NC}        - Send context file to all"
    echo -e "${GREEN}prompts${NC}        - Send prompts to each LLM"
    echo -e "${GREEN}help${NC}           - Show this help"
    echo -e "${GREEN}exit${NC}           - Exit controller"
}

# Main REPL
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}           Review Controller - Round $ROUND${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Type 'help' for commands"
echo ""

while true; do
    echo -n -e "${GREEN}review> ${NC}"
    read -r cmd args
    
    case "$cmd" in
        all)
            send_all "$args"
            ;;
        claude)
            send_to_pane 1 "$args"
            ;;
        codex)
            send_to_pane 2 "$args"
            ;;
        context)
            echo "Sending context to all LLMs..."
            content=$(cat "$CONTEXT_FILE" 2>/dev/null)
            send_all "$content"
            ;;
        prompts)
            echo "Sending prompts..."
            send_to_pane 1 "$(cat $ROUND_DIR/claude-prompt.md)"
            send_to_pane 2 "$(cat $ROUND_DIR/codex-prompt.md)"
            ;;
        help)
            show_help
            ;;
        exit|quit)
            exit 0
            ;;
        *)
            echo "Unknown command: $cmd"
            ;;
    esac
done
