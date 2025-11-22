
import pytest
from unittest.mock import patch, MagicMock

# Since webdav4 might not be installed in all test environments,
# we use a mock to represent it.
mock_sync_webdav_client = MagicMock()

# We need to patch the location where SyncWebDAVClient is imported and used.
# It's imported in 'utils.webdav_client'.
@patch('utils.webdav_client.SyncWebDAVClient', new=mock_sync_webdav_client)
def test_torbox_webdav_client_passes_timeout_to_sync_client():
    """
    Verify that the TorboxWebDAVClient correctly passes the timeout
    parameter to the underlying SyncWebDAVClient.
    """
    from utils.webdav_client import TorboxWebDAVClient

    # Reset the mock before the test to clear any previous calls
    mock_sync_webdav_client.reset_mock()

    # Define test parameters
    base_url = "https://webdav.example.com"
    username = "testuser"
    password = "testpassword"
    timeout = 90  # A specific timeout value to check for

    # Instantiate the client, which should in turn instantiate SyncWebDAVClient
    TorboxWebDAVClient(
        base_url=base_url,
        username=username,
        password=password,
        timeout=timeout
    )

    # Check that SyncWebDAVClient was called exactly once
    mock_sync_webdav_client.assert_called_once()

    # Get the arguments it was called with
    args, kwargs = mock_sync_webdav_client.call_args

    # Verify that the 'timeout' keyword argument was passed with the correct value
    assert 'timeout' in kwargs, "The 'timeout' keyword argument was not passed to SyncWebDAVClient"
    assert kwargs['timeout'] == timeout, f"Expected timeout to be {timeout}, but got {kwargs['timeout']}"

    # Verify other arguments as a sanity check
    assert 'base_url' in kwargs and kwargs['base_url'] == base_url
    assert 'auth' in kwargs and kwargs['auth'] == (username, password)
