#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 
# 
# 2022-12-15


__version__ = "0.9.8"
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
# from werkzeug.middleware.profiler import ProfilerMiddleware

from base import *
from managers import *
from flask_functions import *

from sqlalchemy_declarative import DeclarativeBase, File, Directory
from sqlalchemy import create_engine, select, Index, inspect

import json
import urllib.parse



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
		if os.sep not in self._config.get("main", "log_file"): # autodetect absolute or relative path to file
			self.LOG_FILE = os.path.join(os.path.abspath(os.path.dirname(__file__)), self._config.get("main", "log_file"))
		else:
			self.LOG_FILE = self._config.get("main", "log_file")
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
		self.task_autostart = True if self._config.get("main", "task_autostart") == "yes" else False
		# set DB file as either local or absolute
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
		# managers
		self.file_manager = FileManager(logger = self._logger.getChild("FileManager"))
		self.dir_manager = DirManager(logger = self._logger.getChild("DirManager"))
		self.task_manager = TaskManager(logger = self._logger.getChild("TaskManager"),
			checksum_algorithm = self.checksum_algorithm,
			ignore_duplicates = self.ignore_duplicates,
			task_autostart = self.task_autostart)
		# sub-init objects
		self.init_DB_orm()
		self.init_managers()
	
	
	def get_current_schema(self):
		inspector = inspect(self._engine)
		schemas = inspector.get_schema_names()
		for schema in schemas:
			self._logger.debug(f"get_current_schema: found schema {schema}")
			for table_name in inspector.get_table_names(schema = schema):
				self._logger.debug(f"get_current_schema: already existing: table: {table_name}, columns: {inspector.get_columns(table_name, schema = schema)}")
				self._logger.debug(f"get_current_schema: already existing: table: {table_name}, indexes: {inspector.get_indexes(table_name)}")
	
	
	def create_DB_schema(self):
		self._logger.debug("create_DB_schema: starting")
		try:
			File.__table__.create(bind = self._engine, checkfirst = True)
			Directory.__table__.create(bind = self._engine, checkfirst = True)
			TaskRecord.__table__.create(bind = self._engine, checkfirst = True)
			ind = Index("ix_checksum", File.__table__.c.checksum) # should be not there
		except Exception as e:
			self._logger.error(f"create_DB_schema: got error while creating db: {e}, traceback: {traceback.format_exc()}")
			return False
		self._logger.debug("create_DB_schema: complete")
		return True
	
	
	def init_DB_orm(self):
		self._logger.debug(f"init_DB_orm: starting, will use db file {self.DB_FILE}")
		self._engine = create_engine(f"sqlite:///{self.DB_FILE}", connect_args = {"check_same_thread": False})
		DeclarativeBase.metadata.bind = self._engine
		self.create_DB_schema()
		self.get_current_schema()
		from sqlalchemy.orm import sessionmaker
		DBSession = sessionmaker(autocommit = False, autoflush = False)
		DBSession.bind = self._engine
		self._session = DBSession()
		self._logger.debug("init_DB_orm: init complete")
	
	
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
	
	
	def backup_DB(self):
		"""will backup DB to file - just copy it to self.DB_FILENAME with appended postfix"""
		import shutil
		DATETIME_FORMAT_STR = "%Y-%m-%d_%H-%M-%S"
		DEST_FILENAME = self.DB_FILE + f"_backup_{datetime.datetime.now().strftime(DATETIME_FORMAT_STR)}"
		self._logger.debug(f"backup_DB: will backup DB file {self.DB_FILE}")
		if not self.task_manager.running:
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
	
	
	def run_web_app(self):
		web_app = Flask(__name__)
		web_app.secret_key = self._config.get("web", "secret")
		# web_app.wsgi_app = ProfilerMiddleware(web_app.wsgi_app)
		
		
		
		
		@web_app.route("/ui/", methods = ["GET"])
		def show_main():
			if request.method == "GET":
				return render_template("main_page.html", dirs = [], version = __version__, tasks = [], db_file = self.DB_FILE)
		
		
		@web_app.route("/ui/show-all-dirs", methods = ["GET"])
		def show_all_dirs():
			if request.method == "GET":
				dir_list = list(self.dir_manager.get_full_list())
				dir_list.sort(key = lambda _dir: _dir.id)
				return render_template("show_all_dirs.html", dirs = dir_list)
		
		
		@web_app.route("/ui/show-dir/<int:dir_id>")
		def show_dir(dir_id):
			if request.method == "GET":
				return render_template("show_dir.html", dir = self.dir_manager.get_by_id(dir_id))
		
		
		@web_app.route("/ui/show-file/<int:file_id>", methods = ["GET"])
		def show_file(file_id):
			if request.method == "GET":
				found_file = self.file_manager.get_by_id(file_id)
				if found_file is None:
					self._logger.error(f"show_file: file with id {file_id} not found!")
					return render_template("blank_page.html", page_text = f"ERROR file with id {file_id} not found!")
				duplicates = self.file_manager.get_by_checksum(found_file.checksum)
				self._logger.debug(f"show file: will show file {found_file.full_path}, duplicates: {duplicates}")
				return render_template("show_file.html", file = found_file, duplicates = duplicates)
		
		
		@web_app.route("/api/get-files-by-checksum", methods = ["GET"])
		def get_files_by_checksum_api():
			requested_dir = self.dir_manager.get_by_id(request.args.get("dir_id"))
			found_files = self.file_manager.get_by_checksum(request.args.get("checksum"), idir = requested_dir)
			return render_template("show_files.html", files = found_files)
		
		
		@web_app.route("/ui/add-dir", methods = ["GET", "POST"])
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
		
		
		@web_app.route("/api/add-dirs", methods = ["GET"])
		def add_dirs_api():
			path_to_new_dir_list = get_path_to_new_dirs_from_request(request)
			is_etalon, add_subdirs = get_add_options_for_new_dirs_from_request(request)
			self._logger.debug(f"add_dirs_api: will add dirs {path_to_new_dir_list}, is_etalon: {is_etalon}, add_subdirs: {add_subdirs}")
			return render_template("blank_page.html", page_text = "")
		
		
		@web_app.route("/api/delete-file", methods = ["GET"])
		def delete_file_api():
			target_file_list = get_file_objects_from_request(request, get_by_id = self.file_manager.get_by_id)
			self.task_manager.delete_files(target_file_list)
			return render_template("blank_page.html", page_text = f"Deleted {len(target_file_list)} files - task added")
		
		
		@web_app.route("/api/delete-dirs", methods = ["GET"])
		def delete_dirs_api():
			target_dir_list = get_dir_objects_from_request(request, get_by_id = self.dir_manager.get_by_id)
			for dir_obj in target_dir_list:
				self.task_manager.delete_directory(dir_obj)
			return render_template("blank_page.html", page_text = f"Added tasks for deleting {len(target_dir_list)} dirs: {[d.url_html_code for d in target_dir_list]}")
		
		
		@web_app.route("/ui/show-task/<int:task_id>", methods = ["GET", "POST"])
		def show_task(task_id):
			self._logger.debug(f"show_task: will show task {task_id}")
			try:
				target_task = self.task_manager.get_by_id(task_id)
				self._logger.debug(f"show_task: will use task {target_task}, length of result_html: {len(target_task.result_html)}")
			except Exception as e:
				self._logger.error(f"show_task: gor error {e}, traceback: {traceback.format_exc()}")
				return render_template("blank_page.html", text = f"error {e}")
			return render_template("show_task.html", task = target_task)
		
		
		@web_app.route("/ui/show-all-tasks", methods = ["GET", "POST"])
		def show_all_tasks():
			return render_template("show_all_tasks.html",
				all_tasks = self.task_manager.get_full_list(),
				current_task_list = self.task_manager.current_tasks,
				current_task = self.task_manager.current_running_task,
				is_running = self.task_manager.running,
				autostart = self.task_manager.autostart_enabled)
		
		
		@web_app.route("/ui/delete-task/<int:task_id>", methods = ["GET", "POST"])
		def delete_task(task_id):
			target_task = self.task_manager.get_by_id(task_id)
			if request.method == "GET":
				return render_template("delete_task.html", task = target_task)
			if request.method == "POST":
				self.task_manager.delete(target_task)
				return render_template("blank_page.html", page_text = f"task {target_task} removed")
		
		
		@web_app.route("/ui/delete-all-tasks", methods = ["GET"])
		def delete_all_tasks():
			all_tasks = self.task_manager.get_full_list()
			for t in all_tasks:
				if t not in self.task_manager.current_tasks:
					self.task_manager.delete(t)
			return render_template("show_all_tasks.html",
				all_tasks = self.task_manager.get_full_list(),
				current_task_list = self.task_manager.current_tasks,
				current_task = self.task_manager.current_running_task,
				is_running = self.task_manager.running,
				autostart = self.task_manager.autostart_enabled)
		
		
		web_app.route("/api/delete-task", methods = ["GET"])
		def delete_task_api():
			target_dir_list = get_task_objects_from_request(request, get_by_id = self.task_manager.get_by_id)
			for task in target_dir_list:
				self.task_manager.delete(task)
			return render_template("blank_page.html", page_text = f"tasks {target_dir_list} removed")
		
		
		@web_app.route("/ui/show-log", methods = ["GET"])
		def show_log():
			with open(self.LOG_FILE, "r") as f:
				log_text = f.read()
			return render_template("blank_page.html", page_text = log_text.replace("\n", "<br>\n"))
		
		
		# all actions in one form
		@web_app.route("/ui/actions", methods = ["GET"])
		def actions():
			if request.method == "GET":
				return render_template("actions.html", dirs = self.dir_manager.get_full_list())
		
		
		@web_app.route("/api/compare-dirs", methods = ["GET"])
		def compare_dirs_api():
			if request.method == "GET":
				dir_a_id = request.args.get("dir_a_id")
				dir_b_id = request.args.get("dir_b_id")
				dir_a = self.dir_manager.get_by_id(dir_a_id)
				dir_b = self.dir_manager.get_by_id(dir_b_id)
				if dir_a is None:
					return render_template("blank_page.html", page_text = f"ERROR Directory A with id {dir_a_id} does not exist!")
				if dir_b is None:
					return render_template("blank_page.html", page_text = f"ERROR Directory B with id {dir_b_id} does not exist!")
				self.task_manager.compare_directories(dir_a, dir_b)
				return render_template("blank_page.html", page_text = "task CompareDirsTask launched, see all tasks - [<a href='/show-all-tasks' title='show tasks'>show tasks</a>]<br>")
		
		
		@web_app.route("/api/check-dirs", methods = ["GET"])
		def check_dirs_api():
			target_dir_list = get_dir_objects_from_request(request, get_by_id = self.dir_manager.get_by_id)
			for dir_obj in target_dir_list:
				self.task_manager.check_dir(dir_obj)
			return render_template("blank_page.html", page_text = f"Added tasks for checking {len(target_dir_list)} dirs: {[d.url_html_code for d in target_dir_list]}")
		
		
		@web_app.route("/api/find-copies", methods = ["GET"])
		def find_copies_api():
			target_dir_list = get_dir_objects_from_request(request, get_by_id = self.dir_manager.get_by_id)
			for dir_obj in target_dir_list:
				self.task_manager.find_copies(dir_obj)
			return render_template("blank_page.html", page_text = f"Added tasks FindCopiesTask for {len(target_dir_list)} dirs: {[d.url_html_code for d in target_dir_list]}")
		
		
		@web_app.route("/ui/shutdown-app", methods = ["GET", "POST"])
		def shutdown_app():
			if request.method == "GET":
				if self.task_manager.running:
					self._logger.info("shutdown_app: should shutdown, but can not - there is an running task")
					return render_template("blank_page.html", page_text = "Cannot shutdown, there is running task")
				else:
					self._logger.info("shutdown_app: will shutdown")
					time.sleep(3)
					sys.exit(0)
					return render_template("blank_page.html", page_text = "shutted down") # this will be never returned 
		
		
		# start one task
		@web_app.route("/ui/start-task/<int:task_id>", methods = ["GET"])
		def start_task(task_id):
			if request.method == "GET":
				try:
					self.task_manager.start_task(self.task_manager.get_by_id(task_id))
					return redirect("/ui/show-all-tasks")
				except Exception as e:
					self._logger.error(f"start_task: got error {e} while strting task num {task_id}. traceback: {traceback.format_exc()}")
					return render_template("blank_page.html", page_text = f"ERROR could not start task number {task_id}, error: {e}")
		
		
		# start autostart thread
		@web_app.route("/ui/start-autostart", methods = ["GET"])
		def start_autostart():
			if request.method == "GET":
				self.task_manager.start_autostart_thread()
				return redirect("/ui/show-all-tasks")
		
		
		@web_app.route("/ui/stop-autostart", methods = ["GET"])
		def stop_autostart():
			if request.method == "GET":
				self.task_manager.autostart_enabled = False
				return redirect("/ui/show-all-tasks")
		
		
		@web_app.route("/ui/backup-db", methods = ["GET"])
		def backup_DB():
			"""create copy of DB file with current date as filename suffix"""
			if request.method == "GET":
				self._logger.debug("backup_DB: will try to start backup of DB")
				if self.backup_DB():
					return render_template("blank_page.html", page_text = "DB backup complete OK")
				else:
					return render_template("blank_page.html", page_text = "DB backup FAILED")
		
		
		# TODO: under heavy development
		@web_app.route("/ui/edit-dir/<int:dir_id>", methods = ["GET", "POST"])
		def edit_dir(dir_id):
			target_dir = self.dir_manager.get_by_id(dir_id)
			if target_dir is None:
				return render_template("blank_page.html", page_text = f"ERROR dir with id {dir_id} not found!")
			if request.method == "GET":
				return render_template("edit_dir_js.html", dir = target_dir)
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
		
		
		# TODO: under construction
		@web_app.route("/api/edit-dir", methods = ["GET"])
		def edit_dir_api():
			target_dir = get_dir_objects_from_request(request, get_by_id = self.dir_manager.get_by_id)[0]
			# full_path = 
			return render_template("blank_page.html")
		
		
		@web_app.route("/api/split-dirs", methods = ["GET"])
		def split_dir_api():
			target_dir_list = get_dir_objects_from_request(request, get_by_id = self.dir_manager.get_by_id)
			for dir_obj in target_dir_list:
				self.task_manager.split_dir(dir_obj)
			return render_template("blank_page.html", page_text = f"Added tasks SplitDirTask for splitting {len(target_dir_list)} dirs: {[d.url_html_code for d in target_dir_list]}")
		
		
		@web_app.route("/ui/execute-sql-query", methods = ["GET", "POST"])
		def execute_sql_query():
			if request.method == "GET":
				return render_template("execute_sql_query.html")
			if request.method == "POST":
				query_text = request.form["query_text"]
				result = self.execute_sql_query(query_text)
				return render_template("execute_sql_query.html", result = str(result))
		
		
		@web_app.route("/api/compile-dir", methods = ["GET", "POST"])
		def compile_dir_api():
			input_dir_list, path_to_new_dir = get_dir_objects_from_request_compile(request, get_by_id = self.dir_manager.get_by_id)
			if len(input_dir_list) == 0:
				self._logger.error("compile_dir_api: got empty input dir list, aborting compiling")
				return render_template("blank_page.html", page_text = "Got empty dir list after parsing")
			self._logger.debug(f"compile_dir: creating new task for new_dir {path_to_new_dir}, input dir list is: {[idir.full_path for idir in input_dir_list]}")
			new_task = self.task_manager.compile_dir(path_to_new_dir, input_dir_list)
			return render_template("blank_page.html", page_text = f"New task CompileDirTask for new_dir {path_to_new_dir}, input dir list: {[idir.full_path for idir in input_dir_list]} created")
		
		# TODO: remove this
		@web_app.route("/ui/save-task/<int:task_id>", methods = ["GET", "POST"])
		def save_task(task_id):
			if request.method == "GET":
				self.task_manager.save_task_result(self.task_manager.tasks[task_id])
				return render_template("blank_page.html", page_text = f"task number {task_id} saved to file.")
		
		
		# API
		# get_dir_full_path_by_id
		@web_app.route("/api/get_dir_full_path_by_id", methods = ["GET"])
		def get_dir_full_path_by_id_api():
			target_dir = get_dir_objects_from_request(request)[0]
			return target_dir.full_path
		
		
		# get_file_full_path_by_id
		@web_app.route("/api/get_file_full_path_by_id", methods = ["GET"])
		def get_file_full_path_by_id_api():
			target_file = get_file_objects_from_request(request, get_by_id = self.file_manager.get_by_id)[0]
			return target_file.full_path
		
			
		# get_file_by_id
		
		
		
		# delete_files_api
		
		
		# api_task_json
		@web_app.route("/api/get_task_js", methods = ["GET"])
		def get_task_js_api():
			target_task = get_task_objects_from_request(request, get_by_id = self.task_manager.get_by_id)[0]
			
			pass
			
		
		
		# get_file_by_id_to_js
		@web_app.route("/api/get_file_by_id_to_js", methods = ["GET"])
		def get_file_by_id_to_js():
			target_file = get_file_objects_from_request(request, get_by_id = self.file_manager.get_by_id)[0]
			return json.dumps(target_file.dict_for_json)
			
		
		# get_dir_by_id_to_js
		@web_app.route("/api/get_dir_by_id_to_js", methods = ["GET"])
		def get_dir_by_id_to_js():
			target_dir = get_dir_objects_from_request(request, get_by_id = self.dir_manager.get_by_id)[0]
			return json.dumps(target_dir.dict_for_json)
		
		
		@web_app.route("/api/get_task_descr", methods = ["GET"])
		def get_task_descr_api():
			target_task_id = request.args.get("task_id")
			target_task = self.task_manager.tasks[target_task_id]
			return target_task.descr
		
		
		# TODO: remove
		@web_app.route("/api/get_running_task_descr", methods = ["GET"])
		def get_running_task_descr_api():
			crt = self.task_manager.current_running_task
			return "" if crt is None else crt.descr
		
		
		
		
		web_app.jinja_env.filters["empty_on_None"] = empty_on_None
		web_app.jinja_env.filters["newline_to_br"] = newline_to_br
		web_app.jinja_env.filters["secs_to_hrf"] = secs_to_hrf
		
		print("starting web interface...\n")
		web_app.run(host = self.addr, port = self.port, use_reloader = False)
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
