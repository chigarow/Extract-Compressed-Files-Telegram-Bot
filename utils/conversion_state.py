"""
Conversion state management for crash-resilient video conversion.
Tracks conversion progress and enables resume after crashes.
"""

import os
import json
import time
import logging
from typing import Optional, Dict, List
from .constants import DATA_DIR

logger = logging.getLogger('extractor')

# Conversion state file
CONVERSION_STATE_FILE = os.path.join(DATA_DIR, 'conversion_state.json')


class ConversionStateManager:
    """Manages state for video conversions with crash recovery support."""
    
    def __init__(self, state_file: str = CONVERSION_STATE_FILE):
        self.state_file = state_file
        self.states = {}
        self._load_states()
    
    def _load_states(self):
        """Load conversion states from disk."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    self.states = json.load(f)
                logger.info(f"Loaded {len(self.states)} conversion states from disk")
            except Exception as e:
                logger.error(f"Failed to load conversion states: {e}")
                self.states = {}
        else:
            self.states = {}
    
    def _save_states(self):
        """Save conversion states to disk."""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(self.states, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save conversion states: {e}")
    
    def save_state(
        self,
        file_path: str,
        status: str,
        progress: int,
        output_path: str,
        error: Optional[str] = None
    ):
        """
        Save conversion state for a file.
        
        Args:
            file_path: Path to the original video file
            status: Current status (pending, in_progress, completed, failed)
            progress: Conversion progress percentage (0-100)
            output_path: Path to the output converted file
            error: Error message if status is 'failed'
        """
        state = {
            'file_path': file_path,
            'output_path': output_path,
            'status': status,
            'progress': progress,
            'last_updated': time.time(),
            'error': error
        }
        
        # Add started_at timestamp if this is a new conversion
        if file_path not in self.states:
            state['started_at'] = time.time()
            state['retry_count'] = 0
        else:
            # Preserve started_at and retry_count from previous state
            state['started_at'] = self.states[file_path].get('started_at', time.time())
            state['retry_count'] = self.states[file_path].get('retry_count', 0)
        
        self.states[file_path] = state
        self._save_states()
        
        logger.debug(f"💾 Saved conversion state: {os.path.basename(file_path)} - {status} ({progress}%)")
    
    def load_state(self, file_path: str) -> Optional[Dict]:
        """
        Load conversion state for a file.
        
        Args:
            file_path: Path to the original video file
            
        Returns:
            State dictionary or None if not found
        """
        return self.states.get(file_path)
    
    def mark_completed(self, file_path: str):
        """Mark a conversion as completed."""
        if file_path in self.states:
            self.states[file_path]['status'] = 'completed'
            self.states[file_path]['progress'] = 100
            self.states[file_path]['last_updated'] = time.time()
            self._save_states()
            logger.info(f"✅ Marked conversion completed: {os.path.basename(file_path)}")
    
    def mark_failed(self, file_path: str, error: str):
        """Mark a conversion as failed."""
        if file_path in self.states:
            self.states[file_path]['status'] = 'failed'
            self.states[file_path]['error'] = error
            self.states[file_path]['last_updated'] = time.time()
            self._save_states()
            logger.error(f"❌ Marked conversion failed: {os.path.basename(file_path)} - {error}")
    
    def increment_retry_count(self, file_path: str):
        """Increment retry count for a conversion."""
        if file_path in self.states:
            self.states[file_path]['retry_count'] = self.states[file_path].get('retry_count', 0) + 1
            self._save_states()
    
    def get_incomplete_conversions(self) -> List[Dict]:
        """
        Get list of incomplete conversions (pending or in_progress).
        
        Returns:
            List of state dictionaries for incomplete conversions
        """
        incomplete = []
        
        for file_path, state in self.states.items():
            status = state.get('status')
            
            if status in ('pending', 'in_progress'):
                # Check if file still exists
                if os.path.exists(file_path):
                    incomplete.append(state)
                else:
                    logger.warning(f"⚠️ Incomplete conversion file missing: {file_path}")
                    # Mark as failed since file is gone
                    self.mark_failed(file_path, "Original file missing")
        
        return incomplete
    
    def cleanup_completed(self, max_age_hours: int = 24):
        """
        Clean up completed conversion states older than max_age_hours.
        
        Args:
            max_age_hours: Maximum age in hours for completed states to keep
        """
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        to_remove = []
        
        for file_path, state in self.states.items():
            if state.get('status') == 'completed':
                last_updated = state.get('last_updated', 0)
                age_seconds = current_time - last_updated
                
                if age_seconds > max_age_seconds:
                    to_remove.append(file_path)
        
        for file_path in to_remove:
            del self.states[file_path]
            logger.debug(f"🧹 Cleaned up old conversion state: {os.path.basename(file_path)}")
        
        if to_remove:
            self._save_states()
            logger.info(f"🧹 Cleaned up {len(to_remove)} old conversion states")
    
    def get_stats(self) -> Dict:
        """
        Get statistics about conversions.
        
        Returns:
            Dictionary with conversion statistics
        """
        stats = {
            'total': len(self.states),
            'pending': 0,
            'in_progress': 0,
            'completed': 0,
            'failed': 0
        }
        
        for state in self.states.values():
            status = state.get('status', 'unknown')
            if status in stats:
                stats[status] += 1
        
        return stats
    
    def clear_all(self):
        """Clear all conversion states (use with caution)."""
        self.states = {}
        self._save_states()
        logger.warning("⚠️ Cleared all conversion states")
