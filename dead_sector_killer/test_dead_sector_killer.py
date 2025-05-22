import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import sys
import io
import errno
import uuid # For predictable UUIDs in tests

# Assuming dead_sector_killer.py is in the same directory or accessible in PYTHONPATH
from dead_sector_killer import (
    get_filesystem_info,
    prepare_quarantine_directory,
    fill_free_space,
    check_file_integrity,
    process_filler_files,
    list_quarantine_files,
    delete_quarantine_files,
    get_human_readable_size, # Helper, might be useful
    QUARANTINE_DIR_NAME
)

class TestGetFilesystemInfo(unittest.TestCase):

    @patch('psutil.disk_usage')
    def test_get_filesystem_info_success(self, mock_disk_usage):
        mock_disk_usage.return_value = MagicMock(free=1000, total=2000, used=1000)
        expected = {"free_space": 1000, "total_space": 2000, "used_space": 1000}
        result = get_filesystem_info('/fake/path')
        self.assertEqual(result, expected)

    @patch('psutil.disk_usage', side_effect=FileNotFoundError("Path not found"))
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_get_filesystem_info_path_not_found(self, mock_stdout, mock_disk_usage):
        result = get_filesystem_info('/nonexistent/path')
        self.assertIsNone(result)
        self.assertIn("Error: Filesystem path '/nonexistent/path' not found.", mock_stdout.getvalue())

    @patch('psutil.disk_usage', side_effect=Exception("Some other error"))
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_get_filesystem_info_other_exception(self, mock_stdout, mock_disk_usage):
        result = get_filesystem_info('/fake/path')
        self.assertIsNone(result)
        self.assertIn("Error: Could not retrieve disk usage for '/fake/path'. Exception: Some other error", mock_stdout.getvalue())


class TestPrepareQuarantineDirectory(unittest.TestCase):

    @patch('os.makedirs')
    @patch('os.path.exists', return_value=False)
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_prepare_quarantine_directory_creates_new(self, mock_stdout, mock_exists, mock_makedirs):
        target_path = '/fake/target'
        expected_quarantine_path = os.path.join(target_path, QUARANTINE_DIR_NAME)
        result = prepare_quarantine_directory(target_path)
        mock_exists.assert_called_once_with(expected_quarantine_path)
        mock_makedirs.assert_called_once_with(expected_quarantine_path)
        self.assertEqual(result, expected_quarantine_path)
        self.assertIn(f"Info: Created quarantine directory at '{expected_quarantine_path}'.", mock_stdout.getvalue())

    @patch('os.makedirs')
    @patch('os.path.exists', return_value=True)
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_prepare_quarantine_directory_already_exists(self, mock_stdout, mock_exists, mock_makedirs):
        target_path = '/fake/target'
        expected_quarantine_path = os.path.join(target_path, QUARANTINE_DIR_NAME)
        result = prepare_quarantine_directory(target_path)
        mock_exists.assert_called_once_with(expected_quarantine_path)
        mock_makedirs.assert_not_called()
        self.assertEqual(result, expected_quarantine_path)
        self.assertIn(f"Info: Quarantine directory already exists at '{expected_quarantine_path}'.", mock_stdout.getvalue())

    @patch('os.makedirs', side_effect=OSError("Creation failed"))
    @patch('os.path.exists', return_value=False)
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_prepare_quarantine_directory_creation_fails(self, mock_stdout, mock_exists, mock_makedirs):
        target_path = '/fake/target'
        expected_quarantine_path = os.path.join(target_path, QUARANTINE_DIR_NAME)
        result = prepare_quarantine_directory(target_path)
        mock_exists.assert_called_once_with(expected_quarantine_path)
        mock_makedirs.assert_called_once_with(expected_quarantine_path)
        self.assertIsNone(result)
        self.assertIn(f"Error: Could not create quarantine directory at '{expected_quarantine_path}'. OSError: Creation failed", mock_stdout.getvalue())


