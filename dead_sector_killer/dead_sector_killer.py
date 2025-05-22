import psutil
import os
import subprocess
import re
import time # For progress reporting delay
import argparse
import sys # For sys.stdout.reconfigure and sys.exit
import uuid


QUARANTINE_DIR_NAME = ".quarantine_files"

def get_filesystem_info(target_path):
    """Gets filesystem information for the given target path."""
    try:
        usage = psutil.disk_usage(target_path)
        return {
            "free_space": usage.free,
            "total_space": usage.total,
            "used_space": usage.used,
        }
    except FileNotFoundError:
        print(f"  Error: Filesystem path '{target_path}' not found.")
        return None
    except Exception as e:
        print(f"  Error: Could not retrieve disk usage for '{target_path}'. {type(e).__name__}: {e}")
        return None

def prepare_quarantine_directory(target_path):
    """Prepares the quarantine directory at the target path."""
    quarantine_path = os.path.join(target_path, QUARANTINE_DIR_NAME)
    if not os.path.exists(quarantine_path):
        try:
            os.makedirs(quarantine_path)
            print(f"  Info: Created quarantine directory at '{quarantine_path}'.")
        except OSError as e:
            print(f"  Error: Could not create quarantine directory at '{quarantine_path}'. {type(e).__name__}: {e}")
            return None
    else:
        print(f"  Info: Quarantine directory already exists at '{quarantine_path}'.")
    return quarantine_path

def fill_free_space(filesystem_path, quarantine_dir_path, filler_file_size_mb, fill_percentage):
    """Fills a percentage of free space with temporary files."""
    print(f"\n--- Filling Free Space on '{filesystem_path}' ---")
    print(f"  Targeting {fill_percentage}% of free space.")
    print(f"  Individual filler file size: {filler_file_size_mb} MB.")

    fs_info = get_filesystem_info(filesystem_path)
    if not fs_info:
        return [], [("Filesystem Info Error", f"Could not get free space for {filesystem_path}.")]

    free_space_bytes = fs_info['free_space']
    target_bytes_to_fill = int(free_space_bytes * (fill_percentage / 100.0))
    filler_file_size_bytes = filler_file_size_mb * 1024 * 1024

    if target_bytes_to_fill == 0:
        print("  Info: No space to fill (target fill amount is 0 bytes, possibly due to low free space or low percentage).")
        return [], []
    if filler_file_size_bytes == 0:
        print("  Error: Filler file size cannot be 0 MB.")
        return [], [("Configuration Error", "Filler file size is 0 MB.")]


    print(f"  Current free space: {get_human_readable_size(free_space_bytes)}")
    print(f"  Target space to fill: {get_human_readable_size(target_bytes_to_fill)}")

    total_bytes_written_overall = 0
    created_files_list = []
    write_errors = []
    file_index = 0
    # Use a reasonably sized chunk, e.g., 1MB, to avoid excessive memory usage for very large filler files
    # but also not too small to cause too many write calls.
    write_chunk_size = 1 * 1024 * 1024 # 1MB

    while total_bytes_written_overall < target_bytes_to_fill:
        file_index += 1
        filename = f"filler_{file_index:04d}.tmp"
        file_path = os.path.join(quarantine_dir_path, filename)
        
        # Determine how much to write for *this* file
        bytes_remaining_for_target = target_bytes_to_fill - total_bytes_written_overall
        current_file_target_size = min(filler_file_size_bytes, bytes_remaining_for_target)

        if current_file_target_size == 0: # No more space needed to reach overall target
            break

        print(f"  Creating filler file: {filename} (Size: {get_human_readable_size(current_file_target_size)})")
        
        bytes_written_for_this_file = 0
        try:
            with open(file_path, 'wb') as f:
                while bytes_written_for_this_file < current_file_target_size:
                    # Ensure we don't write more than needed for this file, or more than overall target
                    bytes_to_write_this_chunk = min(write_chunk_size, 
                                                    current_file_target_size - bytes_written_for_this_file)
                    
                    # This check is crucial to ensure we don't exceed the *overall* target_bytes_to_fill
                    # if the last chunk of the last file would make it go over.
                    if total_bytes_written_overall + bytes_written_for_this_file + bytes_to_write_this_chunk > target_bytes_to_fill:
                        bytes_to_write_this_chunk = target_bytes_to_fill - (total_bytes_written_overall + bytes_written_for_this_file)

                    if bytes_to_write_this_chunk <= 0: # Should not happen if outer loop condition is correct
                        break
                        
                    f.write(b'\0' * bytes_to_write_this_chunk) # Write null bytes for simplicity
                    bytes_written_for_this_file += bytes_to_write_this_chunk
            
            created_files_list.append(file_path)
            total_bytes_written_overall += bytes_written_for_this_file
            print(f"  Successfully wrote {filename}. Total space filled: {get_human_readable_size(total_bytes_written_overall)} / {get_human_readable_size(target_bytes_to_fill)}")

        except IOError as e:
            err_msg = f"IOError writing to {file_path}: {e}. This file might be on a bad sector or disk is full."
            print(f"  Error: {err_msg}")
            write_errors.append((file_path, err_msg))
            # If it's a "No space left on device" error, we should stop.
            if e.errno == 28: # ENOSPC
                print("  Warning: Disk ran out of space. Stopping filler file creation.")
                break 
            # For other IOErrors, we still try to continue with the next file, assuming it might be a localized bad sector.
        except OSError as e:
            err_msg = f"OSError creating/writing to {file_path}: {e}. This file might be on a bad sector or disk is full."
            print(f"  Error: {err_msg}")
            write_errors.append((file_path, err_msg))
            if e.errno == 28: # ENOSPC
                print("  Warning: Disk ran out of space. Stopping filler file creation.")
                break
            # For other OSErrors, attempt to continue
        except Exception as e: # Catch any other unexpected errors during file write
            err_msg = f"Unexpected error writing to {file_path}: {type(e).__name__} - {e}."
            print(f"  Error: {err_msg}")
            write_errors.append((file_path, err_msg))
            break # For unexpected errors, it's safer to stop the filling process.

    print("--- Fill Summary ---")
    print(f"  Targeted {fill_percentage}% of free space ({get_human_readable_size(target_bytes_to_fill)}).")
    print(f"  Actually filled: {get_human_readable_size(total_bytes_written_overall)} across {len(created_files_list)} files.")
    if write_errors:
        print(f"  Encountered {len(write_errors)} errors during file creation/writing.")
    return created_files_list, write_errors

