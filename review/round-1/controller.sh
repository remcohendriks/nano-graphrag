#!/bin/bash

# Configuration
ROUND=1
MAX_ROUNDS=3
PROJECT="nano-graphrag"
CONTEXT_FILE="review/round-1/context.md"
ROUND_DIR="review/round-1"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

# Send text to a specific screen session
send_to_screen() {
    local session=$1
    shift
    local text="$*"
    
    # Send text to screen session
    # -X stuff sends keystrokes, $'\n' adds newline for execution
    screen -S "$session" -X stuff "$text"$'\n'
}

# Send to specific LLM
send_to_llm() {
    local llm_index=$1
    shift
    local text="$*"
    
    case $llm_index in
        1) send_to_screen "claude-review" "$text" ;;
        2) send_to_screen "codex-review" "$text" ;;
        3) send_to_screen "gemini-review" "$text" ;;
    esac
}

# Send to all LLMs
send_all() {
    local text="$*"
    send_to_llm 1 "$text"
    send_to_llm 2 "$text"
    send_to_llm 3 "$text"
}

# Show help
show_help() {
    echo -e "${CYAN}═══ Commands ═══${NC}"
    echo -e "${GREEN}all <text>${NC}     - Send text to all LLMs"
    echo -e "${GREEN}claude <text>${NC}  - Send to Claude only"
    echo -e "${GREEN}codex <text>${NC}   - Send to Codex only"
    echo -e "${GREEN}gemini <text>${NC}  - Send to Gemini only"
    echo -e "${GREEN}context${NC}        - Send context file to all"
    echo -e "${GREEN}prompts${NC}        - Send prompts to each LLM"
    echo -e "${GREEN}status${NC}         - Show session status"
    echo -e "${GREEN}help${NC}           - Show this help"
    echo -e "${GREEN}exit${NC}           - Exit controller"
}

# Check screen sessions
check_sessions() {
    echo -e "${CYAN}Screen Sessions:${NC}"
    screen -ls | grep -E "(claude|codex|gemini)-review" || echo "  No review sessions found"
}

# Main REPL
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}           Review Controller - Round $ROUND${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "📁 Project: $PROJECT"
echo -e "📝 Context: $CONTEXT_FILE"
echo ""
echo "Waiting for screen sessions to start..."
sleep 2
check_sessions
echo ""
echo "Type 'help' for commands"
echo ""

while true; do
    echo -n -e "${GREEN}review> ${NC}"
    read -r cmd args
    
    case "$cmd" in
        all)
            if [ -z "$args" ]; then
                echo "Usage: all <text>"
            else
                echo -e "${YELLOW}Sending to all LLMs...${NC}"
                send_all "$args"
            fi
            ;;
        claude)
            if [ -z "$args" ]; then
                echo "Usage: claude <text>"
            else
                echo -e "${YELLOW}Sending to Claude...${NC}"
                send_to_llm 1 "$args"
            fi
            ;;
        codex)
            if [ -z "$args" ]; then
                echo "Usage: codex <text>"
            else
                echo -e "${YELLOW}Sending to Codex...${NC}"
                send_to_llm 2 "$args"
            fi
            ;;
        gemini)
            if [ -z "$args" ]; then
                echo "Usage: gemini <text>"
            else
                echo -e "${YELLOW}Sending to Gemini...${NC}"
                send_to_llm 3 "$args"
            fi
            ;;
        context)
            echo -e "${YELLOW}Sending context to all LLMs...${NC}"
            if [ -f "$CONTEXT_FILE" ]; then
                content=$(cat "$CONTEXT_FILE")
                send_all "$content"
                echo -e "${GREEN}✓ Context sent${NC}"
            else
                echo -e "${RED}Error: Context file not found${NC}"
            fi
            ;;
        prompts)
            echo -e "${YELLOW}Sending prompts to LLMs...${NC}"
            if [ -f "$ROUND_DIR/claude-prompt.md" ]; then
                send_to_llm 1 "$(cat $ROUND_DIR/claude-prompt.md)"
                echo "  → Claude prompt sent"
            fi
            if [ -f "$ROUND_DIR/codex-prompt.md" ]; then
                send_to_llm 2 "$(cat $ROUND_DIR/codex-prompt.md)"
                echo "  → Codex prompt sent"
            fi
            if [ -f "$ROUND_DIR/gemini-prompt.md" ]; then
                send_to_llm 3 "$(cat $ROUND_DIR/gemini-prompt.md)"
                echo "  → Gemini prompt sent"
            fi
            echo -e "${GREEN}✓ Prompts sent${NC}"
            ;;
        status)
            check_sessions
            ;;
        help)
            show_help
            ;;
        exit|quit)
            echo -e "${CYAN}Goodbye!${NC}"
            exit 0
            ;;
        *)
            if [ -z "$cmd" ]; then
                continue
            else
                echo -e "${RED}Unknown command: $cmd${NC}"
            fi
            ;;
    esac
done
