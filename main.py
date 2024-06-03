import diskforge
from colorama import Fore, init

init(autoreset=True)

if __name__ == "__main__":
    disks = diskforge.identify_disks()
    print(f"{Fore.BLUE}====================================")
    diskforge.check_disk_health(disks)
    print(f"{Fore.BLUE}====================================")

    diskforge.visualize_disk_sizes(disks)
    print(f"{Fore.BLUE}====================================")

    diskforge.confirm_action(disks)
    print(f"{Fore.BLUE}====================================")

    diskforge.clear_partitions_all(disks)
    print(f"{Fore.BLUE}====================================")

    diskforge.format_all_disks(disks)
    print(f"{Fore.BLUE}====================================")

    diskforge.set_labels(disks)
    print(f"{Fore.BLUE}====================================")
