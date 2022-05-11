#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 
# 
# 2022-05-06

__version__ = "0.7.1"
__author__ = "Igor Martynov (phx.planewalker@gmail.com)"



"""This app stores, compares and manages lists of checksums of files.

Originally written to manage photo collection and store checksums of RAW files.
"""


import sys
import os.path
import os
import datetime
import time
import glob
import configparser

# logging
import logging
import logging.handlers

import traceback

# Flask
from flask import Flask, request, Response, render_template, redirect, url_for, session, g


from base import *
from managers import *


from sqlalchemy_declarative import DeclarativeBase, File, Directory
from sqlalchemy import create_engine, select




"""DuplicateChecker

What app should do:
	1. Calculate checksums of all files in dir
	2. Store checksums of files in dir. Files in one dir may be:
		a) totally different
		b) equal checkums but different names - file1.jpg and file1-2.jpg
		c) equal names but different checksums - file1.jpg and edited/file1.jpg
		d) equal checksums and names - file1.jpg and copy/file1.jpg
	3. Files on different dirs can be:
		a) Comepletely identical - the same full_path, name, checksum - but still they are individual 
		b) equal checkums but different names - file1.jpg and file1-2.jpg - copies of one file
		c) equal names but different checksums - file1.jpg and file1.jpg - the same file
		d) totally different
		
	
	
"""

	
class DuplicateChecker(object):
	"""DuplicateChecker app"""
	
	def __init__(self, db_file = None, config_file = os.path.join(os.path.abspath(os.path.dirname(__file__)), "duplicate_checker.conf")):
		super(DuplicateChecker, self).__init__()
		
		# config
		self.CONFIG_FILE = config_file
		self._config = configparser.ConfigParser()
		self._config.read(self.CONFIG_FILE)
		
		# logging
		if os.sep not in self._config.get("main", "log_file"):
			self.LOG_FILE = os.path.join(os.path.abspath(os.path.dirname(__file__)), self._config.get("main", "log_file"))
			print(f"Using relative path to log file: {self.LOG_FILE}")
		else:
			self.LOG_FILE = self._config.get("main", "log_file")
			print(f"Using absolute path to log file: {self.LOG_FILE}")
		self.rotate_logs()
		self._logger = logging.getLogger("duplicate_checker")
		self._logger.setLevel(logging.DEBUG)
		fh = logging.FileHandler(self.LOG_FILE)
		fh.setLevel(logging.DEBUG)
		formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
		fh.setFormatter(formatter)
		self._logger.addHandler(fh)
		
		self._logger.debug("======== duplicate_checker starting, version " + __version__ + " ========")
		
		self.checksum_algorithm = self._config.get("main", "checksum_algorithm")
		self.ignore_duplicates = False
		
		if db_file is not None:
			self.DB_FILE = db_file
		else:
			if os.sep not in self._config.get("main", "db_file"):
				self.DB_FILE = os.path.join(os.path.abspath(os.path.dirname(__file__)), self._config.get("main", "db_file"))
				print(f"Using relative path to DB file: {self.DB_FILE}")
			else:
				self.DB_FILE = self._config.get("main", "db_file")
				print(f"Using absolute path to DB file: {self.DB_FILE}")

		
		# sqlalchemy
		self._engine = None
		self._session = None
		
		self.file_manager = FileManager(logger = self._logger.getChild("FileManager"))
		self.dir_manager = DirManager(logger = self._logger.getChild("DirManager"))
		# self.comparison_manager = ComparisonManager(logger = self._logger.getChild("DirManager")) # not used any more
		self.task_manager = TaskManager(logger = self._logger.getChild("TaskManager"),
			checksum_algorithm = self.checksum_algorithm,
			ignore_duplicates = self.ignore_duplicates)
		
		self.init_DB_orm()
		self.init_managers()
		pass
	
	
	def create_DB_schema(self):
		self._logger.debug("create_DB_schema: starting")
		File.__table__.create(bind = self._engine, checkfirst = True)
		Directory.__table__.create(bind = self._engine, checkfirst = True)
		self._logger.debug("create_DB_schema: complete")
	
	
	def init_DB_orm(self):
		self._logger.debug(f"init_DB_orm: starting. will use db file {self.DB_FILE}")
		self._engine = create_engine(f"sqlite:///{self.DB_FILE}", connect_args = {"check_same_thread": False})
		DeclarativeBase.metadata.bind = self._engine
		# if not os.path.exists(self.DB_FILE):
		# 	self._logger.debug("init_DB_orm: DB file does not exist, will try to create it")
		# 	DeclarativeBase.metadata.create_all(self._engine)
		# 	self._logger.debug("init_DB_orm: all created, will continue")
		
		self.create_DB_schema()
		
		from sqlalchemy.orm import sessionmaker
		DBSession = sessionmaker(autocommit = False, autoflush = False)
		DBSession.bind = self._engine
		self._session = DBSession()	
		self._logger.debug("init_DB_orm: complete")
	
	
	def init_managers(self):
		self.file_manager.set_db_session(self._session)
		self.dir_manager.set_db_session(self._session)
		self.task_manager.set_db_session(self._session)
		self.task_manager.set_file_manager(self.file_manager)
		self.task_manager.set_dir_manager(self.dir_manager)
	
	
	def rotate_logs(self):
		"""will rotate .log file to .log.old, thus new log file will be used on each start"""
		OLD_LOG_POSTFIX = ".old"
		if os.path.isfile(self.LOG_FILE + OLD_LOG_POSTFIX):
			os.unlink(self.LOG_FILE + OLD_LOG_POSTFIX)
		try:
			os.rename(self.LOG_FILE, self.LOG_FILE + OLD_LOG_POSTFIX)
		except Exception as e:
			print(f"could not rotate log file {self.LOG_FILE}, will overwrite old file!")
	
	
	def delete_directory(self, _dir):
		try:
			date_start = datetime.datetime.now()
			for f in _dir.files:
				self.file_manager.delete(f)
			self.dir_manager.delete(_dir)
			date_end = datetime.datetime.now()
			self._logger.info(f"delete_directory: deleted directory {_dir.full_path}, took {(date_end - date_start).total_seconds()}s")
			return True
		except Exception as e:
			self._logger.error(f"delete_directory: got error while deleting directory {_dir.full_path}, error: {e}, traceback: {traceback.format_exc()}")
			return False
	
	
	def backup_DB(self):
		"""will backup DB file - just copy it to self.DB_FILENAME with appended postfix"""
		import shutil
		DATETIME_FORMAT_STR = "%Y-%m-%d_%H-%M-%S"
		DEST_FILENAME = self.DB_FILE + f"_backup_{datetime.datetime.now().strftime(DATETIME_FORMAT_STR)}"
		self._logger.debug(f"backup_DB: will backup DB file {self.DB_FILE}")
		if not self.task_manager.task_is_running():
			try:
				shutil.copy(self.DB_FILE, DEST_FILENAME)
				self._logger.info(f"backup_DB: DB backed up to file {DEST_FILENAME}")
				return True
			except Exception as e:
				self._logger.error(f"backup_DB: could not backup DB, got error {e}, exception: {traceback.format_exc()}")
				return False
		else:
			self._logger.debug("backup_DB: could not backup DB because task is running.")
			return False
	
	
	def execute_sql_query(self, query_text):
		self._logger.info(f"execute_sql_query: will execute query: {query_text}")
		try:
			result = self._session.execute(query_text)
			return result
		except Exception as e:
			self._logger.error(f"execute_sql_query: got error {e}, traceback: {traceback.format_exc()}")
			return None



