#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 
# 
# 2023-05-09


__version__ = "0.9.11"
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

# from sqlalchemy_declarative import DeclarativeBase, File, Directory
# from sqlalchemy import create_engine, select, Index, inspect

import json
import urllib.parse



"""DuplicateChecker app
"""

	
class DuplicateChecker(object):
	"""DuplicateChecker app class, provides base functionality"""
	
	def __init__(self, db_file = None, config_file = os.path.join(os.path.abspath(os.path.dirname(__file__)), "duplicate_checker.conf")):
		super(DuplicateChecker, self).__init__()
		
		# config handling
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
		self._logger.debug(f"======== duplicate_checker starting, version {__version__} ========")
		self.checksum_algorithm = self._config.get("main", "checksum_algorithm")
		self.ignore_duplicates = False
		self.task_autostart = True if self._config.get("main", "task_autostart") == "yes" else False
		# set DB file as either relative or absolute
		if db_file is not None:
			self.DB_FILE = db_file
		else:
			if os.sep not in self._config.get("main", "db_file"):
				self.DB_FILE = os.path.join(os.path.abspath(os.path.dirname(__file__)), self._config.get("main", "db_file"))
			else:
				self.DB_FILE = self._config.get("main", "db_file")
		# managers
		self.db_manager = DBManager(db_file = self.DB_FILE, logger = self._logger.getChild("DBManager"))
		self.file_manager = FileManager(logger = self._logger.getChild("FileManager"))
		self.dir_manager = DirManager(logger = self._logger.getChild("DirManager"))
		self.task_manager = TaskManager(logger = self._logger.getChild("TaskManager"),
			checksum_algorithm = self.checksum_algorithm,
			ignore_duplicates = self.ignore_duplicates,
			task_autostart = self.task_autostart)
		self.init_object_managers()
	
	
	def init_object_managers(self):
		self.file_manager.set_DB_manager(self.db_manager)
		self.dir_manager.set_DB_manager(self.db_manager)
		self.task_manager.set_DB_manager(self.db_manager)
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
	
	

