# JIRA Ticket: Multi-LLM Code Review Orchestrator for macOS

## Summary
Build a minimalist CLI tool that orchestrates code reviews from three LLMs (Claude, Codex, Gemini) using tmux to manage interactive sessions with both direct and orchestrated control, with specialized reviewer personas and round-based review templates.

## Description

### Background
We need a local tool to streamline code review workflows using multiple LLMs. Each LLM has different strengths (Claude: architecture, Codex: debugging, Gemini: requirements), and we want to leverage all three in parallel while maintaining full control over the process.

### Problem Statement
Currently, managing three separate LLM sessions for code review is manual and tedious. We need to:
- Manually copy context to each LLM
- Switch between three different terminals
- Manually track review rounds and feedback
- Rebuild context for each subsequent round
- Manually set up each reviewer's focus area

### Proposed Solution
A tmux-based orchestrator that:
1. Opens three interactive LLM sessions with specialized personas
2. Provides a command pane for orchestrated control
3. Automatically manages context and review rounds with templates
4. Captures all output while maintaining interactivity

## Acceptance Criteria

### Core Functionality
- [ ] Tool creates a tmux session with 4 panes (3 LLMs + 1 command)
- [ ] Each LLM starts with a persona prompt defining their review role
- [ ] Each LLM runs in interactive mode and can be controlled directly
- [ ] Command pane can send commands to any/all LLMs via tmux send-keys
- [ ] All output is automatically logged to files
- [ ] Support for multiple review rounds with progressive templates

### Startup Procedure
- [ ] Check prerequisites (tmux installed, LLM CLIs authenticated)
- [ ] Create review directory structure if not exists
- [ ] Load configuration (personas, templates)
- [ ] Initialize tmux session with proper layout
- [ ] Start LLM CLIs in interactive mode
- [ ] Send persona prompts to establish reviewer roles
- [ ] Load and send round-appropriate review template
- [ ] Begin logging all panes

### Commands
- [ ] `review start` - Initialize first review round with personas
- [ ] `review next` - Progress to next round with accumulated context
- [ ] `review status` - Check current round and session state
- [ ] `review attach` - Reattach to existing tmux session
- [ ] `review reset` - Clean state for new review cycle

### Persona & Template Management
- [ ] Each LLM receives a persona prompt on startup
- [ ] Round 1 uses comprehensive review template
- [ ] Round 2+ uses convergence-focused template
- [ ] Templates stored in `~/.review/templates/`
- [ ] Personas stored in `~/.review/personas/`

## Technical Requirements

### Dependencies
- tmux (assumed installed via Homebrew)
- Claude CLI (authenticated)
- Codex CLI (authenticated)
- Gemini CLI (authenticated)
- Bash 5.0+

### Configuration Structure
```
~/.review/
├── personas/
│   ├── claude.md    # Architecture reviewer persona
│   ├── codex.md     # Debug specialist persona
│   └── gemini.md    # Requirements analyst persona
├── templates/
│   ├── round-1.md   # Comprehensive review template
│   ├── round-n.md   # Convergence review template
│   └── final.md     # Ship/no-ship decision template
└── config.sh        # Tool configuration
```

### Project Structure
```
project/
├── review/
│   ├── round-1/
│   │   ├── context.md      # Built context for round
│   │   ├── claude.log      # Complete session log
│   │   ├── codex.log       # Complete session log
│   │   └── gemini.log      # Complete session log
│   ├── current-round.txt   # "1", "2", etc.
│   └── session.lock        # Prevent multiple sessions
├── src/                    # Code to review
└── requirements.md         # Project requirements
```

## Implementation Details

### Startup Procedure (`review start`)

```bash
1. Pre-flight checks:
   - Verify tmux installed
   - Check LLM CLIs authenticated (claude --version, etc.)
   - Check for existing session (session.lock)
   - Create review directory structure

2. Initialize tmux session:
   - Create session named "review-[project]"
   - Split into 4 panes (3 top, 1 bottom)
   - Set pane titles (Claude, Codex, Gemini, Command)
   - Enable logging for each pane

3. Start LLM CLIs:
   - Send "claude" to pane 0.0
   - Send "codex" to pane 0.1  
   - Send "gemini" to pane 0.2
   - Wait for prompts to be ready

4. Establish personas:
   - Send persona prompt from ~/.review/personas/claude.md to Claude
   - Send persona prompt from ~/.review/personas/codex.md to Codex
   - Send persona prompt from ~/.review/personas/gemini.md to Gemini
   - Wait for acknowledgment

5. Build and send review context:
   - Build context.md with code + requirements
   - Merge with round-1 template
   - Send to all three LLMs
   - Start command parser in bottom pane

6. Begin review session:
   - Show status message
   - Enable command input
```

