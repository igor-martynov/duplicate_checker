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

from sqlalchemy_declarative import DeclarativeBase, File, Directory
from sqlalchemy import create_engine, select, Index, inspect
from sqlalchemy.orm import joinedload

sys.path.append("./")
from base import *
from tasks import *
		

"""

    

"""



class BaseManager(object, metaclass = MetaSingleton):
	"""BaseManager - base class for all managers. """
	# TODO: all class methods to abstract
	
	def __init__(self, logger = None):
		super(BaseManager, self).__init__()
		self._logger = logger
	
	
	def set_DB_manager(self, db_manager = None):
		self._db_manager = db_manager
		self.get_session = db_manager.get_session
		self.close_session = db_manager.close_session
		self._logger.debug(f"set_DB_manager: db_manager set to {db_manager}")
	
	
	def get_by_id(self, _id, session = None):
		raise NotImplemented
	
	
	def get_by_path(self, _path):
		raise NotImplemented
		
	
	def get_pre_list(self):
		"""get a pre-list, list of summaries, i.e. names only"""
		raise NotImplemented
	
	
	def get_full_list(self):
		"""fully load all objects"""
		raise NotImplemented
	
	
	def update(self, obj, session = None):
		try:
			if session is None:
				_session = self.get_session()
			else:
				_session = session
			_session.merge(obj)
			if session is None:
				self.close_session(_session, commit = True)
			self._logger.info(f"update: object updated: {obj}")
			return True
		except Exception as e:
			self._logger.error(f"update: got error while updating {obj}: {e}, traceback: {traceback.format_exc()}")
			_session.rollback()
			if session is None:
				self.close_session(_session, commit = False)
			return False
	
	
	def delete(self, obj, session = None):
		"""fully delete object, including DB commit"""
		try:
			if session is None:
				_session = self.get_session()
			else:
				_session = session
			_session.delete(obj)
			if session is None:
				self.close_session(_session)
			self._logger.info(f"delete: object deleted: {obj}")
			return True
		except Exception as e:
			self._logger.error(f"delete: got error while deleting {obj}: {e}, traceback: {traceback.format_exc()}")
			_session.rollback()
			if session is None:
				self.close_session(_session, commit = False)
			return False
	
	
	def create(self, full_path = ""):
		raise NotImplemented



class FileManager(BaseManager):
	"""FileManager
	
	responsible for all file operations
	"""
	
	def __init__(self, logger = None):
		super(FileManager, self).__init__(logger = logger)
		pass
	
	
	def get_by_id(self, _id, session = None):
		if session is None:
			_session = self.get_session()
		else:
			_session = session
		res = _session.query(File).options(joinedload(File.dir)).get(_id)
		if session is None:
			self.close_session(_session, commit = False)
		return res
	
	
	def get_by_checksum(self, checksum, idir = None, session = None):
		if session is None:
			_session = self.get_session()
		else:
			_session = session
		if idir is None:
			res = _session.query(File).options(joinedload(File.dir)).filter(File.checksum == checksum).all()
		else:
			res = _session.query(File).options(joinedload(File.dir)).filter(File.checksum == checksum, File.dir_id == idir.id).all()
		if session is None:
			self.close_session(_session, commit = False)
		return res
	
	
	def get_by_path(self, _path, session = None):
		if session is None:
			_session = self.get_session()
		else:
			_session = session
		res = _session.query(File).options(joinedload(File.dir)).filter(File.full_path == _path).all()
		if session is None:
			self.close_session(_session, commit = False)
		return res
	
	
	def create(self,
		path_to_file,
		checksum = "",
		date_added = None,
		date_checked = None,
		is_etalon = False,
		comment = "",
		save = True,
		session = None):
		new_file = File(full_path = path_to_file,
			checksum = checksum,
			date_added = date_added,
			date_checked = date_checked,
			is_etalon = is_etalon,
			comment = comment)
		if not save:
			return new_file
		if session is None:
			_session = self.get_session()
		else:
			_session = session
		_session.add(new_file)
		if session is None:
			self.close_session(_session, commit = True)
		return new_file
	
	
	def find_copies(self, _file, session = None, ignore_same_fullpath = True):
		if session is None:
			_session = self.get_session()
		else:
			_session = session
		if ignore_same_fullpath:
			res = _session.query(File).filter(File.checksum == _file.checksum, File.full_path != _file.full_path).all()
		else:
			res = _session.query(File).filter(File.checksum == _file.checksum).all()
		if session is None:
			self.close_session(_session, commit = False)
		self._logger.debug(f"find_copies: searched for copies of file {_file.full_path}, found: {len(res)}")
		return res
	
	