class TestFillFreeSpace(unittest.TestCase):
    def setUp(self):
        # Default mocks for most tests in this class
        self.mock_fs_info = {'free_space': 200 * 1024 * 1024, 'total_space': 500 * 1024 * 1024, 'used_space': 300 * 1024 * 1024}

    @patch('dead_sector_killer.get_filesystem_info')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.join', side_effect=lambda *args: "/".join(args)) # Simple join for testing
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_fill_free_space_success_partial_fill(self, mock_stdout, mock_os_join, mock_open_func, mock_get_fs_info):
        mock_get_fs_info.return_value = self.mock_fs_info
        
        # Target 50% of 200MB free space = 100MB. Filler file size 40MB. Expect 3 files (40, 40, 20)
        created_files, write_errors = fill_free_space(
            filesystem_path='/fake/fs',
            quarantine_dir_path='/fake/fs/.quarantine_files',
            filler_file_size_mb=40,
            fill_percentage=50
        )
        
        self.assertEqual(len(created_files), 3)
        self.assertEqual(created_files[0], '/fake/fs/.quarantine_files/filler_0001.tmp')
        self.assertEqual(created_files[1], '/fake/fs/.quarantine_files/filler_0002.tmp')
        self.assertEqual(created_files[2], '/fake/fs/.quarantine_files/filler_0003.tmp')
        self.assertEqual(len(write_errors), 0)

        # Check open calls: file path and mode
        self.assertEqual(mock_open_func.call_count, 3)
        mock_open_func.assert_any_call('/fake/fs/.quarantine_files/filler_0001.tmp', 'wb')
        mock_open_func.assert_any_call('/fake/fs/.quarantine_files/filler_0002.tmp', 'wb')
        mock_open_func.assert_any_call('/fake/fs/.quarantine_files/filler_0003.tmp', 'wb')

        # Check write calls (bytes written)
        # File 1: 40MB
        # File 2: 40MB
        # File 3: 20MB (to reach 100MB total)
        # Each write is 1MB chunk
        total_write_calls = (40) + (40) + (20) 
        self.assertEqual(mock_open_func().write.call_count, total_write_calls)
        
        output = mock_stdout.getvalue()
        self.assertIn("Targeting 50% of free space.", output)
        self.assertIn("Target space to fill: 100.00MB", output)
        self.assertIn("Creating filler file: filler_0001.tmp (Size: 40.00MB)", output)
        self.assertIn("Creating filler file: filler_0002.tmp (Size: 40.00MB)", output)
        self.assertIn("Creating filler file: filler_0003.tmp (Size: 20.00MB)", output)
        self.assertIn("Actually filled: 100.00MB across 3 files.", output)


    @patch('dead_sector_killer.get_filesystem_info')
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_fill_free_space_target_zero(self, mock_stdout, mock_get_fs_info):
        mock_get_fs_info.return_value = {'free_space': 10 * 1024 * 1024} # 10MB free
        
        created_files, write_errors = fill_free_space(
            filesystem_path='/fake/fs',
            quarantine_dir_path='/fake/fs/.quarantine_files',
            filler_file_size_mb=20,
            fill_percentage=0 # 0% of free space
        )
        self.assertEqual(len(created_files), 0)
        self.assertEqual(len(write_errors), 0)
        self.assertIn("Info: No space to fill", mock_stdout.getvalue())

        # Test with very low free space resulting in 0 target bytes
        mock_get_fs_info.return_value = {'free_space': 100} # 100 bytes free
        created_files, write_errors = fill_free_space(
            filesystem_path='/fake/fs',
            quarantine_dir_path='/fake/fs/.quarantine_files',
            filler_file_size_mb=1, # 1MB filler files
            fill_percentage=10 # 10% of 100 bytes is 10 bytes, less than 1MB
        )
        self.assertEqual(len(created_files), 0)
        self.assertEqual(len(write_errors), 0)
        self.assertIn("Info: No space to fill", mock_stdout.getvalue())


    @patch('dead_sector_killer.get_filesystem_info')
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_fill_free_space_filler_size_zero(self, mock_stdout, mock_get_fs_info):
        mock_get_fs_info.return_value = self.mock_fs_info
        created_files, write_errors = fill_free_space(
            filesystem_path='/fake/fs',
            quarantine_dir_path='/fake/fs/.quarantine_files',
            filler_file_size_mb=0, # 0 MB filler files
            fill_percentage=50
        )
        self.assertEqual(len(created_files), 0)
        self.assertEqual(len(write_errors), 1)
        self.assertEqual(write_errors[0][0], "Configuration Error")
        self.assertIn("Error: Filler file size cannot be 0 MB.", mock_stdout.getvalue())

    @patch('dead_sector_killer.get_filesystem_info')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.join', side_effect=lambda *args: "/".join(args))
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_fill_free_space_write_error_enospc(self, mock_stdout, mock_os_join, mock_open_func, mock_get_fs_info):
        mock_get_fs_info.return_value = self.mock_fs_info # 200MB free
        
        # Make write fail on the second chunk of the first file
        mock_file_handle = mock_open_func.return_value
        mock_file_handle.write.side_effect = [
            None, # First 1MB chunk succeeds
            IOError(errno.ENOSPC, "No space left on device"), # Second 1MB chunk fails
            # Subsequent writes for other files should not happen
        ]

        created_files, write_errors = fill_free_space(
            filesystem_path='/fake/fs',
            quarantine_dir_path='/fake/fs/.quarantine_files',
            filler_file_size_mb=100, # Try to write one 100MB file
            fill_percentage=80 # Target 160MB
        )
        
        self.assertEqual(len(created_files), 0) # File creation failed
        self.assertEqual(len(write_errors), 1)
        self.assertEqual(write_errors[0][0], '/fake/fs/.quarantine_files/filler_0001.tmp')
        self.assertIn("No space left on device", write_errors[0][1])
        
        output = mock_stdout.getvalue()
        self.assertIn("Creating filler file: filler_0001.tmp", output)
        self.assertIn("IOError writing to /fake/fs/.quarantine_files/filler_0001.tmp", output)
        self.assertIn("Warning: Disk ran out of space. Stopping filler file creation.", output)
        # Ensure it doesn't try to create more files
        self.assertNotIn("Creating filler file: filler_0002.tmp", output)

    @patch('dead_sector_killer.get_filesystem_info')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.join', side_effect=lambda *args: "/".join(args))
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_fill_free_space_write_error_other(self, mock_stdout, mock_os_join, mock_open_func, mock_get_fs_info):
        mock_get_fs_info.return_value = self.mock_fs_info # 200MB free
        
        mock_file_handle = mock_open_func.return_value
        generic_io_error = IOError("Some other disk error")

        # Fail on first file, succeed on second
        def write_side_effect(*args, **kwargs):
            # Allow inspecting which file is being written, not straightforward with just mock_open
            # This is a simplified check; real check is on created_files / write_errors
            current_call_count = mock_open_func().write.call_count
            if mock_open_func.call_count == 1 and current_call_count == 1: # First write of first file
                 raise generic_io_error
            return None # Success for other writes

        mock_file_handle.write.side_effect = write_side_effect
        
        created_files, write_errors = fill_free_space(
            filesystem_path='/fake/fs',
            quarantine_dir_path='/fake/fs/.quarantine_files',
            filler_file_size_mb=10, # Small files, attempt to create multiple
            fill_percentage=15 # Target 30MB -> try for 3 files
        )
        
        # First file should be in errors, second and third should be created
        self.assertEqual(len(created_files), 2) # filler_0002.tmp, filler_0003.tmp
        self.assertEqual(created_files[0], '/fake/fs/.quarantine_files/filler_0002.tmp')
        self.assertEqual(created_files[1], '/fake/fs/.quarantine_files/filler_0003.tmp')
        
        self.assertEqual(len(write_errors), 1)
        self.assertEqual(write_errors[0][0], '/fake/fs/.quarantine_files/filler_0001.tmp')
        self.assertIn("Some other disk error", write_errors[0][1])
        
        output = mock_stdout.getvalue()
        self.assertIn("Creating filler file: filler_0001.tmp", output)
        self.assertIn("IOError writing to /fake/fs/.quarantine_files/filler_0001.tmp", output)
        self.assertNotIn("Warning: Disk ran out of space", output) # Should not stop for generic error
        self.assertIn("Creating filler file: filler_0002.tmp", output) # Attempted next file
        self.assertIn("Creating filler file: filler_0003.tmp", output)