class DuplicateCheckerFlask(DuplicateChecker):
	"""DuplicateChecker web app with Flask web interface"""
	
	def __init__(self, db_file = "", config_file = os.path.join(os.path.abspath(os.path.dirname(__file__)), "duplicate_checker.conf")):
		super(DuplicateCheckerFlask, self).__init__(db_file = db_file, config_file = config_file)
		
		# web interface properties
		self.port = int(self._config.get("web", "port"))
		self.addr = self._config.get("web", "host")
	
	
	def run_web_app(self):
		web_app = Flask(__name__)
		web_app.secret_key = self._config.get("web", "secret")		
		
		
		
		@web_app.route("/", methods = ["GET"])
		def redirect_main():
			return redirect("/ui")
		
		
		@web_app.route("/ui/", methods = ["GET"])
		def show_main():
			if request.method == "GET":
				return render_template("main_page.html", dirs = [], version = __version__, db_file = self.DB_FILE)
		
		
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
				return render_template("blank_page.html", page_text = "task CompareDirsTask launched, see all tasks - [<a href='/ui/show-all-tasks' title='show tasks'>show tasks</a>]<br>")
		
		
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
		
		
		@web_app.route("/api/edit-dir", methods = ["GET"])
		def edit_dir_api():
			dir_dict = get_dir_dict_from_request(request)
			target_dir = self.dir_manager.get_by_id(dir_dict["id"])
			if target_dir.full_path != dir_dict["full_path"]:
				self._logger.debug(f"edit_dir_api: got new full_path: {dir_dict['full_path']}")
				target_dir.full_path = dir_dict["full_path"]
				new_subpath = dir_dict["full_path"]
				for f in target_dir.files:
					f.full_path = os.path.join(new_subpath, os.path.basename(f.full_path))
					self._logger.debug(f"edit_dir_api: edited file {f.id} - {f.full_path}")
			if target_dir.is_etalon != dir_dict["is_etalon"]:
				self._logger.debug(f"edit_dir_api: got new is_etalon: {dir_dict['is_etalon']}")
				target_dir.is_etalon = dir_dict["is_etalon"]
			if target_dir.comment != dir_dict["comment"]:
				self._logger.debug(f"edit_dir_api: got new comment: {dir_dict['comment']}")
				target_dir.comment = dir_dict["comment"]
			if target_dir.enabled != dir_dict["enabled"]:
				self._logger.debug(f"edit_dir_api: got new enabled: {dir_dict['enabled']}")
				target_dir.enabled = dir_dict["enabled"]
			self.dir_manager.update(target_dir)
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
			input_dir_list, path_to_new_dir = get_dir_objects_and_new_dir_from_request(request, get_by_id = self.dir_manager.get_by_id)
			if len(input_dir_list) == 0:
				self._logger.error("compile_dir_api: got empty input dir list, aborting compiling")
				return render_template("blank_page.html", page_text = "Got empty dir list after parsing")
			self._logger.debug(f"compile_dir: creating new task for new_dir {path_to_new_dir}, input dir list is: {[idir.full_path for idir in input_dir_list]}")
			new_task = self.task_manager.compile_dir(path_to_new_dir, input_dir_list)
			return render_template("blank_page.html", page_text = f"New task CompileDirTask for new_dir {path_to_new_dir}, input dir list: {[idir.full_path for idir in input_dir_list]} created")
		
		
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
		
			
		# get_running_task
		@web_app.route("/api/get_running_task_to_js", methods = ["GET"])
		def get_running_task_id_api():
			target_task = self.task_manager.current_running_task
			if target_task is None:
				return ""
			return json.dumps(target_task.dict_for_json)
		
		
		# api_task_json
		@web_app.route("/api/get_task_to_js", methods = ["GET"])
		def get_task_js_api():
			target_task = get_task_objects_from_request(request, get_by_id = self.task_manager.get_by_id)[0]
			if target_task is None:
				return ""
			return json.dumps(target_task.dict_for_json)
		
		
		# get_file_by_id_to_js
		@web_app.route("/api/get_file_by_id_to_js", methods = ["GET"])
		def get_file_by_id_to_js():
			target_file = get_file_objects_from_request(request, get_by_id = self.file_manager.get_by_id)[0]
			if target_file is None:
				return ""
			return json.dumps(target_file.dict_for_json)
			
		
		# get_dir_by_id_to_js
		@web_app.route("/api/get_dir_by_id_to_js", methods = ["GET"])
		def get_dir_by_id_to_js():
			target_dir = get_dir_objects_from_request(request, get_by_id = self.dir_manager.get_by_id)[0]
			if target_dir is None:
				return ""
			return json.dumps(target_dir.dict_for_json)
		
		
		@web_app.route("/api/enable-dirs", methods = ["GET"])
		def enable_dirs_api():
			target_dir_list = get_dir_objects_from_request(request, get_by_id = self.dir_manager.get_by_id)
			try:
				for target_dir in target_dir_list:
					target_dir.enabled = True
					self.dir_manager.update(target_dir)
				self._logger.debug(f"enable_dirs_api: enabled dirs: {[str(d) for d in target_dir_list]}")
			except Exception as e:
				self._logger.error(f"enable_dirs_api: enabling dirs: {[str(d) for d in target_dir_list]} - got error {e}, traceback: {traceback.format_exc()}")
			return redirect("/ui/actions")
		
		
		@web_app.route("/api/disable-dirs", methods = ["GET"])
		def disable_dirs_api():
			target_dir_list = get_dir_objects_from_request(request, get_by_id = self.dir_manager.get_by_id)
			try:
				for target_dir in target_dir_list:
					target_dir.enabled = False
					self.dir_manager.update(target_dir)
				self._logger.debug(f"disable_dirs_api: disabled dirs: {[str(d) for d in target_dir_list]}")
			except Exception as e:
				self._logger.error(f"disable_dirs_api: disabling dirs: {[str(d) for d in target_dir_list]} - got error {e}, traceback: {traceback.format_exc()}")
			return redirect("/ui/actions")
		
		
		
		
		web_app.jinja_env.filters["empty_on_None"] = empty_on_None
		web_app.jinja_env.filters["newline_to_br"] = newline_to_br
		web_app.jinja_env.filters["secs_to_hrf"] = secs_to_hrf
		
		print("starting web interface...\n")
		web_app.run(host = self.addr, port = self.port, use_reloader = False)
		

	
if __name__ == "__main__":
	print(f"DuplicateChecker version {__version__}")
	
	if "--help" in sys.argv[1:]:
		print("DuplicateChecker web app")
		print("	--db-file /path/to/db")
		print("")
		exit(0)
	
	
	if "--version" in sys.argv[1:]:
		print("version " + __version__ + "\n")
		exit(0)
		
	
	if "--db-file" in sys.argv[1:]:
		DB_FILE = sys.argv[sys.argv.index("--db-file") + 1]
		print(f"Using DB file from command arguments: {DB_FILE}")
	else:
		DB_FILE = None
	

	dc = DuplicateCheckerFlask(db_file = DB_FILE)
	dc.run_web_app()
	
