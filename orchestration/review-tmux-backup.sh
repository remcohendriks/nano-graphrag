#!/bin/bash

# Multi-LLM Code Review Orchestrator with Personas and Templates
# Orchestrates code reviews from Claude, Codex, and Gemini using tmux

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load configuration
CONFIG_FILE="$HOME/.review/config.sh"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
else
    # Use defaults if config doesn't exist
    source "$SCRIPT_DIR/defaults/config.sh"
fi

# Configuration
PROJECT_NAME="$(basename "$(pwd)")"
SESSION_NAME="${SESSION_PREFIX}-${PROJECT_NAME}"
REVIEW_DIR="review"
CURRENT_ROUND_FILE="$REVIEW_DIR/current-round.txt"
SESSION_LOCK_FILE="$REVIEW_DIR/session.lock"
COMMAND_PARSER_SCRIPT="$SCRIPT_DIR/command_parser.sh"

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

log_fail() {
    echo -e "${RED}${CROSS_MARK}${NC} $1"
}

# Setup and installation functions
install_defaults() {
    log_info "Installing default configuration..."
    
    # Create directories
    mkdir -p "$PERSONAS_DIR" "$TEMPLATES_DIR" "$LOGS_DIR"
    
    # Copy default files
    cp -n "$SCRIPT_DIR/defaults/personas/"*.md "$PERSONAS_DIR/" 2>/dev/null || true
    cp -n "$SCRIPT_DIR/defaults/templates/"*.md "$TEMPLATES_DIR/" 2>/dev/null || true
    cp -n "$SCRIPT_DIR/defaults/config.sh" "$HOME/.review/" 2>/dev/null || true
    
    log_success "Default configuration installed at ~/.review/"
}

setup_review_home() {
    if [ ! -d "$HOME/.review" ]; then
        log_info "First time setup detected"
        install_defaults
    fi
}

# Pre-flight checks
check_tmux() {
    if command -v tmux &> /dev/null; then
        log_success "tmux available ($(tmux -V))"
        return 0
    else
        log_fail "tmux not found"
        echo "  To install tmux on macOS:"
        echo "    brew install tmux"
        echo ""
        echo "  Or if Homebrew is not installed:"
        echo "    /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        echo "    brew install tmux"
        return 1
    fi
}

check_llm_auth() {
    local llm=$1
    local name=$2
    
    if command -v "$llm" &> /dev/null; then
        # Try to verify authentication
        if $llm --version &> /dev/null || $llm help &> /dev/null; then
            log_success "$name CLI authenticated"
            return 0
        else
            log_warn "$name CLI found but may not be authenticated"
            return 0
        fi
    else
        log_fail "$name CLI not found"
        return 1
    fi
}

check_dependencies() {
    log_info "Running pre-flight checks..."
    echo ""
    
    local all_good=true
    local missing_count=0
    
    # Check tmux
    if ! check_tmux; then
        all_good=false
        ((missing_count++))
    fi
    
    # Check LLMs
    if ! check_llm_auth "claude" "Claude"; then
        all_good=false
        ((missing_count++))
        echo "  To install Claude CLI:"
        echo "    Visit: https://claude.ai/cli"
        echo ""
    fi
    
    if ! check_llm_auth "codex" "Codex"; then
        all_good=false
        ((missing_count++))
        echo "  Note: Codex CLI installation varies by provider"
        echo ""
    fi
    
    if ! check_llm_auth "gemini" "Gemini"; then
        all_good=false
        ((missing_count++))
        echo "  Note: Gemini CLI installation varies by provider"
        echo ""
    fi
    
    echo ""
    
    if [ "$all_good" = false ]; then
        log_error "Pre-flight checks failed ($missing_count dependencies missing)"
        echo ""
        echo "Please install the missing dependencies above and try again."
        echo "You can also run './orchestration/review.sh check' to verify installation."
        exit 1
    else
        log_success "All checks passed. Ready to review!"
    fi
}

