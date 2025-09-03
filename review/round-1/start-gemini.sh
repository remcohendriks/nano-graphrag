#!/bin/bash
cd '/Users/remcohendriks/work/nano-graphrag'
echo '═══════════════════════════════════════════════════════════════'
echo '          Gemini - Requirements Review'
echo '═══════════════════════════════════════════════════════════════'
echo ''
echo 'Starting screen session for Gemini...'
export SCREENRC='/Users/remcohendriks/.review/screenrc'
exec screen -c '/Users/remcohendriks/.review/screenrc' -S gemini-review gemini
