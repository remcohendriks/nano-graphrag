#!/bin/bash

# Create the controller CLI
cat > /tmp/review-controller.sh << 'CONTROLLER'
#!/bin/bash

# Configuration
1=CURRENT_1
MAX_1S=MAX_1S_VAR
PROJECT="orchestration_VAR"
review/round-1/context.md="review/round-1/context.md_VAR"
review/round-1="review/round-1_VAR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
RED='\033[0;31m'
NC='\033[0m'
BOLD='\033[1m'

# Send text to a specific window (1=Claude, 2=Codex, 3=Gemini)
# Windows are created in order: Claude, Codex, Gemini, Command
# So we use reverse order since newest windows are first
send_to_pane() {
    local pane_index=$1
    shift
    local text="$*"
    
    # Map to window index
    case $pane_index in
        1) window_index=4 ;;  # Claude (first created, now 4th from top)
        2) window_index=3 ;;  # Codex (second created, now 3rd from top)
        3) window_index=2 ;;  # Gemini (third created, now 2nd from top)
    esac
    
    # Send to window - use System Events to send proper keystrokes
    osascript << END 2>/dev/null
tell application "iTerm"
    if (count of windows) >= $window_index then
        -- Select the window to make it frontmost
        select window $window_index
        
        -- Send text and return key via System Events
        tell application "System Events"
            keystroke "$text"
            keystroke return
        end tell
    end if
end tell
END
}

# Send to all LLMs
send_all() {
    local text="$*"
    send_to_pane 1 "$text"
    send_to_pane 2 "$text"
    send_to_pane 3 "$text"
}

# Show status
show_status() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}                Review Controller - Round $1${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "📁 Project: ${BOLD}$PROJECT${NC}"
    echo -e "🔄 Round: ${BOLD}$1 / $MAX_1S${NC}"
    echo -e "🎯 Focus: ${BOLD}$(get_severity)${NC}"
    echo ""
}

# Get severity for current round
get_severity() {
    case $1 in
        1) echo "All Issues" ;;
        2) echo "Critical and High" ;;
        3) echo "Critical Only" ;;
        *) echo "Ship-Blocking Only" ;;
    esac
}

# Show help
show_help() {
    echo -e "${CYAN}═══ Review Commands ═══${NC}"
    echo -e "${GREEN}start${NC}          - Send context and prompts to all LLMs"
    echo -e "${GREEN}context${NC}        - Send context file to all LLMs"
    echo -e "${GREEN}prompts${NC}        - Send individual prompts to each LLM"
    echo -e "${GREEN}status${NC}         - Show current review status"
    echo ""
    echo -e "${CYAN}═══ Direct Commands ═══${NC}"
    echo -e "${GREEN}all <text>${NC}     - Send text to all LLMs"
    echo -e "${GREEN}claude <text>${NC}  - Send to Claude only"
    echo -e "${GREEN}codex <text>${NC}   - Send to Codex only"
    echo -e "${GREEN}gemini <text>${NC}  - Send to Gemini only"
    echo ""
    echo -e "${CYAN}═══ Utility Commands ═══${NC}"
    echo -e "${GREEN}clear${NC}          - Clear all LLM screens"
    echo -e "${GREEN}help${NC}           - Show this help"
    echo -e "${GREEN}exit${NC}           - Exit controller"
}

# Start review - send context and prompts
start_review() {
    echo -e "${GREEN}Starting Round $1 review...${NC}"
    echo ""
    
    # Check if files exist
    if [ ! -f "$review/round-1/context.md" ]; then
        echo -e "${RED}Error: Context file not found: $review/round-1/context.md${NC}"
        return 1
    fi
    
    echo -e "${YELLOW}Step 1/3: Sending context to all LLMs...${NC}"
    local context=$(cat "$review/round-1/context.md" 2>/dev/null)
    send_all "$context"
    sleep 2
    
    echo -e "${YELLOW}Step 2/3: Sending individual prompts...${NC}"
    
    # Send Claude prompt
    if [ -f "$review/round-1/claude-prompt.md" ]; then
        echo "  → Sending architecture prompt to Claude"
        send_to_pane 1 "$(cat $review/round-1/claude-prompt.md)"
    fi
    
    # Send Codex prompt
    if [ -f "$review/round-1/codex-prompt.md" ]; then
        echo "  → Sending debug prompt to Codex"
        send_to_pane 2 "$(cat $review/round-1/codex-prompt.md)"
    fi
    
    # Send Gemini prompt
    if [ -f "$review/round-1/gemini-prompt.md" ]; then
        echo "  → Sending requirements prompt to Gemini"
        send_to_pane 3 "$(cat $review/round-1/gemini-prompt.md)"
    fi
    
    echo ""
    echo -e "${GREEN}✓ Review started!${NC}"
    echo "The LLMs are now processing your code review request."
    echo ""
}