def list_quarantine_files(quarantine_dir_path):
    """Lists files currently in the quarantine directory."""
    print(f"\n--- Quarantined Files in {quarantine_dir_path} ---")
    if not os.path.exists(quarantine_dir_path):
        print(f"  Error: Quarantine directory '{quarantine_dir_path}' not found.")
        return

    try:
        files = [f for f in os.listdir(quarantine_dir_path) if os.path.isfile(os.path.join(quarantine_dir_path, f))]
        if not files:
            print("  No files found in the quarantine directory.")
            return

        for filename in files:
            print(f"  - {filename}")
            # Optional: Add logic here to parse filename for error reasons if they are encoded.
            # For now, just listing names.
    except OSError as e:
        print(f"  Error: Could not list files in quarantine directory '{quarantine_dir_path}'. {type(e).__name__}: {e}")

def delete_quarantine_files(quarantine_dir_path, filename_to_delete=None, delete_all=False):
    """Deletes specific or all files from the quarantine directory."""
    print(f"\n--- Delete Quarantined Files from {quarantine_dir_path} ---")
    if not os.path.exists(quarantine_dir_path):
        print(f"  Error: Quarantine directory '{quarantine_dir_path}' not found.")
        return

    if not filename_to_delete and not delete_all:
        print("  Error: Specify a filename with --filename or use --all to delete all files.")
        return

    files_to_delete = []
    if delete_all:
        try:
            files_to_delete = [f for f in os.listdir(quarantine_dir_path) if os.path.isfile(os.path.join(quarantine_dir_path, f))]
            if not files_to_delete:
                print("  No files found to delete in the quarantine directory.")
                return
            confirm_msg = f"Are you sure you want to delete ALL {len(files_to_delete)} files from '{quarantine_dir_path}'? (yes/no): "
        except OSError as e:
            print(f"  Error: Could not list files for deletion in '{quarantine_dir_path}'. {type(e).__name__}: {e}")
            return
    elif filename_to_delete:
        full_file_path = os.path.join(quarantine_dir_path, filename_to_delete)
        if not os.path.exists(full_file_path) or not os.path.isfile(full_file_path):
            print(f"  Error: File '{filename_to_delete}' not found in quarantine directory '{quarantine_dir_path}'.")
            return
        files_to_delete.append(filename_to_delete) # Store only the basename for consistency in loop
        confirm_msg = f"Are you sure you want to delete '{filename_to_delete}' from '{quarantine_dir_path}'? (yes/no): "

    try:
        confirm = input(confirm_msg).strip().lower()
    except KeyboardInterrupt:
        print("\nDeletion cancelled by user (KeyboardInterrupt).")
        return

    if confirm != 'yes':
        print("Deletion cancelled by user.")
        return

    for filename in files_to_delete:
        file_path_to_delete = os.path.join(quarantine_dir_path, filename)
        try:
            os.remove(file_path_to_delete)
            print(f"  Successfully deleted: {filename}")
        except OSError as e:
            print(f"  Error deleting file {filename}: {e}")

