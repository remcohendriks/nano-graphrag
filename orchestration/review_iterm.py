#!/usr/bin/env python3
"""
Multi-LLM Code Review Orchestrator using iTerm2 Python API
Manages Claude, Codex, and Gemini in separate windows with reliable text sending
"""

import iterm2
import asyncio
import os
import sys
import json
from pathlib import Path
from typing import Dict, Optional

# Configuration
REVIEW_HOME = Path.home() / ".review"
PERSONAS_DIR = REVIEW_HOME / "personas"
TEMPLATES_DIR = REVIEW_HOME / "templates"

class ReviewSession:
    """Manages a review session with multiple LLM windows"""
    
    def __init__(self):
        self.sessions: Dict[str, iterm2.Session] = {}
        self.round = 1
        self.project_name = Path.cwd().name
        self.round_dir = Path.cwd() / "review" / f"round-{self.round}"
        
    async def create_window(self, connection: iterm2.Connection, name: str, title: str, command: str = None) -> iterm2.Session:
        """Create a new iTerm2 window and return its session"""
        # Create new window with a command to ensure session exists
        if command:
            # Start with the command directly
            window = await iterm2.Window.async_create(connection, command=command)
        else:
            # Start with bash to ensure we have a session
            window = await iterm2.Window.async_create(connection, command="/bin/bash")
        
        if window is None:
            print(f"  ✗ Failed to create window for {name}")
            return None
        
        try:
            await window.async_set_title(title)
        except:
            pass  # Title setting might fail but that's ok
        
        # Try multiple methods to get the session
        session = None
        max_attempts = 10
        
        for attempt in range(max_attempts):
            await asyncio.sleep(0.5)
            
            # Method 1: Try current_tab
            try:
                if window.current_tab and window.current_tab.current_session:
                    session = window.current_tab.current_session
                    break
            except:
                pass
            
            # Method 2: Try tabs list
            try:
                tabs = window.tabs
                if tabs and len(tabs) > 0:
                    if tabs[0].current_session:
                        session = tabs[0].current_session
                        break
                    # Try sessions list
                    sessions = tabs[0].sessions
                    if sessions and len(sessions) > 0:
                        session = sessions[0]
                        break
            except:
                pass
            
            # Method 3: Get app and search for our window
            try:
                app = await iterm2.async_get_app(connection)
                for w in app.windows:
                    if w.window_id == window.window_id:
                        if w.current_tab and w.current_tab.current_session:
                            session = w.current_tab.current_session
                            break
                        if w.tabs and len(w.tabs) > 0:
                            if w.tabs[0].current_session:
                                session = w.tabs[0].current_session
                                break
            except:
                pass
                
            if session:
                break
        
        if session:
            # Store session reference
            self.sessions[name] = session
            print(f"  ✓ Session created for {name}")
        else:
            print(f"  ✗ Could not get session for {name} after {max_attempts} attempts")
        
        return session
    
    async def send_to_llm(self, name: str, text: str, execute: bool = True):
        """Send text to a specific LLM session"""
        if name not in self.sessions:
            print(f"Error: Session '{name}' not found")
            return
            
        session = self.sessions[name]
        # Add newline if we want to execute the command
        if execute and not text.endswith('\n'):
            text += '\n'
        await session.async_send_text(text)
    
    async def send_to_all(self, text: str, execute: bool = True):
        """Send text to all LLM sessions"""
        for name in ['claude', 'codex', 'gemini']:
            if name in self.sessions:
                await self.send_to_llm(name, text, execute)
    
    async def start_llm(self, connection: iterm2.Connection, name: str, command: str, title: str, persona_file: str):
        """Start an LLM in a new window"""
        print(f"Starting {title}...")
        
        # Create window with the LLM command directly
        session = await self.create_window(connection, name, title, command=command)
        
        if not session:
            print(f"  ✗ Failed to get session for {name}")
            return
        
        # Wait a moment for CLI to start
        await asyncio.sleep(2)
        
        # Load and send persona if it exists
        persona_path = PERSONAS_DIR / persona_file
        if persona_path.exists():
            print(f"  Loading persona from {persona_file}")
            persona = persona_path.read_text()
            # Send persona (this will be typed into the CLI)
            await session.async_send_text(persona)
            await session.async_send_text("\n")
        else:
            print(f"  Note: Persona file {persona_file} not found")
    
    async def start_controller(self, connection: iterm2.Connection):
        """Start the controller window"""
        print("Starting Controller...")
        
        # Create controller window
        session = await self.create_window(connection, 'controller', 'Review Controller')
        
        if not session:
            print("  ✗ Failed to get session for controller")
            return
            
        # Start a bash shell and display info
        info_text = f"""
echo '═══════════════════════════════════════════════════════════════'
echo '           Review Controller - Round {self.round}'
echo '═══════════════════════════════════════════════════════════════'
echo 'Project: {self.project_name}'
echo ''
echo 'Commands:'
echo '  all <text>     - Send to all LLMs'
echo '  claude <text>  - Send to Claude only'
echo '  codex <text>   - Send to Codex only'
echo '  gemini <text>  - Send to Gemini only'
echo '  help           - Show this help'
echo ''
echo 'Note: Use the separate controller script to send commands'
echo ''
"""
        await session.async_send_text(info_text)
    
    async def setup_review_session(self, connection: iterm2.Connection):
        """Set up the complete review session"""
        # Create review directory
        self.round_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"Setting up review session for {self.project_name}")
        print(f"Round: {self.round}")
        print("")
        
        # Start each LLM in its own window
        await self.start_llm(
            connection, 
            'claude', 
            'claude',
            'Claude - Architecture Review',
            'claude.md'
        )
        
        await self.start_llm(
            connection,
            'codex',
            'codex', 
            'Codex - Debug Review',
            'codex.md'
        )
        
        await self.start_llm(
            connection,
            'gemini',
            'gemini',
            'Gemini - Requirements Review', 
            'gemini.md'
        )
        
        # Start controller
        await self.start_controller(connection)
        
        print("")
        print("✓ Window creation completed!")
        print("")
        
        # Only test if we have sessions
        if self.sessions:
            print("Quick test - sending 'hello' to active LLMs...")
            await asyncio.sleep(2)
            
            # Test sending to all active sessions
            for name, session in self.sessions.items():
                if session:
                    try:
                        await session.async_send_text("# Test message: hello from orchestrator\n")
                        print(f"  ✓ Sent test to {name}")
                    except:
                        print(f"  ✗ Failed to send to {name}")
        
        print("✓ Test message sent")
        print("")
        print("Review session ready!")
        print("Use the Controller window to manage the review")

async def main(connection: iterm2.Connection):
    """Main entry point"""
    session = ReviewSession()
    await session.setup_review_session(connection)
    
    # Keep the connection alive to maintain control
    # In a real implementation, this would run a command loop
    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    print("Starting iTerm2 Review Orchestrator...")
    print("Make sure iTerm2 is running and Python API is enabled")
    print("(iTerm2 > Preferences > General > Magic > Enable Python API)")
    print("")
    
    # Check if required directories exist
    if not REVIEW_HOME.exists():
        print(f"Creating {REVIEW_HOME}...")
        REVIEW_HOME.mkdir(parents=True)
        PERSONAS_DIR.mkdir(exist_ok=True)
        TEMPLATES_DIR.mkdir(exist_ok=True)
        print("Note: Copy persona and template files to ~/.review/")
    
    # Run the iTerm2 script
    iterm2.run_until_complete(main)