# Send context only
send_context() {
    if [ ! -f "$review/round-1/context.md" ]; then
        echo -e "${RED}Error: Context file not found: $review/round-1/context.md${NC}"
        return 1
    fi
    
    echo -e "${YELLOW}Sending context to all LLMs...${NC}"
    local context=$(cat "$review/round-1/context.md" 2>/dev/null)
    send_all "$context"
    echo -e "${GREEN}✓ Context sent${NC}"
}

# Send prompts only
send_prompts() {
    echo -e "${YELLOW}Sending prompts to respective LLMs...${NC}"
    
    if [ -f "$review/round-1/claude-prompt.md" ]; then
        echo "  → Claude (Architecture)"
        send_to_pane 1 "$(cat $review/round-1/claude-prompt.md)"
    fi
    
    if [ -f "$review/round-1/codex-prompt.md" ]; then
        echo "  → Codex (Debug)"
        send_to_pane 2 "$(cat $review/round-1/codex-prompt.md)"
    fi
    
    if [ -f "$review/round-1/gemini-prompt.md" ]; then
        echo "  → Gemini (Requirements)"
        send_to_pane 3 "$(cat $review/round-1/gemini-prompt.md)"
    fi
    
    echo -e "${GREEN}✓ Prompts sent${NC}"
}

# Main REPL
clear
show_status
echo -e "${CYAN}Type 'help' for commands or 'start' to begin review${NC}"
echo ""

while true; do
    echo -n -e "${GREEN}review> ${NC}"
    read -r cmd args
    
    case "$cmd" in
        start)
            start_review
            ;;
        context)
            send_context
            ;;
        prompts)
            send_prompts
            ;;
        status)
            show_status
            ;;
        all)
            if [ -z "$args" ]; then
                echo "Usage: all <text>"
            else
                echo -e "${YELLOW}Sending to all LLMs: $args${NC}"
                send_all "$args"
            fi
            ;;
        claude)
            if [ -z "$args" ]; then
                echo "Usage: claude <text>"
            else
                echo -e "${YELLOW}Sending to Claude: $args${NC}"
                send_to_pane 1 "$args"
            fi
            ;;
        codex)
            if [ -z "$args" ]; then
                echo "Usage: codex <text>"
            else
                echo -e "${YELLOW}Sending to Codex: $args${NC}"
                send_to_pane 2 "$args"
            fi
            ;;
        gemini)
            if [ -z "$args" ]; then
                echo "Usage: gemini <text>"
            else
                echo -e "${YELLOW}Sending to Gemini: $args${NC}"
                send_to_pane 3 "$args"
            fi
            ;;
        clear)
            send_all "clear"
            clear
            show_status
            ;;
        help|h|?)
            show_help
            ;;
        exit|quit|q)
            echo -e "${CYAN}Goodbye!${NC}"
            exit 0
            ;;
        "")
            # Empty command, just show prompt again
            ;;
        *)
            echo -e "${RED}Unknown command: $cmd${NC} (type 'help' for commands)"
            ;;
    esac
done
CONTROLLER

# Substitute variables
chmod +x /tmp/review-controller.sh
sed -i '' "s|CURRENT_1|1|g" /tmp/review-controller.sh
sed -i '' "s|MAX_1S_VAR|MAX_1S|g" /tmp/review-controller.sh
sed -i '' "s|orchestration_VAR|orchestration|g" /tmp/review-controller.sh
sed -i '' "s|review/round-1/context.md_VAR|review/round-1/context.md|g" /tmp/review-controller.sh
sed -i '' "s|review/round-1_VAR|review/round-1|g" /tmp/review-controller.sh

# Start the controller
exec /tmp/review-controller.sh
