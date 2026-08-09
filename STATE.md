# Loop Engineering State Memory

**Goal**: Add a tracking flag to autoreload to track changes in manage.py. This should automatically restart the server when manage.py is edited.
**Status**: Working on step 1 (Attempt 1)

## Tasks:
- [/] Step 1: Modify the autoreload module to include a tracking flag for manage.py changes.
- [ ] Step 2: Update the server management script (e.g., manage.py) to use the new tracking flag.
- [ ] Step 3: Implement file change monitoring logic in the autoreload module to detect edits to manage.py and trigger server restart.
- [ ] Step 4: Add command-line argument parsing to manage.py to accept the --track-changes flag and pass it to the server.
