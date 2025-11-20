#!/usr/bin/env python3
"""
Test suite to verify cleanup command handler imports are working correctly.
This test ensures the fix for the ImportError is effective.
"""

import os
import sys
import pytest

# Add script directory to path
script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, script_dir)


class TestCleanupImports:
    """Test suite for cleanup command handler imports."""
    
    def test_import_cleanup_handlers_from_utils(self):
        """Test that cleanup handlers can be imported from utils package."""
        try:
            from utils import (
                handle_cleanup_command,
                handle_confirm_cleanup_command,
                handle_cleanup_orphans_command
            )
            
            # Verify all imports succeeded
            assert handle_cleanup_command is not None, "handle_cleanup_command is None"
            assert handle_confirm_cleanup_command is not None, "handle_confirm_cleanup_command is None"
            assert handle_cleanup_orphans_command is not None, "handle_cleanup_orphans_command is None"
            
        except ImportError as e:
            pytest.fail(f"Failed to import cleanup handlers from utils: {e}")
    
    def test_cleanup_handlers_are_callable(self):
        """Test that imported cleanup handlers are callable functions."""
        from utils import (
            handle_cleanup_command,
            handle_confirm_cleanup_command,
            handle_cleanup_orphans_command
        )
        
        assert callable(handle_cleanup_command), "handle_cleanup_command is not callable"
        assert callable(handle_confirm_cleanup_command), "handle_confirm_cleanup_command is not callable"
        assert callable(handle_cleanup_orphans_command), "handle_cleanup_orphans_command is not callable"
    
    def test_direct_import_from_command_handlers(self):
        """Test that cleanup handlers can be imported directly from command_handlers."""
        try:
            from utils.command_handlers import (
                handle_cleanup_command,
                handle_confirm_cleanup_command,
                handle_cleanup_orphans_command
            )
            
            assert handle_cleanup_command is not None
            assert handle_confirm_cleanup_command is not None
            assert handle_cleanup_orphans_command is not None
            
        except ImportError as e:
            pytest.fail(f"Failed to import cleanup handlers from command_handlers: {e}")
    
    def test_all_command_handlers_importable(self):
        """Test that all command handlers (including cleanup) can be imported together."""
        try:
            from utils import (
                handle_password_command, 
                handle_max_concurrent_command, 
                handle_set_max_archive_gb_command,
                handle_toggle_fast_download_command, 
                handle_toggle_wifi_only_command, 
                handle_toggle_transcoding_command, 
                handle_compression_timeout_command, 
                handle_help_command, 
                handle_battery_status_command, 
                handle_status_command, 
                handle_queue_command, 
                handle_cancel_password,
                handle_cancel_extraction, 
                handle_cancel_process,
                handle_cleanup_command, 
                handle_confirm_cleanup_command, 
                handle_cleanup_orphans_command
            )
            
            # Verify all handlers are imported
            handlers = [
                handle_password_command,
                handle_max_concurrent_command,
                handle_set_max_archive_gb_command,
                handle_toggle_fast_download_command,
                handle_toggle_wifi_only_command,
                handle_toggle_transcoding_command,
                handle_compression_timeout_command,
                handle_help_command,
                handle_battery_status_command,
                handle_status_command,
                handle_queue_command,
                handle_cancel_password,
                handle_cancel_extraction,
                handle_cancel_process,
                handle_cleanup_command,
                handle_confirm_cleanup_command,
                handle_cleanup_orphans_command
            ]
            
            for handler in handlers:
                assert handler is not None, f"Handler {handler.__name__ if handler else 'unknown'} is None"
                assert callable(handler), f"Handler {handler.__name__} is not callable"
            
        except ImportError as e:
            pytest.fail(f"Failed to import all command handlers: {e}")
    
    def test_utils_all_exports(self):
        """Test that cleanup handlers are in __all__ exports."""
        import utils
        
        assert hasattr(utils, '__all__'), "utils module has no __all__ attribute"
        
        required_exports = [
            'handle_cleanup_command',
            'handle_confirm_cleanup_command',
            'handle_cleanup_orphans_command'
        ]
        
        for export_name in required_exports:
            assert export_name in utils.__all__, f"{export_name} not in utils.__all__"
    
    def test_import_as_used_in_main_file(self):
        """Test imports exactly as they appear in extract-compressed-files.py."""
        try:
            # This is the exact import from the main file
            from utils import (
                handle_password_command, 
                handle_max_concurrent_command, 
                handle_set_max_archive_gb_command,
                handle_toggle_fast_download_command, 
                handle_toggle_wifi_only_command, 
                handle_toggle_transcoding_command, 
                handle_compression_timeout_command, 
                handle_help_command, 
                handle_battery_status_command, 
                handle_status_command, 
                handle_queue_command, 
                handle_cancel_password,
                handle_cancel_extraction, 
                handle_cancel_process, 
                handle_cleanup_command, 
                handle_confirm_cleanup_command, 
                handle_cleanup_orphans_command
            )
            
            # If we get here, the import succeeded
            assert True
            
        except ImportError as e:
            pytest.fail(f"Failed to import as in main file: {e}")
    
    def test_function_signatures(self):
        """Test that cleanup handlers have the expected function signatures."""
        from utils import (
            handle_cleanup_command,
            handle_confirm_cleanup_command,
            handle_cleanup_orphans_command
        )
        
        import inspect
        
        # Check handle_cleanup_command signature
        sig = inspect.signature(handle_cleanup_command)
        params = list(sig.parameters.keys())
        assert 'event' in params, "handle_cleanup_command missing 'event' parameter"
        
        # Check handle_confirm_cleanup_command signature
        sig = inspect.signature(handle_confirm_cleanup_command)
        params = list(sig.parameters.keys())
        assert 'event' in params, "handle_confirm_cleanup_command missing 'event' parameter"
        
        # Check handle_cleanup_orphans_command signature
        sig = inspect.signature(handle_cleanup_orphans_command)
        params = list(sig.parameters.keys())
        assert 'event' in params, "handle_cleanup_orphans_command missing 'event' parameter"
    
    def test_functions_are_coroutines(self):
        """Test that cleanup handlers are async functions (coroutines)."""
        from utils import (
            handle_cleanup_command,
            handle_confirm_cleanup_command,
            handle_cleanup_orphans_command
        )
        
        import inspect
        
        assert inspect.iscoroutinefunction(handle_cleanup_command), \
            "handle_cleanup_command is not an async function"
        assert inspect.iscoroutinefunction(handle_confirm_cleanup_command), \
            "handle_confirm_cleanup_command is not an async function"
        assert inspect.iscoroutinefunction(handle_cleanup_orphans_command), \
            "handle_cleanup_orphans_command is not an async function"


def test_no_import_error_on_module_load():
    """Test that simply importing the main module doesn't raise ImportError."""
    import importlib
    import sys
    
    # Import utils module
    if 'utils' in sys.modules:
        utils = importlib.reload(sys.modules['utils'])
    else:
        import utils as utils_module
        utils = utils_module
    
    # Verify cleanup handlers are accessible
    assert hasattr(utils, 'handle_cleanup_command')
    assert hasattr(utils, 'handle_confirm_cleanup_command')
    assert hasattr(utils, 'handle_cleanup_orphans_command')


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
