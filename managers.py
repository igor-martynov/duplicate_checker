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

sess.query(User).filter(User.age == 25).\
    delete(synchronize_session=False)
    
    

"""



class BaseManager(object, metaclass = MetaSingleton):
	"""docstring for BaseManager"""
	
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
	
	
	# def delete(self, obj):
	# 	raise NotImplemented
	
	def delete(self, obj):
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
	"""docstring for FileManager
	
	responsible for: all file operations: get by id, get by checksum, 
	"""
	
	def __init__(self, session = None, logger = None):
		super(FileManager, self).__init__(session = session, logger = logger)
		pass
	
	
	def get_by_id(self, _id):
		res = self._session.query(File).get(_id)
		# self._logger.debug(f"get_by_id: will return {res}")
		return res
	
	
	def get_by_checksum(self, checksum):
		res = self._session.query(File).filter(File.checksum == checksum).all()
		# self._logger.debug(f"get_by_checksum: for input {checksum} will return {[f.full_path for f in res]}")
		return res
	
	
	def get_by_path(self, _path):
		res = self._session.query(File).filter(File.full_path == _path).all()
		# self._logger.debug(f"get_by_path: found files: {res} with target path {_path} and query {res}.")
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
		# self._logger.debug(f"get_full_list: will return {[d.full_path for d in res]}")
		return res
	
	
	def get_by_id(self, _id):
		res = self._session.query(Directory).get(_id)
		# self._logger.debug(f"get_by_id: will return {res}")
		return res
	
	
	def get_by_path(self, _path):
		res = self._session.query(Directory).filter(Directory.full_path == _path).all()
		# self._logger.debug(f"get_by_path: found dirs: {res} with target path {_path} and query {res}.")
		return res
	
	
	def create(self, path_to_dir, is_etalon = False, date_added = None, date_checked = None, comment = "", safe = True):
		# now = datetime.datetime.now()
		new_dir = Directory(full_path = path_to_dir, date_added = date_added, date_checked = date_checked, is_etalon = is_etalon, comment = comment)
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
	"""docstring for TaskManager"""
	
	def __init__(self, session = None, logger = None, file_manager = None, dir_manager = None):
		super(TaskManager, self).__init__(session = session, logger = logger)
		
		self._file_manager = file_manager
		self._dir_manager = dir_manager
		
		self.tasks = []
		self.autostart = False
		
		self.__thread = None
		self.SLEEP_BETWEEN_TASKS = 1.5
		self.SLEEP_BETWEEN_CHECKS = 5
		pass
	
	
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
							pass
			self._logger.debug(f"run_successively: complete for all tasks")
		
		
		self.__thread = threading.Thread(target = run_successively)
		self.__thread.start()
		self._logger.debug("start_all_tasks_successively: tasks run started")
		pass
	
	
	def add_directory(self, path_to_dir, is_etalon = False):
		if not os.path.isdir(path_to_dir):
			self._logger.info(f"add_directory: will not add dir {path_to_dir} as it is not a dir")
			return None
		if self._dir_manager.directory_exist(path_to_dir):
			self._logger.info(f"add_directory: directory {path_to_dir} already exist, not adding it")
			return None
			
		# adding dir
		self._logger.info(f"add_directory: adding directory {path_to_dir}")
		new_task = AddDirTask(path_to_dir, logger = self._logger.getChild("AddDirTask_" + str(path_to_dir.split(os.sep)[-1])), file_manager = self._file_manager, dir_manager = self._dir_manager, is_etalon = is_etalon)
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
		new_task = CheckDirTask(target_dir, logger = self._logger.getChild(f"CheckDirTask_{target_dir.id}"), file_manager = self._file_manager, dir_manager = self._dir_manager)
		self.add_task(new_task)
		return new_task
	
	
	def split_dir(self, target_dir):
		new_task = SplitDirTask(target_dir, logger = self._logger.getChild(f"CheckDirTask_{target_dir.id}"), file_manager = self._file_manager, dir_manager = self._dir_manager)
		self.add_task(new_task)
		return new_task
	
	
	def task_is_running(self):
		"""return True if any of tasks is running"""
		for t in self.tasks:
			if t.running:
				return True
		return False
	
	