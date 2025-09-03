#!/bin/bash
cd '/Users/remcohendriks/work/nano-graphrag'
echo '═══════════════════════════════════════════════════════════════'
echo '              Codex - Debug Review'
echo '═══════════════════════════════════════════════════════════════'
echo ''
echo 'Starting screen session for Codex...'
export SCREENRC='/Users/remcohendriks/.review/screenrc'
exec screen -c '/Users/remcohendriks/.review/screenrc' -S codex-review codex
