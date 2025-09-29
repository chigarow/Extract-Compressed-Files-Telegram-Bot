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
    """
    try:
        # First try patoolib for general extraction
        import patoolib
        if check_file_command_supports_mime():
            patoolib.extract_archive(temp_archive_path, outdir=extract_path, verbosity=-1)
            logger.info(f'Archive extracted successfully using patoolib: {filename}')
            return True, None
        else:
            logger.warning("patoolib might fail due to 'file' command incompatibility")
    except Exception as patoo_err:
        logger.info(f'patoolib extraction failed, trying alternatives: {patoo_err}')
        
        # Try format-specific extractors
        try:
            if filename.lower().endswith('.zip'):
                import zipfile
                with zipfile.ZipFile(temp_archive_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)
                logger.info(f'ZIP archive extracted using zipfile: {filename}')
                return True, None
            elif filename.lower().endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2')):
                import tarfile
                with tarfile.open(temp_archive_path, 'r:*') as tar_ref:
                    tar_ref.extractall(extract_path)
                logger.info(f'TAR archive extracted using tarfile: {filename}')
                return True, None
            elif filename.lower().endswith('.rar'):
                # Try unrar command
                unrar = shutil.which('unrar')
                if unrar:
                    result = subprocess.run([unrar, 'x', '-y', temp_archive_path, extract_path], 
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        logger.info(f'RAR archive extracted using unrar: {filename}')
                        return True, None
                    else:
                        logger.error(f'unrar failed: {result.stderr}')
                        return False, f'unrar failed: {result.stderr}'
                else:
                    logger.error('unrar not found for RAR extraction')
                    return False, 'unrar not found for RAR extraction'
            else:
                # Try 7z as last resort
                sevenzip = shutil.which('7z') or shutil.which('7za')
                if sevenzip:
                    result = subprocess.run([sevenzip, 'x', '-y', f'-o{extract_path}', temp_archive_path], 
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        logger.info(f'Archive extracted using 7z: {filename}')
                        return True, None
                    else:
                        logger.error(f'7z extraction failed: {result.stderr}')
                        return False, f'7z extraction failed: {result.stderr}'
                else:
                    logger.error('No suitable extraction tool found')
                    return False, 'No suitable extraction tool found'
        except Exception as e:
            logger.error(f'All extraction methods failed: {e}')
            return False, f'All extraction methods failed: {e}'
    
    logger.error(f'Could not extract archive: {filename}')
    return False, f'Could not extract archive: {filename}'


# Check file command support at module level
FILE_CMD_OK = check_file_command_supports_mime()