check_existing_session() {
    if [ -f "$SESSION_LOCK_FILE" ]; then
        log_warn "Session lock file exists"
        
        # Check if tmux session actually exists
        if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
            log_error "Active session exists. Use 'review attach' or 'review reset'"
            return 1
        else
            log_info "Stale lock file detected, removing..."
            rm -f "$SESSION_LOCK_FILE"
        fi
    fi
    
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        log_error "Session already exists. Use 'review attach' or 'review reset'"
        return 1
    fi
    
    return 0
}

# Session management functions
create_session() {
    log_info "Creating tmux session: $SESSION_NAME"
    
    # Create session with first pane
    tmux new-session -d -s "$SESSION_NAME" -n "review"
    
    # Split horizontally to create bottom pane (command pane)
    tmux split-window -t "$SESSION_NAME:0" -v -p 30
    
    # Split top section into 3 vertical panes for LLMs
    tmux select-pane -t "$SESSION_NAME:0.0"
    tmux split-window -t "$SESSION_NAME:0.0" -h -p 66
    tmux split-window -t "$SESSION_NAME:0.1" -h -p 50
    
    # Set pane titles (requires tmux 2.3+)
    tmux select-pane -t "$SESSION_NAME:0.0" -T "Claude (Architecture)"
    tmux select-pane -t "$SESSION_NAME:0.1" -T "Codex (Debug)"
    tmux select-pane -t "$SESSION_NAME:0.2" -T "Gemini (Requirements)"
    tmux select-pane -t "$SESSION_NAME:0.3" -T "Command"
    
    # Create session lock
    echo "$$" > "$SESSION_LOCK_FILE"
    
    log_success "tmux layout created with 4 panes"
}

attach_session() {
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        log_info "Attaching to existing session"
        tmux attach-session -t "$SESSION_NAME"
    else
        log_error "No session exists. Run 'review start' first"
        exit 1
    fi
}

kill_session() {
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        log_info "Killing session: $SESSION_NAME"
        tmux kill-session -t "$SESSION_NAME"
    fi
    
    # Remove lock file
    rm -f "$SESSION_LOCK_FILE"
}

# Round management functions
get_current_round() {
    if [ -f "$CURRENT_ROUND_FILE" ]; then
        cat "$CURRENT_ROUND_FILE"
    else
        echo "1"
    fi
}

set_current_round() {
    local round=$1
    mkdir -p "$REVIEW_DIR"
    echo "$round" > "$CURRENT_ROUND_FILE"
}

increment_round() {
    local current=$(get_current_round)
    local next=$((current + 1))
    set_current_round "$next"
    echo "$next"
}

create_round_dir() {
    local round=$1
    local round_dir="$REVIEW_DIR/round-$round"
    mkdir -p "$round_dir"
    echo "$round_dir"
}

# Persona management
load_persona() {
    local pane=$1
    local llm_name=$2
    local persona_file="$PERSONAS_DIR/${llm_name,,}.md"
    
    if [ ! -f "$persona_file" ]; then
        log_warn "Persona file not found: $persona_file"
        return 1
    fi
    
    log_info "Loading $llm_name persona..."
    
    # Read persona and send line by line
    while IFS= read -r line; do
        tmux send-keys -t "$SESSION_NAME:0.$pane" "$line" Enter
        sleep 0.05
    done < "$persona_file"
    
    # Add extra newline to trigger response
    tmux send-keys -t "$SESSION_NAME:0.$pane" "" Enter
    
    return 0
}

wait_for_persona_ack() {
    local pane=$1
    local llm_name=$2
    local timeout=${PERSONA_ACK_TIMEOUT:-10}
    
    log_info "Waiting for $llm_name acknowledgment..."
    
    # Simple wait for now - could be enhanced to check output
    sleep 3
    
    log_success "$llm_name persona established"
}

# Template processing
get_severity_for_round() {
    local round=$1
    
    case $round in
        1) echo "$ROUND_1_SEVERITY" ;;
        2) echo "$ROUND_2_SEVERITY" ;;
        3) echo "$ROUND_3_SEVERITY" ;;
        *) echo "$FINAL_SEVERITY" ;;
    esac
}

