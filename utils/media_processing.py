"""
Media processing module for the Telegram Compressed File Extractor.
Contains functions for video processing, format validation, and media operations.
"""

import os
import shutil
import subprocess
import asyncio
import logging
from .constants import TRANSCODE_ENABLED, COMPRESSION_TIMEOUT_SECONDS

logger = logging.getLogger('extractor')


def is_ffmpeg_available():
    """Check if ffmpeg is available in the system"""
    return shutil.which('ffmpeg') is not None


def is_ffprobe_available():
    """Check if ffprobe is available in the system"""
    return shutil.which('ffprobe') is not None


def validate_video_file(file_path: str) -> dict:
    """
    Validate video file and extract metadata using ffprobe.
    Returns a dictionary with video information or empty dict if validation fails.
    """
    if not is_ffprobe_available():
        logger.warning("ffprobe not found, skipping video validation")
        return {}
    
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            import json
            info = json.loads(result.stdout)
            return info
        else:
            logger.error(f"Video validation failed for {file_path}: {result.stderr}")
            return {}
    except Exception as e:
        logger.error(f"Error during video validation for {file_path}: {e}")
        return {}


def is_telegram_compatible_video(file_path: str) -> bool:
    """
    Check if a video is already compatible with Telegram's requirements.
    Returns True if the video is compatible with Telegram, False otherwise.
    """
    if not is_ffprobe_available():
        logger.warning("ffprobe not found, assuming video is not Telegram compatible")
        return False
    
    try:
        # Check if file is MP4 container with H.264 codec
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-show_entries', 'format=format_name,codec_name',
            '-select_streams', 'v:0',
            '-of', 'csv=p=0',
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            # Get the video format info
            output = result.stdout.strip().split(',')
            if len(output) >= 2:
                container = output[0].lower()
                codec = output[1].lower()
                
                # Check if it's MP4 container with H.264 codec
                if container == 'mp4' and codec in ['h264', 'avc1']:
                    logger.info(f"{file_path} is already Telegram compatible")
                    return True
                else:
                    logger.info(f"{file_path} is not Telegram compatible (container={container}, codec={codec})")
                    return False
            else:
                logger.warning(f"Could not parse ffprobe output for {file_path}")
                return False
        else:
            logger.warning(f"ffprobe failed for {file_path}, assuming video is not Telegram compatible")
            return False
    except Exception as e:
        logger.error(f"Error checking if video is Telegram compatible: {e}")
        return False


def needs_video_processing(file_path: str) -> bool:
    """
    Check if a video needs processing based on its format, metadata, and user settings.
    Returns True if the video should be processed, False otherwise.
    """
    if not is_ffprobe_available():
        logger.warning("ffprobe not found, checking transcode setting")
        # Without ffprobe, respect user setting
        return TRANSCODE_ENABLED
    
    # .ts files can be streamed directly in Telegram, don't convert them
    if file_path.lower().endswith('.ts'):
        logger.info(f"Skipping .ts file conversion (streamable): {file_path}")
        return False
    
    # If transcoding is disabled, don't process any files
    if not TRANSCODE_ENABLED:
        logger.info(f"Transcoding disabled, skipping: {file_path}")
        return False
    
    # Check if the video is already compatible with Telegram
    if is_telegram_compatible_video(file_path):
        # Video is already compatible, and user has transcoding enabled
        # Still process to ensure optimal settings
        return True
    else:
        # Video is not Telegram compatible, and user has transcoding enabled
        return True


