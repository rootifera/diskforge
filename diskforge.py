import logging
import math
import os
import subprocess
import sys
import threading
import time

from tqdm import tqdm
from colorama import Fore, init, Style

init(autoreset=True)

# logging
logging.basicConfig(filename='/var/log/diskforge.log', level=logging.INFO)


def confirm_action(disks):
    disk_names_with_numbers = [f"Disk {i + 1} ({disk})" for i, disk in enumerate(disks)]
    print(f"The following disks will be cleared and formatted: {', '.join(disk_names_with_numbers)}")
    confirmation = input("Are you sure you want to proceed? Type 'yes' to continue: ")
    if confirmation.lower() != 'yes':
        print("Operation cancelled.")
        sys.exit(0)


def _all_disks():
    try:
        output = subprocess.check_output(['lsblk', '-o', 'NAME'])

        disk_names = set()
        for line in output.decode().split('\n'):
            if not line:
                continue
            disk_name = line.strip().split()[0]
            if disk_name == 'NAME' or disk_name.startswith('sr'):
                continue
            disk_name = '/dev/' + disk_name  # /dev/ added
            disk_names.add(disk_name)

        return list(disk_names)
    except subprocess.CalledProcessError:
        print("Error: Unable to retrieve disk information.")
        return []


def identify_disks():
    disk_list = _all_disks()

    if not disk_list:
        print(f"{Fore.RED}No disks found.{Style.RESET_ALL}")
        return []

    # disk sorting
    disk_list = sorted([disk for disk in disk_list if disk.startswith('/dev/sd')])

    os_disks = []
    try:
        os_disk_output = subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '/']).strip().decode()
        if os_disk_output.startswith('/dev/mapper'):
            # for LVM or RAID
            pvs_output = subprocess.check_output(['pvs', '--noheadings', '-o', 'pv_name']).strip().decode()
            pvs_disks = ['/dev/' + line.split('/')[-1] for line in pvs_output.split('\n')]
            os_disks.extend(pvs_disks)
        else:
            # usual sdx
            os_disk = os_disk_output.rsplit('/', 1)[-1]
            os_disk_base = os_disk.rstrip('0123456789')
            os_disks.append('/dev/' + os_disk_base)
        print(f"{Fore.GREEN}OS Disk(s) found: {', '.join(os_disks)}{Style.RESET_ALL}")
    except subprocess.CalledProcessError as e:
        print(f"{Fore.RED}Error: Unable to identify the OS disk. Operation halted. {e}{Style.RESET_ALL}")
        sys.exit(1)

    for os_disk in os_disks:
        if os_disk in disk_list:
            disk_list.remove(os_disk)

    # exclude NVME disks from the list
    disk_list = [disk for disk in disk_list if not disk.startswith('/dev/nvme')]

    if len(disk_list) == 0:
        print("No other disks found.")
        return []

    return disk_list


def unmount_disks_partitions(disks):
    any_unmounted = False

    for disk in disks:
        try:
            partitions_output = subprocess.check_output(
                f"lsblk -ln -o NAME {disk}",
                shell=True,
                universal_newlines=True
            ).strip()

            partitions = [f"/dev/{part}" for part in partitions_output.split('\n') if part]

            if not partitions:
                continue

            for partition in partitions:
                try:
                    mount_points = subprocess.check_output(
                        f"findmnt -rno TARGET -S {partition}",
                        shell=True,
                        universal_newlines=True
                    ).strip().split('\n')

                    for mount_point in mount_points:
                        if mount_point:
                            subprocess.run(
                                f"sudo umount -f {mount_point}",
                                shell=True,
                                check=True,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                            )
                            print(f"Unmounted {mount_point}")
                            any_unmounted = True
                except subprocess.CalledProcessError:
                    pass

        except subprocess.CalledProcessError:
            pass

    if not any_unmounted:
        print("None Found")


def verify_disk_partitions(disk):
    try:
        output = subprocess.check_output(['lsblk', '-o', 'NAME,SIZE,TYPE', disk]).decode()
        logging.info(f"Disk {disk} state:\n{output}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to verify disk {disk}: {e}")
        return False
    return True


def clear_partitions(disk, progress_bar, success_count, failure_count):
    try:
        # verify disk state before operation
        verify_disk_partitions(disk)

        # clear existing partitions, gpt and create new partition.
        subprocess.run(['sudo', 'parted', '--script', disk, 'mklabel', 'gpt', 'mkpart', 'primary', '0%', '100%'],
                       check=True)
        # set partition type to msftdata - workaround for fs not recognized by M$
        subprocess.run(['sudo', 'parted', '--script', disk, 'set', '1', 'msftdata', 'on'],
                       check=True)

        # verify disk state after operation - double checking
        verify_disk_partitions(disk)

        progress_bar.update(1)
        success_count.append(disk)
        # logs go into diskforge.log - not sure if each run clears the log
        logging.info(f"Partitions cleared for disk {disk} and GPT label created")
    except subprocess.CalledProcessError as e:
        failure_count.append(disk)
        logging.error(f"Failed to clear partitions and create GPT label for disk {disk}: {e}")


