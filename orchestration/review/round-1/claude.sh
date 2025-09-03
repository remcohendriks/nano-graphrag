#!/bin/bash
echo -e "\033[1;36m═══════════════════════════════════════════════════════════════\033[0m"
echo -e "\033[1;36m           Claude - Architecture Review (Pane 1)\033[0m"
echo -e "\033[1;36m═══════════════════════════════════════════════════════════════\033[0m"
echo ""
echo "Context: review/round-1/context.md"
echo "Prompt: review/round-1/claude-prompt.md"
echo ""
echo "Starting Claude..."
echo ""

# Start claude in interactive mode (REPL)
exec claude