process_template() {
    local template_file=$1
    local round=$2
    local role=$3
    local context_file=$4
    local output_file=$5
    
    # Read template
    local template=$(cat "$template_file")
    
    # Read context
    local context=""
    if [ -f "$context_file" ]; then
        context=$(cat "$context_file")
    fi
    
    # Get requirements if exists
    local requirements=""
    if [ -f "requirements.md" ]; then
        requirements=$(cat requirements.md)
    fi
    
    # Get severity threshold
    local severity=$(get_severity_for_round "$round")
    
    # Process substitutions
    template="${template//\[ROUND_NUMBER\]/$round}"
    template="${template//\[ROLE\]/$role}"
    template="${template//\[PROJECT_REQUIREMENTS\]/$requirements}"
    template="${template//\[SOURCE_CODE\]/$context}"
    template="${template//\[SEVERITY_THRESHOLD\]/$severity}"
    
    # Handle round-specific focus
    local focus=""
    case $round in
        2) focus="Focus only on Critical and High priority issues" ;;
        3) focus="Only flag ship-blocking issues" ;;
        *) focus="Provide comprehensive review" ;;
    esac
    template="${template//\[ROUND_SPECIFIC_FOCUS\]/$focus}"
    
    # Handle final round additions
    if [ "$round" -gt "$MAX_ROUNDS" ]; then
        template="${template//\[FINAL_ROUND_ONLY\]/Provide SHIP or NO-SHIP recommendation}"
    else
        template="${template//\[FINAL_ROUND_ONLY\]/}"
    fi
    
    # Save processed template
    echo "$template" > "$output_file"
}

# Context building functions
build_initial_context() {
    local round=$1
    local context_file="$REVIEW_DIR/round-$round/context.md"
    
    log_info "Building initial context for round $round"
    
    {
        echo "## Source Code"
        echo ""
        
        # Find source files (using configuration patterns)
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
        done < <(find . -type f \( $DEFAULT_FILE_PATTERNS \) \
                 -not -path "./.venv/*" \
                 -not -path "./node_modules/*" \
                 -not -path "./.git/*" \
                 -not -path "./review/*" 2>/dev/null)
        
        echo "Total files included: $file_count"
        
    } > "$context_file"
    
    log_info "Context saved to: $context_file"
    echo "$context_file"
}

build_review_context() {
    local round=$1
    local prev_round=$((round - 1))
    local context_file="$REVIEW_DIR/round-$round/previous-reviews.md"
    
    log_info "Building review context from round $prev_round"
    
    {
        echo "## Previous Reviews (Round $prev_round)"
        echo ""
        
        # Include previous reviews
        for llm in claude codex gemini; do
            local log_file="$REVIEW_DIR/round-$prev_round/${llm}.log"
            if [ -f "$log_file" ]; then
                echo "### ${llm^}'s Review"
                echo '```'
                cat "$log_file"
                echo '```'
                echo ""
            fi
        done
        
    } > "$context_file"
    
    echo "$context_file"
}

# LLM management functions
start_llm_in_pane() {
    local pane=$1
    local llm_name=$2
    local llm_cmd=$3
    local log_file=$4
    
    log_info "Starting $llm_name in pane $pane"
    
    # Start the LLM with logging
    tmux send-keys -t "$SESSION_NAME:0.$pane" "$llm_cmd 2>&1 | tee -a $log_file" Enter
    
    # Wait for LLM to start
    sleep ${LLM_START_TIMEOUT:-5}
}

send_prompt_to_llm() {
    local pane=$1
    local prompt_file=$2
    
    if [ ! -f "$prompt_file" ]; then
        log_error "Prompt file not found: $prompt_file"
        return 1
    fi
    
    # Send prompt line by line with small delays
    while IFS= read -r line; do
        tmux send-keys -t "$SESSION_NAME:0.$pane" "$line" Enter
        sleep 0.05
    done < "$prompt_file"
    
    # Send extra newline to trigger processing
    tmux send-keys -t "$SESSION_NAME:0.$pane" "" Enter
}