class TestCheckFileIntegrity(unittest.TestCase):

    @patch('os.path.getsize', return_value=2*1024*1024) # 2MB file
    @patch('builtins.open', new_callable=mock_open)
    @patch('sys.stdout', new_callable=io.StringIO) # To suppress progress print
    def test_check_file_integrity_success(self, mock_stdout, mock_open_func, mock_getsize):
        mock_file_handle = mock_open_func.return_value
        # Simulate reading 1MB chunks for a 2MB file
        mock_file_handle.read.side_effect = [b'a'*(1024*1024), b'b'*(1024*1024), b''] 
        
        is_ok, message = check_file_integrity('/fake/file.tmp')
        
        self.assertTrue(is_ok)
        self.assertEqual(message, "File read successfully")
        mock_getsize.assert_called_once_with('/fake/file.tmp')
        mock_open_func.assert_called_once_with('/fake/file.tmp', 'rb')
        self.assertEqual(mock_file_handle.read.call_count, 3)

    @patch('os.path.getsize', return_value=1024*1024) # 1MB file
    @patch('builtins.open', new_callable=mock_open)
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_check_file_integrity_read_error(self, mock_stdout, mock_open_func, mock_getsize):
        mock_file_handle = mock_open_func.return_value
        mock_file_handle.read.side_effect = IOError("Disk read error")

        is_ok, message = check_file_integrity('/fake/file.tmp')
        
        self.assertFalse(is_ok)
        self.assertIn("Read error: Disk read error", message)
        self.assertIn("Read error in /fake/file.tmp at offset ~0B: Disk read error", mock_stdout.getvalue())


    @patch('os.path.getsize', side_effect=FileNotFoundError("No such file"))
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_check_file_integrity_file_not_found_size(self, mock_stdout, mock_getsize):
        is_ok, message = check_file_integrity('/fake/file.tmp')
        self.assertFalse(is_ok)
        self.assertEqual(message, "File not found")
        self.assertIn("Error: File not found during size check: /fake/file.tmp", mock_stdout.getvalue())

    @patch('os.path.getsize', return_value=1024) # Exists for size check
    @patch('builtins.open', side_effect=FileNotFoundError("No such file on open"))
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_check_file_integrity_file_not_found_open(self, mock_stdout, mock_open_func, mock_getsize):
        is_ok, message = check_file_integrity('/fake/file.tmp')
        self.assertFalse(is_ok)
        self.assertEqual(message, "File not found")
        self.assertIn("Error: File not found when trying to open: /fake/file.tmp", mock_stdout.getvalue())

    @patch('os.path.getsize', return_value=0)
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_check_file_integrity_zero_byte_file(self, mock_stdout, mock_getsize):
        is_ok, message = check_file_integrity('/fake/file.tmp')
        self.assertTrue(is_ok)
        self.assertEqual(message, "File is zero bytes and considered intact.")
        self.assertIn("Integrity check PASSED for: /fake/file.tmp (Zero-byte file)", mock_stdout.getvalue())