### Persona Prompts

#### `~/.review/personas/claude.md`
```markdown
You are a Senior Software Architect conducting a code review. Your expertise:
- System design and architectural patterns
- Code organization and modularity
- Design patterns and best practices
- Technical debt identification
- Scalability and maintainability concerns
- Integration and interface design

Focus on the big picture while noting specific implementation concerns.
Acknowledge this role with "Architect reviewer ready."
```

#### `~/.review/personas/codex.md`
```markdown
You are a Debug Specialist and Security Expert conducting a code review. Your expertise:
- Finding bugs and logic errors
- Identifying edge cases and race conditions
- Security vulnerability detection
- Performance bottlenecks
- Error handling gaps
- Test coverage analysis
- Memory and resource management

Hunt for bugs others might miss. Be specific about reproduction steps.
Acknowledge this role with "Debug reviewer ready."
```

#### `~/.review/personas/gemini.md`
```markdown
You are a Requirements Analyst and QA Lead conducting a code review. Your expertise:
- Requirements compliance verification
- Acceptance criteria validation
- Documentation completeness
- Test coverage assessment
- User experience implications
- API contract adherence
- Production readiness

Ensure the implementation fully satisfies specifications.
Acknowledge this role with "Requirements reviewer ready."
```

### Review Templates

#### `~/.review/templates/round-1.md`
```markdown
# Code Review Request - Round 1 (Comprehensive)

## Your Task
Conduct a thorough review of the codebase below. As the [ROLE] reviewer, focus on your areas of expertise while noting any other concerns.

## Code Context
[PROJECT_REQUIREMENTS]
[SOURCE_CODE]

## Review Instructions
Provide a comprehensive review covering:
1. Critical issues (must fix before deployment)
2. High priority issues (should fix soon)
3. Medium priority suggestions (improvements)
4. Low priority notes (nice to have)
5. Positive observations (well-done aspects)

Be specific with:
- File names and line numbers
- Clear reproduction steps for bugs
- Concrete fix recommendations
- Code examples where helpful

## Output Format
Structure your review with clear sections and priorities.
Use markdown formatting for readability.
```

#### `~/.review/templates/round-n.md`
```markdown
# Code Review Request - Round [ROUND_NUMBER] (Convergence)

## Previous Review Context
[PREVIOUS_REVIEWS]

## Updated Code
[SOURCE_CODE_DIFF]

## Your Task - Round [ROUND_NUMBER]
This is round [ROUND_NUMBER] of [MAX_ROUNDS]. Focus on convergence:

1. Verify your previous concerns were addressed
2. Check if fixes introduced new issues
3. [IF_ROUND_2] Focus only on Critical and High priority issues
4. [IF_ROUND_3] Only flag ship-blocking issues
5. [IF_FINAL] Provide SHIP or NO-SHIP recommendation

## What Changed
[IMPLEMENTATION_NOTES]

## Review Scope for This Round
- Previously flagged issues: [COUNT]
- Issues marked fixed: [COUNT]
- New code sections: [LIST]

Only raise new issues if they are severity level [SEVERITY_THRESHOLD] or higher.
```

### Round Kickoff Procedures

#### Round 1 Kickoff
```bash
kickoff_round_1() {
  # Build context from scratch
  context=$(build_base_context)  # Code + requirements
  
  # Load round 1 template
  template=$(cat ~/.review/templates/round-1.md)
  
  # Substitute placeholders
  final_prompt=$(echo "$template" | 
    sed "s/\[PROJECT_REQUIREMENTS\]/$requirements/g" |
    sed "s/\[SOURCE_CODE\]/$code/g" |
    sed "s/\[ROLE\]/Architecture/g")  # Per LLM
  
  # Send to all LLMs
  for pane in 0.0 0.1 0.2; do
    tmux send-keys -t review:$pane "$final_prompt" Enter
  done
}
```