def process_filler_files(quarantine_dir_path, healthy_files, bad_files_with_errors):
    """Processes filler files: deletes healthy ones, renames and retains bad ones."""
    print("\n--- Processing Filler Files (Retention/Deletion) ---")
    retained_files_info = []
    deleted_files_count = 0

    # Process Healthy Files
    print("  Processing healthy files for deletion...")
    for file_path in healthy_files:
        print(f"  Deleting healthy file: {file_path}")
        try:
            os.remove(file_path)
            deleted_files_count += 1
        except OSError as e:
            print(f"  Error deleting healthy file {file_path}: {e}")

    # Process Bad Files
    print("\n  Processing bad files for retention...")
    bad_file_rename_counter = 0 # Used if UUID somehow produces a collision, or as a fallback
    for file_path, error_message in bad_files_with_errors:
        original_basename = os.path.basename(file_path)
        base_name_no_ext, _ = os.path.splitext(original_basename) # Removes .tmp or any other extension
        
        unique_id = uuid.uuid4().hex[:8] # Generate 8-char hex UUID
        new_filename = f"{base_name_no_ext}.quarantined.{unique_id}.bad"
        new_file_path = os.path.join(quarantine_dir_path, new_filename)

        # Ensure uniqueness in the unlikely event of a hash collision
        while os.path.exists(new_file_path):
            bad_file_rename_counter += 1
            unique_id_collision = f"{unique_id}_{bad_file_rename_counter}"
            new_filename = f"{base_name_no_ext}.quarantined.{unique_id_collision}.bad"
            new_file_path = os.path.join(quarantine_dir_path, new_filename)
            if bad_file_rename_counter > 100: # Safety break for the loop
                print(f"  Critical Error: Could not generate a unique name for {file_path} after multiple attempts. Skipping rename.")
                # Add original file path with error to retained_info if it couldn't be renamed
                retained_files_info.append((file_path, f"Original error: {error_message}, Critical: Failed to generate unique rename path."))
                continue # Skip to next bad file

        print(f"  Retaining bad file: {file_path} as {new_file_path} due to: {error_message}")
        try:
            if not os.path.exists(file_path):
                # If the original file doesn't exist, it can't be renamed.
                # This might happen if it was a creation error and the file was never fully created or already cleaned up.
                print(f"  Warning: Original bad file {file_path} not found for renaming. It might have been an error during creation or already moved/deleted.")
                # Log the error for the original path as it's still a "bad" outcome.
                retained_files_info.append((file_path, f"Original error: {error_message}, File was not found for rename."))
                continue

            os.rename(file_path, new_file_path)
            retained_files_info.append((new_file_path, error_message))
        except OSError as e:
            print(f"  Error renaming bad file {file_path} to {new_file_path}: {e}. It might still exist with its original name if the error is non-critical.")
            # If rename fails, the original file (e.g. filler_xxxx.tmp) is still in the quarantine dir.
            # We should record this fact along with the original error.
            retained_files_info.append((file_path, f"Original error: {error_message}, Rename failed: {e}"))

    return retained_files_info, deleted_files_count

def check_file_integrity(file_path, read_chunk_size_kb=1024):
    """Checks the integrity of a file by reading it in chunks."""
    print(f"\n  Checking integrity of: {file_path}")
    total_bytes_read = 0
    read_chunk_size_bytes = read_chunk_size_kb * 1024
    file_name = os.path.basename(file_path)
    
    try:
        file_size = os.path.getsize(file_path)
        if file_size == 0: # Handle zero-byte files separately
            print(f"  Integrity check PASSED for: {file_path} (Zero-byte file)")
            return (True, "File is zero bytes and considered intact.")
    except FileNotFoundError:
        print(f"  Error: File not found during size check: {file_path}")
        return (False, "File not found")
    except OSError as e:
        print(f"  Error: Could not get size for {file_path}: {e}")
        return (False, f"Error getting file size: {e}")

    f = None  # Initialize f to None
    try:
        f = open(file_path, 'rb')
        last_progress_print_time = time.time()
        
        while True:
            try:
                chunk = f.read(read_chunk_size_bytes)
            except (IOError, OSError) as e:
                error_msg = f"Read error in {file_path} at offset ~{get_human_readable_size(total_bytes_read)}: {e}"
                print(f"  Error: {error_msg}")
                if f: f.close()
                return (False, f"Read error: {e}")

            if not chunk:
                break # End of file
            
            total_bytes_read += len(chunk)

            current_time = time.time()
            # Print progress every 2 seconds or if fully read
            if current_time - last_progress_print_time >= 2 or total_bytes_read == file_size:
                progress_percent = (total_bytes_read / file_size) * 100 if file_size > 0 else 100
                read_hr = get_human_readable_size(total_bytes_read)
                total_hr = get_human_readable_size(file_size)
                # Use \r for progress, but ensure final messages are on new lines
                sys.stdout.write(f"\r  Progress: Checked {read_hr} / {total_hr} ({progress_percent:.2f}%) for {file_name}...")
                sys.stdout.flush()
                last_progress_print_time = current_time
        
        sys.stdout.write("\r" + " " * 80 + "\r") # Clear progress line
        sys.stdout.flush()
        if total_bytes_read == file_size:
            print(f"  Integrity check PASSED for: {file_path}")
            if f: f.close()
            return (True, "File read successfully")
        else:
            # This case should ideally not be reached if EOF handling is correct
            # but is a safeguard.
            warn_msg = f"Unexpected EOF or read mismatch for {file_path}. Read {total_bytes_read}, expected {file_size}."
            print(f"  Warning: {warn_msg}")
            if f: f.close()
            return (False, warn_msg)

    except FileNotFoundError:
        # This specific check might be redundant if os.path.getsize already caught it, but good for safety.
        sys.stdout.write("\r" + " " * 80 + "\r") # Clear progress line
        sys.stdout.flush()
        print(f"  Error: File not found when trying to open: {file_path}")
        if f: f.close() # Should be None here, but defensive
        return (False, "File not found")
    except Exception as e: # Catch any other unexpected errors during open or loop setup
        sys.stdout.write("\r" + " " * 80 + "\r") # Clear progress line
        sys.stdout.flush()
        error_msg = f"An unexpected error occurred checking {file_path}: {type(e).__name__} - {e}"
        print(f"  Error: {error_msg}")
        if f: f.close()
        return (False, error_msg)
    finally:
        if f and not f.closed:
            f.close()