start_all_llms() {
    local round=$1
    local round_dir="$REVIEW_DIR/round-$round"
    
    log_info "Starting all LLMs for round $round"
    
    # Start each LLM
    start_llm_in_pane 0 "Claude" "claude" "$round_dir/claude.log"
    start_llm_in_pane 1 "Codex" "codex --config model_reasoning_effort='high' exec --skip-git-repo-check" "$round_dir/codex.log"
    start_llm_in_pane 2 "Gemini" "gemini" "$round_dir/gemini.log"
    
    log_info "Establishing personas..."
    
    # Load personas
    load_persona 0 "Claude"
    wait_for_persona_ack 0 "Claude"
    
    load_persona 1 "Codex"
    wait_for_persona_ack 1 "Codex"
    
    load_persona 2 "Gemini"
    wait_for_persona_ack 2 "Gemini"
    
    log_success "All LLMs started with personas"
}

send_review_prompts() {
    local round=$1
    local round_dir="$REVIEW_DIR/round-$round"
    
    log_info "Sending review prompts for round $round"
    
    # Determine template to use
    local template_file
    if [ "$round" -eq 1 ]; then
        template_file="$TEMPLATES_DIR/round-1.md"
    elif [ "$round" -gt "$MAX_ROUNDS" ]; then
        template_file="$TEMPLATES_DIR/final.md"
    else
        template_file="$TEMPLATES_DIR/round-n.md"
    fi
    
    # Build context
    local context_file
    if [ "$round" -eq 1 ]; then
        context_file=$(build_initial_context "$round")
    else
        # For round 2+, include previous reviews
        build_review_context "$round"
        context_file=$(build_initial_context "$round")
    fi
    
    # Process templates for each LLM
    process_template "$template_file" "$round" "Architecture" "$context_file" "$round_dir/claude-prompt.md"
    process_template "$template_file" "$round" "Debug" "$context_file" "$round_dir/codex-prompt.md"
    process_template "$template_file" "$round" "Requirements" "$context_file" "$round_dir/gemini-prompt.md"
    
    # Send prompts to LLMs
    send_prompt_to_llm 0 "$round_dir/claude-prompt.md"
    send_prompt_to_llm 1 "$round_dir/codex-prompt.md"
    send_prompt_to_llm 2 "$round_dir/gemini-prompt.md"
    
    log_success "Review prompts sent"
}

start_command_parser() {
    log_info "Starting command parser in pane 3"
    
    # Start the command parser
    tmux send-keys -t "$SESSION_NAME:0.3" "$COMMAND_PARSER_SCRIPT $SESSION_NAME $(get_current_round)" Enter
}

# Main command handlers
cmd_setup() {
    log_info "Setting up review orchestrator..."
    install_defaults
    log_success "Setup complete. Configuration installed at ~/.review/"
}

cmd_check() {
    setup_review_home
    check_dependencies
}

cmd_start() {
    # Setup home directory if needed
    setup_review_home
    
    # Pre-flight checks
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}        Starting Review Session for: $PROJECT_NAME${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    check_dependencies
    check_existing_session || exit 1
    
    # Initialize round 1
    set_current_round 1
    local round_dir=$(create_round_dir 1)
    
    # Create tmux session
    echo ""
    log_info "Initializing session..."
    create_session
    
    # Start all LLMs with personas
    echo ""
    start_all_llms 1
    
    # Send review prompts
    echo ""
    send_review_prompts 1
    
    # Start command parser
    start_command_parser
    
    echo ""
    log_success "Review session started (Round 1)"
    log_info "Session: $SESSION_NAME"
    log_info "Logs: $round_dir/"
    echo ""
    echo "You can now:"
    echo "  - Click any LLM pane to interact directly"
    echo "  - Use command pane for orchestration"
    echo "  - Type 'help' in command pane for available commands"
    echo ""
    
    # Check if we're already in a tmux session
    if [ -n "$TMUX" ]; then
        echo -e "${YELLOW}Already in a tmux session. Open a new terminal and run:${NC}"
        echo "  ./orchestration/review.sh attach"
    else
        # Attach to session
        echo -e "${GREEN}Attaching to tmux session...${NC}"
        echo ""
        echo "tmux controls:"
        echo "  - Switch panes: Ctrl+B then arrow keys"
        echo "  - Detach: Ctrl+B then D"
        echo "  - Scroll: Ctrl+B then [ (then q to exit scroll)"
        echo ""
        sleep 2
        attach_session
    fi
}

