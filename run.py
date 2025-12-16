#!/usr/bin/env python3
# run.py - develop entypoint
import sys
import os

# Add src to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from kc_session_manager.main import main

if __name__ == "__main__":
    sys.exit(main())