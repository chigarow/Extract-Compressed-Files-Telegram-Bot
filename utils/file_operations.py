"""
File operations module for the Telegram Compressed File Extractor.
Contains functions for file hashing, extraction, and file system operations.
"""

import os
import hashlib
import shutil
import subprocess
import logging
from .constants import BASE_DIR

logger = logging.getLogger('extractor')


def check_file_command_supports_mime():
    """Checks if the system's 'file' command supports the --mime-type flag."""
    # On some systems like Termux, the 'file' command is older and uses -i.
    # patoolib uses --mime-type, causing errors. This check prevents that.
    dummy_path = os.path.join(BASE_DIR, 'file_check.tmp')
    try:
        with open(dummy_path, 'w') as f:
            f.write('test')
        # We capture stderr to prevent it from printing to the console.
        result = subprocess.run(
            ['file', '--brief', '--mime-type', dummy_path],
            check=True, capture_output=True
        )
        # Check for the expected output format
        return 'text/plain' in result.stdout.decode().lower()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    finally:
        if os.path.exists(dummy_path):
            os.remove(dummy_path)


def compute_sha256(path: str, chunk_size: int = 1024 * 1024) -> str:
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def extract_with_password(archive_path: str, extract_path: str, password: str) -> None:
    """Extract password-protected archive using 7z."""
    # Use 7z for universal extraction; requires p7zip (Termux: pkg install p7zip)
    sevenzip = shutil.which('7z') or shutil.which('7za')
    if not sevenzip:
        raise RuntimeError('7z binary not found; install p7zip to extract password-protected archives')
    cmd = [sevenzip, 'x', '-y', f'-p{password}', f'-o{extract_path}', archive_path]
    logger.info('Running password extraction via 7z')
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if res.returncode != 0:
        raise RuntimeError(f'7z extraction failed (code {res.returncode}): {res.stdout[-400:]}')


def is_password_error(err_text: str) -> bool:
    """Check if error text indicates a password-related error."""
    t = err_text.lower()
    return 'password' in t or 'wrong password' in t or 'incorrect password' in t


