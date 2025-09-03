#!/bin/bash

# Review Orchestrator Configuration

# Review settings
MAX_ROUNDS=3
DEFAULT_MAX_FILES=20
DEFAULT_FILE_PATTERNS="-name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.go' -o -name '*.rs'"

# Session settings
SESSION_PREFIX="review"
LOCK_FILE_NAME="session.lock"

# Directory paths
REVIEW_HOME="$HOME/.review"
PERSONAS_DIR="$REVIEW_HOME/personas"
TEMPLATES_DIR="$REVIEW_HOME/templates"
LOGS_DIR="$REVIEW_HOME/logs"

# Severity thresholds per round
ROUND_1_SEVERITY="All"
ROUND_2_SEVERITY="Critical and High"
ROUND_3_SEVERITY="Critical only"
FINAL_SEVERITY="Ship-blocking only"

# Timeouts
PERSONA_ACK_TIMEOUT=10  # seconds to wait for persona acknowledgment
LLM_START_TIMEOUT=5     # seconds to wait for LLM to start

# Colors for output
export RED='\033[0;31m'
export GREEN='\033[0;32m'
export YELLOW='\033[1;33m'
export CYAN='\033[0;36m'
export BLUE='\033[0;34m'
export MAGENTA='\033[0;35m'
export NC='\033[0m' # No Color

# Check mark and cross symbols
export CHECK_MARK="✓"
export CROSS_MARK="✗"

# Export all for use in scripts
export MAX_ROUNDS DEFAULT_MAX_FILES DEFAULT_FILE_PATTERNS
export SESSION_PREFIX LOCK_FILE_NAME
export REVIEW_HOME PERSONAS_DIR TEMPLATES_DIR LOGS_DIR
export ROUND_1_SEVERITY ROUND_2_SEVERITY ROUND_3_SEVERITY FINAL_SEVERITY
export PERSONA_ACK_TIMEOUT LLM_START_TIMEOUT