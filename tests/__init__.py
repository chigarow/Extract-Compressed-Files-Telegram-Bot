# Test package for extract-compressed-files.py
"""
Test suite for the modular extract-compressed-files application.

This package contains comprehensive tests for all modules including:
- Queue management with concurrency control
- Telegram operations and file handling
- Cache management and persistence  
- Command processing and validation
- Media processing and conversion
- File operations and archive extraction
- Network monitoring and connection handling
- Progress tracking and rate limiting
- Error handling and retry mechanisms
"""

# Add parent directory to Python path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))