class DirManager(BaseManager):
	"""DirManager
	responsible for all directory operations"""
	
	def __init__(self, logger = None):
		super(DirManager, self).__init__(logger = logger)
		pass
	
	
	def get_full_list(self, session = None):
		if session is None:
			_session = self.get_session()
		else:
			_session = session
		res = _session.query(Directory).all()
		if session is None:
			self.close_session(_session, commit = False)
		return res
	
	
	def get_by_id(self, _id, session = None):
		if session is None:
			_session = self.get_session()
		else:
			_session = session
		res = _session.query(Directory).options(joinedload(Directory.files)).get(_id)
		if session is None:
			self.close_session(_session, commit = False)
		return res
	
	
	def get_by_path(self, _path, session = None):
		if session is None:
			_session = self.get_session()
		else:
			_session = session
		res = _session.query(Directory).filter(Directory.full_path == _path).all()
		if session is None:
			self.close_session(_session, commit = False)
		return res
	
	
	def create(self, path_to_dir, is_etalon = False, date_added = None, date_checked = None, comment = "", save = True, name = "", files = [], session = None):
		new_dir = Directory(full_path = path_to_dir,
			date_added = date_added,
			date_checked = date_checked,
			is_etalon = is_etalon,
			comment = comment,
			name = name,
			files = files)
		if not save:
			return new_dir
		if session is None:
			_session = self.get_session(expire_on_commit = False)
		else:
			_session = session
		_session.add(new_dir)
		if session is None:
			self.close_session(_session, commit = True)
		return new_dir
	
	
	def directory_exist(self, path_to_dir):
		res = self.get_by_path(path_to_dir)
		if (type(res) == type(list()) and len(res) != 0):
			return True
		else:
			return False
		