class TestProcessFillerFiles(unittest.TestCase):

    @patch('os.remove')
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_process_healthy_files_deleted(self, mock_stdout, mock_os_remove):
        healthy_files = ['/q/h1.tmp', '/q/h2.tmp']
        bad_files = []
        retained, deleted_count = process_filler_files('/q', healthy_files, bad_files)
        
        self.assertEqual(deleted_count, 2)
        self.assertEqual(len(retained), 0)
        mock_os_remove.assert_any_call('/q/h1.tmp')
        mock_os_remove.assert_any_call('/q/h2.tmp')
        self.assertIn("Deleting healthy file: /q/h1.tmp", mock_stdout.getvalue())

    @patch('os.remove', side_effect=OSError("Permission denied"))
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_process_healthy_files_delete_error(self, mock_stdout, mock_os_remove):
        healthy_files = ['/q/h1.tmp']
        bad_files = []
        retained, deleted_count = process_filler_files('/q', healthy_files, bad_files)
        
        self.assertEqual(deleted_count, 0)
        self.assertEqual(len(retained), 0)
        self.assertIn("Error deleting healthy file /q/h1.tmp: Permission denied", mock_stdout.getvalue())

    @patch('uuid.uuid4')
    @patch('os.rename')
    @patch('os.path.exists') # To control uniqueness check and original file existence
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_process_bad_files_retained_renamed(self, mock_stdout, mock_path_exists, mock_os_rename, mock_uuid):
        # Ensure os.path.exists returns True for original file, False for new unique name
        mock_path_exists.side_effect = lambda path: path == '/q/b1.tmp' # Only original exists
        
        mock_uuid.return_value = MagicMock(hex='testuuid')
        
        bad_files = [('/q/b1.tmp', "Read error at sector X")]
        healthy_files = []
        
        retained, deleted_count = process_filler_files('/q', healthy_files, bad_files)
        
        self.assertEqual(deleted_count, 0)
        self.assertEqual(len(retained), 1)
        expected_new_name = '/q/b1.quarantined.testuuid.bad'
        self.assertEqual(retained[0][0], expected_new_name)
        self.assertEqual(retained[0][1], "Read error at sector X")
        mock_os_rename.assert_called_once_with('/q/b1.tmp', expected_new_name)
        self.assertIn(f"Retaining bad file: /q/b1.tmp as {expected_new_name}", mock_stdout.getvalue())

    @patch('uuid.uuid4')
    @patch('os.rename', side_effect=OSError("Cannot rename"))
    @patch('os.path.exists', return_value=True) # Original file exists
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_process_bad_files_rename_error(self, mock_stdout, mock_path_exists, mock_os_rename, mock_uuid):
        mock_uuid.return_value = MagicMock(hex='testuuid')
        bad_files = [('/q/b1.tmp', "Disk error")]
        healthy_files = []

        retained, deleted_count = process_filler_files('/q', healthy_files, bad_files)

        self.assertEqual(deleted_count, 0)
        self.assertEqual(len(retained), 1)
        # Should retain original path with error message about rename failure
        self.assertEqual(retained[0][0], '/q/b1.tmp') 
        self.assertIn("Original error: Disk error", retained[0][1])
        self.assertIn("Rename failed: Cannot rename", retained[0][1])
        self.assertIn("Error renaming bad file /q/b1.tmp", mock_stdout.getvalue())

    @patch('uuid.uuid4')
    @patch('os.rename') # Should not be called
    @patch('os.path.exists', return_value=False) # Original file does NOT exist
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_process_bad_files_original_not_found_for_rename(self, mock_stdout, mock_path_exists, mock_os_rename, mock_uuid):
        mock_uuid.return_value = MagicMock(hex='testuuid')
        bad_files = [('/q/b1_nonexistent.tmp', "Creation error, never existed")]
        healthy_files = []

        retained, deleted_count = process_filler_files('/q', healthy_files, bad_files)

        self.assertEqual(deleted_count, 0)
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0][0], '/q/b1_nonexistent.tmp')
        self.assertIn("File was not found for rename", retained[0][1])
        mock_os_rename.assert_not_called()
        self.assertIn("Warning: Original bad file /q/b1_nonexistent.tmp not found for renaming.", mock_stdout.getvalue())