def clear_partitions_all(disks):
    success_count = []
    failure_count = []

    print(f"Total Disks found: {len(disks)}")
    print("Clearing partition tables...")

    progress_bar = tqdm(total=len(disks), desc="Overall Progress")

    # creating threads for each disk
    threads = []
    for device in disks:
        thread = threading.Thread(target=clear_partitions, args=(device, progress_bar, success_count, failure_count))
        threads.append(thread)
        thread.start()

    # waiting for all to complete
    for thread in threads:
        thread.join()

    progress_bar.close()
    # this is here to make the progress bar visible, otherwise it just disappears
    time.sleep(2)

    # reset the terminal, just a lazy trick to print properly
    os.system('reset')

    print(f"Total Success: {len(success_count):<5}")
    print(f"Total Failure: {len(failure_count):<5}")
    print("Moving to next stage in 5 seconds")
    time.sleep(5)  # giving user some time to read.


def format_disk(disk, progress_bar, success_count, failure_count):
    try:
        # append partition number 1 to the disk path
        disk_partition = disk + '1'

        # formatting as exFAT - on ubuntu exfatprogs needs to be installed
        subprocess.run(['sudo', 'mkfs.exfat', disk_partition], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)

        success_count.append(disk)
        logging.info(f"Formatted disk {disk_partition} as exFAT")
    except subprocess.CalledProcessError as e:
        failure_count.append(disk)
        logging.error(f"Failed to format disk {disk_partition}: {e}")
    finally:
        progress_bar.update(1)


def format_all_disks(disks):
    success_count = []
    failure_count = []

    print(f"Total Disks found: {len(disks)}")
    print("Formatting disks to exFAT...")

    # single progress bar for all disks
    progress_bar = tqdm(total=len(disks), desc="Formatting Progress")

    threads = []
    for disk in disks:
        thread = threading.Thread(target=format_disk, args=(disk, progress_bar, success_count, failure_count))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    progress_bar.close()
    # this is here to make the progress bar visible, otherwise it just disappears
    time.sleep(2)

    # reset the terminal, just a lazy trick to print properly
    os.system('reset')

    print(f"Total Success: {len(success_count):<5}")
    print(f"Total Failure: {len(failure_count):<5}")


def get_disk_sizes(disks):
    disk_sizes = {}

    for disk in disks:
        try:
            output = subprocess.check_output(['lsblk', '-b', '--output', 'SIZE', '-n', '-d', disk]).decode().strip()
            size = int(output)
            disk_sizes[disk] = size
        except subprocess.CalledProcessError as e:
            logging.error(f"Error: Unable to retrieve size information for disk {disk} - {e}")

    return disk_sizes


def convert_size(size_in_bytes):
    size_units = ['bytes', 'KB', 'MB', 'GB', 'TB']
    exponent = int(math.log(size_in_bytes, 1024))
    size = size_in_bytes / (1024 ** exponent)
    rounded_size = round(size)

    # had to hardcode that, so we don't get non-standard size labels (like 930GB instead of 1TB)
    size_ranges = [
        (10 * 1024 ** 3, 16 * 1024 ** 3, '16GB'),
        (25 * 1024 ** 3, 32 * 1024 ** 3, '32GB'),
        (50 * 1024 ** 3, 64 * 1024 ** 3, '64GB'),
        (100 * 1024 ** 3, 120 * 1024 ** 3, '120GB'),
        (115 * 1024 ** 3, 128 * 1024 ** 3, '128GB'),
        (200 * 1024 ** 3, 256 * 1024 ** 3, '256GB'),
        (400 * 1024 ** 3, 500 * 1024 ** 3, '500GB'),
        (690 * 1024 ** 3, 750 * 1024 ** 3, '750GB'),
        (900 * 1024 ** 3, 1000 * 1024 ** 3, '1TB'),
        (1300 * 1024 ** 3, 1500 * 1024 ** 3, '1.5TB'),
        (1700 * 1024 ** 3, 2000 * 1024 ** 3, '2TB'),
        (2500 * 1024 ** 3, 3000 * 1024 ** 3, '3TB'),
        (3500 * 1024 ** 3, 4000 * 1024 ** 3, '4TB'),
        (5500 * 1024 ** 3, 6000 * 1024 ** 3, '6TB'),
        (7500 * 1024 ** 3, 8000 * 1024 ** 3, '8TB'),
        (10000 * 1024 ** 3, 12000 * 1024 ** 3, '12TB')
    ]

    for start, end, label in size_ranges:
        if start <= size_in_bytes < end:
            return f"{label}"

    # fallback - if size doesn't fall into any predefined range, return the default formatted size
    return f"{rounded_size}{size_units[exponent]}"


