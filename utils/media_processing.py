"""
Media processing module for the Telegram Compressed File Extractor.
Contains functions for video processing, format validation, and media operations.
"""

import os
import io
import shutil
import subprocess
import asyncio
import logging
import hashlib
from .constants import TRANSCODE_ENABLED, COMPRESSION_TIMEOUT_SECONDS, RECOVERY_DIR

logger = logging.getLogger('extractor')

# Telegram's 10MB photo upload limit (in bytes)
TELEGRAM_PHOTO_SIZE_LIMIT = 10 * 1024 * 1024  # 10MB


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


def convert_video_for_recovery(input_path: str) -> str:
    """
    Convert a problematic video into a Telegram-friendly MP4 for recovery uploads.
    
    Returns the output path on success, or None on failure.
    """
    if not input_path or not os.path.exists(input_path):
        logger.error(f"Recovery conversion input missing: {input_path}")
        return None
    
    if not is_ffmpeg_available():
        logger.error("ffmpeg not found for recovery conversion. Please install ffmpeg.")
        return None
    
    # Stable output name based on file hash to allow resumable conversion
    try:
        with open(input_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read(8192)).hexdigest()  # partial hash for speed
    except Exception:
        file_hash = os.path.basename(input_path)
    
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_name = f"{base_name}_{file_hash[:8]}_recovery.mp4"
    output_path = os.path.join(RECOVERY_DIR, output_name)
    
    # Reuse existing converted file if present
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        logger.info(f"Reusing existing converted file for recovery: {output_path}")
        return output_path
    
    cmd = [
        'ffmpeg',
        '-y',
        '-i', input_path,
        '-c:v', 'libx264',
        '-preset', 'medium',
        '-crf', '23',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-movflags', '+faststart',
        output_path
    ]
    
    try:
        logger.info(f"Starting recovery conversion: {input_path} -> {output_path}")
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False
        )
        if result.returncode != 0:
            logger.error(f"ffmpeg recovery conversion failed ({result.returncode}) for {input_path}")
            logger.debug(result.stderr.decode(errors='ignore'))
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            return None
        
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            logger.error(f"ffmpeg reported success but output missing/empty: {output_path}")
            return None
        
        logger.info(f"Recovery conversion completed: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Unexpected error during recovery conversion: {e}")
        import traceback
        logger.debug(traceback.format_exc())
    
    return None