def get_human_readable_size(size_bytes):
    """Converts size in bytes to a human-readable format."""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = 0
    while size_bytes >= 1024 and i < len(size_name) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f}{size_name[i]}"

def list_disk_partitions_and_devices():
    """
    Lists detailed partition information and attempts to identify potential raw physical device names
    that can be used with --smart or --scan.
    """
    print("--- Available Disk Partitions and Mountpoints ---")
    try:
        partitions = psutil.disk_partitions(all=False) 
        if not partitions:
            print("  Info: No disk partitions found or all are filtered (e.g., optical drives).")
        else:
            for partition in partitions:
                print(f"  Device: {partition.device}")
                print(f"    Mountpoint: {partition.mountpoint}")
                print(f"    File system type: {partition.fstype}")
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    print(f"    Total Size: {get_human_readable_size(usage.total)}")
                    print(f"    Used: {get_human_readable_size(usage.used)}")
                    print(f"    Free: {get_human_readable_size(usage.free)}")
                    print(f"    Percentage Used: {usage.percent}%")
                except PermissionError:
                    print("    Usage: Permission denied to access disk usage information.")
                except FileNotFoundError:
                    print(f"    Usage: Mountpoint '{partition.mountpoint}' not found or not accessible.")
                except Exception as e:
                    print(f"    Usage: Could not retrieve usage info for {partition.mountpoint}. Error: {e}")
                print("-" * 20)
    except Exception as e:
        print(f"  Error: Could not retrieve disk partition list. {type(e).__name__}: {e}")


    print("\n--- Potential Raw Physical Devices for --scan or --smart ---")
    raw_devices_identified = set() # Use a different variable name to avoid confusion
    if os.name == 'posix':
        try:
            all_partitions_for_raw = psutil.disk_partitions(all=True)
            for p in all_partitions_for_raw:
                device_name = p.device
                if '/dev/mapper/' in device_name or '/dev/loop' in device_name:
                    continue
                match = re.match(r'(/dev/(?:sd[a-z]+|hd[a-z]+|vd[a-z]+|nvme[0-9]+n[0-9]+))p?[0-9]*$', device_name)
                if match:
                    raw_devices_identified.add(match.group(1))
                elif re.match(r'/dev/(?:sd[a-z]+|hd[a-z]+|vd[a-z]+|nvme[0-9]+n[0-9]+)$', device_name):
                    raw_devices_identified.add(device_name)
            
            valid_raw_devices = []
            import stat
            for dev_path in sorted(list(raw_devices_identified)):
                try:
                    if stat.S_ISBLK(os.stat(dev_path).st_mode):
                        valid_raw_devices.append(dev_path)
                except FileNotFoundError:
                    print(f"  Warning: Device {dev_path} listed but not found during verification.")
                except Exception as e:
                    print(f"  Warning: Could not verify device {dev_path}. Error: {e}")
            raw_devices_identified = valid_raw_devices
        except Exception as e:
            print(f"  Error: Failed to identify raw devices on POSIX. {type(e).__name__}: {e}")
    
    elif os.name == 'nt':
        print("  Info: On Windows, raw device names are typically like '\\\\.\\PhysicalDrive0', '\\\\.\\PhysicalDrive1'.")
        try:
            proc = subprocess.run(['wmic', 'diskdrive', 'get', 'DeviceID,Model'], 
                                  capture_output=True, text=True, check=False, shell=True, timeout=10)
            if proc.returncode == 0 and proc.stdout:
                lines = proc.stdout.strip().splitlines()
                if len(lines) > 1:
                    print("  Info: Found via WMIC (may require admin privileges for this script):")
                    for line in lines[1:]:
                        parts = line.strip().split()
                        if parts: raw_devices_identified.add(parts[0]) 
                else:
                    print("  Info: WMIC returned no disk drive data.")
            elif proc.stderr:
                print(f"  Warning: WMIC command failed or returned an error. Stderr: {proc.stderr.strip()}")
            else:
                 print(f"  Warning: WMIC command failed with return code {proc.returncode} and no stderr output.")
        except FileNotFoundError:
            print("  Error: WMIC command not found. Cannot list physical drives automatically on Windows.")
        except subprocess.TimeoutExpired:
            print("  Error: WMIC command timed out. Cannot list physical drives automatically on Windows.")
        except Exception as e:
            print(f"  Error: Failed to identify raw devices on Windows using WMIC. {type(e).__name__}: {e}")

    if raw_devices_identified:
        for dev in sorted(list(raw_devices_identified)): print(f"  - {dev}")
    else:
        print("  Info: No raw physical devices automatically identified. Specify the device path manually.")
        if os.name == 'posix': print("    Common Linux examples: /dev/sda, /dev/sdb, /dev/nvme0n1.")
    print("\nNote: For --scan or --smart, use the raw physical device path (e.g., /dev/sda on Linux).")


