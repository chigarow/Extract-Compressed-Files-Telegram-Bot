"""
Configuration module for the Telethon archive extractor bot.

Loads configuration from secrets.properties and provides a centralized
Config class to access all configuration values.
"""

import os
import configparser
def strtobool(val):
    """Convert a string representation of truth to true (1) or false (0).

    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    val = val.lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return 1
    elif val in ('n', 'no', 'f', 'false', 'off', '0'):
        return 0
    else:
        raise ValueError("invalid truth value %r" % (val,))


class Config:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.config_path = os.path.join(self.base_dir, 'secrets.properties')
        self.data_dir = os.path.join(self.base_dir, 'data')
        
        self._config = configparser.ConfigParser()
        self._config.read(self.config_path)
        
        self.api_id = self._getint('APP_API_ID')
        self.api_hash = self._get('APP_API_HASH')
        self.target_username = self._get('ACCOUNT_B_USERNAME')
        
        self.max_archive_gb = self._getfloat('MAX_ARCHIVE_GB', 6.0)
        self.disk_space_factor = self._getfloat('DISK_SPACE_FACTOR', 2.5)
        self.max_concurrent = self._getint('MAX_CONCURRENT', 1)
        self.download_chunk_size_kb = self._getint('DOWNLOAD_CHUNK_SIZE_KB', 1024)
        self.parallel_downloads = self._getint('PARALLEL_DOWNLOADS', 4)
        self.video_transcode_threshold_mb = self._getint('VIDEO_TRANSCODE_THRESHOLD_MB', 100)
        self.transcode_enabled = self._getboolean('TRANSCODE_ENABLED', False)
        self.fast_download_enabled = self._getboolean('FAST_DOWNLOAD_ENABLED', True)
        self.fast_download_connections = self._getint('FAST_DOWNLOAD_CONNECTIONS', 8)
        self.wifi_only_mode = self._getboolean('WIFI_ONLY_MODE', True)
        # Video compression timeout (seconds). Default 300 (5 minutes)
        # Can be overridden in secrets.properties via COMPRESSION_TIMEOUT_SECONDS
        self.compression_timeout_seconds = self._getint('COMPRESSION_TIMEOUT_SECONDS', 300)

    def _get(self, key, fallback=None):
        return self._config.get('DEFAULT', key, fallback=fallback)

    def _getint(self, key, fallback=None):
        return self._config.getint('DEFAULT', key, fallback=fallback)

    def _getfloat(self, key, fallback=None):
        return self._config.getfloat('DEFAULT', key, fallback=fallback)

    def _getboolean(self, key, fallback=None):
        try:
            return self._config.getboolean('DEFAULT', key)
        except (ValueError, AttributeError, configparser.NoOptionError):
            val = self._config.get('DEFAULT', key, fallback=fallback)
            if isinstance(val, bool):
                return val
            return bool(strtobool(str(val)))

    def save(self):
        """Save the current configuration to the secrets.properties file."""
        with open(self.config_path, 'w') as configfile:
            self._config.write(configfile)

# Create a single instance of the Config class
config = Config(os.path.dirname(__file__))
