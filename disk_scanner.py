import os
import time
import subprocess
import curses
import threading
from collections import defaultdict


def log_summary(update_queue, disk_map):
    with open('diskforge_scan.log', 'w') as log_file:
        log_file.write("Diskforge Scan Summary\n")
        log_file.write("=" * 30 + "\n")
        for disk_num, disk in disk_map.items():
            log_file.write(f"Disk {disk_num + 1} ({disk}):\n")
            stats = update_queue[disk]
            for key, value in stats.items():
                log_file.write(f"{key}: {value}\n")
            log_file.write("-" * 30 + "\n")


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
    try:
        bytes_written = os.write(fd.fileno(), b'\0' * size)
        if bytes_written != size:
            raise IOError("Failed to write full sector")
    except Exception as e:
        print(f"Error writing sector {sector}: {e}")


def read_sector(fd, sector, size):
    os.lseek(fd.fileno(), sector * size, os.SEEK_SET)
    try:
        data = os.read(fd.fileno(), size)
        if len(data) != size:
            raise IOError("Failed to read full sector")
        return data
    except Exception as e:
        return None


def scan_disk(disk_path, sector_size, update_queue, lock, stop_event, perform_write):
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
                        update_queue[disk_path]['status'] = 'DONE'
                    break

                read_time = time_operation(read_sector, fd, sector, sector_size)

                if perform_write:
                    write_time = time_operation(write_sector, fd, sector, sector_size)
                else:
                    write_time = None

                with lock:
                    update_disk_stats(update_queue, disk_path, read_time)
                    if perform_write:
                        update_disk_stats(update_queue, disk_path, write_time)

            if not stop_event.is_set():
                with lock:
                    update_queue[disk_path]['status'] = 'DONE'

    except Exception as e:
        with lock:
            update_queue[disk_path]['error'] = f"Failed to open disk: {e}"


def update_disk_stats(update_queue, disk_path, operation_time):
    if operation_time is not None:
        if operation_time < 0.005:
            update_queue[disk_path]['<5ms'] += 1
        elif operation_time < 0.01:
            update_queue[disk_path]['<10ms'] += 1
        elif operation_time < 0.02:
            update_queue[disk_path]['<20ms'] += 1
        elif operation_time < 0.05:
            update_queue[disk_path]['<50ms'] += 1
        elif operation_time < 0.15:
            update_queue[disk_path]['<150ms'] += 1
        elif operation_time < 0.5:
            update_queue[disk_path]['<500ms'] += 1
        else:
            update_queue[disk_path]['>500ms'] += 1
    else:
        update_queue[disk_path]['bad'] += 1


def draw_disk_stats(stdscr, y, x, disk_num, disk, update_queue, lock):
    stdscr.addstr(y, x, f"Disk {disk_num}: {disk}")
    with lock:
        stats = update_queue[disk]
        stdscr.addstr(y + 1, x, f"<5ms     = {stats['<5ms']}", curses.color_pair(1))
        stdscr.addstr(y + 2, x, f"<10ms    = {stats['<10ms']}", curses.color_pair(2))
        stdscr.addstr(y + 3, x, f"<20ms    = {stats['<20ms']}", curses.color_pair(3))
        stdscr.addstr(y + 4, x, f"<50ms    = {stats['<50ms']}", curses.color_pair(3))
        stdscr.addstr(y + 5, x, f"<150ms   = {stats['<150ms']}", curses.color_pair(4))
        stdscr.addstr(y + 6, x, f"<500ms   = {stats['<500ms']}", curses.color_pair(5))
        stdscr.addstr(y + 7, x, f">500ms   = {stats['>500ms']}", curses.color_pair(6))
        stdscr.addstr(y + 8, x, f"BAD      = {stats['bad']}", curses.color_pair(6) | curses.A_BOLD)

        separator_y = y + 9
        stdscr.addstr(separator_y, x, f"-------------------", curses.color_pair(7) | curses.A_BOLD)

        status_y = y + 10
        status = stats.get('status', 'SCANNING')
        stdscr.addstr(status_y, x, f"STATUS   = {status}", curses.color_pair(7) | curses.A_BOLD)


def update_ui(stdscr, update_queue, lock, disk_map, stop_events):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.echo()

    curses.start_color()

    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_BLUE, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(7, curses.COLOR_GREEN, curses.COLOR_BLACK)

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

            if y + 9 >= height:
                stdscr.addstr(height - 1, 0, "Not all disks are displayed.")
                break

            disk_display = f"Disk {disk_num + 1}: {disk}"

            if 'error' in update_queue[disk]:
                stdscr.addstr(y, x, f"{disk_display}: {update_queue[disk]['error']}", curses.color_pair(7))
                continue

            stdscr.addstr(y, x, disk_display)
            draw_disk_stats(stdscr, y, x, disk_num + 1, disk, update_queue, lock)

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
                if disk_num - 1 in stop_events:
                    stop_events[disk_num - 1].set()
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

    print("Do you want to perform write tests as well? (yes/no): ")
    perform_write = input().lower() == 'yes'

    threads = []
    for i, disk in disk_map.items():
        t = threading.Thread(target=scan_disk,
                             args=(disk, sector_size, update_queue, lock, stop_events[i], perform_write))
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

    log_summary(update_queue, disk_map)
    os.system('reset')
    print("Scan complete. Summary written to diskforge_scan.log.")