class TestListQuarantineFiles(unittest.TestCase):

    @patch('os.path.isfile', return_value=True)
    @patch('os.listdir', return_value=['file1.bad', 'file2.quarantined'])
    @patch('os.path.exists', return_value=True)
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_list_quarantine_files_success(self, mock_stdout, mock_exists, mock_listdir, mock_isfile):
        list_quarantine_files('/q_test')
        output = mock_stdout.getvalue()
        self.assertIn("--- Quarantined Files in /q_test ---", output)
        self.assertIn("- file1.bad", output)
        self.assertIn("- file2.quarantined", output)
        mock_listdir.assert_called_once_with('/q_test')

    @patch('os.listdir', return_value=[])
    @patch('os.path.exists', return_value=True)
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_list_quarantine_files_empty(self, mock_stdout, mock_exists, mock_listdir):
        list_quarantine_files('/q_empty')
        output = mock_stdout.getvalue()
        self.assertIn("No files found in the quarantine directory.", output)

    @patch('os.path.exists', return_value=False)
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_list_quarantine_files_dir_not_found(self, mock_stdout, mock_exists):
        list_quarantine_files('/q_nonexistent')
        output = mock_stdout.getvalue()
        self.assertIn("Error: Quarantine directory '/q_nonexistent' not found.", output)


