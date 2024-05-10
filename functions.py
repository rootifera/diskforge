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
            disk_name = ''.join(filter(str.isalpha, disk_name))  # clean up
            disk_names.add(disk_name)

        return list(disk_names)
    except subprocess.CalledProcessError:
        print("Error: Unable to retrieve disk information.")
        return []


def identify_disks():
    disk_list = _all_disks()

    # find OS disk, we don't want to format that
    os_disk = os.popen("df / | grep -Eo '^/[^0-9]+'").read().strip()
    os_disk = os_disk.split('/')[-1]

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
        # Using parted for this operation
        subprocess.run(['sudo', 'parted', '--script', disk, 'mklabel', 'gpt'], check=True)
        progress_bar.update(1)
        success_count.append(disk)
        # logs goes into diskforge.log
        logging.info(f"Partitions cleared for disk {disk}")
    except subprocess.CalledProcessError as e:
        failure_count.append(disk)
        logging.error(f"Failed to clear partitions for disk {disk}: {e}")


def clear_partitions_all(disks):
    success_count = []
    failure_count = []

    print(f"Total Disks found: {len(disks)}")
    print("Clearing partition tables...")

    # adding '/dev/' to disk names
    dev_disks = ['/dev/' + disk for disk in disks]

    # single progress bar for all
    progress_bar = tqdm(total=len(dev_disks), desc="Overall Progress")

    # creating threads for each disk
    threads = []
    for dev_disk in dev_disks:
        thread = threading.Thread(target=clear_partitions, args=(dev_disk, progress_bar, success_count, failure_count))
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