class DuplicateCheckerFlask(DuplicateChecker):
	"""DuplicateChecker web app with Flask"""
	
	def __init__(self, db_file = "", config_file = os.path.join(os.path.abspath(os.path.dirname(__file__)), "duplicate_checker.conf")):
		super(DuplicateCheckerFlask, self).__init__(db_file = db_file, config_file = config_file)
		
		# web interface
		self.port = int(self._config.get("web", "port"))
		self.addr = self._config.get("web", "host")
		pass
	
	
	def run_web_app(self):
		web_app = Flask(__name__)
		web_app.secret_key = self._config.get("web", "secret")
		
		
		
		@web_app.route("/", methods = ["GET"])
		def show_main():
			if request.method == "GET":
				return render_template("main_page.html", dirs = [], version = __version__, tasks = [], db_file = self.DB_FILE)
		
		
		@web_app.route("/show-all-dirs", methods = ["GET"])
		def show_all_dirs():
			if request.method == "GET":
				dir_list = list(self.dir_manager.get_full_list())
				dir_list.sort(key = lambda _dir: _dir.id)
				return render_template("show_all_dirs.html", dirs = dir_list)
		
		
		@web_app.route("/show-dir/<int:dir_id>")
		def show_dir(dir_id):
			if request.method == "GET":
				return render_template("show_dir.html", dir = self.dir_manager.get_by_id(dir_id))
		
		
		@web_app.route("/show-file/<int:file_id>", methods = ["GET"])
		def show_file(file_id):
			if request.method == "GET":
				found_file = self.file_manager.get_by_id(file_id)
				if found_file is None:
					return render_template("blank_page.html", page_text = f"ERROR file with id {file_id} not found!")
				return render_template("show_file.html", file = found_file, duplcates = self.comparison_manager.find_file_duplicates(found_file))
		
		
		@web_app.route("/search-files-by-checksum/<string:file_checksum>", methods = ["GET"])
		def find_files_by_checksum(file_checksum):
			found_files = self.file_manager.get_by_checksum(file_checksum)
			self._logger.debug(f"find_files_by_checksum: found files {found_files} by checksum {file_checksum}")
			return render_template("show_files.html", files = found_files)
		
		
		@web_app.route("/add-dir", methods = ["GET", "POST"])
		def add_directory():
			if request.method == "GET":
				return render_template("add_dir.html")
				
			if request.method == "POST":
				dirs = str(request.form["path_to_dir"]).splitlines()
				is_etalon = True if request.form.get("is_etalon") is not None else False
				add_subdirs = True if request.form.get("add_subdirs") is not None else False
				self._logger.debug(f"add_directory: got input values from form: list of dirs: {dirs}, is etalon: {is_etalon}.")
				try:
					for d in dirs:
						if not add_subdirs:
							if not os.path.isdir(d):
								self._logger.info(f"add_directory: {d} is not a dir, will not add it")
							else:
								self.task_manager.add_directory(normalize_path_to_dir(d), is_etalon = is_etalon)
						else:
							subdirs = []
							subdirs = glob.glob(os.path.join(d, "*/"), recursive = False)
							self._logger.debug(f"add_directory: will add subdirs of directory {d}: {subdirs}")
							for p in subdirs:
								if os.path.isdir(p):
									self.task_manager.add_directory(normalize_path_to_dir(p), is_etalon = is_etalon)
								else:
									self._logger.info(f"add_directory: will not add subdir {p} of dir {d} - it is not a dir, ignoring")
				except Exception as e:
					self._logger.error(f"add_directory: could not add dirs - got error {e}, traceback: {traceback.format_exc()}")
					return render_template("blank_page.html", page_text = f"ERROR: {e}, traceback: {traceback.format_exc()}")
				return render_template("add_dir.html", msg_text = f"dir(s) added")
		
		
		@web_app.route("/delete-file/<int:file_id>", methods = ["GET", "POST"])
		def delete_file(file_id):
			target_file = self.file_manager.get_by_id(file_id)
			if target_file is None:
				return render_template("blank_page.html", page_text = f"ERROR file with id {file_id} not found")
			if request.method == "GET":
				return render_template("delete_file.html", file = target_file)
			if request.method == "POST":
				self.file_manager.delete(target_file)
				return render_template("blank_page.html", page_text = f"deleted successfuly file with id {file_id}")
		
		
		@web_app.route("/delete-dir/<int:dir_id>", methods = ["GET", "POST"])
		def delete_directory(dir_id):
			target_dir = self.dir_manager.get_by_id(dir_id)
			if target_dir is None:
				return render_template("blank_page.html", page_text = f"ERROR dir with id {dir_id} not found")
			if request.method == "GET":
				return render_template("delete_dir.html", dir = target_dir)
			if request.method == "POST":
				result = self.delete_directory(target_dir)
				if result:
					return render_template("blank_page.html", page_text = f"deleted successfuly dir with id {dir_id}")
				else:
					return render_template("blank_page.html", page_text = f"ERROR got error while deling dir with id {dir_id}")
		
		
		@web_app.route("/show-task/<int:task_id>", methods = ["GET", "POST"])
		def show_task(task_id):
			self._logger.debug(f"show_task: will show task {task_id}")
			try:
				found_task = self.task_manager.tasks[task_id]
				self._logger.debug(f"show_task: will use task {found_task}")
			except Exception as e:
				self._logger.error(f"show_task: gor error {e}, traceback: {traceback.format_exc()}")
				return render_template("blank_page.html", text = f"error {e}")
			return render_template("show_task.html", task = found_task)
		
		
		@web_app.route("/show-all-tasks", methods = ["GET", "POST"])
		def show_tasks():
			return render_template("show_all_tasks.html", tasks = self.task_manager.tasks)
		
		
		@web_app.route("/show-log", methods = ["GET"])
		def show_log():
			with open(self.LOG_FILE, "r") as f:
				log_text = f.read()
			return render_template("blank_page.html", page_text = log_text.replace("\n", "<br>\n"))
		
		
		# compare dirs
		@web_app.route("/compare-dirs-form", methods = ["GET", "POST"])
		def compare_directories():
			if request.method == "GET":
				return render_template("compare_dirs_form.html")
			if request.method == "POST":
				dir_a_id = request.form["dir_a_id"]
				dir_b_id = request.form["dir_b_id"]
				dir_a = self.dir_manager.get_by_id(dir_a_id)
				dir_b = self.dir_manager.get_by_id(dir_b_id)
				if dir_a is None:
					return render_template("blank_page.html", page_text = f"ERROR Directory A with id {dir_a_id} does not exist!")
				if dir_b is None:
					return render_template("blank_page.html", page_text = f"ERROR Directory B with id {dir_b_id} does not exist!")
				self.task_manager.compare_directories(dir_a, dir_b)
				return render_template("blank_page.html", page_text = "task CompareDirsTask launched, see all tasks - [<a href='/show-all-tasks' title='show tasks'>show tasks</a>]<br>")
		
		
		@web_app.route("/check-dir/<int:dir_id>", methods = ["GET"])
		def check_dir(dir_id):
			target_dir = self.dir_manager.get_by_id(dir_id)
			if target_dir is None:
				return render_template("blank_page.html", page_text = f"ERROR dir with id {dir_id} not found!")
			if request.method == "GET":
				if not os.path.isdir(target_dir.full_path):
					return render_template("blank_page.html", page_text = f"Cannot check directory {target_dir.full_path} - it does not exist or is unavailable")
				self.task_manager.check_dir(target_dir)
				return render_template("blank_page.html", page_text = f"Task CheckDirTask created for dir {target_dir.full_path} check, see tasks " + "- [<a href='/show-all-tasks' title='show tasks'>show tasks</a>]<br>")
		
		
		# check dir has copies
		@web_app.route("/find-copies/<int:dir_id>", methods = ["GET"])
		def find_copies(dir_id):
			target_dir = self.dir_manager.get_by_id(dir_id)
			if target_dir is None:
				return render_template("blank_page.html", page_text = f"ERROR dir with id {dir_id} not found!")
			self.task_manager.find_copies(target_dir)
			return render_template("blank_page.html", page_text = "task FindCopiesTask launched, see tasks - [<a href='/show-all-tasks' title='show tasks'>show tasks</a>]<br>")
		
		
		# shutdown app
		@web_app.route("/shutdown-app", methods = ["GET", "POST"])
		def shutdown_app():
			if request.method == "GET":
				if self.task_manager.task_is_running():
					self._logger.info("shutdown_app: should shutdown, but can not - there is an running task")
					return render_template("blank_page.html", page_text = "Cannot shutdown, there is running task")
				else:
					self._logger.info("shutdown_app: will shutdown")
					time.sleep(3)
					sys.exit(0)
					return render_template("blank_page.html", page_text = "shutted down") # this will be never returned 
		
		
		# start one task
		@web_app.route("/start-task/<int:task_num>", methods = ["GET"])
		def start_task(task_num):
			if request.method == "GET":
				try:
					self.task_manager.start_task(self.task_manager.tasks[task_num])
					# return render_template("blank_page.html", page_text = f"task {self.task_manager.tasks[task_num]} started")
					return redirect("/show-all-tasks")
				except Exception as e:
					self._logger.error(f"start_task: got error {e} while strting task num {task_num}. traceback: {traceback.format_exc()}")
					return render_template("blank_page.html", page_text = f"ERROR could not start task number {task_num}, error: {e}")
		
		
		# start all task
		@web_app.route("/start-all-tasks", methods = ["GET"])
		def start_all_tasks():
			if request.method == "GET":
				self.task_manager.start_all_tasks_successively()
				return redirect("/show-all-tasks")
		
		
		@web_app.route("/backup-db", methods = ["GET"])
		def backup_DB():
			"""create copy of DB file with current date as filename suffix"""
			if request.method == "GET":
				self._logger.debug("backup_DB: will try to start backup of DB")
				if self.backup_DB():
					return render_template("blank_page.html", page_text = "DB backup complete OK")
				else:
					return render_template("blank_page.html", page_text = "DB backup FAILED")
		
		
		# TODO: under heavy development
		@web_app.route("/edit-dir/<int:dir_id>", methods = ["GET", "POST"])
		def edit_dir(dir_id):
			target_dir = self.dir_manager.get_by_id(dir_id)
			if target_dir is None:
				return render_template("blank_page.html", page_text = f"ERROR dir with id {dir_id} not found!")
			if request.method == "GET":
				return render_template("edit_dir.html", dir = target_dir)
			if request.method == "POST":
				dir_fullpath = request.form["full_path"]
				dir_comment = request.form["comment"]
				is_etalon = True if request.form.get("is_etalon") is not None else False
				enabled = True if request.form.get("is_enabled") is not None else False
				self._logger.debug(f"edit_dir: for dir {target_dir.full_path} got: full_path: {dir_fullpath}, comment: {dir_comment}, is_etalon: {is_etalon}, enabled: {enabled} ")
				target_dir.comment = dir_comment
				target_dir.is_etalon = is_etalon
				target_dir.enabled = enabled
				self.dir_manager.db_commit()
				self._logger.debug(f"edit_dir: complete for dir {target_dir.full_path}")
				return render_template("edit_dir.html", dir = target_dir)
			
		
		@web_app.route("/split-dir/<int:dir_id>", methods = ["GET", "POST"])
		def split_dir(dir_id):
			target_dir = self.dir_manager.get_by_id(dir_id)
			if target_dir is None:
				# return render_template("blank_page.html", page_text = f"ERROR dir with id {dir_id} not found!")
				return render_template("blank_page.html", page_text = f"ERROR dir with id {dir_id} not found!")
			if request.method == "GET":
				self.task_manager.split_dir(target_dir)
				return render_template("blank_page.html", page_text = "task SplitDirTask launched, see tasks - [<a href='/show-all-tasks' title='show tasks'>show tasks</a>]<br>")
			# if request.method == "POST":
			# 	pass
		
		
		@web_app.route("/execute-sql-query", methods = ["GET", "POST"])
		def execute_sql_query():
			if request.method == "GET":
				return render_template("execute_sql_query.html")
			if request.method == "POST":
				query_text = request.form["query_text"]
				result = self.execute_sql_query(query_text)
				return render_template("execute_sql_query.html", result = str(result))
			pass
		
		
		# disable all
		
		
		# enable all
		
		
		
		web_app.jinja_env.filters["empty_on_None"] = empty_on_None
		web_app.jinja_env.filters["newline_to_br"] = newline_to_br
		
		print("starting web interface...\n")
		web_app.run(host = self.addr, port = self.port, use_reloader = False)
		# print("\n\nPlease open http://127.0.0.1:" + str(self.port) + " or http://SERVER_IP:" + str(self.port) + " in ypur browser.")
		pass
		
		

	
if __name__ == "__main__":
	
	if "--help" in sys.argv[1:]:
		print("DuplicateChecker web app")
		print("	--db-file /path/to/db")
		# print("--web-app")
		print("")
		exit(0)
	
	
	if "--version" in sys.argv[1:]:
		print("version " + __version__ + "\n")
		exit(0)
		
	
	if "--db-file" in sys.argv[1:]:
		DB_FILE = sys.argv[sys.argv.index("--db-file") + 1]
		print(f"Using DB file from command arguments: {DB_FILE}")
	else:
		# DB_FILE = os.path.join(os.path.abspath(os.path.dirname(__file__)),"duplicate_checker.db")
		DB_FILE = None
	

	dc = DuplicateCheckerFlask(db_file = DB_FILE)
	dc.run_web_app()
	pass
