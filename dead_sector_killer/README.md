# Dead Sector Killer (Python CLI)

## Description

DeadSectorKiller is a Python command-line utility designed to help you assess the health of your disk drives. It can list disk partition information, retrieve S.M.A.R.T. (Self-Monitoring, Analysis, and Reporting Technology) health data, and perform a read-only surface scan to identify potential read errors, often indicative of "bad sectors."

## Features

*   **List Disk Information**: Displays mounted partitions, their usage (total, used, free space), and filesystem types.
*   **Identify Physical Devices**: Attempts to identify underlying physical disk device names suitable for S.M.A.R.T. queries and scans (e.g., `/dev/sda`, `\\.\PhysicalDrive0`).
*   **S.M.A.R.T. Data Retrieval**: Fetches and displays key S.M.A.R.T. attributes from drives that support this technology.
*   **Disk Surface Scan**: Performs a read-only scan of specified disk devices, block by block, to detect sectors that cannot be read.
*   **Customizable Scanning**: Allows specifying the block size for reads and limiting the scan to a certain number of Gigabytes from the start of the disk.

## Requirements

*   **Python**: Version 3.6 or newer.
*   **`psutil` Python library**: Used for listing disk partitions and usage.
*   **`smartmontools`**: This external utility (specifically the `smartctl` command) must be installed and accessible in the system's PATH for S.M.A.R.T. data retrieval.
*   **Administrator/Root Privileges**: Required for:
    *   Retrieving S.M.A.R.T. data (`smartctl` usually needs elevated privileges).
    *   Performing direct disk scans (opening raw device paths).

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

The script generally requires administrator/root privileges for S.M.A.R.T. checks and disk scanning.

**General Command Structure**:
```bash
# On Linux/macOS
sudo python3 dead_sector_killer.py <action> [options]

# On Windows (run in an Administrator Command Prompt/PowerShell)
python dead_sector_killer.py <action> [options]
```

### Actions:

1.  **List Disks and Partitions (`--list-disks` or `-l`)**:
    Displays information about mounted partitions (like drive letters on Windows or mount points on Linux/macOS), their usage statistics, and also attempts to identify the underlying physical device names that you would use for `--smart` or `--scan` commands.
    ```bash
    python3 dead_sector_killer.py --list-disks
    ```
    *(Note: `sudo` is not strictly required for listing basic partition info, but the raw device identification part might be more accurate or complete with it, especially on Windows for WMIC access).*

2.  **Get S.M.A.R.T. Information (`--smart` or `-s`)**:
    Retrieves S.M.A.R.T. health attributes for the specified physical device. Replace `<device_path>` with the actual device path (e.g., `/dev/sda` on Linux, `\\.\PhysicalDrive0` on Windows).
    ```bash
    # Linux/macOS example
    sudo python3 dead_sector_killer.py --smart /dev/sda

    # Windows example
    python dead_sector_killer.py --smart \\.\PhysicalDrive0
    ```

3.  **Scan Disk for Bad Sectors (`--scan` or `-c`)**:
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

*   **Linux**: Physical disks are typically named `/dev/sda`, `/dev/sdb`, `/dev/nvme0n1`, etc. Partitions are like `/dev/sda1`. For `--smart` and `--scan`, use the physical disk name (e.g., `/dev/sda`).
*   **Windows**: Physical disks are typically named `\\.\PhysicalDrive0`, `\\.\PhysicalDrive1`, etc. The `--list-disks` command attempts to identify these, but you might need to confirm the correct one through Disk Management.
*   **macOS**: Similar to Linux, e.g., `/dev/disk0`, `/dev/disk1`. Use the whole disk identifier, not a partition slice like `/dev/disk0s2`.

The `--list-disks` command helps identify appropriate device names.

### Privileges

*   **Linux/macOS**: Use `sudo` before your `python3 dead_sector_killer.py` command when using `--smart` or `--scan`.
    ```bash
    sudo python3 dead_sector_killer.py --scan /dev/sda
    ```
*   **Windows**: You must run the Command Prompt (cmd.exe) or PowerShell as an Administrator, then execute the script.
    ```powershell
    python dead_sector_killer.py --scan \\.\PhysicalDrive0
    ```

## Disclaimer

This tool is intended for read-only operations to assess disk health status. However, interacting with disk devices at a low level, even for reading, always carries inherent risks. Incorrect usage (e.g., specifying the wrong device for a scan) could theoretically lead to attempts to read from critical system areas if not careful, though the script itself does not perform any writes.

**Use this tool responsibly and at your own risk. The authors or contributors are not responsible for any data loss or damage that may occur in connection with the use of this software.** Always ensure you have backups of important data before performing any intensive disk operations or diagnostics.
