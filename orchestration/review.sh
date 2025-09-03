#!/bin/bash

# iTerm2 Native Orchestrator for Multi-LLM Code Review
# Clean, simple, macOS-native using iTerm2 splits

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load configuration
CONFIG_FILE="$HOME/.review/config.sh"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
else
    source "$SCRIPT_DIR/defaults/config.sh"
fi

# Configuration
PROJECT_NAME="$(basename "$(pwd)")"
REVIEW_DIR="review"
CURRENT_ROUND_FILE="$REVIEW_DIR/current-round.txt"

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_success() {
    echo -e "${GREEN}${CHECK_MARK}${NC} $1"
}


# Setup functions
setup_review_home() {
    if [ ! -d "$HOME/.review" ]; then
        log_info "First time setup - installing defaults"
        mkdir -p "$PERSONAS_DIR" "$TEMPLATES_DIR" "$LOGS_DIR"
        cp -n "$SCRIPT_DIR/defaults/personas/"*.md "$PERSONAS_DIR/" 2>/dev/null || true
        cp -n "$SCRIPT_DIR/defaults/templates/"*.md "$TEMPLATES_DIR/" 2>/dev/null || true
        cp -n "$SCRIPT_DIR/defaults/config.sh" "$HOME/.review/" 2>/dev/null || true
        cp -n "$SCRIPT_DIR/defaults/screenrc" "$HOME/.review/" 2>/dev/null || true
        log_success "Configuration installed at ~/.review/"
    else
        # Always update screenrc to get latest color fixes
        cp "$SCRIPT_DIR/defaults/screenrc" "$HOME/.review/screenrc" 2>/dev/null || true
    fi
}

# Round management
get_current_round() {
    if [ -f "$CURRENT_ROUND_FILE" ]; then
        cat "$CURRENT_ROUND_FILE"
    else
        echo "1"
    fi
}

set_current_round() {
    mkdir -p "$REVIEW_DIR"
    echo "$1" > "$CURRENT_ROUND_FILE"
}

create_round_dir() {
    local round=$1
    local round_dir="$REVIEW_DIR/round-$round"
    mkdir -p "$round_dir"
    echo "$round_dir"
}

# Get severity for round
get_severity_for_round() {
    local round=$1
    case $round in
        1) echo "All Issues" ;;
        2) echo "Critical and High" ;;
        3) echo "Critical Only" ;;
        *) echo "Ship-Blocking Only" ;;
    esac
}

