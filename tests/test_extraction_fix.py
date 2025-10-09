"""
Comprehensive unit tests for the archive extraction fix.
Tests various extraction scenarios including edge cases.
"""

import os
import sys
import tempfile
import shutil
import zipfile
import tarfile
import pytest
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.file_operations import extract_archive_async, check_file_command_supports_mime


class TestExtractionFix:
    """Test suite for archive extraction functionality"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        # Cleanup after test
        if os.path.exists(temp_path):
            shutil.rmtree(temp_path, ignore_errors=True)
    
    @pytest.fixture
    def sample_zip(self, temp_dir):
        """Create a sample ZIP file for testing"""
        zip_path = os.path.join(temp_dir, 'test_archive.zip')
        
        # Create some test files
        test_files = {
            'file1.txt': b'This is test file 1',
            'file2.txt': b'This is test file 2',
            'subdir/file3.txt': b'This is test file 3 in subdirectory'
        }
        
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for filename, content in test_files.items():
                zf.writestr(filename, content)
        
        return zip_path, test_files
    
    @pytest.fixture
    def sample_tar(self, temp_dir):
        """Create a sample TAR file for testing"""
        tar_path = os.path.join(temp_dir, 'test_archive.tar')
        
        # Create a temporary directory with test files
        content_dir = os.path.join(temp_dir, 'tar_content')
        os.makedirs(content_dir, exist_ok=True)
        
        test_files = {
            'file1.txt': b'Tar test file 1',
            'file2.txt': b'Tar test file 2'
        }
        
        for filename, content in test_files.items():
            file_path = os.path.join(content_dir, filename)
            with open(file_path, 'wb') as f:
                f.write(content)
        
        # Create tar archive
        with tarfile.open(tar_path, 'w') as tf:
            for filename in test_files.keys():
                file_path = os.path.join(content_dir, filename)
                tf.add(file_path, arcname=filename)
        
        return tar_path, test_files
    
    def test_extract_valid_zip_with_zipfile(self, temp_dir, sample_zip):
        """Test extracting a valid ZIP file using Python's zipfile module"""
        zip_path, expected_files = sample_zip
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        # Extract the archive
        success, error_msg = extract_archive_async(zip_path, extract_dir, 'test_archive.zip')
        
        # Verify success
        assert success is True, f"Extraction should succeed, but got error: {error_msg}"
        assert error_msg is None
        
        # Verify all files were extracted
        for filename, expected_content in expected_files.items():
            extracted_path = os.path.join(extract_dir, filename)
            assert os.path.exists(extracted_path), f"File {filename} should be extracted"
            
            with open(extracted_path, 'rb') as f:
                actual_content = f.read()
                assert actual_content == expected_content, f"Content of {filename} should match"
    
    def test_extract_valid_tar_with_tarfile(self, temp_dir, sample_tar):
        """Test extracting a valid TAR file using Python's tarfile module"""
        tar_path, expected_files = sample_tar
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        # Extract the archive
        success, error_msg = extract_archive_async(tar_path, extract_dir, 'test_archive.tar')
        
        # Verify success
        assert success is True, f"Extraction should succeed, but got error: {error_msg}"
        assert error_msg is None
        
        # Verify all files were extracted
        for filename, expected_content in expected_files.items():
            extracted_path = os.path.join(extract_dir, filename)
            assert os.path.exists(extracted_path), f"File {filename} should be extracted"
            
            with open(extracted_path, 'rb') as f:
                actual_content = f.read()
                assert actual_content == expected_content, f"Content of {filename} should match"
    
    def test_extract_nonexistent_file(self, temp_dir):
        """Test extracting a file that doesn't exist"""
        nonexistent_path = os.path.join(temp_dir, 'nonexistent.zip')
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        # Try to extract
        success, error_msg = extract_archive_async(nonexistent_path, extract_dir, 'nonexistent.zip')
        
        # Should fail
        assert success is False
        assert error_msg is not None
        assert 'does not exist' in error_msg.lower()
    
    def test_extract_invalid_zip(self, temp_dir):
        """Test extracting an invalid/corrupted ZIP file"""
        # Create a file with invalid ZIP content
        invalid_zip = os.path.join(temp_dir, 'invalid.zip')
        with open(invalid_zip, 'wb') as f:
            f.write(b'This is not a valid ZIP file content')
        
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        # Try to extract
        success, error_msg = extract_archive_async(invalid_zip, extract_dir, 'invalid.zip')
        
        # Should fail gracefully
        assert success is False
        assert error_msg is not None
    
    def test_extract_with_patoolib_unavailable(self, temp_dir, sample_zip):
        """Test extraction when patoolib is unavailable (simulates Termux scenario)"""
        zip_path, expected_files = sample_zip
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        # Mock check_file_command_supports_mime to return False
        with patch('utils.file_operations.check_file_command_supports_mime', return_value=False):
            # Extract should still work using zipfile fallback
            success, error_msg = extract_archive_async(zip_path, extract_dir, 'test_archive.zip')
            
            # Verify success
            assert success is True, f"Extraction should succeed with fallback, but got error: {error_msg}"
            assert error_msg is None
            
            # Verify files were extracted
            for filename in expected_files.keys():
                extracted_path = os.path.join(extract_dir, filename)
                assert os.path.exists(extracted_path), f"File {filename} should be extracted"
    
    def test_extract_with_patoolib_failure(self, temp_dir, sample_zip):
        """Test extraction when patoolib fails but fallback succeeds"""
        zip_path, expected_files = sample_zip
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        # Mock patoolib to raise an exception
        with patch('utils.file_operations.check_file_command_supports_mime', return_value=True):
            with patch('patoolib.extract_archive', side_effect=Exception("Patoolib failed")):
                # Extract should still work using zipfile fallback
                success, error_msg = extract_archive_async(zip_path, extract_dir, 'test_archive.zip')
                
                # Verify success with fallback
                assert success is True, f"Extraction should succeed with fallback, but got error: {error_msg}"
                assert error_msg is None
    
    def test_extract_zip_with_subdirectories(self, temp_dir):
        """Test extracting a ZIP file with nested directory structure"""
        zip_path = os.path.join(temp_dir, 'nested.zip')
        
        # Create ZIP with nested structure
        test_structure = {
            'root.txt': b'Root file',
            'dir1/file1.txt': b'File in dir1',
            'dir1/subdir/file2.txt': b'File in nested subdir',
            'dir2/file3.txt': b'File in dir2'
        }
        
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for filename, content in test_structure.items():
                zf.writestr(filename, content)
        
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        # Extract
        success, error_msg = extract_archive_async(zip_path, extract_dir, 'nested.zip')
        
        # Verify success
        assert success is True, f"Extraction should succeed, but got error: {error_msg}"
        
        # Verify all files and directories were created
        for filename, expected_content in test_structure.items():
            extracted_path = os.path.join(extract_dir, filename)
            assert os.path.exists(extracted_path), f"File {filename} should be extracted"
            
            with open(extracted_path, 'rb') as f:
                actual_content = f.read()
                assert actual_content == expected_content
    
    def test_extract_large_zip(self, temp_dir):
        """Test extracting a ZIP file with many files"""
        zip_path = os.path.join(temp_dir, 'large.zip')
        
        # Create ZIP with many files
        num_files = 100
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for i in range(num_files):
                filename = f'file_{i:03d}.txt'
                content = f'Content of file {i}'.encode()
                zf.writestr(filename, content)
        
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        # Extract
        success, error_msg = extract_archive_async(zip_path, extract_dir, 'large.zip')
        
        # Verify success
        assert success is True, f"Extraction should succeed, but got error: {error_msg}"
        
        # Verify all files were extracted
        extracted_files = os.listdir(extract_dir)
        assert len(extracted_files) == num_files, f"Should extract {num_files} files"
    
    def test_extract_empty_zip(self, temp_dir):
        """Test extracting an empty ZIP file"""
        zip_path = os.path.join(temp_dir, 'empty.zip')
        
        # Create empty ZIP
        with zipfile.ZipFile(zip_path, 'w') as zf:
            pass  # No files added
        
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        # Extract
        success, error_msg = extract_archive_async(zip_path, extract_dir, 'empty.zip')
        
        # Should succeed even though no files
        assert success is True, f"Extraction should succeed, but got error: {error_msg}"
    
    def test_extract_with_special_characters_in_filename(self, temp_dir):
        """Test extracting files with special characters in names"""
        zip_path = os.path.join(temp_dir, 'special_chars.zip')
        
        # Create ZIP with special character filenames
        test_files = {
            'file with spaces.txt': b'File with spaces',
            'file-with-dashes.txt': b'File with dashes',
            'file_with_underscores.txt': b'File with underscores',
            'file.multiple.dots.txt': b'File with dots'
        }
        
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for filename, content in test_files.items():
                zf.writestr(filename, content)
        
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        # Extract
        success, error_msg = extract_archive_async(zip_path, extract_dir, 'special_chars.zip')
        
        # Verify success
        assert success is True, f"Extraction should succeed, but got error: {error_msg}"
        
        # Verify all files were extracted
        for filename in test_files.keys():
            extracted_path = os.path.join(extract_dir, filename)
            assert os.path.exists(extracted_path), f"File {filename} should be extracted"
    
    def test_check_file_command_supports_mime(self):
        """Test the file command check function"""
        # This test just verifies the function doesn't crash
        result = check_file_command_supports_mime()
        assert isinstance(result, bool), "Should return a boolean value"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
