import logging
from functions import identify_disks, clear_partitions_all, format_all_disks

logging.basicConfig(filename='diskforge.log', level=logging.INFO)


def main():
    # Step 1: wipe and create partitions
    disks = identify_disks()
    if disks:
        clear_partitions_all(disks)
    else:
        print("No disks found.")
        return

    # Step 2: format all disks with exFAT
    format_all_disks(disks)


if __name__ == "__main__":
    main()