class TaskManager(BaseManager):
	"""TaskManager - create and manage tasks"""
	
	def __init__(self,
		logger = None,
		file_manager = None,
		dir_manager = None,
		checksum_algorithm = "md5",
		ignore_duplicates = False,
		task_autostart = False):
		super(TaskManager, self).__init__(logger = logger)
		
		self._file_manager = file_manager
		self._dir_manager = dir_manager
		
		self.checksum_algorithm = checksum_algorithm
		self.ignore_duplicates = ignore_duplicates
		
		self.current_tasks = [] # only tasks from this session
		self.autostart_enabled = task_autostart
		
		self.__thread = None
		self.SLEEP_BETWEEN_TASKS = 3
		self.SLEEP_BETWEEN_CHECKS = 5
	
	
	def get_full_list(self, session = None):
		if session is None:
			_session = self.get_session()
		else:
			_session = session
		res = _session.query(TaskRecord).all()
		if session is None:
			self.close_session(_session, commit = False)
		self._logger.debug(f"get_full_list: got {len(res)} -  {res}.")
		return res
	
	
	def get_by_id(self, _id, session = None):
		if session is None:
			_session = self.get_session()
		else:
			_session = session
		res = _session.query(TaskRecord).get(_id)
		if session is None:
			self.close_session(_session, commit = False)
		return res
	
	
	@property
	def current_running_task(self):
		for task in self.current_tasks:
			if task.running:
				return task
		return None
	
	
	@property
	def running(self):
		return False if self.current_running_task is None else True
	
	
	def set_file_manager(self, file_manager):
		self._file_manager = file_manager
	
	
	def set_dir_manager(self, dir_manager):
		self._dir_manager = dir_manager
	
	
	def add_task(self, task = None, session = None):
		if task is None: return None
		if session is None:
			_session = self.get_session(expire_on_commit = False)
		else:
			_session = session
		_session.add(task)
		if session is None:
			self.close_session(_session, commit = True)
		self.current_tasks.append(task)
		self._logger.debug(f"create_task: task added: {task.descr}")
	
	
	def start_task(self, task):
		if task in self.current_tasks:
			if task.running is None:
				self._logger.info(f"start_task: starting task {task} on request")
				task.start()
				task.save_task()
			else:
				self._logger.info(f"start_task: should start task {task} but it is already running, so ignoring")
		else:
			# re-run task here
			self._logger.info(f"start_task: re-starting task {task} on request")
			self.re_run_task(task)
			self._logger.error(f"start_task: could not find task {task} in current task list, ignoring")
	
	
	def re_run_task(self, task):
		# detect task type
		if task._type == "AddDirTask":
			new_task = self.add_directory(task.target_dir_full_path, is_etalon = False)
		elif task._type == "CompareDirsTask":
			pass
		elif task._type == "FindCopiesTask":
			pass
		elif task._type == "CheckDirTask":
				pass
		# create new
		
		# start
		
		pass
	
	
	
	def start_autostart_thread(self):
		def wait_till_task_completes(task):
			while task.running:
				time.sleep(self.SLEEP_BETWEEN_CHECKS)
				# task.save_task()
			
		def autostart_thread():
			time.sleep(self.SLEEP_BETWEEN_CHECKS)
			self._logger.debug(f"autostart_thread: will start with current_tasks: {self.current_tasks}")
			while self.autostart_enabled is True:
				for task in self.current_tasks:
					if self.autostart_enabled is False:
						break
					if task.running or task.pending is False:
						# ignore task
						pass
					else:
						task.start()
						time.sleep(self.SLEEP_BETWEEN_CHECKS)
						wait_till_task_completes(task)
				time.sleep(self.SLEEP_BETWEEN_TASKS)
			self._logger.info(f"start_autostart_thread: complete on user request")
		
		if self.autostart_enabled:
			self._logger.info(f"start_autostart_thread: autostart already enabled, ignoring")
			return
		self.autostart_enabled = True
		self.__thread = threading.Thread(target = autostart_thread)
		self.__thread.start()
		self._logger.info(f"start_autostart_thread: thread started")
		
	
	def add_directory(self, path_to_dir, is_etalon = False):
		if not os.path.isdir(path_to_dir):
			self._logger.info(f"add_directory: will not add dir {path_to_dir} - it is not a dir or does not exist")
			return None
		if self.ignore_duplicates and self._dir_manager.directory_exist(path_to_dir):
			self._logger.info(f"add_directory: directory {path_to_dir} already exist, not adding it")
			return None
		# adding dir
		self._logger.info(f"add_directory: adding directory {path_to_dir}")
		new_task = AddDirTask(path_to_dir,
			logger = self._logger.getChild("AddDirTask_" + str(path_to_dir.split(os.sep)[-1])),
			db_manager = self._db_manager,
			file_manager = self._file_manager,
			dir_manager = self._dir_manager,
			task_manager = self,
			is_etalon = is_etalon,
			checksum_algorithm = self.checksum_algorithm)
		self.add_task(new_task)
		self._logger.debug(f"add_directory: complete for {path_to_dir}")
		return new_task
	
	
	def delete_directory(self, target_dir):
		new_task = DeleteDirTask(target_dir,
			logger = self._logger.getChild("DeleteDirTask_" + str(target_dir.full_path.split(os.sep)[-1])),
			db_manager = self._db_manager,
			file_manager = self._file_manager,
			dir_manager = self._dir_manager,
			task_manager = self)
		self.add_task(new_task)
		return new_task
	
	
	def compare_directories(self, dir_a, dir_b):
		new_task = CompareDirsTask(dir_a, dir_b,
			logger = self._logger.getChild(f"CompareDirsTask_{dir_a.id}_{dir_b.id}"),
			db_manager = self._db_manager,
			file_manager = self._file_manager,
			dir_manager = self._dir_manager,
			task_manager = self)
		self.add_task(new_task)
		return new_task
	
	
	def find_copies(self, target_dir):
		new_task = FindCopiesTask(target_dir,
			logger = self._logger.getChild(f"FindCopiesTask_{target_dir.id}"),
			db_manager = self._db_manager,
			file_manager = self._file_manager,
			dir_manager = self._dir_manager,
			task_manager = self)
		self.add_task(new_task)
		return new_task
		
	
	def check_dir(self, target_dir):
		new_task = CheckDirTask(target_dir,
			logger = self._logger.getChild(f"CheckDirTask_{target_dir.id}"),
			db_manager = self._db_manager,
			file_manager = self._file_manager,
			dir_manager = self._dir_manager,
			task_manager = self,
			checksum_algorithm = self.checksum_algorithm)
		self.add_task(new_task)
		return new_task
	
	
	def split_dir(self, target_dir):
		new_task = SplitDirTask(target_dir,
			logger = self._logger.getChild(f"SplitDirTask_{target_dir.id}"),
			db_manager = self._db_manager,
			file_manager = self._file_manager,
			dir_manager = self._dir_manager,
			task_manager = self)
		self.add_task(new_task)
		return new_task
	
	
	def compile_dir(self, path_to_new_dir, input_dir_list):
		new_task = CompileDirTask(path_to_new_dir,
			logger = self._logger.getChild(f"CompileDirTask_{os.path.basename(path_to_new_dir)}"),
			db_manager = self._db_manager,
			file_manager = self._file_manager,
			dir_manager = self._dir_manager,
			task_manager = self,
			input_dir_list = input_dir_list)
		self.add_task(new_task)
		return new_task
	
	
	def delete_files(self, files_to_delete):
		new_task = DeleteFilesTask(files_to_delete,
			logger = self._logger.getChild(f"DeleteFilesTask_{len(self.current_tasks)}"),
			db_manager = self._db_manager,
			file_manager = self._file_manager,
			dir_manager = self._dir_manager,
			task_manager = self)
		self.add_task(new_task)
		return new_task
	