async def compress_image_for_telegram(input_path: str, output_path: str = None, target_size: int = TELEGRAM_PHOTO_SIZE_LIMIT) -> str:
    """
    Compress image to under Telegram's 10MB photo upload limit using iterative quality reduction.
    
    This function uses Pillow to:
    1. Convert PNG/WEBP/other formats to JPEG for better compression
    2. Iteratively reduce JPEG quality (starting at 95, decreasing by 5) until target size is met
    3. Resize image dimensions as a last resort if quality reduction isn't enough
    4. Maintain minimum quality threshold of 50 to ensure usability
    
    Args:
        input_path: Path to the input image file
        output_path: Path for the compressed output (optional, will generate from input_path if not provided)
        target_size: Target file size in bytes (default: 10MB for Telegram limit)
    
    Returns:
        Path to the compressed image file if successful, None if compression failed
    """
    try:
        from PIL import Image
    except ImportError:
        logger.error("Pillow library not found. Install with: pip install Pillow")
        return None
    
    if not os.path.exists(input_path):
        logger.error(f"Input image file not found: {input_path}")
        return None
    
    # Check if image is already under the limit
    original_size = os.path.getsize(input_path)
    if original_size <= target_size:
        logger.info(f"Image already under {target_size} bytes: {input_path} ({original_size} bytes)")
        return input_path
    
    # Generate output path if not provided
    if output_path is None:
        base_name, ext = os.path.splitext(input_path)
        output_path = base_name + '_compressed.jpg'
    
    try:
        logger.info(f"Starting image compression: {input_path} ({original_size} bytes) -> target: {target_size} bytes")
        
        # Open image with Pillow
        with Image.open(input_path) as img:
            # Convert to RGB if necessary (for PNG with transparency, WEBP, etc.)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create white background for transparency
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            original_dimensions = img.size
            logger.info(f"Original image dimensions: {original_dimensions[0]}x{original_dimensions[1]}")
            
            # Strategy 1: Iterative quality reduction
            quality = 95
            min_quality = 50
            quality_step = 5
            
            while quality >= min_quality:
                # Save to memory buffer to check size
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=quality, optimize=True)
                compressed_size = buffer.tell()
                
                logger.debug(f"Quality {quality}: {compressed_size} bytes")
                
                if compressed_size <= target_size:
                    # Success! Save to actual file
                    with open(output_path, 'wb') as f:
                        f.write(buffer.getvalue())
                    
                    reduction_pct = ((original_size - compressed_size) / original_size) * 100
                    logger.info(f"Image compression successful at quality={quality}: {output_path} ({compressed_size} bytes, {reduction_pct:.1f}% reduction)")
                    return output_path
                
                quality -= quality_step
            
            # Strategy 2: If quality reduction isn't enough, resize dimensions
            logger.info("Quality reduction insufficient, attempting dimension resize...")
            
            # Try progressively smaller sizes: 90%, 80%, 70%, 60%, 50%
            for scale in [0.9, 0.8, 0.7, 0.6, 0.5]:
                new_width = int(original_dimensions[0] * scale)
                new_height = int(original_dimensions[1] * scale)
                
                # Ensure even dimensions
                new_width = (new_width // 2) * 2
                new_height = (new_height // 2) * 2
                
                resized_img = img.resize((new_width, new_height), Image.LANCZOS)
                
                # Try with quality 85 for resized image
                buffer = io.BytesIO()
                resized_img.save(buffer, format='JPEG', quality=85, optimize=True)
                compressed_size = buffer.tell()
                
                logger.debug(f"Resize {scale*100:.0f}% ({new_width}x{new_height}): {compressed_size} bytes")
                
                if compressed_size <= target_size:
                    # Success! Save resized image
                    with open(output_path, 'wb') as f:
                        f.write(buffer.getvalue())
                    
                    reduction_pct = ((original_size - compressed_size) / original_size) * 100
                    logger.info(f"Image compression successful with resize {scale*100:.0f}% at quality=85: {output_path} ({compressed_size} bytes, {reduction_pct:.1f}% reduction)")
                    return output_path
            
            # If we reach here, even aggressive resizing didn't work
            logger.error(f"Failed to compress image under {target_size} bytes even with aggressive resizing")
            
            # Save the most compressed version we have as a last resort
            resized_img = img.resize((int(original_dimensions[0] * 0.5), int(original_dimensions[1] * 0.5)), Image.LANCZOS)
            resized_img.save(output_path, format='JPEG', quality=min_quality, optimize=True)
            
            final_size = os.path.getsize(output_path)
            logger.warning(f"Saved heavily compressed image: {output_path} ({final_size} bytes) - may still exceed Telegram limit")
            return output_path
            
    except Exception as e:
        logger.error(f"Error during image compression for {input_path}: {e}")
        # Clean up any partial output file
        if output_path and os.path.exists(output_path) and output_path != input_path:
            try:
                os.remove(output_path)
                logger.debug(f"Cleaned up partial compression file: {output_path}")
            except Exception as cleanup_e:
                logger.warning(f"Failed to clean up partial file {output_path}: {cleanup_e}")
        return None


def is_telegram_photo_size_error(error_message: str) -> bool:
    """
    Check if an error message indicates Telegram's 10MB photo upload limit was exceeded.
    
    Args:
        error_message: The error message string to check
    
    Returns:
        True if the error is about photo size exceeding 10MB, False otherwise
    """
    if not error_message:
        return False
    
    error_lower = str(error_message).lower()
    
    # Check for the specific error message from Telegram
    indicators = [
        'cannot be saved by telegram',
        'exceeds 10mb',
        '10 mb',
        'photo you tried to send',
        'uploadmediarequest'
    ]
    
    # Must contain at least 2 of these indicators to be considered a photo size error
    matches = sum(1 for indicator in indicators if indicator in error_lower)
    
    return matches >= 2
