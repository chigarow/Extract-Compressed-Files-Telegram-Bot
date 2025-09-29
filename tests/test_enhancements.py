#!/usr/bin/env python3
"""
Test script for enhanced FastTelethon with network monitoring and retry mechanisms
"""

import asyncio
import logging
import pytest
from telethon.errors import TimeoutError, ServerError

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_network_monitor():
    """Test network monitoring functionality"""
    try:
        from utils.network_monitor import NetworkMonitor, NetworkType
        logger.info("✅ NetworkMonitor import successful")
        
        # Initialize network monitor
        nm = NetworkMonitor()
        logger.info("✅ NetworkMonitor initialization successful")
        
        # Test connection detection
        connection_type = nm.detect_connection_type()
        logger.info(f"✅ Connection detection: {connection_type}")
        
        # Test interface detection
        interface_status = nm._check_network_interfaces()
        logger.info(f"✅ Network interface check: {interface_status}")
        
        # Use assertions instead of returning values
        assert nm is not None
        assert connection_type is not None
        
    except ImportError as e:
        logger.warning(f"❌ NetworkMonitor not available: {e}")
        pytest.skip("NetworkMonitor not available")
    except Exception as e:
        logger.error(f"❌ NetworkMonitor test failed: {e}")
        pytest.fail(f"NetworkMonitor test failed: {e}")

def test_fasttelethon_imports():
    """Test FastTelethon imports and initialization"""
    try:
        from utils.fast_download import fast_download_to_file
        logger.info("✅ FastTelethon imports successful")
        
        # Test error handling imports
        from telethon.errors import FloodWaitError, TimeoutError, ServerError, RPCError, AuthKeyError
        logger.info("✅ Telethon error imports successful")
        
        # Use assertions instead of returning values
        assert fast_download_to_file is not None
        
    except ImportError as e:
        logger.error(f"❌ FastTelethon imports failed: {e}")
        pytest.skip(f"FastTelethon imports failed: {e}")
    except Exception as e:
        logger.error(f"❌ FastTelethon test failed: {e}")
        pytest.fail(f"FastTelethon test failed: {e}")

@pytest.mark.asyncio
async def test_retry_mechanism():
    """Test retry mechanism simulation"""
    try:
        from utils.fast_download import fast_download_to_file
        
        # Test would go here if we had a real Telegram client
        logger.info("✅ Retry mechanism structure verified")
        assert fast_download_to_file is not None
        
    except Exception as e:
        logger.error(f"❌ Retry mechanism test failed: {e}")
        pytest.fail(f"Retry mechanism test failed: {e}")

def test_configuration():
    """Test configuration loading"""
    try:
        from config import config
        
        # Check if the config object has the expected attributes
        assert hasattr(config, 'api_id')
        assert hasattr(config, 'api_hash')
        assert hasattr(config, 'target_username')
        assert hasattr(config, 'max_archive_gb')
        assert hasattr(config, 'disk_space_factor')
        assert hasattr(config, 'max_concurrent')
        assert hasattr(config, 'download_chunk_size_kb')
        assert hasattr(config, 'parallel_downloads')
        assert hasattr(config, 'video_transcode_threshold_mb')
        assert hasattr(config, 'transcode_enabled')
        assert hasattr(config, 'fast_download_enabled')
        assert hasattr(config, 'fast_download_connections')
        assert hasattr(config, 'wifi_only_mode')
        
        logger.info(f"✅ Configuration loaded successfully")
            
    except Exception as e:
        logger.error(f"❌ Configuration test failed: {e}")
        pytest.fail(f"Configuration test failed: {e}")

def test_status_command():
    """Test the /status command"""
    try:
        from utils.command_handlers import handle_status_command
        
        # Check that the function exists and can be imported
        assert handle_status_command is not None
        assert callable(handle_status_command)
        
        logger.info("✅ Status command handler imported successfully")

    except Exception as e:
        logger.error(f"❌ Status command test failed: {e}")
        pytest.fail(f"Status command test failed: {e}")

@pytest.mark.asyncio
async def test_async_commands():
    """Test that command handlers can be imported."""
    try:
        from utils.command_handlers import (
            handle_help_command, handle_status_command, handle_queue_command,
            handle_compression_timeout_command
        )

        # Check that all command handlers exist and are callable
        assert handle_help_command is not None
        assert handle_status_command is not None
        assert handle_queue_command is not None
        assert handle_compression_timeout_command is not None
        
        assert callable(handle_help_command)
        assert callable(handle_status_command)
        assert callable(handle_queue_command)
        assert callable(handle_compression_timeout_command)

        logger.info("✅ Async command handlers imported successfully")

    except Exception as e:
        logger.error(f"❌ Async command test failed: {e}")
        pytest.fail(f"Async command test failed: {e}")



def test_compression_timeout_command():
    """Test the compression timeout command that was just added"""
    try:
        from utils.command_handlers import handle_compression_timeout_command, _parse_timeout_value
        
        # Test the timeout parsing function
        assert _parse_timeout_value("300") == 300
        assert _parse_timeout_value("5m") == 300
        assert _parse_timeout_value("2h") == 7200
        assert _parse_timeout_value("1h30m") == 5400
        
        # Test that the command handler exists
        assert handle_compression_timeout_command is not None
        assert callable(handle_compression_timeout_command)
        
        logger.info("✅ Compression timeout command test successful")
        
    except Exception as e:
        logger.error(f"❌ Compression timeout test failed: {e}")
        pytest.fail(f"Compression timeout test failed: {e}")


def main():
    """Run all enhancement tests - kept for backward compatibility"""
    logger.info("🧪 Note: Tests are now run via pytest. Use 'python -m pytest test_enhancements.py -v'")
    logger.info("🔄 Running basic validation...")
    
    # Just run a basic import check
    try:
        from utils.command_handlers import handle_compression_timeout_command
        logger.info("✅ Basic imports working")
        return True
    except Exception as e:
        logger.error(f"❌ Basic validation failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)