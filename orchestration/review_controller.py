#!/usr/bin/env python3
"""
Interactive controller for the Multi-LLM Review Orchestrator
Provides command interface to control all LLM sessions
"""

import iterm2
import asyncio
import sys
import os
from pathlib import Path
from typing import Optional, Dict
import readline  # For better input handling

class ReviewController:
    """Interactive controller for managing review sessions"""
    
    def __init__(self):
        self.sessions: Dict[str, iterm2.Session] = {}
        self.round = 1
        self.project_name = Path.cwd().name
        self.review_home = Path.home() / ".review"
        self.templates_dir = self.review_home / "templates"
        self.personas_dir = self.review_home / "personas"
        
    async def find_sessions(self, app: iterm2.App):
        """Find all review-related sessions by window title"""
        print("Locating LLM sessions...")
        
        for window in app.windows:
            title = await window.async_get_title()
            
            if "Claude" in title:
                self.sessions['claude'] = window.current_tab.current_session
                print(f"  ✓ Found Claude session")
            elif "Codex" in title:
                self.sessions['codex'] = window.current_tab.current_session
                print(f"  ✓ Found Codex session")
            elif "Gemini" in title:
                self.sessions['gemini'] = window.current_tab.current_session
                print(f"  ✓ Found Gemini session")
    
    async def send_to_session(self, name: str, text: str, execute: bool = True):
        """Send text to a specific session"""
        if name not in self.sessions:
            print(f"  ✗ Session '{name}' not found")
            return False
            
        session = self.sessions[name]
        if execute and not text.endswith('\n'):
            text += '\n'
        
        await session.async_send_text(text)
        return True
    
    async def cmd_all(self, text: str):
        """Send text to all LLM sessions"""
        print(f"Sending to all LLMs: {text[:50]}...")
        sent_count = 0
        for name in ['claude', 'codex', 'gemini']:
            if await self.send_to_session(name, text):
                sent_count += 1
        print(f"  → Sent to {sent_count} sessions")
    
    async def cmd_single(self, name: str, text: str):
        """Send text to a single LLM session"""
        print(f"Sending to {name}: {text[:50]}...")
        if await self.send_to_session(name, text):
            print(f"  → Sent successfully")
    
    async def cmd_status(self):
        """Show status of all sessions"""
        print(f"\n╔══════════════════════════════════════╗")
        print(f"║         Review Status                ║")
        print(f"╠══════════════════════════════════════╣")
        print(f"║ Project: {self.project_name[:20]:<20} ║")
        print(f"║ Round:   {self.round:<20} ║")
        print(f"╠══════════════════════════════════════╣")
        print(f"║ Sessions:                            ║")
        for name in ['claude', 'codex', 'gemini']:
            status = "✓ Connected" if name in self.sessions else "✗ Not found"
            print(f"║   {name.capitalize():<10} {status:<18} ║")
        print(f"╚══════════════════════════════════════╝\n")
    
    async def cmd_round(self):
        """Show current round"""
        print(f"Current round: {self.round}")
    
    async def cmd_next(self):
        """Progress to next round"""
        self.round += 1
        print(f"Progressing to round {self.round}")
        
        # Load round template
        template_file = "round-n.md" if self.round > 1 else "round-1.md"
        template_path = self.templates_dir / template_file
        
        if template_path.exists():
            print(f"Loading template: {template_file}")
            template = template_path.read_text()
            
            # Substitute round number
            template = template.replace("[ROUND_NUMBER]", str(self.round))
            
            # Send to all LLMs
            await self.cmd_all(f"# Starting Round {self.round}")
            await self.cmd_all(template)
        else:
            print(f"Warning: Template {template_file} not found")
    
    async def cmd_load(self, filename: str):
        """Load and send a file to all LLMs"""
        filepath = Path(filename)
        if not filepath.exists():
            print(f"File not found: {filename}")
            return
            
        print(f"Loading file: {filename}")
        content = filepath.read_text()
        await self.cmd_all(content)
    
    async def cmd_help(self):
        """Show help message"""
        help_text = """
╔═══════════════════════════════════════════════════════════════╗
║                    Review Controller Commands                 ║
╠═══════════════════════════════════════════════════════════════╣
║ all <text>      Send text to all LLMs                        ║
║ claude <text>   Send to Claude only                          ║
║ codex <text>    Send to Codex only                           ║
║ gemini <text>   Send to Gemini only                          ║
║ status          Show session status                          ║
║ round           Show current round                           ║
║ next            Progress to next round                       ║
║ load <file>     Load and send file to all LLMs              ║
║ help            Show this help                              ║
║ exit            Exit controller                             ║
╚═══════════════════════════════════════════════════════════════╝
"""
        print(help_text)
    
    async def run_interactive(self, connection: iterm2.Connection):
        """Run the interactive command loop"""
        app = await iterm2.async_get_app(connection)
        
        # Find existing sessions
        await self.find_sessions(app)
        
        print("\n═══════════════════════════════════════════════════════════════")
        print(f"           Review Controller - Round {self.round}")
        print("═══════════════════════════════════════════════════════════════")
        print(f"Project: {self.project_name}")
        print("\nType 'help' for commands, 'exit' to quit\n")
        
        # Command loop
        while True:
            try:
                # Get input
                cmd_line = input("review> ").strip()
                
                if not cmd_line:
                    continue
                
                # Parse command
                parts = cmd_line.split(maxsplit=1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                
                # Execute command
                if cmd == "exit":
                    print("Exiting controller...")
                    break
                elif cmd == "all":
                    if args:
                        await self.cmd_all(args)
                    else:
                        print("Usage: all <text>")
                elif cmd in ["claude", "codex", "gemini"]:
                    if args:
                        await self.cmd_single(cmd, args)
                    else:
                        print(f"Usage: {cmd} <text>")
                elif cmd == "status":
                    await self.cmd_status()
                elif cmd == "round":
                    await self.cmd_round()
                elif cmd == "next":
                    await self.cmd_next()
                elif cmd == "load":
                    if args:
                        await self.cmd_load(args)
                    else:
                        print("Usage: load <filename>")
                elif cmd == "help":
                    await self.cmd_help()
                else:
                    print(f"Unknown command: {cmd}")
                    print("Type 'help' for available commands")
                    
            except KeyboardInterrupt:
                print("\n\nUse 'exit' to quit")
                continue
            except EOFError:
                print("\nExiting...")
                break
            except Exception as e:
                print(f"Error: {e}")

async def main(connection: iterm2.Connection):
    """Main entry point"""
    controller = ReviewController()
    await controller.run_interactive(connection)

if __name__ == "__main__":
    print("iTerm2 Review Controller")
    print("Connecting to iTerm2...")
    
    # Run the controller
    iterm2.run_until_complete(main)