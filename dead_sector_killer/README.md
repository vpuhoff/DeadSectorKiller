# Dead Sector Killer (Python CLI)

## Description

DeadSectorKiller is a Python command-line utility designed to help you assess the health of your disk drives. It can list disk partition information, retrieve S.M.A.R.T. (Self-Monitoring, Analysis, and Reporting Technology) health data, perform a read-only surface scan to identify potential read errors (often indicative of "bad sectors"), and attempt to isolate these sectors at a filesystem level.

## Features

*   **List Disk Information**: Displays mounted partitions, their usage (total, used, free space), and filesystem types.
*   **Identify Physical Devices**: Attempts to identify underlying physical disk device names suitable for S.M.A.R.T. queries and scans (e.g., `/dev/sda`, `\\.\PhysicalDrive0`).
*   **S.M.A.R.T. Data Retrieval**: Fetches and displays key S.M.A.R.T. attributes from drives that support this technology.
*   **Disk Surface Scan**: Performs a read-only scan of specified disk devices, block by block, to detect sectors that cannot be read.
*   **Customizable Scanning**: Allows specifying the block size for reads and limiting the scan to a certain number of Gigabytes from the start of the disk.
*   **Isolate Bad Sectors (via File Allocation)**: A mode to fill free space on a target filesystem, identify files that cause read errors (potentially due to bad sectors), and retain these files to prevent the OS from reusing those sectors. (Experimental)
*   **Quarantine Management**: List and delete files that have been quarantined by the isolation process.

## Requirements

*   **Python**: Version 3.6 or newer.
*   **`psutil` Python library**: Used for listing disk partitions and usage.
*   **`smartmontools`**: This external utility (specifically the `smartctl` command) must be installed and accessible in the system's PATH for S.M.A.R.T. data retrieval.
*   **Administrator/Root Privileges**: Required for:
    *   Retrieving S.M.A.R.T. data (`smartctl` usually needs elevated privileges).
    *   Performing direct disk scans (opening raw device paths).
    *   Potentially for creating the `.quarantine_files` directory in restricted locations during sector isolation.

## Installation

1.  **Clone the Repository (Optional)**:
    If you have cloned this repository, navigate to the `dead_sector_killer` directory.

2.  **Python Libraries**:
    The primary Python dependency is `psutil`. You can install it using the provided `requirements.txt` file (if you cloned the repo) or directly via pip:
    ```bash
    pip install -r requirements.txt
    ```
    Or, if you only have the script file:
    ```bash
    pip install psutil
    ```

