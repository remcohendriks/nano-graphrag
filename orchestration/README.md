# Multi-LLM Code Review Orchestrator

A tmux-based CLI tool that orchestrates parallel code reviews from Claude, Codex, and Gemini with specialized reviewer personas, progressive review templates, and both direct interaction and orchestrated control capabilities.

## Features

- **Specialized Reviewer Personas**: Each LLM has a defined expertise role
  - Claude: Senior Software Architect (system design, patterns, architecture)
  - Codex: Debug Specialist (bugs, security, performance)
  - Gemini: Requirements Analyst (compliance, documentation, QA)
- **Progressive Review Templates**: Round-based templates guide convergence
  - Round 1: Comprehensive review (all severities)
  - Round 2: Focus on Critical and High priority
  - Round 3+: Critical only, then ship decision
- **Pre-flight Checks**: Automatic verification of dependencies and authentication
- **Session Management**: Lock files prevent duplicate sessions
- **Interactive Control**: Direct interaction with each LLM or orchestrated commands
- **Automatic Logging**: All outputs captured with round organization

## Prerequisites

- macOS (tested on macOS 12+)
- tmux 3.0+ (`brew install tmux`)
- Claude CLI (authenticated)
- Codex CLI (authenticated)
- Gemini CLI (authenticated)
- Bash 5.0+

## Installation

1. Clone or download the orchestration scripts to your project directory

2. Make the scripts executable:
```bash
chmod +x orchestration/*.sh
```

3. Install dependencies (macOS):
```bash
# Quick install helper
./orchestration/install-deps.sh

# Or manually install tmux
brew install tmux
```

4. Run initial setup (one-time):
```bash
./orchestration/review.sh setup
```

This installs default personas and templates to `~/.review/`

5. Verify dependencies:
```bash
./orchestration/review.sh check
```

If any dependencies are missing, the check command will provide installation instructions.

6. Optionally, add to PATH:
```bash
export PATH="$PATH:$(pwd)/orchestration"
```

## Configuration

The tool uses configuration files in `~/.review/`:

```
~/.review/
├── config.sh           # Main configuration
├── personas/
│   ├── claude.md      # Architecture reviewer persona
│   ├── codex.md       # Debug specialist persona
│   └── gemini.md      # Requirements analyst persona
└── templates/
    ├── round-1.md     # Comprehensive review template
    ├── round-n.md     # Convergence template
    └── final.md       # Ship decision template
```

### Customizing Personas

Edit `~/.review/personas/{llm}.md` to modify reviewer focus. Each persona should:
- Define expertise areas
- Set review priorities
- End with acknowledgment phrase (e.g., "Architect reviewer ready.")

### Customizing Templates

Templates use placeholders that get substituted:
- `[ROUND_NUMBER]` - Current round number
- `[ROLE]` - Reviewer role (Architecture/Debug/Requirements)
- `[PROJECT_REQUIREMENTS]` - From requirements.md
- `[SOURCE_CODE]` - Aggregated source files
- `[SEVERITY_THRESHOLD]` - Round-based severity focus
- `[PREVIOUS_REVIEWS]` - Prior round reviews (round 2+)

## Usage

### Starting a Review Session

#### Option 1: Direct Terminal (Recommended)
```bash
./orchestration/review.sh start
```

This will create a tmux session and attach to it in your current terminal.

#### Option 2: New Terminal Window (macOS)
```bash
# Opens in a new Terminal/iTerm window
./orchestration/review-gui.sh start
```

#### What Happens:
1. Run pre-flight checks (tmux, LLM authentication)
2. Check for existing sessions (prevents duplicates)
3. Create tmux session with project name
4. Start LLMs with specialized personas
5. Send round 1 comprehensive review template
6. **Attach to the tmux session** (takes over your terminal)

**Note for macOS users**: tmux doesn't create new windows - it runs in your current terminal. The screen will change to show the 4-pane layout. This is normal!

### Session Layout

```
┌─────────────────┬─────────────────┬─────────────────┐
│ Claude          │ Codex           │ Gemini          │  70% height
│ (Architecture)  │ (Debug)         │ (Requirements)  │
├─────────────────┴─────────────────┴─────────────────┤
│                 Command Interface                    │  30% height
│                    [R1]>                             │
└──────────────────────────────────────────────────────┘
```

### Command Interface

