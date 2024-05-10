import os
import subprocess
import sys


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

    # remove the OS disk
    disk_list.remove(os_disk)

    if len(disk_list) == 0:
        print("No other disks found.")
        return []

    return disk_list

