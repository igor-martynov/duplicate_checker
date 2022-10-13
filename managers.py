# import hashlib
import sys
import os.path
import os
import datetime
import time
import math
import glob


import multiprocessing
import threading
# import sqlite3

# logging
import logging
import logging.handlers

import traceback

from sqlalchemy_declarative import DeclarativeBase, File, Directory
from sqlalchemy import create_engine, select

sys.path.append("./")
from base import *
from tasks import *
		

"""

    

"""



class BaseManager(object, metaclass = MetaSingleton):
	"""BaseManager - base class for all managers. """
	# TODO: all class methods to abstract
	
	def __init__(self, session = None, logger = None):
		super(BaseManager, self).__init__()
		self._session = session
		self._logger = logger
	
	
	def set_db_session(self, _session):
		self._session = _session
		self._logger.debug(f"set_db_session: set to {_session}")
		
	
	def get_by_id(self, _id):
		raise NotImplemented
	
	
	def get_by_path(self, _path):
		raise NotImplemented
		
	
	def get_pre_list(self):
		"""get a pre-list, list of summaries, i.e. names only"""
		raise NotImplemented
	
	
	def get_full_list(self):
		"""fully load all objects"""
		raise NotImplemented
	
	
	def delete(self, obj):
		"""fully delete object, including DB commit"""
		self._session.delete(obj)
		self._session.commit()
		self._logger.info(f"delete: object deleted: {obj}, full_path: {obj.full_path}")
		
	
	def create(self, full_path = ""):
		raise NotImplemented

	
	def db_stats(self):
		return {"dirty": str(self._session.dirty), "new": str(self._session.new)}
	
	
	def db_commit(self):
		self._session.commit()
		self._logger.debug("db_commit: complete")



class FileManager(BaseManager):
	"""FileManager
	
	responsible for: all file operations: get by id, get by checksum, 
	"""
	
	def __init__(self, session = None, logger = None):
		super(FileManager, self).__init__(session = session, logger = logger)
		pass
	
	
	def get_by_id(self, _id):
		res = self._session.query(File).get(_id)
		return res
	
	
	def get_by_checksum(self, checksum, idir = None):
		if idir is None:
			res = self._session.query(File).filter(File.checksum == checksum).all()
		else:
			res = self._session.query(File).filter(File.checksum == checksum, File.dir_id == idir.id).all()
		return res
	
	
	def get_by_path(self, _path):
		res = self._session.query(File).filter(File.full_path == _path).all()
		return res
	
	
	def create(self,
		path_to_file,
		checksum = "",
		date_added = None,
		date_checked = None,
		is_etalon = False,
		comment = "",
		save = True):
		new_file = File(full_path = path_to_file,
			checksum = checksum,
			date_added = date_added,
			date_checked = date_checked,
			is_etalon = is_etalon,
			comment = comment)
		if save:
			self._session.add(new_file)
		return new_file
	
	
	def find_copies(self, _file):
		res = self._session.query(File).filter(File.checksum == _file.checksum, File.full_path != _file.full_path).all()
		self._logger.debug(f"find_copies: searched for copies of file {_file.full_path}, found: {len(res)}")
		return res
	
	

class DirManager(BaseManager):
	""" DirManager"""
	def __init__(self, session = None, logger = None):
		super(DirManager, self).__init__(session = session, logger = logger)
		
		pass
	
	
	def get_full_list(self):
		res = self._session.query(Directory).all()
		return res
	
	
	def get_by_id(self, _id):
		res = self._session.query(Directory).get(_id)
		return res
	
	
	def get_by_path(self, _path):
		res = self._session.query(Directory).filter(Directory.full_path == _path).all()
		return res
	
	
	def create(self, path_to_dir, is_etalon = False, date_added = None, date_checked = None, comment = "", save = True, name = ""):
		new_dir = Directory(full_path = path_to_dir,
			date_added = date_added,
			date_checked = date_checked,
			is_etalon = is_etalon,
			comment = comment,
			name = name)
		if save:
			self._session.add(new_dir)
		return new_dir
	
	
	def directory_exist(self, path_to_dir):
		res = self.get_by_path(path_to_dir)
		if (type(res) == type(list()) and len(res) != 0):
			return True
		else:
			return False
		


