import diskforge

if __name__ == "__main__":
    disks = diskforge.identify_disks()

    diskforge.check_disk_health(disks)

    diskforge.visualize_disk_sizes(disks)

    diskforge.confirm_action(disks)

    diskforge.clear_partitions_all(disks)

    diskforge.format_all_disks(disks)

    diskforge.set_labels(disks)
