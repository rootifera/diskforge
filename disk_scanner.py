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
    os.write(fd.fileno(), b'\0' * size)


def read_sector(fd, sector, size):
    os.lseek(fd.fileno(), sector * size, os.SEEK_SET)
    os.read(fd.fileno(), size)


def scan_disk(disk_path, sector_size, update_queue, lock, stop_event):
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
                if stop_event.is_set():
                    with lock:
                        update_queue[disk_path]['stopped'] = True
                    break

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


def update_ui(stdscr, update_queue, lock, disk_map, stop_events):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.echo()

    curses.start_color()
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_BLUE, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
    curses.init_pair(7, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(8, curses.COLOR_RED, curses.COLOR_BLACK)

    height, width = stdscr.getmaxyx()
    max_width_per_disk = 30
    max_disks_per_row = width // max_width_per_disk
    input_buffer = ""

    while True:
        stdscr.clear()
        num_disks = len(disk_map)
        num_rows = (num_disks + max_disks_per_row - 1) // max_disks_per_row
        max_rows_for_display = (height - 1) // 10
        num_rows = min(num_rows, max_rows_for_display)

        for idx, (disk_num, disk) in enumerate(disk_map.items()):
            row = idx // max_disks_per_row
            col = idx % max_disks_per_row
            y = row * 10
            x = col * max_width_per_disk

            if y + 8 >= height:
                stdscr.addstr(height - 1, 0, "Not all disks are displayed.")
                break

            if 'error' in update_queue[disk]:
                stdscr.addstr(y, x, f"Disk {disk_num}: {update_queue[disk]['error']}", curses.color_pair(7))
                continue
            if 'stopped' in update_queue[disk]:
                stdscr.addstr(y, x, f"Disk {disk_num}: Stopped", curses.color_pair(5))
                continue

            stdscr.addstr(y, x, f"Disk {disk_num}: {disk}")
            with lock:
                stats = update_queue[disk]
                stdscr.addstr(y + 1, x, f"<5ms     = {stats['<5ms']}", curses.color_pair(1))
                stdscr.addstr(y + 2, x, f"<10ms    = {stats['<10ms']}", curses.color_pair(2))
                stdscr.addstr(y + 3, x, f"<20ms    = {stats['<20ms']}", curses.color_pair(3))
                stdscr.addstr(y + 4, x, f"<50ms    = {stats['<50ms']}", curses.color_pair(4))
                stdscr.addstr(y + 5, x, f"<150ms   = {stats['<150ms']}", curses.color_pair(5))
                stdscr.addstr(y + 6, x, f"<500ms   = {stats['<500ms']}", curses.color_pair(6))
                stdscr.addstr(y + 7, x, f">500ms   = {stats['>500ms']}", curses.color_pair(7))
                stdscr.addstr(y + 8, x, f"BAD      = {stats['bad']}", curses.color_pair(8) | curses.A_BOLD)

        prompt_str = "Press 'q' to quit. Enter disk number to stop: "
        stdscr.addstr(height - 1, 0, prompt_str)
        stdscr.addstr(height - 1, len(prompt_str), input_buffer)
        stdscr.refresh()

        key = stdscr.getch()

        if key == ord('q'):
            break

        if key == curses.KEY_BACKSPACE or key == 127:
            input_buffer = input_buffer[:-1]

        elif key == curses.KEY_ENTER or key == 10:
            if input_buffer.isdigit():
                disk_num = int(input_buffer)
                if disk_num in stop_events:
                    stop_events[disk_num].set()
            input_buffer = ""

        elif key != -1 and chr(key).isdigit():
            input_buffer += chr(key)

        time.sleep(1)


def scan_disks(disks):
    sector_size = 512
    update_queue = defaultdict(lambda: defaultdict(int))
    lock = threading.Lock()

    disk_map = {i: disk for i, disk in enumerate(disks)}
    stop_events = {i: threading.Event() for i in disk_map}

    threads = []
    for i, disk in disk_map.items():
        t = threading.Thread(target=scan_disk, args=(disk, sector_size, update_queue, lock, stop_events[i]))
        t.start()
        threads.append(t)

    try:
        curses.wrapper(update_ui, update_queue, lock, disk_map, stop_events)
    except KeyboardInterrupt:
        pass
    finally:
        for event in stop_events.values():
            event.set()
        for t in threads:
            t.join()
