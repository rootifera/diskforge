import os
import time
import subprocess
import curses
import threading
from collections import defaultdict


def time_operation(operation, fd, sector, size):
    start_time = time.time()
    try:
        operation(fd, sector, size)
        end_time = time.time()
        return end_time - start_time
    except Exception as e:
        return None


def write_sector(fd, sector, size):
    os.lseek(fd.fileno(), sector * size, os.SEEK_SET)
    os.write(fd.fileno(), b'\0' * size)  # Writing zero bytes to the sector


def read_sector(fd, sector, size):
    os.lseek(fd.fileno(), sector * size, os.SEEK_SET)
    os.read(fd.fileno(), size)


def scan_disk(disk_path, sector_size, update_queue, lock):
    # Get disk size in sectors
    try:
        result = subprocess.run(['blockdev', '--getsz', disk_path], capture_output=True, text=True, check=True)
        total_sectors = int(result.stdout.strip())
    except Exception as e:
        with lock:
            update_queue[disk_path]['error'] = f"Failed to get disk size: {e}"
        return

    try:
        with open(disk_path, 'rb+', buffering=0) as fd:
            for sector in range(total_sectors):
                write_time = time_operation(write_sector, fd, sector, sector_size)
                read_time = time_operation(read_sector, fd, sector, sector_size)

                with lock:
                    if write_time is not None:
                        if write_time < 0.005:
                            update_queue[disk_path]['<5ms'] += 1
                        elif write_time < 0.01:
                            update_queue[disk_path]['<10ms'] += 1
                        elif write_time < 0.02:
                            update_queue[disk_path]['<20ms'] += 1
                        elif write_time < 0.05:
                            update_queue[disk_path]['<50ms'] += 1
                        elif write_time < 0.15:
                            update_queue[disk_path]['<150ms'] += 1
                        elif write_time < 0.5:
                            update_queue[disk_path]['<500ms'] += 1
                        else:
                            update_queue[disk_path]['>500ms'] += 1
                    else:
                        update_queue[disk_path]['bad'] += 1

                    if read_time is not None:
                        if read_time < 0.005:
                            update_queue[disk_path]['<5ms'] += 1
                        elif read_time < 0.01:
                            update_queue[disk_path]['<10ms'] += 1
                        elif read_time < 0.02:
                            update_queue[disk_path]['<20ms'] += 1
                        elif read_time < 0.05:
                            update_queue[disk_path]['<50ms'] += 1
                        elif read_time < 0.15:
                            update_queue[disk_path]['<150ms'] += 1
                        elif read_time < 0.5:
                            update_queue[disk_path]['<500ms'] += 1
                        else:
                            update_queue[disk_path]['>500ms'] += 1
                    else:
                        update_queue[disk_path]['bad'] += 1

    except Exception as e:
        with lock:
            update_queue[disk_path]['error'] = f"Failed to open disk: {e}"


def update_ui(stdscr, update_queue, lock, disks):
    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        cols = width // 30
        rows = (len(disks) + cols - 1)

        for idx, disk in enumerate(disks):
            col = idx % cols
            row = idx // cols

            x = col * 30
            y = row * 10

            if y + 8 >= height:
                stdscr.addstr(height - 1, 0, "Not all disks are displayed.")
                break

            if 'error' in update_queue[disk]:
                stdscr.addstr(y, x, f"{disk}: {update_queue[disk]['error']}")
                continue
            stdscr.addstr(y, x, f"Disk: {disk}")
            with lock:
                stats = update_queue[disk]
                stdscr.addstr(y + 1, x, f"<5ms     = {stats['<5ms']}")
                stdscr.addstr(y + 2, x, f"<10ms    = {stats['<10ms']}")
                stdscr.addstr(y + 3, x, f"<20ms    = {stats['<20ms']}")
                stdscr.addstr(y + 4, x, f"<50ms    = {stats['<50ms']}")
                stdscr.addstr(y + 5, x, f"<150ms   = {stats['<150ms']}")
                stdscr.addstr(y + 6, x, f"<500ms   = {stats['<500ms']}")
                stdscr.addstr(y + 7, x, f">500ms   = {stats['>500ms']}")
                stdscr.addstr(y + 8, x, f"BAD      = {stats['bad']}")

        stdscr.refresh()
        time.sleep(1)


def scan_disks(disks):
    sector_size = 512
    update_queue = defaultdict(lambda: defaultdict(int))
    lock = threading.Lock()

    threads = []
    for disk in disks:
        t = threading.Thread(target=scan_disk, args=(disk, sector_size, update_queue, lock))
        t.start()
        threads.append(t)

    curses.wrapper(update_ui, update_queue, lock, disks)

    for t in threads:
        t.join()
