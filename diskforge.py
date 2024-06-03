import logging
import math
import os
import subprocess
import sys
import threading
import time

from tqdm import tqdm

# logging
logging.basicConfig(filename='diskforge.log', level=logging.INFO)


def confirm_action(disks):
    print(f"The following disks will be cleared and formatted: {', '.join(disks)}")
    confirmation = input("Are you sure you want to proceed? Type 'yes' to continue: ")
    if confirmation.lower() != 'yes':
        print("Operation cancelled.")
        sys.exit(0)


def _all_disks():
    try:
        output = subprocess.check_output(['lsblk', '-o', 'NAME'])

        # removing 'NAME' and 'sr'
        disk_names = set()
        for line in output.decode().split('\n'):
            if not line:
                continue
            disk_name = line.strip().split()[0]
            if disk_name == 'NAME' or disk_name.startswith('sr'):
                continue
            disk_name = '/dev/' + ''.join(filter(str.isalpha, disk_name))  # /dev/ added after clean up
            disk_names.add(disk_name)

        return list(disk_names)
    except subprocess.CalledProcessError:
        print("Error: Unable to retrieve disk information.")
        return []


def get_disk_from_mount_point(mount_point):
    try:
        disk = os.popen(f"df {mount_point} | tail -1 | awk '{{print $1}}'").read().strip()
        return disk
    except Exception as e:
        print(f"Error retrieving disk for mount point {mount_point}: {e}")
        return None


def identify_disks():
    disk_list = _all_disks()


    boot_disk = get_disk_from_mount_point("/boot")
    efi_disk = get_disk_from_mount_point("/boot/efi")

    os_disks = set()
    if boot_disk:
        if "nvme" in boot_disk:
            os_disks.add("/dev/" + boot_disk.split('p')[0])
        else:
            os_disks.add("/dev/" + boot_disk[:-1])
    if efi_disk:
        if "nvme" in efi_disk:
            os_disks.add("/dev/" + efi_disk.split('p')[0])
        else:

            os_disks.add("/dev/" + efi_disk[:-1])

    if not os_disks:
        print("Error: Unable to identify the OS disk. Operation halted.")
        sys.exit(1)

    for os_disk in os_disks:
        if os_disk in disk_list:
            disk_list.remove(os_disk)

    if len(disk_list) == 0:
        print("No other disks found.")
        return []

    return disk_list


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

    # Single progress bar for all
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
    time.sleep(5)  # just to let the user read again.


def format_disk(disk, progress_bar, success_count, failure_count):
    try:
        # append partition number 1 to the disk path
        disk_partition = disk + '1'

        # formatting as exFAT
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

    # create threads for formatting each disk
    threads = []
    for disk in disks:
        thread = threading.Thread(target=format_disk, args=(disk, progress_bar, success_count, failure_count))
        threads.append(thread)
        thread.start()

    # wait for all threads to complete
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
        (900 * 1024 ** 3, 1000 * 1024 ** 3, '1TB'),
        (1300 * 1024 ** 3, 1500 * 1024 ** 3, '1.5TB'),
        (1700 * 1024 ** 3, 2000 * 1024 ** 3, '2TB'),
        (2500 * 1024 ** 3, 3000 * 1024 ** 3, '3TB'),
        (3500 * 1024 ** 3, 4000 * 1024 ** 3, '4TB'),
        (5500 * 1024 ** 3, 6000 * 1024 ** 3, '6TB'),
        (7000 * 1024 ** 3, 8000 * 1024 ** 3, '8TB'),
        (9000 * 1024 ** 3, 10000 * 1024 ** 3, '10TB'),
        (11000 * 1024 ** 3, 12000 * 1024 ** 3, '12TB')
    ]

    for start, end, label in size_ranges:
        if start <= size_in_bytes < end:
            return f"{rounded_size} {size_units[exponent]} ({label})"

    # fallback - if size doesn't fall into any predefined range, return the default formatted size
    return f"{rounded_size} {size_units[exponent]}"


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