def extract_archive_async(temp_archive_path, extract_path, filename):
    """
    Extract archive synchronously (to be run in executor).
    Returns tuple: (success: bool, error_msg: str or None)
    
    This function tries multiple extraction methods in order:
    1. patoolib (if 'file' command supports --mime-type)
    2. Format-specific Python libraries (zipfile, tarfile)
    3. Command-line tools (unrar, 7z)
    
    The function is robust and will try all available methods before giving up.
    """
    logger.info(f'Starting extraction of {filename} from {temp_archive_path}')
    logger.info(f'Target extraction directory: {extract_path}')
    
    # Validate that archive file exists and is readable
    if not os.path.exists(temp_archive_path):
        error_msg = f'Archive file does not exist: {temp_archive_path}'
        logger.error(error_msg)
        return False, error_msg
    
    if not os.path.isfile(temp_archive_path):
        error_msg = f'Archive path is not a file: {temp_archive_path}'
        logger.error(error_msg)
        return False, error_msg
    
    file_size = os.path.getsize(temp_archive_path)
    logger.info(f'Archive file size: {file_size} bytes')
    
    # Track which methods we try
    attempted_methods = []
    
    # Try patoolib first (only if file command is compatible)
    try:
        import patoolib
        if check_file_command_supports_mime():
            logger.info('Attempting extraction with patoolib')
            attempted_methods.append('patoolib')
            patoolib.extract_archive(temp_archive_path, outdir=extract_path, verbosity=-1)
            logger.info(f'✓ Archive extracted successfully using patoolib: {filename}')
            return True, None
        else:
            logger.warning("Skipping patoolib: 'file' command incompatibility detected")
            logger.info("Will try alternative extraction methods")
    except Exception as patoo_err:
        logger.warning(f'patoolib extraction failed: {patoo_err}')
        logger.info('Falling back to alternative extraction methods')
    
    # Try format-specific extractors based on file extension
    logger.info('Trying format-specific extraction methods')
    
    # Method 1: Try zipfile for .zip files
    if filename.lower().endswith('.zip'):
        try:
            import zipfile
            logger.info('Attempting extraction with Python zipfile module')
            attempted_methods.append('zipfile')
            
            # First, verify it's a valid zip file
            if not zipfile.is_zipfile(temp_archive_path):
                logger.warning(f'File does not appear to be a valid ZIP file: {filename}')
            else:
                with zipfile.ZipFile(temp_archive_path, 'r') as zip_ref:
                    # Get info about archive contents
                    file_list = zip_ref.namelist()
                    logger.info(f'ZIP archive contains {len(file_list)} files')
                    
                    # Extract all files
                    zip_ref.extractall(extract_path)
                    logger.info(f'✓ ZIP archive extracted successfully using zipfile: {filename}')
                    return True, None
                    
        except zipfile.BadZipFile as e:
            logger.error(f'zipfile failed - BadZipFile: {e}')
        except zipfile.LargeZipFile as e:
            logger.error(f'zipfile failed - LargeZipFile (requires ZIP64): {e}')
        except Exception as e:
            logger.error(f'zipfile extraction failed with unexpected error: {e}')
            import traceback
            logger.error(f'Traceback: {traceback.format_exc()}')
    
    # Method 2: Try tarfile for tar archives
    elif filename.lower().endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz')):
        try:
            import tarfile
            logger.info('Attempting extraction with Python tarfile module')
            attempted_methods.append('tarfile')
            
            with tarfile.open(temp_archive_path, 'r:*') as tar_ref:
                # Get info about archive contents
                members = tar_ref.getmembers()
                logger.info(f'TAR archive contains {len(members)} members')
                
                # Extract all files
                tar_ref.extractall(extract_path)
                logger.info(f'✓ TAR archive extracted successfully using tarfile: {filename}')
                return True, None
                
        except tarfile.TarError as e:
            logger.error(f'tarfile failed - TarError: {e}')
        except Exception as e:
            logger.error(f'tarfile extraction failed with unexpected error: {e}')
            import traceback
            logger.error(f'Traceback: {traceback.format_exc()}')
    
    # Method 3: Try unrar for .rar files
    elif filename.lower().endswith('.rar'):
        try:
            unrar = shutil.which('unrar')
            if unrar:
                logger.info(f'Attempting extraction with unrar command: {unrar}')
                attempted_methods.append('unrar')
                
                result = subprocess.run(
                    [unrar, 'x', '-y', temp_archive_path, extract_path], 
                    capture_output=True, 
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                if result.returncode == 0:
                    logger.info(f'✓ RAR archive extracted successfully using unrar: {filename}')
                    return True, None
                else:
                    logger.error(f'unrar failed with return code {result.returncode}')
                    logger.error(f'unrar stderr: {result.stderr}')
            else:
                logger.warning('unrar command not found in PATH')
                
        except subprocess.TimeoutExpired:
            logger.error('unrar extraction timed out after 5 minutes')
        except Exception as e:
            logger.error(f'unrar extraction failed with unexpected error: {e}')
            import traceback
            logger.error(f'Traceback: {traceback.format_exc()}')
    
    # Method 4: Try 7z as universal fallback for all formats
    logger.info('Trying 7z as universal fallback extractor')
    try:
        sevenzip = shutil.which('7z') or shutil.which('7za')
        if sevenzip:
            logger.info(f'Attempting extraction with 7z command: {sevenzip}')
            attempted_methods.append('7z')
            
            result = subprocess.run(
                [sevenzip, 'x', '-y', f'-o{extract_path}', temp_archive_path], 
                capture_output=True, 
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                logger.info(f'✓ Archive extracted successfully using 7z: {filename}')
                return True, None
            else:
                logger.error(f'7z failed with return code {result.returncode}')
                logger.error(f'7z stderr: {result.stderr}')
                logger.error(f'7z stdout: {result.stdout}')
        else:
            logger.warning('7z command not found in PATH')
            
    except subprocess.TimeoutExpired:
        logger.error('7z extraction timed out after 5 minutes')
    except Exception as e:
        logger.error(f'7z extraction failed with unexpected error: {e}')
        import traceback
        logger.error(f'Traceback: {traceback.format_exc()}')
    
    # If we get here, all methods failed
    methods_tried = ', '.join(attempted_methods) if attempted_methods else 'none'
    error_msg = f'All extraction methods failed for {filename}. Tried: {methods_tried}'
    logger.error(error_msg)
    logger.error(f'File details - Path: {temp_archive_path}, Size: {file_size} bytes')
    logger.error('Possible causes: corrupted archive, unsupported format, missing extraction tools')
    
    return False, error_msg


# Check file command support at module level
FILE_CMD_OK = check_file_command_supports_mime()
