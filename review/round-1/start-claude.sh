#!/bin/bash
cd '/Users/remcohendriks/work/nano-graphrag'
echo '═══════════════════════════════════════════════════════════════'
echo '           Claude - Architecture Review'
echo '═══════════════════════════════════════════════════════════════════'
echo ''
echo 'Starting screen session for Claude...'
export SCREENRC='/Users/remcohendriks/.review/screenrc'
exec screen -c '/Users/remcohendriks/.review/screenrc' -S claude-review claude