#### Round N Kickoff
```bash
kickoff_round_n() {
  round=$1
  
  # Load previous reviews
  prev_reviews=$(cat review/round-$((round-1))/*.log)
  
  # Build incremental context
  context=$(build_incremental_context $round)
  
  # Load round-n template
  template=$(cat ~/.review/templates/round-n.md)
  
  # Determine severity threshold
  case $round in
    2) severity="Critical or High" ;;
    3) severity="Critical only" ;;
    *) severity="Ship-blocking only" ;;
  esac
  
  # Substitute placeholders
  final_prompt=$(echo "$template" |
    sed "s/\[ROUND_NUMBER\]/$round/g" |
    sed "s/\[PREVIOUS_REVIEWS\]/$prev_reviews/g" |
    sed "s/\[SEVERITY_THRESHOLD\]/$severity/g")
  
  # Send to all LLMs
  for pane in 0.0 0.1 0.2; do
    tmux send-keys -t review:$pane "$final_prompt" Enter
  done
}
```

### Command Parser Enhancement
```bash
# Additional commands for template management
> persona reload          # Reload personas for all LLMs
> template round-1       # Switch to round 1 template
> template final         # Switch to final decision template
> context show           # Display current context size/summary
> round                  # Show current round number
```

## User Workflow

### Initial Setup (One-time)
```bash
# Install and configure
$ brew install tmux
$ review setup
Creating ~/.review directory...
Installing default personas...
Installing review templates...
Setup complete.

# Verify LLM authentication
$ review check
✓ Claude CLI authenticated
✓ Codex CLI authenticated  
✓ Gemini CLI authenticated
Ready to review!
```

### Review Workflow

1. **Start Initial Review**
   ```bash
   $ review start
   [Pre-flight checks...]
   ✓ tmux available
   ✓ LLMs authenticated
   ✓ No existing session
   
   [Initializing session...]
   Creating tmux session 'review-myproject'...
   Starting LLM CLIs...
   
   [Establishing personas...]
   Claude: "Architect reviewer ready."
   Codex: "Debug reviewer ready."
   Gemini: "Requirements reviewer ready."
   
   [Loading round 1 template...]
   Context size: 45KB
   Sending comprehensive review request...
   
   [Session ready]
   You can now:
   - Click any LLM pane to interact directly
   - Use command pane for orchestration
   - Type 'help' for commands
   ```

2. **Monitor and Interact**
   - Watch reviews generate in real-time
   - Click into any pane for direct questions
   - Use command pane for orchestrated queries

3. **Progress to Next Round**
   ```bash
   $ review next
   Saving round 1 outputs...
   
   [Building round 2 context...]
   Including 3 previous reviews (12KB)
   Updated code diff: 8 files changed
   
   [Loading round 2 template...]
   Focus: Critical and High priority only
   Sending convergence review request...
   
   Round 2 started.
   ```

4. **Final Round**
   ```bash
   $ review next
   [Loading final template...]
   This is the ship decision round.
   Reviewers will provide SHIP/NO-SHIP recommendation.
   ```

## Example Session Transcript

```bash
# Round 1 - Comprehensive review with personas
$ review start
[Session initializes with personas]

# Claude (Architecture focus)
"Reviewing architecture... I see concerning coupling between auth and database layers..."

# Codex (Debug focus)  
"Scanning for bugs... Found potential race condition in user creation at line 145..."

# Gemini (Requirements focus)
"Checking requirements compliance... Missing required audit logging for auth events..."

# Command pane interaction
> all: How severe are these issues for MVP launch?

# Round 2 - Convergence focus
$ review next
[Previous reviews included in context]

# Claude
"Checking my previous concerns... The coupling issue was partially addressed but..."

# All reviewers working toward convergence
```

## Definition of Done
- [ ] Startup procedure with pre-flight checks
- [ ] Persona prompts establish reviewer roles
- [ ] Round templates guide review focus
- [ ] Progressive convergence through rounds
- [ ] All acceptance criteria met
- [ ] README with setup and usage instructions
- [ ] Template customization guide

## Notes
- Personas establish expertise focus but don't prevent holistic review
- Templates enforce convergence - each round narrows scope
- Round 1 is comprehensive, Round 2+ focuses on resolution
- Final round is binary ship/no-ship decision
- Keep templates customizable but provide good defaults