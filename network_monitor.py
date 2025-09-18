"""
Network monitoring utility for detecting connection type (WiFi vs mobile data)
and managing download pausing based on connection status.
"""

import asyncio
import logging
import subprocess
import os
import time
import re
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger('network_monitor')

class NetworkType:
    WIFI = "wifi"
    MOBILE = "mobile" 
    ETHERNET = "ethernet"
    UNKNOWN = "unknown"
    DISCONNECTED = "disconnected"

class NetworkMonitor:
    """Monitor network connection type and manage download pausing"""
    
    def __init__(self, check_interval: int = 10, allow_mobile: bool = False):
        """
        Initialize network monitor.
        
        Args:
            check_interval: How often to check connection type (seconds)
            allow_mobile: Whether to allow downloads on mobile data
        """
        self.check_interval = check_interval
        self.allow_mobile = allow_mobile
        self.current_type = NetworkType.UNKNOWN
        self.is_monitoring = False
        self.callbacks: Dict[str, Callable] = {}
        self._monitor_task: Optional[asyncio.Task] = None
        
    def add_callback(self, event: str, callback: Callable):
        """
        Add callback for network events.
        
        Events:
        - 'wifi_connected': Called when WiFi becomes available
        - 'mobile_detected': Called when mobile data is detected
        - 'disconnected': Called when connection is lost
        - 'connection_changed': Called on any connection change
        """
        self.callbacks[event] = callback
    
    def detect_connection_type(self) -> str:
        """
        Detect the current network connection type.
        
        Returns:
            NetworkType constant representing the connection type
        """
        try:
            # Method 1: Check Android network interface (Termux)
            if os.path.exists('/proc/net/route'):
                connection_type = self._check_android_connection()
                if connection_type != NetworkType.UNKNOWN:
                    return connection_type
            
            # Method 2: Check using ip route command
            connection_type = self._check_ip_route()
            if connection_type != NetworkType.UNKNOWN:
                return connection_type
            
            # Method 3: Check network interfaces
            connection_type = self._check_network_interfaces()
            if connection_type != NetworkType.UNKNOWN:
                return connection_type
            
            # Method 4: Check using dumpsys (Android specific)
            connection_type = self._check_dumpsys()
            if connection_type != NetworkType.UNKNOWN:
                return connection_type
                
            return NetworkType.UNKNOWN
            
        except Exception as e:
            logger.warning(f"Error detecting connection type: {e}")
            return NetworkType.UNKNOWN
    
    def _check_android_connection(self) -> str:
        """Check connection type using Android-specific methods"""
        try:
            # Check for rmnet interfaces (mobile data)
            result = subprocess.run(['ip', 'route', 'show'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                routes = result.stdout
                
                # Check for mobile data interfaces
                mobile_patterns = [r'rmnet\d+', r'ccmni\d+', r'pdp_ip\d+', 
                                 r'ppp\d+', r'wwan\d+', r'usb\d+']
                for pattern in mobile_patterns:
                    if re.search(pattern, routes):
                        logger.debug(f"Mobile interface detected: {pattern}")
                        return NetworkType.MOBILE
                
                # Check for WiFi interfaces
                wifi_patterns = [r'wlan\d+', r'wl\d+', r'wifi\d+']
                for pattern in wifi_patterns:
                    if re.search(pattern, routes):
                        logger.debug(f"WiFi interface detected: {pattern}")
                        return NetworkType.WIFI
                
                # Check for ethernet
                if re.search(r'eth\d+', routes):
                    logger.debug("Ethernet interface detected")
                    return NetworkType.ETHERNET
                    
        except Exception as e:
            logger.debug(f"Android connection check failed: {e}")
        
        return NetworkType.UNKNOWN
    
    def _check_ip_route(self) -> str:
        """Check connection type using ip route command"""
        try:
            result = subprocess.run(['ip', 'route', 'get', '8.8.8.8'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                route_info = result.stdout.lower()
                
                # Check interface name in route output
                if any(pattern in route_info for pattern in ['rmnet', 'ccmni', 'pdp_ip', 'ppp', 'wwan']):
                    return NetworkType.MOBILE
                elif any(pattern in route_info for pattern in ['wlan', 'wl', 'wifi']):
                    return NetworkType.WIFI
                elif 'eth' in route_info:
                    return NetworkType.ETHERNET
                    
        except Exception as e:
            logger.debug(f"IP route check failed: {e}")
        
        return NetworkType.UNKNOWN
    
    def _check_network_interfaces(self) -> str:
        """Check active network interfaces"""
        try:
            # Check /proc/net/dev for active interfaces
            with open('/proc/net/dev', 'r') as f:
                interfaces = f.read()
            
            # Look for active interfaces with traffic
            for line in interfaces.split('\n'):
                if ':' in line:
                    iface_name = line.split(':')[0].strip()
                    # Skip loopback
                    if iface_name == 'lo':
                        continue
                    
                    # Check if interface has traffic (RX bytes > 0)
                    parts = line.split()
                    if len(parts) > 2:
                        rx_bytes = int(parts[1])
                        if rx_bytes > 0:
                            # Classify based on interface name
                            iface_lower = iface_name.lower()
                            if any(pattern in iface_lower for pattern in ['rmnet', 'ccmni', 'pdp_ip', 'ppp', 'wwan']):
                                return NetworkType.MOBILE
                            elif any(pattern in iface_lower for pattern in ['wlan', 'wl', 'wifi']):
                                return NetworkType.WIFI
                            elif 'eth' in iface_lower:
                                return NetworkType.ETHERNET
                                
        except Exception as e:
            logger.debug(f"Interface check failed: {e}")
        
        return NetworkType.UNKNOWN
    
    def _check_dumpsys(self) -> str:
        """Check connection using Android dumpsys command"""
        try:
            # Try to get network info using dumpsys
            result = subprocess.run(['dumpsys', 'connectivity'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                output = result.stdout.lower()
                
                # Look for active network type
                if 'wifi' in output and 'state: connected/connected' in output:
                    return NetworkType.WIFI
                elif any(pattern in output for pattern in ['mobile', 'cellular']) and 'state: connected/connected' in output:
                    return NetworkType.MOBILE
                    
        except Exception as e:
            logger.debug(f"Dumpsys check failed: {e}")
        
        return NetworkType.UNKNOWN
    
    def is_download_allowed(self) -> bool:
        """
        Check if download should be allowed based on current connection.
        
        Returns:
            True if download is allowed, False otherwise
        """
        connection_type = self.detect_connection_type()
        
        if connection_type == NetworkType.DISCONNECTED:
            return False
        elif connection_type == NetworkType.MOBILE and not self.allow_mobile:
            return False
        elif connection_type in [NetworkType.WIFI, NetworkType.ETHERNET]:
            return True
        elif connection_type == NetworkType.MOBILE and self.allow_mobile:
            return True
        else:
            # Unknown connection type - allow but warn
            logger.warning(f"Unknown connection type detected: {connection_type}")
            return True
    
    async def start_monitoring(self):
        """Start monitoring network connection type"""
        if self.is_monitoring:
            return
        
        self.is_monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(f"Network monitoring started (check interval: {self.check_interval}s)")
    
    async def stop_monitoring(self):
        """Stop monitoring network connection type"""
        self.is_monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Network monitoring stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop"""
        try:
            while self.is_monitoring:
                old_type = self.current_type
                new_type = self.detect_connection_type()
                
                if new_type != old_type:
                    logger.info(f"Network connection changed: {old_type} -> {new_type}")
                    self.current_type = new_type
                    
                    # Call appropriate callbacks
                    if new_type == NetworkType.WIFI and 'wifi_connected' in self.callbacks:
                        try:
                            await self._safe_callback('wifi_connected')
                        except Exception as e:
                            logger.error(f"Error in wifi_connected callback: {e}")
                    
                    elif new_type == NetworkType.MOBILE and 'mobile_detected' in self.callbacks:
                        try:
                            await self._safe_callback('mobile_detected')
                        except Exception as e:
                            logger.error(f"Error in mobile_detected callback: {e}")
                    
                    elif new_type == NetworkType.DISCONNECTED and 'disconnected' in self.callbacks:
                        try:
                            await self._safe_callback('disconnected')
                        except Exception as e:
                            logger.error(f"Error in disconnected callback: {e}")
                    
                    if 'connection_changed' in self.callbacks:
                        try:
                            await self._safe_callback('connection_changed', old_type, new_type)
                        except Exception as e:
                            logger.error(f"Error in connection_changed callback: {e}")
                
                await asyncio.sleep(self.check_interval)
                
        except asyncio.CancelledError:
            logger.debug("Network monitoring cancelled")
        except Exception as e:
            logger.error(f"Error in network monitoring loop: {e}")
    
    async def _safe_callback(self, event: str, *args):
        """Safely call a callback, handling both sync and async functions"""
        if event not in self.callbacks:
            return
        
        callback = self.callbacks[event]
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args)
            else:
                callback(*args)
        except Exception as e:
            logger.error(f"Callback error for {event}: {e}")

    async def wait_for_wifi(self, timeout: Optional[float] = None, 
                          status_callback: Optional[Callable] = None) -> bool:
        """
        Wait until WiFi connection is available.
        
        Args:
            timeout: Maximum time to wait in seconds (None for infinite)
            status_callback: Function to call with status updates
        
        Returns:
            True if WiFi became available, False if timeout occurred
        """
        start_time = time.time()
        
        while True:
            connection_type = self.detect_connection_type()
            
            if connection_type in [NetworkType.WIFI, NetworkType.ETHERNET]:
                if status_callback:
                    try:
                        if asyncio.iscoroutinefunction(status_callback):
                            await status_callback(f"✅ WiFi connection restored ({connection_type})")
                        else:
                            status_callback(f"✅ WiFi connection restored ({connection_type})")
                    except Exception as e:
                        logger.error(f"Status callback error: {e}")
                return True
            
            # Check timeout
            if timeout and (time.time() - start_time) >= timeout:
                return False
            
            # Status update
            elapsed = int(time.time() - start_time)
            if status_callback and elapsed % 30 == 0:  # Update every 30 seconds
                try:
                    if asyncio.iscoroutinefunction(status_callback):
                        await status_callback(f"⏳ Waiting for WiFi... ({elapsed}s elapsed, current: {connection_type})")
                    else:
                        status_callback(f"⏳ Waiting for WiFi... ({elapsed}s elapsed, current: {connection_type})")
                except Exception as e:
                    logger.error(f"Status callback error: {e}")
            
            await asyncio.sleep(5)  # Check every 5 seconds


def get_network_info() -> Dict[str, Any]:
    """Get detailed network information for debugging"""
    info = {
        'connection_type': NetworkType.UNKNOWN,
        'interfaces': {},
        'routes': [],
        'errors': []
    }
    
    monitor = NetworkMonitor()
    info['connection_type'] = monitor.detect_connection_type()
    
    # Get interface information
    try:
        with open('/proc/net/dev', 'r') as f:
            for line in f:
                if ':' in line:
                    parts = line.split(':')
                    iface = parts[0].strip()
                    if iface != 'Inter-|Receive' and iface != 'face':
                        stats = parts[1].split()
                        if len(stats) >= 8:
                            info['interfaces'][iface] = {
                                'rx_bytes': int(stats[0]),
                                'tx_bytes': int(stats[8]) if len(stats) > 8 else 0
                            }
    except Exception as e:
        info['errors'].append(f"Interface info error: {e}")
    
    # Get routing information
    try:
        result = subprocess.run(['ip', 'route', 'show'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            info['routes'] = result.stdout.strip().split('\n')
        else:
            info['errors'].append(f"Route info error: {result.stderr}")
    except Exception as e:
        info['errors'].append(f"Route command error: {e}")
    
    return info