def _parse_smart_attributes(stdout_str):
    # (No changes to this helper function, assumed to be robust for its specific task)
    attributes_to_find = {"Reallocated_Sector_Ct": "N/A", "Current_Pending_Sector": "N/A", 
                          "Offline_Uncorrectable": "N/A", "Temperature_Celsius": "N/A", "Power_On_Hours": "N/A"}
    parsed_attributes = {}
    for line in stdout_str.splitlines():
        parts = re.split(r'\s+', line.strip())
        if len(parts) < 10: continue
        attr_name, raw_value = parts[1], parts[9]
        if attr_name in attributes_to_find: parsed_attributes[attr_name] = raw_value
    for key in attributes_to_find:
        if key not in parsed_attributes: parsed_attributes[key] = "N/A"
    return parsed_attributes

def get_smart_info(device_path):
    print(f"\n--- S.M.A.R.T. Information for {device_path} ---")
    try:
        subprocess.run(['smartctl', '--version'], capture_output=True, text=True, check=True, timeout=5)
    except FileNotFoundError:
        print("  Error: `smartctl` command not found. Please ensure smartmontools is installed and in your system's PATH.")
        return
    except subprocess.TimeoutExpired:
        print("  Warning: `smartctl --version` check timed out. Attempting S.M.A.R.T. query anyway...")
    except subprocess.CalledProcessError as e:
        print(f"  Warning: `smartctl --version` check failed (Return Code: {e.returncode}). Stderr: {e.stderr.strip()}. Attempting S.M.A.R.T. query anyway...")
    except Exception as e: # Catch any other unexpected error during version check
        print(f"  Warning: An unexpected error occurred during `smartctl --version` check: {e}. Attempting S.M.A.R.T. query anyway...")


    base_command = ['sudo', 'smartctl', '-A'] 
    device_types_to_try = [None, 'sat', 'ata', 'nvme', 'scsi']
    success = False
    for dev_type in device_types_to_try:
        command = list(base_command)
        if dev_type: command.extend(['-d', dev_type])
        command.append(device_path)
        
        action_desc = f"type: {dev_type}" if dev_type else "auto-detect"
        print(f"  Attempting with {action_desc}: {' '.join(command)}")
        try:
            process = subprocess.run(command, capture_output=True, text=True, check=False, timeout=15)
            stdout_str, stderr_str = process.stdout, process.stderr.strip().lower()

            if process.returncode == 0:
                if "s.m.a.r.t. support is: available" in stdout_str.lower() or \
                   "smart support is: enabled" in stdout_str.lower():
                    print("  Info: S.M.A.R.T. Attributes Found:")
                    attributes = _parse_smart_attributes(stdout_str)
                    for attr, value in attributes.items(): print(f"    - {attr}: {value}")
                    success = True; break
                elif "s.m.a.r.t. support is: unavailable" in stdout_str.lower() or \
                     "s.m.a.r.t. support is: disabled" in stdout_str.lower() or \
                     "device lacks s.m.a.r.t. capability" in stdout_str.lower():
                    print(f"  Info: Device {device_path} ({action_desc}) reports S.M.A.R.T. as unavailable or disabled.")
                    continue 
                else: 
                    print("  Info: S.M.A.R.T. Attributes (exit code 0, availability unclear, parsing response):")
                    attributes = _parse_smart_attributes(stdout_str)
                    for attr, value in attributes.items(): print(f"    - {attr}: {value}")
                    success = True; break
            else: 
                # smartctl exit codes are bitmasks, so just checking for non-zero is a basic approach
                # More specific error messages from stderr are more helpful
                if "permission denied" in stderr_str or "must be run as root" in stderr_str:
                    print(f"  Error: Permission denied for `{' '.join(command)}`. If not already, try running the script with sudo/administrator privileges."); return # No point retrying other types
                elif "unable to detect device type" in stderr_str:
                    print(f"  Info: `smartctl` ({action_desc}) was unable to automatically detect the device type for {device_path}.")
                elif "device open failed" in stderr_str or "no such device" in stderr_str:
                    print(f"  Error: Could not open device '{device_path}' with {action_desc}. Check device path. Stderr: {stderr_str if stderr_str else 'N/A'}")
                elif "device lacks s.m.a.r.t. capability" in stderr_str or "s.m.a.r.t. not available" in stderr_str:
                     print(f"  Info: Device '{device_path}' ({action_desc}) may lack S.M.A.R.T. capability. Stderr: {stderr_str if stderr_str else 'N/A'}")
                else: # Generic smartctl error
                    print(f"  Error: `smartctl` ({action_desc}) failed for {device_path} (Return Code: {process.returncode}). Stderr: {stderr_str if stderr_str else 'N/A'}")
        except subprocess.TimeoutExpired:
            print(f"  Error: `smartctl` command ('{' '.join(command)}') timed out.")
        except FileNotFoundError: # Should be caught by version check, but as a fallback for the main command
            print(f"  Error: `sudo` or `smartctl` command not found. Ensure smartmontools and sudo are installed and in PATH.")
            return # Fatal for this function
        except Exception as e:
            print(f"  Error: An unexpected issue occurred while running `smartctl` ({action_desc}): {type(e).__name__} - {e}")
    if not success:
        print(f"  Info: Failed to retrieve S.M.A.R.T. data for {device_path} after all attempts.")


