import logging
import os
import subprocess
import sys
import threading
import time

from tqdm import tqdm

# Set up logging
logging.basicConfig(filename='diskforge.log', level=logging.INFO)


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


def identify_disks():
    disk_list = _all_disks()

    # find OS disk, we don't want to format that
    os_disk = os.popen("df / | grep -Eo '^/[^0-9]+'").read().strip()
    os_disk = '/dev/' + os_disk.split('/')[-1]  # Add '/dev/' to the beginning of the disk name

    if os_disk not in disk_list:
        # safety net, if we can't find the OS disk let's not wipe anything.
        print("Error: Unable to identify the OS disk. Operation halted.")
        sys.exit(1)

    # remove the OS disk from the disks list
    disk_list.remove(os_disk)

    if len(disk_list) == 0:
        print("No other disks found.")
        return []

    return disk_list


def clear_partitions(disk, progress_bar, success_count, failure_count):
    try:
        # clear existing partitions,  gpt and create new partition.
        subprocess.run(['sudo', 'parted', '--script', disk, 'mklabel', 'gpt', 'mkpart', 'primary', '0%', '100%'],
                       check=True)

        progress_bar.update(1)
        success_count.append(disk)
        # logs goes into diskforge.log
        logging.info(f"Partitions cleared for disk {disk} and GPT label created")
    except subprocess.CalledProcessError as e:
        failure_count.append(disk)
        logging.error(f"Failed to clear partitions and create GPT label for disk {disk}: {e}")


def clear_partitions_all(disks):
    success_count = []
    failure_count = []

    print(f"Total Disks found: {len(disks)}")
    print("Clearing partition tables...")

    # single progress bar for all
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