The command pane shows current round and accepts commands:

#### LLM Commands
- `claude: <message>` - Send to Claude only
- `codex: <message>` - Send to Codex only
- `gemini: <message>` - Send to Gemini only
- `all: <message>` - Broadcast to all three

#### Control Commands
- `round` - Show current round information
- `context show` - Display context summary
- `persona reload` - Reload all personas
- `template <name>` - Switch template (round-1/round-n/final)
- `focus <level>` - Set focus (all/high/critical/ship)
- `save` - Save current state
- `help` - Show all commands
- `exit` - Exit command interface

### Direct Interaction

Click into any LLM pane to interact directly:
- Pane navigation: `Ctrl+B` then arrow keys
- Direct questions maintain full LLM capabilities
- Return to command pane (bottom) for orchestration

### Progressing Rounds

After initial reviews converge, advance to next round:

```bash
./orchestration/review.sh next
```

This will:
1. Save current round outputs
2. Build context including previous reviews
3. Apply round-appropriate template (narrower focus)
4. Restart LLMs with new context
5. Continue review process

### Round Progression

| Round | Focus | Template | Description |
|-------|-------|----------|-------------|
| 1 | All Issues | round-1.md | Comprehensive initial review |
| 2 | Critical & High | round-n.md | Address major concerns |
| 3 | Critical Only | round-n.md | Final critical issues |
| 4+ | Ship-Blocking | final.md | Ship/No-ship decision |

### Other Commands

```bash
# Check session status
./orchestration/review.sh status

# Reattach to existing session
./orchestration/review.sh attach

# Reset for new review
./orchestration/review.sh reset
```

## File Structure

```
project/
├── orchestration/
│   ├── review.sh              # Main orchestrator
│   ├── command_parser.sh      # Command interface
│   ├── README.md             # This file
│   └── defaults/
│       ├── config.sh         # Default configuration
│       ├── personas/         # Default personas
│       └── templates/        # Default templates
├── review/
│   ├── round-1/
│   │   ├── context.md        # Source code context
│   │   ├── claude-prompt.md  # Processed prompt
│   │   ├── claude.log        # Claude output
│   │   ├── codex.log         # Codex output
│   │   └── gemini.log        # Gemini output
│   ├── round-2/
│   │   ├── previous-reviews.md  # Round 1 reviews
│   │   └── ...
│   ├── current-round.txt     # Current round number
│   └── session.lock          # Prevents duplicates
└── src/                      # Your source code
```

## Example Workflow

### 1. First-Time Setup
```bash
$ ./orchestration/review.sh setup
[INFO] Installing default configuration...
✓ Default configuration installed at ~/.review/

$ ./orchestration/review.sh check
[INFO] Running pre-flight checks...

✓ tmux available (tmux 3.3a)
✓ Claude CLI authenticated
✓ Codex CLI authenticated
✓ Gemini CLI authenticated

✓ All checks passed. Ready to review!
```

### 2. Start Review Session
```bash
$ ./orchestration/review.sh start
═══════════════════════════════════════════════════════
        Starting Review Session for: nano-graphrag
═══════════════════════════════════════════════════════

[INFO] Running pre-flight checks...
✓ All checks passed. Ready to review!

[INFO] Initializing session...
✓ tmux layout created with 4 panes

[INFO] Starting all LLMs for round 1
[INFO] Establishing personas...
✓ Claude persona established
✓ Codex persona established
✓ Gemini persona established
✓ All LLMs started with personas

[INFO] Sending review prompts for round 1
✓ Review prompts sent

✓ Review session started (Round 1)
[INFO] Session: review-nano-graphrag
[INFO] Logs: review/round-1/
```

### 3. Orchestrate Reviews
```
[R1]> all: Focus on the authentication module for security issues
Broadcasting to all LLMs: Focus on the authentication module

[R1]> round
═══════════════════════════════════════════════════════
                    Round Information
═══════════════════════════════════════════════════════

  Current Round: 1 / 3
  Severity Focus: All Issues
  
  Round Guidelines:
    - Comprehensive review of all code
    - All severity levels reported
    - Focus on your specialty area

[R1]> claude: Can you elaborate on the coupling issue in auth.py?
Sending to Claude (Architecture): Can you elaborate on the coupling issue
```