def set_labels(disks):
    disk_sizes = get_disk_sizes(disks)

    for disk, size in disk_sizes.items():
        partition = disk + '1'  # partition number is always 1
        label = convert_size(size)
        try:
            subprocess.run(['sudo', 'exfatlabel', partition, label], check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            logging.info(f"Label set for disk {disk}: {label}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error setting label for disk {disk}: {e}")


def draw_disk_size_graph(disk_sizes):
    max_size = max(disk_sizes.values())

    for i, (disk, size) in enumerate(disk_sizes.items(), start=1):
        # added leading zero for formatting
        disk_number = f"{i:02d}"
        print(f"Disk {disk_number} ({disk}) = ", end="")

        formatted_size = convert_size(size)

        if formatted_size == '500GB':
            color = Fore.GREEN
        elif formatted_size == '750GB':
            color = Fore.BLUE
        elif formatted_size == '1TB':
            color = Fore.WHITE
        else:
            color = Fore.YELLOW

        scaled_size = size * 40 // max_size
        bar = "|" + "=" * scaled_size + "|"

        print(color + bar.ljust(80), end=" ")
        print(color + formatted_size)


def visualize_disk_sizes(disks):
    disk_sizes = get_disk_sizes(disks)
    draw_disk_size_graph(disk_sizes)


def get_smart_data(disk, timeout=10):
    try:
        process = subprocess.Popen(['sudo', 'smartctl', '-a', disk], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, _ = process.communicate(timeout=timeout)
        return output.decode()
    except subprocess.TimeoutExpired:
        process.kill()
        return "TIMEOUT"
    except subprocess.CalledProcessError as e:
        return e.output.decode()


def analyze_smart_data(smart_data):
    if not smart_data:
        print("No SMART data to analyze.")
        return None, [], None

    lines = smart_data.split('\n')

    serial_number = None
    for line in lines:
        if line.startswith('Serial Number:'):
            serial_number = line.split(':')[1].strip()
            break

    attribute_values = {
        'Reallocated_Sector_Ct': 0,
        'Reported_Uncorrect': 0,
        'Current_Pending_Sector': 0,
    }

    attribute_map = {
        'Reallocated_Sector_Ct': '  5 Reallocated_Sector_Ct',
        'Reported_Uncorrect': '187 Reported_Uncorrect',
        'Current_Pending_Sector': '197 Current_Pending_Sector',
    }

    for line in lines:
        for attribute, identifier in attribute_map.items():
            if line.startswith(identifier):
                try:
                    attribute_values[attribute] = int(line.split()[9])
                except (IndexError, ValueError):
                    print(f"Error parsing attribute {attribute} from line: {line}")

    warnings = []

    # Check attributes and determine health_status
    if attribute_values['Reallocated_Sector_Ct'] > 0 or attribute_values['Current_Pending_Sector'] > 0:
        health_status = 'Failed'
        if attribute_values['Reallocated_Sector_Ct'] > 0:
            warnings.append(f"Reallocated_Sector_Ct = {attribute_values['Reallocated_Sector_Ct']}")
        if attribute_values['Current_Pending_Sector'] > 0:
            warnings.append(f"Current_Pending_Sector = {attribute_values['Current_Pending_Sector']}")
    elif attribute_values['Reported_Uncorrect'] > 0:
        health_status = 'Warning'
        warnings.append(f"Reported_Uncorrect = {attribute_values['Reported_Uncorrect']}")
    else:
        health_status = 'OK'

    return health_status, warnings, serial_number


def check_disk_health(disks):
    disk_sizes = get_disk_sizes(disks)
    for index, disk in enumerate(disks, start=1):
        smart_data = get_smart_data(disk)
        disk_size = convert_size(disk_sizes.get(disk, 0))
        if smart_data == "TIMEOUT":
            print(f"{Fore.RED}SMART Check Time Out for {disk}{Style.RESET_ALL}")
        elif smart_data:
            health_status, warnings, serial_number = analyze_smart_data(smart_data)
            disk_numbered = f"Disk {index:02d} ({disk})"
            if health_status == 'Failed':
                status_color = Fore.RED
            elif health_status == 'Warning':
                status_color = Fore.YELLOW
            else:
                status_color = Fore.GREEN
            issues = ', '.join(warnings) if warnings else 'None'
            serial_number = serial_number if serial_number is not None else ""
            print(
                f"{status_color}{disk_numbered:<20} Size: {disk_size:<8} Status: {health_status:<8} Serial: {serial_number:<20} Issues: {issues}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}Failed to retrieve S.M.A.R.T. data for {disk}{Style.RESET_ALL}")
