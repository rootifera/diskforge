import signal
import sys

import diskforge
from colorama import Fore, init

init(autoreset=True)


def signal_handler(sig, frame):
    print('\nExiting...')
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

    print(f"{Fore.BLUE}=========== OS Disks ===============")
    disks = diskforge.identify_disks()
    print(f"{Fore.BLUE}=========== Disk Health ============")
    diskforge.check_disk_health(disks)
    #  print(f"{Fore.BLUE}=========== Disk Size ==============")
    #  diskforge.visualize_disk_sizes(disks)
    print(f"{Fore.BLUE}=========== Confirmation ===========")
    diskforge.confirm_action(disks)
    print(f"{Fore.BLUE}====================================")
    diskforge.clear_partitions_all(disks)
    print(f"{Fore.BLUE}====================================")
    diskforge.format_all_disks(disks)
    print(f"{Fore.BLUE}====================================")
    diskforge.set_labels(disks)
    print(f"{Fore.BLUE}====================================")