cmd_next() {
    if [ ! -f "$SESSION_LOCK_FILE" ]; then
        log_error "No active session. Run 'review start' first"
        exit 1
    fi
    
    # Increment round
    local next_round=$(increment_round)
    local round_dir=$(create_round_dir "$next_round")
    
    log_info "Advancing to Round $next_round"
    
    # Clear all LLM panes
    for pane in 0 1 2; do
        tmux send-keys -t "$SESSION_NAME:0.$pane" C-c
        sleep 0.5
        tmux send-keys -t "$SESSION_NAME:0.$pane" "clear" Enter
    done
    
    # Restart all LLMs
    start_all_llms "$next_round"
    
    # Send new prompts
    send_review_prompts "$next_round"
    
    log_success "Advanced to Round $next_round"
    
    # Update command parser with new round
    tmux send-keys -t "$SESSION_NAME:0.3" C-c
    start_command_parser
    
    # Reattach to session
    attach_session
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
    
    if [ -f "$SESSION_LOCK_FILE" ] && tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "  Session: ${GREEN}Active${NC} ($SESSION_NAME)"
        echo ""
        echo "  Panes:"
        echo "    0: Claude (Architecture focus)"
        echo "    1: Codex (Debug focus)"
        echo "    2: Gemini (Requirements focus)"
        echo "    3: Command interface"
    else
        echo "  Session: ${RED}Not active${NC}"
    fi
    
    if [ -d "$REVIEW_DIR/round-$round" ]; then
        echo ""
        echo "  Round $round files:"
        ls -la "$REVIEW_DIR/round-$round/" 2>/dev/null | grep -E "\.(log|md)$" | awk '{print "    " $NF}'
    fi
    
    echo ""
    echo "  Configuration: ${REVIEW_HOME:-~/.review}"
}

cmd_attach() {
    attach_session
}

cmd_reset() {
    echo -e "${YELLOW}Warning: This will kill the active session and reset the review state.${NC}"
    read -p "Continue? (y/N) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Kill existing session if any
        kill_session
        
        # Reset round counter
        set_current_round 1
        
        # Optionally clean review directory
        read -p "Remove all review logs? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$REVIEW_DIR"
            log_info "Review logs removed"
        fi
        
        log_success "Review system reset. Run 'review start' to begin new review cycle"
    else
        log_info "Reset cancelled"
    fi
}

# Main entry point
main() {
    case "${1:-}" in
        setup)
            cmd_setup
            ;;
        check)
            cmd_check
            ;;
        start)
            cmd_start
            ;;
        next)
            cmd_next
            ;;
        status)
            cmd_status
            ;;
        attach)
            cmd_attach
            ;;
        reset)
            cmd_reset
            ;;
        *)
            echo "Usage: $0 {setup|check|start|next|status|attach|reset}"
            echo ""
            echo "Commands:"
            echo "  setup   - Install default configuration to ~/.review"
            echo "  check   - Verify dependencies and authentication"
            echo "  start   - Start new review session with personas"
            echo "  next    - Progress to next round with new template"
            echo "  status  - Show current session and round status"
            echo "  attach  - Reattach to existing tmux session"
            echo "  reset   - Kill session and reset for new review"
            exit 1
            ;;
    esac
}

main "$@"