class DBManager(object, metaclass = MetaSingleton):
	"""docstring for DBManager"""
	def __init__(self,
		db_file = None,
		logger = None):
		super(DBManager, self).__init__()
		self._logger = logger
		self.DB_FILE = db_file
		self._engine = None
		self.session_in_use = False
		self.WAIT_LOCK_DELAY = 0.3
		# sub-init
		self.init_DB_ORM()
		self.create_DB_schema()
		self.get_current_schema()
	
	
	
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
	
	
	def init_DB_ORM(self):
		self._logger.debug(f"init_DB_ORM: starting, will use db file {self.DB_FILE}")
		self._engine = create_engine(f"sqlite:///{self.DB_FILE}", connect_args = {"check_same_thread": False})
		DeclarativeBase.metadata.bind = self._engine
		self._logger.debug("init_DB_ORM: init complete")
	
	
	def get_session(self, expire_on_commit = True):
		from sqlalchemy.orm import sessionmaker
		while self.session_in_use:
			self._logger.debug(f"get_session: waiting for lock on DB session...")
			time.sleep(self.WAIT_LOCK_DELAY)
		self.session_in_use = True
		DBSession = sessionmaker(autocommit = False, autoflush = False)
		DBSession.bind = self._engine
		_session = DBSession()
		if expire_on_commit is False:
			_session.expire_on_commit = False
		_session.begin()
		return _session
	
	
	def close_session(self, _session, commit = True):
		if commit is False:
			_session.close()
			self.session_in_use = False
			return
		_session.commit()
		_session.flush()
		_session.close()
		self.session_in_use = False
	
	
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
			_session = self.get_session()
			result = _session.execute(query_text)
			self.close_session(_session, commit = True)
			return result
		except Exception as e:
			self._logger.error(f"execute_sql_query: got error {e}, traceback: {traceback.format_exc()}")
			return None

	
	def run_vacuum(self):
		try:
			_session = self.get_session()
			cursor = _session.connection()
			cursor.execute("VACUUM")
			self.close_session(_session)
			self._logger.info(f"run_vacuum: vacuum complete")
		except Exception as e:
			self._logger.error(f"run_vacuum: got error {e}, traceback: {traceback.format_exc()}")
	