class TaskManager(BaseManager):
	"""TaskManager - create and manage tasks"""
	
	def __init__(self, session = None,
		logger = None,
		file_manager = None,
		dir_manager = None,
		checksum_algorithm = "md5",
		ignore_duplicates = False,
		task_autostart = False):
		super(TaskManager, self).__init__(session = session, logger = logger)
		
		self._file_manager = file_manager
		self._dir_manager = dir_manager
		
		self.checksum_algorithm = checksum_algorithm
		self.ignore_duplicates = ignore_duplicates
		
		self.tasks = []
		self.autostart = task_autostart
		# self.current_running_task = None
		self.running = False
		
		self.__thread = None
		self.SLEEP_BETWEEN_TASKS = 1.5
		self.SLEEP_BETWEEN_CHECKS = 5
	
	
	@property
	def current_running_task(self):
		for task in self.tasks:
			if task.running:
				return task
		return None
	
	
	def set_file_manager(self, file_manager):
		self._file_manager = file_manager
	
	
	def set_dir_manager(self, dir_manager):
		self._dir_manager = dir_manager
	
	
	def add_task(self, task = None):
		if task is None: return None
		self.tasks.append(task)
		self._logger.debug(f"create_task: task added: {task}")
		if self.autostart:
			task.start()
			self._logger.debug(f"add_task: autostarted task {task}")
	
	
	def start_task(self, task):
		if task in self.tasks:
			if task.running is None:
				self._logger.info(f"start_task: starting task {task}")
				task.start()
			else:
				self._logger.info(f"start_task: should start task {task} but it is already running, so ignoring")
		else:
			self._logger.error(f"start_task: could not find task {task}")
	
	
	def start_all_tasks_successively(self):
		
		def run_successively():
			self._logger.debug(f"run_successively: starting with tasks {self.tasks}")
			self.running = True
			for t in self.tasks:
				if t.running is None:
					self.start_task(t)
					while True:
						time.sleep(self.SLEEP_BETWEEN_CHECKS)
						if t.complete or t.running is False:
							time.sleep(self.SLEEP_BETWEEN_TASKS)
							self._logger.debug(f"run_successively: detected task end of {t}, starting next one")
							break
						else:
							self._logger.debug(f"run_successively: waiting for task...")
			
			self.running = False
			self._logger.debug(f"run_successively: complete for all tasks")
		
		
		self.__thread = threading.Thread(target = run_successively)
		self.__thread.start()
		self._logger.debug("start_all_tasks_successively: tasks run started")
	
	
	def save_task_result(self, task):
		try:
			filename = f"./tasks/task_{task.__class__.__name__}_{task.date_start.isoformat().replace(':','')}.log"
			with open(filename, "w") as f:
				f.write(task.result_html)
				self._logger.info(f"save_task_result: result saved as {filename}")
		except Exception as e:
			self._logger.error(f"save_task_result: error {e}, traceback: {traceback.format_exc()}")
		
	
	def add_directory(self, path_to_dir, is_etalon = False):
		if not os.path.isdir(path_to_dir):
			self._logger.info(f"add_directory: will not add dir {path_to_dir} as it is not a dir")
			return None
		if self.ignore_duplicates and self._dir_manager.directory_exist(path_to_dir):
			self._logger.info(f"add_directory: directory {path_to_dir} already exist, not adding it")
			return None
		# adding dir
		self._logger.info(f"add_directory: adding directory {path_to_dir}")
		new_task = AddDirTask(path_to_dir,
			logger = self._logger.getChild("AddDirTask_" + str(path_to_dir.split(os.sep)[-1])),
			file_manager = self._file_manager,
			dir_manager = self._dir_manager,
			is_etalon = is_etalon,
			checksum_algorithm = self.checksum_algorithm)
		self.add_task(new_task)
		self._logger.debug(f"add_directory: complete for {path_to_dir}")
		return new_task
	
	
	def compare_directories(self, dir_a, dir_b):
		new_task = CompareDirsTask(dir_a, dir_b, logger = self._logger.getChild(f"CompareDirsTask_{dir_a.id}_{dir_b.id}"), file_manager = self._file_manager, dir_manager = self._dir_manager)
		self.add_task(new_task)
		return new_task
	
	
	def find_copies(self, target_dir):
		new_task = FindCopiesTask(target_dir, logger = self._logger.getChild(f"FindCopiesTask_{target_dir.id}"), file_manager = self._file_manager, dir_manager = self._dir_manager)
		self.add_task(new_task)
		return new_task
		
	
	def check_dir(self, target_dir):
		new_task = CheckDirTask(target_dir,
			logger = self._logger.getChild(f"CheckDirTask_{target_dir.id}"),
			file_manager = self._file_manager,
			dir_manager = self._dir_manager,
			checksum_algorithm = self.checksum_algorithm)
		self.add_task(new_task)
		return new_task
	
	
	def split_dir(self, target_dir):
		new_task = SplitDirTask(target_dir, logger = self._logger.getChild(f"CheckDirTask_{target_dir.id}"), file_manager = self._file_manager, dir_manager = self._dir_manager)
		self.add_task(new_task)
		return new_task
	
	
	def compile_dir(self, path_to_new_dir, input_dir_list):
		new_task = CompileDirTask(path_to_new_dir, logger = self._logger.getChild(f"CompileDirTask_{os.path.basename(path_to_new_dir)}"),  file_manager = self._file_manager, dir_manager = self._dir_manager, input_dir_list = input_dir_list)
		self.add_task(new_task)
		return new_task
	
	
	
	def task_is_running(self):
		"""return True if any of tasks is running"""
		for t in self.tasks:
			if t.running:
				return True
		return False
	
	