async def compress_video_for_telegram(input_path: str, output_path: str = None) -> str:
    """
    Compress video to MP4 format optimized for Telegram streaming.
    Uses compatible compression settings to ensure proper metadata, thumbnails, and duration display.
    Returns the path to the compressed file if successful, None if failed.
    """
    if not is_ffmpeg_available():
        logger.warning("ffmpeg not found, skipping video compression")
        return None
    
    # Generate output path if not provided
    if output_path is None:
        base_name = os.path.splitext(input_path)[0]
        output_path = base_name + '_compressed.mp4'
    
    try:
        # Enhanced MP4 compression settings optimized for Telegram
        # Fixed thumbnail and duration display issues
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-c:v', 'libx264',
            '-preset', 'medium',  # Better quality encoding
            '-crf', '23',  # Better quality setting for proper thumbnails
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '48000',  # Higher quality audio sample rate
            # Critical fixes for thumbnail and duration display:
            '-movflags', '+faststart+use_metadata_tags',  # Proper metadata handling
            '-pix_fmt', 'yuv420p',  # Ensures compatibility
            '-profile:v', 'main',  # Main profile is better than baseline for thumbnails
            '-level', '4.0',  # Higher level for better compatibility
            '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',  # Ensure even dimensions
            # Timestamp and duration fixes:
            '-copyts',  # Copy input timestamps
            '-start_at_zero',  # Start timestamps at zero
            '-avoid_negative_ts', 'disabled',  # Don't modify timestamps
            '-fflags', '+genpts+igndts',  # Generate PTS and ignore DTS issues
            # Metadata fixes:
            '-map_metadata', '0',  # Copy metadata from input
            '-write_tmcd', '0',  # Disable timecode track that can cause issues
            # GOP and keyframe settings for proper thumbnails:
            '-g', '48',  # GOP size matching frame rate
            '-keyint_min', '24',  # Minimum GOP size
            '-sc_threshold', '40',  # Allow some scene change detection
            # Force proper frame rate:
            '-r', '24',  # Set output frame rate to ensure consistency
            '-y',  # Overwrite output file
            output_path
        ]
        
        logger.info(f"Compressing video: {input_path} -> {output_path}")
        loop = asyncio.get_running_loop()
        timeout_val = COMPRESSION_TIMEOUT_SECONDS if isinstance(COMPRESSION_TIMEOUT_SECONDS, int) and COMPRESSION_TIMEOUT_SECONDS > 0 else 300
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_val
            )
        )
        
        if result.returncode == 0:
            logger.info(f"Video compression successful: {output_path}")
            return output_path
        else:
            logger.error(f"Video compression failed: {result.stderr}")
            # Clean up failed output file
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                    logger.info(f"Cleaned up failed compression file: {output_path}")
                except Exception as cleanup_e:
                    logger.warning(f"Failed to clean up {output_path}: {cleanup_e}")
            return None
    except subprocess.TimeoutExpired:
        logger.error("Video compression timed out")
        # Clean up incomplete compressed file after timeout
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
                logger.info(f"Cleaned up timed-out compression file: {output_path}")
            except Exception as cleanup_e:
                logger.warning(f"Failed to clean up timed-out file {output_path}: {cleanup_e}")
        return None
    except Exception as e:
        logger.error(f"Error during video compression: {e}")
        # Clean up any partial output file
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
                logger.info(f"Cleaned up partial compression file: {output_path}")
            except Exception as cleanup_e:
                logger.warning(f"Failed to clean up partial file {output_path}: {cleanup_e}")
        return None


async def get_video_attributes_and_thumbnail(input_path: str) -> tuple:
    """
    Get video attributes (duration, dimensions) and generate a thumbnail for Telegram.
    Uses ffprobe to extract metadata and ffmpeg to create a thumbnail.
    Returns a tuple of (duration, width, height, thumbnail_path) or (0, 0, 0, None) if failed.
    """
    if not is_ffprobe_available():
        logger.warning("ffprobe not found, using default video attributes")
        return 0, 0, 0, None
    
    try:
        # Extract video metadata using ffprobe
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            input_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            import json
            info = json.loads(result.stdout)
            
            # Find video stream
            video_stream = None
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break
            
            if video_stream:
                # Get duration
                duration_str = video_stream.get('duration', '0')
                try:
                    duration = int(float(duration_str))
                except ValueError:
                    duration = 0
                
                # Get dimensions
                width = video_stream.get('width', 0)
                height = video_stream.get('height', 0)
                
                # Generate thumbnail
                thumbnail_path = None
                if width > 0 and height > 0:
                    thumbnail_path = input_path + '.thumb.jpg'
                    thumbnail_cmd = [
                        'ffmpeg',
                        '-i', input_path,
                        '-ss', '00:00:01',  # Get thumbnail from 1 second into the video
                        '-vframes', '1',
                        '-f', 'mjpeg',
                        thumbnail_path,
                        '-y'  # Overwrite existing file
                    ]
                    
                    thumb_result = subprocess.run(thumbnail_cmd, capture_output=True, text=True, timeout=30)
                    if thumb_result.returncode != 0:
                        logger.warning(f"Thumbnail generation failed: {thumb_result.stderr}")
                        thumbnail_path = None
                
                return duration, width, height, thumbnail_path
            else:
                logger.warning(f"No video stream found in {input_path}")
                return 0, 0, 0, None
        else:
            logger.error(f"Video metadata extraction failed for {input_path}: {result.stderr}")
            return 0, 0, 0, None
    except Exception as e:
        logger.error(f"Error extracting video attributes for {input_path}: {e}")
        return 0, 0, 0, None
