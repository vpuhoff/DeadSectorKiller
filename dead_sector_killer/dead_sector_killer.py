import psutil
import os
import subprocess
import re
import time # For progress reporting delay
import argparse
import sys # For sys.stdout.reconfigure and sys.exit

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