class TestDeleteQuarantineFiles(unittest.TestCase):

    @patch('os.remove')
    @patch('builtins.input', return_value='yes')
    @patch('os.path.isfile', return_value=True)
    @patch('os.listdir', return_value=['f1.bad', 'f2.bad'])
    @patch('os.path.exists', return_value=True) # For directory
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_delete_all_success(self, mock_stdout, mock_exists, mock_listdir, mock_isfile, mock_input, mock_remove):
        delete_quarantine_files('/q', delete_all=True)
        self.assertEqual(mock_remove.call_count, 2)
        mock_remove.assert_any_call(os.path.join('/q', 'f1.bad'))
        mock_remove.assert_any_call(os.path.join('/q', 'f2.bad'))
        self.assertIn("Successfully deleted: f1.bad", mock_stdout.getvalue())

    @patch('os.remove')
    @patch('builtins.input', return_value='no')
    @patch('os.path.isfile', return_value=True)
    @patch('os.listdir', return_value=['f1.bad'])
    @patch('os.path.exists', return_value=True)
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_delete_all_cancel(self, mock_stdout, mock_exists, mock_listdir, mock_isfile, mock_input, mock_remove):
        delete_quarantine_files('/q', delete_all=True)
        mock_remove.assert_not_called()
        self.assertIn("Deletion cancelled by user.", mock_stdout.getvalue())

    @patch('os.remove')
    @patch('builtins.input', return_value='yes')
    @patch('os.path.isfile', return_value=True) # For specific file
    @patch('os.path.exists') # For dir and specific file
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_delete_specific_success(self, mock_stdout, mock_exists, mock_isfile, mock_input, mock_remove):
        # os.path.exists needs to return True for dir, then True for file
        mock_exists.side_effect = [True, True] 
        delete_quarantine_files('/q', filename_to_delete='f1.bad')
        mock_remove.assert_called_once_with(os.path.join('/q', 'f1.bad'))
        self.assertIn("Successfully deleted: f1.bad", mock_stdout.getvalue())

    @patch('os.remove')
    @patch('os.path.isfile', return_value=False) # Specific file is not a file
    @patch('os.path.exists') # Dir exists, file does not
    @patch('sys.stdout', new_callable=io.StringIO)
    def test_delete_specific_not_found(self, mock_stdout, mock_exists, mock_isfile, mock_remove):
        mock_exists.side_effect = [True, False]
        delete_quarantine_files('/q', filename_to_delete='f1.bad')
        mock_remove.assert_not_called()
        self.assertIn("File 'f1.bad' not found in quarantine directory '/q'.", mock_stdout.getvalue())

    @patch('sys.stdout', new_callable=io.StringIO)
    @patch('os.path.exists', return_value=True) # Quarantine dir exists
    def test_delete_nothing_specified(self, mock_exists, mock_stdout):
        delete_quarantine_files('/q') # No filename, delete_all=False
        self.assertIn("Error: Specify a filename with --filename or use --all to delete all files.", mock_stdout.getvalue())


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
