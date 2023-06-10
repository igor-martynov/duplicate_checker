
# Duplicate Checker.

This app was intended to save and manage file's checksums, to be sure that files are not corrupted by any cause.
Uses Flask for webUI and SQLAlchemy for SQLite database.


Originally was intended to manage photo collection - directories with many RAW files. 

Use cases:
1. Check consistency of all files that were stored for N years
2. Check consistency of copies (or find backups) of these files
3. Compare source dir and it's copy
4. Find duplicates of files or whole dirs on various medias
5. Make sure that there are copies of original files.	


Considerations:
	- Supported types of checksums are md5 and sha512 (recommended)
	- There can be many dirs and files with the same path and checksum
	


Typical workflows are:
1. Add all required dirs to app's database:
	- click "add dir" button on top
	- enter or paste path (or multiple paths, one per line)
	- mark checkbox "mark as etalon", if dir(s) you are adding is(are) logical etalon (i.e. original photo, which is supposed to be master)
	- mark checkbox "add subdirs instead of dir" if you want to add all subdirs of specified directory
	- press "add dir" button to finally add new AddDir task
	- go to tasks, press "autostart on" if it is disabled
	- wait till task is complete

2. Compare two dirs:
	- both dirs should be already added to database
	- go to "actions"
	- select both dirs with checkboxes
	- press "compare" button to add CompareDirs task
	- go to tasks, press "autostart on" if it is disabled
	- wait till task is complete
	- see the report of this task(s)

3. Find all copies of dir(s), either full or partial
	- of course, all dirs should be already in database
	- go to "actions"
	- select target dirs
	- press "find copies"
	- as usual, go to tasks, press "autostart on" if it is disabled
	- wait till task is complete
	- see the report of this task(s)

4. Split dir with files into separate subdirs
	- of course, all dirs should be already in database
	- go to "actions"
	- select target dirs
	- press "split"
	- as usual, go to tasks, press "autostart on" if it is disabled
	- wait till task is complete
	- new dirs will be added to database
	- see the report of this task

5. Compile new dir with files of target dirs, whose files will be copied to new dir
	- of course, all dirs should be already in database
	- and all dirs and files should be accessible at this moment
	- go to "actions"
	- select target dirs
	- press "compile new dir"
	- as usual, go to tasks, press "autostart on" if it is disabled
	- wait till task is complete

6. Delete, enable or disable dir(s)
	- of course, all dirs should be already in database
	- go to "actions"
	- select target dirs
	- "delete" will permanently delete selected dir. This cannot be undone.
	- "enable" will set "enabled" flag on dir. Enabled dir will participate in all operations. All dirs are enabled on creation
	- "disable" will unset "enabled" flag on dir. Disabled dir will ne ignored in all operations. This is useful when you want to ignore dir, but don't want to delete it
	


Roadmap.
	- fix issue with subtasks that are added as tasks
	- fix issue with new dir added when CheckDirTask is used
	- release of stable version 1.0
	- add functionality "copy all files without_copies to new dir"
	- add functionaluty "copy pathes to all files without_copies to clipboard"
	- add functionality "link to compare copy and orig on find copies result page"
	- add feature "substatus" in tasks which show current task operation


