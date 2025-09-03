#!/bin/bash
echo -e "\033[1;33m═══════════════════════════════════════════════════════════════\033[0m"
echo -e "\033[1;33m              Codex - Debug Review (Pane 2)\033[0m"
echo -e "\033[1;33m═══════════════════════════════════════════════════════════════\033[0m"
echo ""
echo "Context: review/round-1/context.md"
echo "Prompt: review/round-1/codex-prompt.md"
echo ""
echo "Starting Codex..."
echo ""

# Start codex in interactive mode
exec codex