def scan_disk(device_path, block_size_kb=64, scan_limit_gb=None):
    print(f"\n--- Disk Scan for {device_path} ---")
    if os.name != 'nt' and os.geteuid() != 0:
        print("  Error: Disk scanning requires root/administrator privileges. Please run the script using 'sudo'.")
        return

    block_size_bytes = block_size_kb * 1024
    fd = None
    bytes_read_total, errors_found = 0, 0 # Initialize here for summary if open fails
    error_locations = []
    total_bytes_to_scan_final = 0 # Initialize for summary

    try:
        print(f"  Info: Opening device: {device_path} (Block Size: {block_size_kb}KB, Limit: {scan_limit_gb or 'Full Disk'}GB)")
        open_flags = os.O_RDONLY
        if hasattr(os, 'O_SYNC'): open_flags |= os.O_SYNC
        fd = os.open(device_path, open_flags)
        
        os.lseek(fd, 0, os.SEEK_SET)
        disk_size_bytes = os.lseek(fd, 0, os.SEEK_END)
        os.lseek(fd, 0, os.SEEK_SET)
        print(f"  Info: Device Size: {get_human_readable_size(disk_size_bytes)}")

        total_bytes_to_scan_final = disk_size_bytes
        if scan_limit_gb is not None and scan_limit_gb > 0:
            limit_bytes = int(scan_limit_gb * (1024**3))
            if limit_bytes == 0 and scan_limit_gb > 0: limit_bytes = block_size_bytes
            total_bytes_to_scan_final = min(disk_size_bytes, limit_bytes)
            print(f"  Info: Effective Scan Limit: {get_human_readable_size(total_bytes_to_scan_final)}")
        else:
            print(f"  Info: Scanning up to: {get_human_readable_size(total_bytes_to_scan_final)}")
        if total_bytes_to_scan_final == 0 :
            print("  Info: Nothing to scan (device size or scan limit is zero).")
            return


        start_time = last_progress_print_time = time.time()
        print("  Info: Starting scan...")

        while bytes_read_total < total_bytes_to_scan_final:
            bytes_to_read_this_iteration = min(block_size_bytes, total_bytes_to_scan_final - bytes_read_total)
            try:
                block_data = os.read(fd, bytes_to_read_this_iteration)
                if not block_data:
                    if bytes_read_total < total_bytes_to_scan_final:
                        print(f"\n  Warning: Unexpected EOF at {get_human_readable_size(bytes_read_total)}. Expected {get_human_readable_size(total_bytes_to_scan_final)}.")
                    break
                bytes_read_total += len(block_data)
            except (IOError, OSError) as e:
                errors_found += 1
                current_offset_of_error = bytes_read_total 
                error_locations.append(current_offset_of_error)
                print(f"\n  Error: Read error at offset ~{get_human_readable_size(current_offset_of_error)}: {e}")
                try:
                    next_block_start_offset = current_offset_of_error + bytes_to_read_this_iteration
                    os.lseek(fd, next_block_start_offset, os.SEEK_SET)
                    print(f"  Info: Attempting to continue scan from offset {get_human_readable_size(next_block_start_offset)}")
                    bytes_read_total = next_block_start_offset 
                except (IOError, OSError) as seek_e:
                    print(f"  Critical: Seek failed after read error ({seek_e}). Aborting scan for this device.")
                    break
            
            current_time = time.time()
            if current_time - last_progress_print_time >= 1 or bytes_read_total == total_bytes_to_scan_final :
                progress_percent = (bytes_read_total / total_bytes_to_scan_final) * 100 if total_bytes_to_scan_final > 0 else 0
                scanned_hr, total_scan_hr = get_human_readable_size(bytes_read_total), get_human_readable_size(total_bytes_to_scan_final)
                elapsed_time = current_time - start_time
                speed_mb_s = (bytes_read_total / (1024**2)) / elapsed_time if elapsed_time > 0 else 0
                print(f"\r  Progress: {progress_percent:.2f}% ({scanned_hr}/{total_scan_hr}) | Speed: {speed_mb_s:.2f} MB/s | Errors: {errors_found}", end="")
                last_progress_print_time = current_time
        
        print("\n  Info: Scan finished.")
    except PermissionError: 
        print(f"  Error: Permission denied when opening or accessing {device_path}. Ensure you are running with sudo/administrator rights.")
        return 
    except FileNotFoundError:
        print(f"  Error: Device {device_path} not found.")
        return
    except Exception as e:
        print(f"\n  Error: An unexpected issue occurred during scan of {device_path}: {type(e).__name__} - {e}")
    finally:
        if fd is not None:
            try: os.close(fd); print(f"  Info: Device {device_path} closed.")
            except OSError as e: print(f"  Error: Could not close device {device_path}: {e}")

    print("\n--- Scan Summary ---")
    print(f"  Device Scanned: {device_path}")
    print(f"  Total Data Processed: {get_human_readable_size(bytes_read_total)} of {get_human_readable_size(total_bytes_to_scan_final)} planned")
    print(f"  Number of Read Errors Encountered: {errors_found}")
    if error_locations:
        print(f"  Approximate Error Locations (offsets from start of scan): {[get_human_readable_size(loc) for loc in error_locations]}")
    else:
        print("  Info: No read errors detected during this scan segment.")
    print("-" * 20)