3.  **`smartmontools`**:
    This is crucial for the S.M.A.R.T. functionality.
    *   **Linux (Debian/Ubuntu/Mint)**:
        ```bash
        sudo apt-get update
        sudo apt-get install smartmontools
        ```
    *   **Linux (Fedora/CentOS/RHEL)**:
        ```bash
        sudo yum install smartmontools
        ```
        Or for DNF-based systems (newer Fedora):
        ```bash
        sudo dnf install smartmontools
        ```
    *   **macOS (using Homebrew)**:
        ```bash
        brew install smartmontools
        ```
    *   **Windows**:
        Download the installer from the [official smartmontools website](https://www.smartmontools.org/wiki/Download). During installation, ensure that `smartctl.exe` is added to your system's PATH environment variable.

## Usage

The script generally requires administrator/root privileges for S.M.A.R.T. checks, disk scanning, and potentially for the sector isolation feature depending on the target path's permissions.

**General Command Structure**:
```bash
# On Linux/macOS
sudo python3 dead_sector_killer.py <action> [options_or_subcommand]

# On Windows (run in an Administrator Command Prompt/PowerShell)
python dead_sector_killer.py <action> [options_or_subcommand]
```

### Actions:

1.  **List Disks and Partitions (`--list-disks` or `-l`)**:
    Displays information about mounted partitions (like drive letters on Windows or mount points on Linux/macOS), their usage statistics, and also attempts to identify the underlying physical device names that you would use for `--smart` or `--scan` commands.
    ```bash
    python3 dead_sector_killer.py --list-disks
    ```
    *(Note: `sudo` is not strictly required for listing basic partition info, but the raw device identification part might be more accurate or complete with it, especially on Windows for WMIC access).*

2.  **Get S.M.A.R.T. Information (`--smart DEVICE_PATH` or `-s DEVICE_PATH`)**:
    Retrieves S.M.A.R.T. health attributes for the specified physical device. Replace `<device_path>` with the actual device path (e.g., `/dev/sda` on Linux, `\\.\PhysicalDrive0` on Windows).
    ```bash
    # Linux/macOS example
    sudo python3 dead_sector_killer.py --smart /dev/sda

    # Windows example
    python dead_sector_killer.py --smart \\.\PhysicalDrive0
    ```

3.  **Scan Disk for Bad Sectors (`--scan DEVICE_PATH` or `-c DEVICE_PATH`)**:
    Performs a read-only surface scan of the specified physical device. This command requires administrator/root privileges.
    ```bash
    # Linux/macOS example
    sudo python3 dead_sector_killer.py --scan /dev/sdb

    # Windows example
    python dead_sector_killer.py --scan \\.\PhysicalDrive1
    ```
    **Scan Options**:
    *   `--block-size <kb>` or `-bs <kb>`: Sets the size (in Kilobytes) of the blocks to read during the scan. Default is 64 KB. Larger blocks might speed up the scan but could be less granular in pinpointing errors.
        ```bash
        sudo python3 dead_sector_killer.py --scan /dev/sdb --block-size 256
        ```
    *   `--limit-gb <gb>` or `-lim <gb>`: Limits the scan to the first `<gb>` Gigabytes of the disk. If not specified, the entire disk is scanned (which can take a very long time).
        ```bash
        sudo python3 dead_sector_killer.py --scan /dev/sdb --limit-gb 100  # Scans the first 100 GB
        ```

4.  **Isolate Sectors (`--isolate-sectors TARGET_PATH` or `-is TARGET_PATH`)**:
    Attempts to identify and "quarantine" bad sectors at the filesystem level. It does this by filling a specified percentage of free space on the `TARGET_PATH` (e.g., `/mnt/data` on Linux, `C:\` on Windows) with temporary "filler" files. Each file is then read back; if a read error occurs, the file is considered to be residing on a bad sector and is retained in a special quarantine directory. Healthy files are deleted.
    
    **Key Options for `--isolate-sectors`**:
    *   `--filler-file-size-mb SIZE_MB`: Specifies the size of individual temporary files created during the process. Default is 100 MB.
    *   `--fill-percentage PERCENT`: Defines what percentage of the currently free space on `TARGET_PATH` should be filled with these temporary files. Default is 80%.

    **Process**:
    1.  Calculates free space on `TARGET_PATH`.
    2.  Creates filler files (e.g., `filler_0001.tmp`, `filler_0002.tmp`, etc.) in a directory named `.quarantine_files` located at the root of `TARGET_PATH`.
    3.  Reads each filler file to check for read errors.
    4.  Files that are read successfully ("healthy") are deleted.
    5.  Files that cause read errors ("bad") are renamed (e.g., `filler_0001.quarantined.<uuid>.bad`) and kept in the `.quarantine_files` directory. This aims to prevent the operating system from trying to use the disk sectors occupied by these "bad" files for new data.

    **Warning**: This operation is I/O intensive and can put significant stress on the target drive. It may take a very long time, especially on large drives or with high fill percentages. This is a software-level workaround, not a hardware fix for bad sectors. Always ensure you have backups of critical data.

    **Example Usage**:
    ```bash
    # Linux/macOS example (fill 75% of /mnt/my_drive with 50MB files)
    sudo python3 dead_sector_killer.py --isolate-sectors /mnt/my_drive --fill-percentage 75 --filler-file-size-mb 50

    # Windows example (fill 80% of D: with default 100MB files)
    python dead_sector_killer.py --isolate-sectors D:\ 
    ```

5.  **Manage Quarantine (`--manage-quarantine TARGET_PATH` or `-mq TARGET_PATH`)**:
    Provides tools to manage files within the `.quarantine_files` directory that was created by a previous `--isolate-sectors` run on the specified `TARGET_PATH`.
    
    **Sub-commands for `--manage-quarantine`**:
    *   `list`: Lists all files currently in the quarantine directory (`<TARGET_PATH>/.quarantine_files`).
        ```bash
        # Linux/macOS example
        python3 dead_sector_killer.py --manage-quarantine /mnt/my_drive list

        # Windows example
        python dead_sector_killer.py --manage-quarantine D:\ list
        ```
    *   `delete [--filename FILENAME | --all]`: Deletes files from the quarantine directory. You must specify either a particular file to delete or opt to delete all files. This action requires confirmation.
        ```bash
        # Delete a specific file (Linux/macOS)
        python3 dead_sector_killer.py --manage-quarantine /mnt/my_drive delete --filename filler_0001.quarantined.xxxx.bad

        # Delete all files in quarantine (Windows), after confirmation
        python dead_sector_killer.py --manage-quarantine D:\ delete --all
        ```

## Understanding Bad Sector Isolation / Quarantine

The `--isolate-sectors` feature provides a software-level mechanism to work around bad sectors on a disk, particularly when replacing the drive isn't immediately possible. Here's how it works:

1.  **File Creation**: The tool writes temporary "filler" files to the free space of the target filesystem (e.g., your D: drive or /home partition).
2.  **Integrity Check**: Each of these filler files is then read back entirely.
3.  **Quarantining**: If a file cannot be read back without errors, the tool assumes that one or more disk sectors occupied by this file are damaged ("bad"). This problematic file is then renamed (e.g., `filler_0023.quarantined.a1b2c3d4.bad`) and kept in a special directory named `.quarantine_files`, located at the root of the `TARGET_PATH` (e.g., `D:\.quarantine_files` or `/mnt/my_drive/.quarantine_files`).
4.  **Outcome**: By keeping this "bad" file, the disk space it occupies remains allocated. This discourages the operating system from attempting to write new data to those potentially unreliable sectors. Files that are read back successfully are deleted, freeing up space that is presumed healthy.

**Important Considerations**:
*   **Not a Hardware Fix**: This process does *not* repair bad sectors. It's a strategy to tell the OS "don't use this area." The underlying physical damage to the disk remains.
*   **Filesystem Dependent**: This technique operates at the filesystem level, not the raw disk block level like `badblocks` in Linux.
*   **S.M.A.R.T. Data**: Always correlate findings from this isolation process with S.M.A.R.T. data (`--smart` command). Attributes like `Reallocated_Sector_Ct`, `Current_Pending_Sector`, and `Offline_Uncorrectable` provide critical insights into the drive's true hardware health. A drive with increasing bad sectors is typically failing and should be replaced.
*   **Temporary Measure**: Consider this a temporary workaround. If a drive is showing signs of bad sectors, the best course of action is to back up all data immediately and replace the drive.

## Understanding the Output

### S.M.A.R.T. Data

When you use the `--smart` command, the tool attempts to display several attributes. Some critical ones to watch for include:

*   **`Reallocated_Sector_Ct` (Reallocated Sector Count)**: Number of sectors that have been remapped due to read/write/verification errors. A non-zero value indicates the drive has found bad sectors and moved data from them to spare areas. Higher values are a concern.
*   **`Current_Pending_Sector` (Current Pending Sector Count)**: Number of "unstable" sectors that are currently waiting to be remapped. If a subsequent write to this sector is successful, the sector is re-evaluated. If not, it may be reallocated. Non-zero values are a warning sign.
*   **`Offline_Uncorrectable` (Offline Uncorrectable Sector Count)**: Number of uncorrectable errors found during offline scans. These are definitive bad sectors.

*Note: The interpretation of S.M.A.R.T. values can be complex. Consult online resources for detailed explanations of specific attributes for your drive model.*

### Scan Results

The `--scan` operation reads the disk block by block.
*   **No Errors**: If the scan completes without issues for the specified area, it means all sectors in that region were readable at the time of the scan.
*   **Read Errors**: If errors are reported (e.g., "Read Error at offset..."), it means the operating system was unable to read data from that specific location on the disk. The reported offset is the byte position from the beginning of the disk where the problematic block starts. Multiple errors can indicate failing hardware.

## Platform-Specific Notes

### Device Naming

The way you refer to disk devices varies by operating system:

*   **Linux**: Physical disks are typically named `/dev/sda`, `/dev/sdb`, `/dev/nvme0n1`, etc. Partitions are like `/dev/sda1`. For `--smart` and `--scan`, use the physical disk name (e.g., `/dev/sda`). The `TARGET_PATH` for `--isolate-sectors` and `--manage-quarantine` should be a mount point like `/mnt/data` or `/home`.
*   **Windows**: Physical disks are typically named `\\.\PhysicalDrive0`, `\\.\PhysicalDrive1`, etc. The `--list-disks` command attempts to identify these. The `TARGET_PATH` for `--isolate-sectors` and `--manage-quarantine` should be a drive letter like `C:\` or `D:\`.
*   **macOS**: Similar to Linux, e.g., `/dev/disk0`, `/dev/disk1`. Use the whole disk identifier for scans. `TARGET_PATH` for isolation/quarantine would be a mount point like `/Volumes/MyExternalDrive`.

The `--list-disks` command helps identify appropriate device names for scanning and mount points for filesystem operations.

### Privileges

*   **Linux/macOS**: Use `sudo` before your `python3 dead_sector_killer.py` command when using `--smart`, `--scan`, or `--isolate-sectors` if the target path requires root permissions for writing (e.g., creating `.quarantine_files` in certain locations).
    ```bash
    sudo python3 dead_sector_killer.py --scan /dev/sda
    sudo python3 dead_sector_killer.py --isolate-sectors /mnt/important_drive
    ```
*   **Windows**: You must run the Command Prompt (cmd.exe) or PowerShell as an Administrator, then execute the script, especially for `--smart`, `--scan`, and `--isolate-sectors`.
    ```powershell
    python dead_sector_killer.py --scan \\.\PhysicalDrive0
    python dead_sector_killer.py --isolate-sectors C:\
    ```

## Disclaimer

This tool is intended for read-only operations (like `--scan` and `--smart`) and filesystem-level operations (like `--isolate-sectors`) to assess and manage disk health status. However, interacting with disk devices, even for reading or filesystem manipulation, always carries inherent risks. Incorrect usage (e.g., specifying the wrong device for a scan or the wrong target path for isolation) could theoretically lead to attempts to read from critical system areas or manipulate files in unintended locations. The sector isolation feature (`--isolate-sectors`) creates and deletes files; ensure the target path is correct and that you understand the process.

**Use this tool responsibly and at your own risk. The authors or contributors are not responsible for any data loss or damage that may occur in connection with the use of this software.** Always ensure you have backups of important data before performing any intensive disk operations or diagnostics.
