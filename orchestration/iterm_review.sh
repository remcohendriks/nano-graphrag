#!/bin/bash
#
# iTerm2-based Multi-LLM Code Review Orchestrator
# Launcher script for the Python-based orchestrator

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Use venv Python if available
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
else
    PYTHON="python3"
fi

# Check dependencies
check_dependencies() {
    echo -e "${CYAN}Checking dependencies...${NC}"
    
    # Check Python 3
    if ! command -v "$PYTHON" &> /dev/null; then
        echo -e "${RED}✗ Python not found${NC}"
        echo "Please install Python 3.7 or later"
        exit 1
    fi
    echo -e "${GREEN}✓ Python found ($PYTHON)${NC}"
    
    # Check iTerm2
    if ! osascript -e 'tell application "System Events" to get exists application process "iTerm2"' &> /dev/null; then
        echo -e "${YELLOW}⚠ iTerm2 not running${NC}"
        echo "Starting iTerm2..."
        open -a iTerm2
        sleep 2
    fi
    echo -e "${GREEN}✓ iTerm2 is running${NC}"
    
    # Check iterm2 Python package
    if ! "$PYTHON" -c "import iterm2" 2>/dev/null; then
        echo -e "${YELLOW}⚠ iterm2 Python package not installed${NC}"
        if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
            echo "Installing iterm2 package in venv..."
            "$SCRIPT_DIR/.venv/bin/pip" install iterm2
        else
            echo "Installing iterm2 package..."
            pip3 install iterm2
        fi
    fi
    echo -e "${GREEN}✓ iterm2 Python package installed${NC}"
    
    # Check LLM CLIs
    echo ""
    echo "Checking LLM CLIs..."
    
    if command -v claude &> /dev/null; then
        echo -e "${GREEN}✓ Claude CLI found${NC}"
    else
        echo -e "${YELLOW}⚠ Claude CLI not found${NC}"
    fi
    
    if command -v codex &> /dev/null; then
        echo -e "${GREEN}✓ Codex CLI found${NC}"
    else
        echo -e "${YELLOW}⚠ Codex CLI not found${NC}"
    fi
    
    if command -v gemini &> /dev/null; then
        echo -e "${GREEN}✓ Gemini CLI found${NC}"
    else
        echo -e "${YELLOW}⚠ Gemini CLI not found${NC}"
    fi
}

# Setup review home
setup_review_home() {
    REVIEW_HOME="$HOME/.review"
    
    if [ ! -d "$REVIEW_HOME" ]; then
        echo -e "${CYAN}Setting up review home...${NC}"
        mkdir -p "$REVIEW_HOME/personas"
        mkdir -p "$REVIEW_HOME/templates"
        
        # Copy default files if they exist
        if [ -d "$SCRIPT_DIR/defaults" ]; then
            cp -r "$SCRIPT_DIR/defaults/personas/"*.md "$REVIEW_HOME/personas/" 2>/dev/null || true
            cp -r "$SCRIPT_DIR/defaults/templates/"*.md "$REVIEW_HOME/templates/" 2>/dev/null || true
        fi
        
        echo -e "${GREEN}✓ Review home created at ~/.review${NC}"
    fi
}

# Enable iTerm2 Python API
enable_python_api() {
    echo ""
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}                    IMPORTANT SETUP STEP                       ${NC}"
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "To use the Python API, you must enable it in iTerm2:"
    echo ""
    echo "  1. Open iTerm2 Preferences (⌘,)"
    echo "  2. Go to: General → Magic"
    echo "  3. Check: ☑ Enable Python API"
    echo ""
    echo "Press Enter when you've enabled the Python API..."
    read -r
}

# Main menu
show_menu() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}           iTerm2 Multi-LLM Review Orchestrator                ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  1) Start new review session    (launches all LLMs)"
    echo "  2) Connect to existing session (control running LLMs)"
    echo "  3) Setup/check configuration"
    echo "  4) Exit"
    echo ""
    echo -n "Select option: "
}

# Main
main() {
    clear
    check_dependencies
    setup_review_home
    
    while true; do
        show_menu
        read -r choice
        
        case $choice in
            1)
                echo ""
                echo -e "${CYAN}Starting new review session...${NC}"
                echo "This will open 4 iTerm2 windows (Claude, Codex, Gemini, Controller)"
                echo ""
                "$PYTHON" "$SCRIPT_DIR/review_iterm.py"
                ;;
            2)
                echo ""
                echo -e "${CYAN}Connecting to existing sessions...${NC}"
                echo "This will connect to already running LLM windows"
                echo ""
                "$PYTHON" "$SCRIPT_DIR/review_controller.py"
                ;;
            3)
                echo ""
                enable_python_api
                check_dependencies
                setup_review_home
                echo -e "${GREEN}✓ Configuration complete${NC}"
                ;;
            4)
                echo "Goodbye!"
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}"
                ;;
        esac
    done
}

# Run main
main "$@"