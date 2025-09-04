#!/usr/bin/env python
"""
Development convenience script to run the Code Scope MCP server.
"""
import sys
import os
import traceback

# Add src directory to path
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
sys.path.insert(0, src_path)

try:
    from code_scope_mcp.server import main

    if __name__ == "__main__":
        print("Starting Code Scope MCP server...", file=sys.stderr)
        print(f"Added path: {src_path}", file=sys.stderr)
        main()
except ImportError as e:
    print(f"Import Error: {e}", file=sys.stderr)
    print(f"Current sys.path: {sys.path}", file=sys.stderr)
    print("Traceback:", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
except Exception as e:
    print(f"Error starting server: {e}", file=sys.stderr)
    print("Traceback:", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