def main(argv=None):
    """Main function to parse arguments and dispatch actions."""
    parser = argparse.ArgumentParser(
        description="DeadSectorKiller: A utility to list disks, check S.M.A.R.T. status, and scan for bad sectors.",
        formatter_class=argparse.RawTextHelpFormatter # Allows for better formatting of help text
    )
    parser.add_argument('--version', action='version', version='%(prog)s 0.1.0') # Example version

    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument("--list-disks", "-l", action="store_true",
                              help="List available disk partitions and potential raw physical devices.\nProvides an overview of storage devices and their mountpoints.")
    action_group.add_argument("--smart", "-s", metavar="DEVICE_PATH", type=str,
                              help="Retrieve S.M.A.R.T. information for the specified device.\nExample: /dev/sda (Linux), \\\\.\\PhysicalDrive0 (Windows).")
    action_group.add_argument("--scan", "-c", metavar="DEVICE_PATH", type=str,
                              help="Scan the specified device for readable sectors. Requires sudo/admin.\nExample: /dev/sda (Linux), \\\\.\\PhysicalDrive0 (Windows).")
    action_group.add_argument("--isolate-sectors", "-is", metavar="TARGET_PATH", type=str,
                              help="Isolate sectors for the target filesystem path.\nExample: /mnt/data (Linux), C:\\ (Windows).")
    action_group.add_argument("--manage-quarantine", "-mq", metavar="TARGET_PATH", type=str,
                              help="Manage files in the quarantine directory for the given target path.\nExample: /mnt/data (Linux), C:\\.")

    # Sub-parsers for --manage-quarantine
    # Note: Keep this after the main parser and action_group are defined.
    # We will attach subparsers to the main parser, and then check args.manage_quarantine to see if it was called.
    # A bit of a workaround as subparsers normally replace the parent parser's other arguments.
    # A more typical approach is for the subparser 'action' to be a top-level choice.
    # However, the request is for -mq to be in the mutually exclusive group.
    # Let's try adding subparsers directly to the main parser but only process them if -mq is active.
    # This might mean `target_path` for -mq is parsed by the main parser, and then we look at subparser args.

    subparsers = parser.add_subparsers(title="Quarantine Management Actions", dest="quarantine_action",
                                       help="Specify an action for quarantine management. Use with -mq TARGET_PATH.")

    # List sub-command
    parser_list_quarantine = subparsers.add_parser("list", help="List files currently in the quarantine directory.")
    # No arguments for list

    # Delete sub-command
    parser_delete_quarantine = subparsers.add_parser("delete", help="Delete specific or all files from the quarantine directory.")
    delete_group = parser_delete_quarantine.add_mutually_exclusive_group(required=False) # Becomes required if no filename/all logic fails
    delete_group.add_argument("--filename", metavar="FILENAME", type=str,
                               help="Name of a specific file to delete from quarantine.")
    delete_group.add_argument("--all", action="store_true",
                               help="Delete all files from the quarantine directory.")


    # Arguments specific to --isolate-sectors
    parser.add_argument("--filler-file-size-mb", metavar="SIZE_MB", type=int, default=100,
                        help="Size of individual filler files in Megabytes for --isolate-sectors. Default: 100 MB.")
    parser.add_argument("--fill-percentage", metavar="PERCENT", type=int, default=80, choices=range(1, 101),
                        help="Percentage of free space to fill with filler files for --isolate-sectors. Default: 80%% (1-100).")

    parser.add_argument("--block-size", "-bs", type=int, default=64,
                        help="Block size in KB for disk scan. Default: 64 KB.")
    parser.add_argument("--limit-gb", "-lim", type=float, default=None,
                        help="Limit the scan to a certain number of GB from the beginning of the disk.\nDefault: Full disk scan.")

    args = parser.parse_args(argv)

    try:
        if args.list_disks:
            list_disk_partitions_and_devices()
        elif args.smart:
            if not args.smart: # Should be caught by argparse, but as a safeguard
                print("Error: --smart option requires a device path.")
                parser.print_help()
                sys.exit(1)
            get_smart_info(args.smart)
        elif args.scan:
            if not args.scan: # Should be caught by argparse, but as a safeguard
                print("Error: --scan option requires a device path.")
                parser.print_help()
                sys.exit(1)
            scan_disk(args.scan, args.block_size, args.limit_gb)
        elif args.manage_quarantine:
            # This block will be chosen if -mq is present.
            # args.manage_quarantine will hold the TARGET_PATH for -mq.
            if not args.manage_quarantine: # Should be caught by argparse if metavar is set
                 print("Error: --manage-quarantine option requires a target path.")
                 parser.print_help()
                 sys.exit(1)
            
            quarantine_dir_path = os.path.join(args.manage_quarantine, QUARANTINE_DIR_NAME)

            if args.quarantine_action == "list":
                list_quarantine_files(quarantine_dir_path)
            elif args.quarantine_action == "delete":
                if not args.filename and not args.all:
                    print("Error: For 'delete' action, you must specify --filename or --all.")
                    # parser_delete_quarantine.print_help() # How to show help for subparser?
                    # The main parser's help might be more confusing here.
                    # A simple error is okay as per instructions.
                    sys.exit(1)
                delete_quarantine_files(quarantine_dir_path, args.filename, args.all)
            else:
                # This case should ideally be handled by argparse if subparsers are required.
                # If -mq is given but no sub-command (list/delete), argparse might error or print help.
                # If it reaches here, it means -mq was given but no valid sub-command.
                print(f"Error: No valid action (list, delete) specified for --manage-quarantine.")
                # Attempt to print help for the main parser, which should show subcommands.
                parser.print_help()
                sys.exit(1)

        elif args.isolate_sectors:
            if not args.isolate_sectors: # Should be caught by argparse, but as a safeguard
                print("Error: --isolate-sectors option requires a target path.")
                parser.print_help()
                sys.exit(1)
            # print(f"Isolate sectors action called for target: {args.isolate_sectors}")
            fs_info = get_filesystem_info(args.isolate_sectors)
            if not fs_info: # Exit if fs_info could not be retrieved
                print(f"  Critical: Could not get filesystem info for {args.isolate_sectors}. Aborting.")
                sys.exit(1)
            
            print(f"  Free space on '{args.isolate_sectors}': {get_human_readable_size(fs_info['free_space'])}")
            
            quarantine_dir = prepare_quarantine_directory(args.isolate_sectors)
            if not quarantine_dir: # Exit if quarantine_dir could not be prepared
                print(f"  Critical: Could not prepare quarantine directory in {args.isolate_sectors}. Aborting.")
                sys.exit(1)

            print(f"  Quarantine directory prepared at: {quarantine_dir}")

            # ---- Initial Information Display and Confirmation ----
            target_bytes_to_fill = (fs_info['free_space'] * args.fill_percentage) // 100
            
            print("\n--- Operation Summary & Confirmation ---")
            print(f"  Target device/path: {args.isolate_sectors}")
            print(f"  Quarantine directory: {quarantine_dir}")
            print(f"  Available free space: {get_human_readable_size(fs_info['free_space'])}")
            print(f"  Targeting to fill: {get_human_readable_size(target_bytes_to_fill)} ({args.fill_percentage}%)")
            print(f"  Individual filler file size: {args.filler_file_size_mb} MB")
            
            print("\nWARNING: This process will create many files and perform intensive read/write operations on the selected path. "
                  "This can take a significant amount of time and put stress on the disk. It is intended to help isolate "
                  "potentially bad sectors by occupying space with files that trigger read errors.")
            print("Ensure you have selected the correct target path. Data loss is unlikely with this specific operation "
                  "but always ensure backups of critical data.")
            
            try:
                confirm = input("\nDo you want to proceed? (yes/no): ").strip().lower()
            except KeyboardInterrupt:
                print("\nOperation cancelled by user (KeyboardInterrupt).")
                sys.exit(0)

            if confirm != 'yes':
                print("Operation cancelled by user.")
                sys.exit(0)
            # ---- End of Confirmation ----

            created_files, write_errors = fill_free_space(
                filesystem_path=args.isolate_sectors,
                quarantine_dir_path=quarantine_dir,
                    filler_file_size_mb=args.filler_file_size_mb,
                    fill_percentage=args.fill_percentage
                )

            # Initialize lists for integrity check results
            healthy_files = []
            bad_files_with_errors = []

            # Add files that had write errors directly to bad_files_with_errors
            for err_file, err_msg in write_errors:
                bad_files_with_errors.append((err_file, f"Failed during creation: {err_msg}"))

            if created_files:
                print("\n--- Starting Integrity Check for Successfully Created Filler Files ---")
                for f_path in created_files:
                    # Skip check if file was already marked bad due to write error, though
                    # `created_files` should ideally not contain them if `fill_free_space`
                    # excludes them from its `created_files_list` upon error.
                    # Assuming `created_files` are those believed to be successfully written.
                    is_ok, message = check_file_integrity(f_path)
                    if is_ok:
                        healthy_files.append(f_path)
                    else:
                        bad_files_with_errors.append((f_path, message))
            
            print("\n--- Integrity Check Summary ---")
            if healthy_files:
                print(f"  Healthy files ({len(healthy_files)}):")
                for f_path in healthy_files:
                    print(f"    - {f_path}")
            else:
                print("  No healthy filler files found or created.")

            if bad_files_with_errors:
                print(f"\n  Bad or Errored files ({len(bad_files_with_errors)}):")
                for f_path, err_msg in bad_files_with_errors:
                    print(f"    - File: {f_path}, Error: {err_msg}")
            else:
                print("  No bad or errored files identified (this includes files that failed during creation).")

            # --- Process Filler Files (Retention/Deletion) ---
            print("\n--- Processing Filler Files (Retention/Deletion) ---") # Added explicit print here
            retained_info, deleted_count = process_filler_files(
                quarantine_dir_path=quarantine_dir, 
                healthy_files=healthy_files,
                bad_files_with_errors=bad_files_with_errors
            )

            # --- Retention/Deletion Summary ---
            print("\n--- Retention/Deletion Summary ---")
            print(f"  Number of healthy files deleted: {deleted_count}")
            if retained_info:
                print("  Files retained in quarantine due to errors:")
                for f_path, err_msg in retained_info:
                    print(f"    - {f_path}: Reason: {err_msg}")
            else:
                print("  No files were quarantined.")
            print(f"  Quarantine directory: {quarantine_dir}")
        else:
            parser.print_help()
            # print("\nDefaulting to listing disks as no specific action was chosen:")
            # list_disk_partitions_and_devices()
    except Exception as e:
        print(f"\nError: An unexpected critical error occurred in the application: {type(e).__name__} - {e}", file=sys.stderr)
        # Consider adding traceback print here for debugging development versions
        # import traceback
        # traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    if hasattr(sys, 'stdout') and hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass 
    main()
