#!/bin/bash
echo -e "\033[1;35m═══════════════════════════════════════════════════════════════\033[0m"
echo -e "\033[1;35m          Gemini - Requirements Review (Pane 3)\033[0m"
echo -e "\033[1;35m═══════════════════════════════════════════════════════════════\033[0m"
echo ""

# Check if gemini CLI exists
if command -v gemini &> /dev/null; then
    echo "Context: review/round-1/context.md"
    echo "Prompt: review/round-1/gemini-prompt.md"
    echo ""
    echo "Starting Gemini..."
    echo ""
    
    # Start gemini in interactive mode
    exec gemini
else
    echo "Gemini CLI not found. This pane is ready for manual interaction."
    exec bash
fi