# Build context
build_context() {
    local round=$1
    local context_file="$REVIEW_DIR/round-$round/context.md"
    
    log_info "Building context for round $round" >&2
    
    {
        echo "# Code Review - Round $round"
        echo "## Project: $PROJECT_NAME"
        echo "## Date: $(date)"
        echo "## Severity Focus: $(get_severity_for_round $round)"
        echo ""
        
        # Include previous reviews for round 2+
        if [ "$round" -gt 1 ]; then
            local prev_round=$((round - 1))
            echo "## Previous Reviews (Round $prev_round)"
            echo ""
            
            for llm in claude codex gemini; do
                local prev_log="$REVIEW_DIR/round-$prev_round/${llm}.log"
                if [ -f "$prev_log" ] && [ -s "$prev_log" ]; then
                    echo "### ${llm^} Review:"
                    echo '```'
                    head -100 "$prev_log"
                    echo '```'
                    echo ""
                fi
            done
        fi
        
        # Include requirements
        if [ -f "requirements.md" ]; then
            echo "## Requirements"
            cat requirements.md
            echo ""
        fi
        
        echo "## Source Code to Review"
        echo ""
        
        # Find and include source files
        local file_count=0
        while IFS= read -r file; do
            if [ $file_count -ge ${DEFAULT_MAX_FILES:-20} ]; then
                echo "... (additional files truncated)"
                break
            fi
            
            echo "### File: $file"
            echo '```'
            cat "$file"
            echo '```'
            echo ""
            ((file_count++))
        done < <(find . -type f \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.go" \) \
                 -not -path "./.venv/*" \
                 -not -path "./node_modules/*" \
                 -not -path "./.git/*" \
                 -not -path "./review/*" 2>/dev/null)
        
        echo "Total files included: $file_count"
        
    } > "$context_file"
    
    # Log to stderr so it doesn't get captured
    log_success "Context built: $context_file ($(wc -l < "$context_file") lines)" >&2
    # Return just the path - no color codes, just the plain path
    printf "%s" "$context_file"
}

# Process template with persona
process_review_prompt() {
    local round=$1
    local role=$2
    local llm_name=$3
    local output_file=$4
    
    # Select template
    local template_file
    if [ "$round" -eq 1 ]; then
        template_file="$TEMPLATES_DIR/round-1.md"
    elif [ "$round" -gt 3 ]; then
        template_file="$TEMPLATES_DIR/final.md"
    else
        template_file="$TEMPLATES_DIR/round-n.md"
    fi
    
    # Load persona (convert to lowercase for macOS compatibility)
    local llm_lower=$(echo "$llm_name" | tr '[:upper:]' '[:lower:]')
    local persona_file="$PERSONAS_DIR/${llm_lower}.md"
    
    {
        # Start with persona
        if [ -f "$persona_file" ]; then
            cat "$persona_file"
            echo ""
            echo "---"
            echo ""
        fi
        
        # Add template
        if [ -f "$template_file" ]; then
            cat "$template_file" | \
                sed "s/\[ROUND_NUMBER\]/$round/g" | \
                sed "s/\[ROLE\]/$role/g" | \
                sed "s/\[SEVERITY_THRESHOLD\]/$(get_severity_for_round $round)/g"
        else
            echo "Please review the code in the context file."
        fi
        
    } > "$output_file"
}

# Launch screen sessions in separate iTerm2 windows
launch_screen_review() {
    local round=$(get_current_round)
    local round_dir=$(create_round_dir "$round")
    local context_file=$(build_context "$round")
    
    log_info "Preparing review session for round $round"
    
    # Process prompts for each LLM
    process_review_prompt "$round" "Architecture" "Claude" "$round_dir/claude-prompt.md"
    process_review_prompt "$round" "Debug" "Codex" "$round_dir/codex-prompt.md"
    process_review_prompt "$round" "Requirements" "Gemini" "$round_dir/gemini-prompt.md"
    
    # Kill any existing screen sessions
    screen -S claude-review -X quit 2>/dev/null || true
    screen -S codex-review -X quit 2>/dev/null || true
    screen -S gemini-review -X quit 2>/dev/null || true
    
    # Create startup scripts for each window
    cat > "$round_dir/start-claude.sh" << EOF
#!/bin/bash
cd '$PWD'
echo '═══════════════════════════════════════════════════════════════'
echo '           Claude - Architecture Review'
echo '═══════════════════════════════════════════════════════════════════'
echo ''
echo 'Starting screen session for Claude...'
export SCREENRC='$REVIEW_HOME/screenrc'
exec screen -c '$REVIEW_HOME/screenrc' -S claude-review claude
EOF
    
    cat > "$round_dir/start-codex.sh" << EOF
#!/bin/bash
cd '$PWD'
echo '═══════════════════════════════════════════════════════════════'
echo '              Codex - Debug Review'
echo '═══════════════════════════════════════════════════════════════'
echo ''
echo 'Starting screen session for Codex...'
export SCREENRC='$REVIEW_HOME/screenrc'
exec screen -c '$REVIEW_HOME/screenrc' -S codex-review codex
EOF
    
    cat > "$round_dir/start-gemini.sh" << EOF
#!/bin/bash
cd '$PWD'
echo '═══════════════════════════════════════════════════════════════'
echo '          Gemini - Requirements Review'
echo '═══════════════════════════════════════════════════════════════'
echo ''
echo 'Starting screen session for Gemini...'
export SCREENRC='$REVIEW_HOME/screenrc'
exec screen -c '$REVIEW_HOME/screenrc' -S gemini-review gemini
EOF
    
    chmod +x "$round_dir"/start-*.sh
    
    # Create iTerm2 windows and run the startup scripts
    osascript << EOF
tell application "iTerm"
    -- Create Claude window
    create window with default profile
    tell current session of current window
        write text "$PWD/$round_dir/start-claude.sh"
    end tell
    
    -- Create Codex window
    create window with default profile
    tell current session of current window
        write text "$PWD/$round_dir/start-codex.sh"
    end tell
    
    -- Create Gemini window
    create window with default profile
    tell current session of current window
        write text "$PWD/$round_dir/start-gemini.sh"
    end tell
    
    -- Create Controller window
    create window with default profile
    tell current session of current window
        write text "$PWD/$round_dir/controller.sh"
    end tell
    
    activate
end tell
EOF
    
    # Create controller script
    cat > "$round_dir/controller.sh" << 'EOF'
#!/bin/bash

# Configuration
ROUND=CURRENT_ROUND
MAX_ROUNDS=MAX_ROUNDS_VAR
PROJECT="PROJECT_NAME_VAR"
CONTEXT_FILE="CONTEXT_FILE_VAR"
ROUND_DIR="ROUND_DIR_VAR"

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
EOF
    
    # Substitute variables in controller script
    chmod +x "$round_dir/controller.sh"
    sed -i '' "s|CURRENT_ROUND|$round|g" "$round_dir/controller.sh"
    sed -i '' "s|MAX_ROUNDS_VAR|$MAX_ROUNDS|g" "$round_dir/controller.sh"
    sed -i '' "s|PROJECT_NAME_VAR|$PROJECT_NAME|g" "$round_dir/controller.sh"
    sed -i '' "s|CONTEXT_FILE_VAR|$context_file|g" "$round_dir/controller.sh"
    sed -i '' "s|ROUND_DIR_VAR|$round_dir|g" "$round_dir/controller.sh"
    
    echo ""
    log_success "iTerm2 windows with screen sessions launched!"
    echo ""
    echo "🖥️  4 separate iTerm2 windows created:"
    echo "  1. Claude (Architecture Review) - with screen session"
    echo "  2. Codex (Debug Review) - with screen session"
    echo "  3. Gemini (Requirements Review) - with screen session"
    echo "  4. Controller - sends commands to all sessions"
    echo ""
    echo "📝 How it works:"
    echo "  • Each LLM runs in a screen session in its own window"
    echo "  • Controller can send text to any screen session"
    echo "  • Text is executed properly with Enter key"
    echo ""
    echo "🎯 Quick Start:"
    echo "  • In Controller window, type: all hello"
    echo "  • This sends 'hello' to all three LLMs"
    echo "  • Type 'help' for all commands"
    echo ""
    echo "📁 Logs saved to: $round_dir/"
}

# Main commands
cmd_start() {
    if ! command -v screen &> /dev/null; then
        log_error "screen not found. Please install screen first."
        exit 1
    fi
    
    setup_review_home
    
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}        Starting LLM Review Session for $PROJECT_NAME${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    set_current_round 1
    launch_screen_review
}

cmd_next() {
    if ! command -v screen &> /dev/null; then
        log_error "screen not found. Please install screen first."
        exit 1
    fi
    
    local current=$(get_current_round)
    local next=$((current + 1))
    
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}           Advancing to Round $next${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    set_current_round $next
    launch_screen_review
}

cmd_status() {
    local round=$(get_current_round)
    
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}                    Review Status${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  Project: $PROJECT_NAME"
    echo "  Current Round: $round / $MAX_ROUNDS"
    echo "  Severity Focus: $(get_severity_for_round $round)"
    echo "  Review Directory: $REVIEW_DIR/"
    
    if [ -d "$REVIEW_DIR/round-$round" ]; then
        echo ""
        echo "  Round $round files:"
        ls -lah "$REVIEW_DIR/round-$round/" 2>/dev/null | grep -E "\.(log|md|sh)$" | awk '{print "    " $9 " (" $5 ")"}'
    fi
    
    echo ""
    echo "  Configuration: ${REVIEW_HOME:-~/.review}"
}

cmd_reset() {
    echo -e "${YELLOW}Reset review state? This will delete all logs. (y/N)${NC}"
    read -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$REVIEW_DIR"
        set_current_round 1
        log_success "Review state reset"
    else
        echo "Reset cancelled"
    fi
}

cmd_setup() {
    log_info "Installing review configuration..."
    mkdir -p "$HOME/.review"
    setup_review_home
    log_success "Setup complete!"
}

# Main entry point
main() {
    case "${1:-}" in
        start)
            cmd_start
            ;;
        next)
            cmd_next
            ;;
        status)
            cmd_status
            ;;
        reset)
            cmd_reset
            ;;
        setup)
            cmd_setup
            ;;
        *)
            echo "Usage: $0 {start|next|status|reset|setup}"
            echo ""
            echo "iTerm2 Multi-LLM Code Review Orchestrator"
            echo ""
            echo "Commands:"
            echo "  start  - Start new review session (Round 1)"
            echo "  next   - Progress to next round"
            echo "  status - Show current round and logs"
            echo "  reset  - Clear all review data"
            echo "  setup  - Install default configuration"
            echo ""
            echo "This version uses iTerm2's native split panes for a cleaner"
            echo "macOS experience. No tmux required!"
            exit 1
            ;;
    esac
}

main "$@"