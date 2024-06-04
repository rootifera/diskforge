## Diskforge
This is a multi-threaded disk formatter application created for a specific use and tested only in that environment. There is a significant chance that it won't work for you without some modifications, so please don't just run it without checking what's going on.

### What does this script do?
- First, it retrieves everything listed by lsblk and then clears anything that doesn't match /dev/sdX.
- Within the devices, it tries to identify the OS disk to prevent accidental wiping. If it can't find the OS disk, the script halts.
- Then, we check the disk health by obtaining SMART info, and the script reports the state of the disks.
- Next, we generate visual disk size indicators to make it easier to identify disks of different sizes in the array.
- At this point, the script asks the user if they want to continue formatting the disks. If the user chooses yes:
  - All disks have their partition tables wiped and then recreated as GPT.
  - All disks are formatted as exFAT.
  - Finally, all disks are labeled according to their size.
 
![Sample Output](https://i.gyazo.com/a939ee6f7a0a3e4a0b0c4a8c19b8b5d2.png)


That's pretty much all.
