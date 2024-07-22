import signal
import sys

import disk_scanner
import diskforge
from colorama import Fore, init

init(autoreset=True)


def signal_handler(sig, frame):
    print('\nExiting...')
    sys.exit(0)


def ask_user(prompt):
    while True:
        response = input(prompt).strip().lower()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        else:
            print("Please enter 'yes' or 'no'.")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

    print(f"{Fore.BLUE}=========== OS Disks ===============")
    disks = diskforge.identify_disks()
    print(f"{Fore.BLUE}=========== Disk Health ============")
    diskforge.check_disk_health(disks)
    print(f"{Fore.BLUE}=========== Disk Size ==============")
    diskforge.visualize_disk_sizes(disks)
    print(f"{Fore.BLUE}=========== Umount Partitions ======")
    diskforge.unmount_disks_partitions(disks)
    print(f"{Fore.BLUE}=========== Confirmation ===========")
    diskforge.confirm_action(disks)
    print(f"{Fore.BLUE}====================================")
    diskforge.clear_partitions_all(disks)
    print(f"{Fore.BLUE}====================================")
    diskforge.format_all_disks(disks)
    print(f"{Fore.BLUE}====================================")
    diskforge.set_labels(disks)
    print(f"{Fore.BLUE}====================================")

    if ask_user("Would you like to surface scan the disks? [If you need to remove disks please do it now] (yes/no): "):
        disks = diskforge.identify_disks()
        disk_scanner.scan_disks(disks)
    else:
        print(f"{Fore.GREEN}Exiting without surface scan.")
        sys.exit(0)
