#!/usr/bin/env python3
"""Test iTerm2 Python API connection"""

import iterm2
import asyncio

async def main(connection):
    """Test creating a window"""
    print("Connected to iTerm2!")
    print("Creating a test window...")
    
    # Try to create a window
    window = await iterm2.Window.async_create(connection)
    if window:
        print("✓ Window created successfully!")
        await window.async_set_title("Test Window")
        
        # Wait for window to be ready
        await asyncio.sleep(0.5)
        
        # Get the session
        tabs = window.tabs
        if tabs and len(tabs) > 0:
            session = tabs[0].current_session
            if session:
                # Send some text
                await session.async_send_text("echo 'iTerm2 Python API is working!'\n")
                print("✓ Command sent successfully!")
            else:
                print("✗ No session found in tab")
        else:
            print("✗ No tabs found in window")
        
        print("✓ Text sent to window")
        print("\nTest completed successfully!")
    else:
        print("✗ Failed to create window")

if __name__ == "__main__":
    print("Testing iTerm2 Python API connection...")
    print("\nIMPORTANT: Make sure you have enabled the Python API:")
    print("  iTerm2 → Preferences → General → Magic → Enable Python API")
    print("\nAttempting connection...")
    
    iterm2.run_until_complete(main)