### 4. Progress to Next Round
```bash
$ ./orchestration/review.sh next
[INFO] Advancing to Round 2
[INFO] Building review context from round 1
✓ Advanced to Round 2

# In command interface:
[R2]> context show
═══════════════════════════════════════════════════════
                 Context Summary - Round 2
═══════════════════════════════════════════════════════

  Source files: 15
  Context size: 48KB
  Previous reviews: 32KB
  Severity focus: Critical and High
  Template: round-n
```

### 5. Final Ship Decision
```bash
$ ./orchestration/review.sh next
[INFO] Advancing to Round 4
✓ Review prompts sent

# LLMs now provide SHIP/NO-SHIP recommendations
```

## Customization

### Modifying File Patterns

Edit `~/.review/config.sh`:
```bash
DEFAULT_FILE_PATTERNS="-name '*.py' -o -name '*.js' -o -name '*.go'"
DEFAULT_MAX_FILES=30
```

### Adjusting Round Progression

Edit severity thresholds in `~/.review/config.sh`:
```bash
ROUND_1_SEVERITY="All"
ROUND_2_SEVERITY="Critical and High"
ROUND_3_SEVERITY="Critical only"
FINAL_SEVERITY="Ship-blocking only"
```

### Custom LLM Commands

Modify `start_llm_in_pane()` in review.sh:
```bash
# Example: Add custom parameters
start_llm_in_pane 0 "Claude" "claude --max-tokens 4000" "$round_dir/claude.log"
```

## Troubleshooting

### Pre-flight Check Failures
```
✗ Claude CLI not found
```
**Solution**: Install and authenticate the missing CLI tool

### Session Already Exists
```
[ERROR] Active session exists. Use 'review attach' or 'review reset'
```
**Solution**: 
- Attach: `./orchestration/review.sh attach`
- Reset: `./orchestration/review.sh reset`

### Personas Not Loading
```
[WARN] Persona file not found: ~/.review/personas/claude.md
```
**Solution**: Run `./orchestration/review.sh setup` to install defaults

### Empty Context
```
No context file found
```
**Solution**: Ensure you have source files matching the configured patterns

### tmux Basics for macOS Users

tmux is a terminal multiplexer - it creates multiple "panes" within a single terminal window.

#### Key Concepts:
- **Session**: A tmux workspace containing multiple panes
- **Panes**: Split sections of your terminal (like split view)
- **Attach**: Connect to a tmux session (takes over your terminal)
- **Detach**: Disconnect from tmux (session keeps running in background)

#### Essential Controls:
- **Switch panes**: `Ctrl+B` then arrow keys
- **Detach session**: `Ctrl+B` then `D` (returns to normal terminal)
- **Scroll in pane**: `Ctrl+B` then `[`, then arrow keys (press `q` to exit scroll)
- **Kill pane**: `Ctrl+B` then `x` (confirm with `y`)

#### Common Issues:
- **"Nothing happens"**: You're already attached! The terminal IS the tmux session
- **"Can't see panes"**: Make terminal window larger
- **"Stuck in tmux"**: Press `Ctrl+B` then `D` to detach
- **"Lost my session"**: Run `./orchestration/review.sh attach` to reconnect

## Tips

1. **Let Personas Guide**: Each LLM will naturally focus on their expertise area
2. **Use Rounds Wisely**: Don't rush through rounds - let discussions converge
3. **Direct vs Orchestrated**: 
   - Orchestrate for broad questions
   - Direct for deep dives
4. **Save Frequently**: Use `save` command at important decision points
5. **Monitor Logs**: Review files in `review/round-N/` for full context

## Advanced Usage

### Custom Session Names
```bash
SESSION_PREFIX="custom" ./orchestration/review.sh start
```

### Headless Operation
```bash
# Start without attaching
tmux new-session -d -s review-session
./orchestration/review.sh start

# Check status remotely
./orchestration/review.sh status
```

### Parallel Projects
Different projects automatically get different session names based on directory.

## Limitations

- Maximum context size limited by LLM token limits
- No automatic synthesis of reviews
- Requires manual progression through rounds
- macOS only (Linux possible with minor mods)
- No automatic code fixing

## Support

For issues:
1. Check pre-flight: `./orchestration/review.sh check`
2. Review logs in `review/round-N/`
3. Verify tmux session: `tmux ls`
4. Reset if needed: `./orchestration/review.sh reset`