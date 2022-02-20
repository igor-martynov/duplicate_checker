import hashlib
import sys
import os.path
import os
import datetime
import time
import math
import glob


import multiprocessing
import threading
import sqlite3

# logging
import logging
import logging.handlers

import traceback
	
	

def get_file_checksum(target_dict, checksum_method = "md5"):
	"""calculate checksum of file
	
	arguments: path_to_file - string with path to file
		checksum_method - string with checksum algorhytm, currently supperted: "md5" or "sha512"
	returns: tuple of path and checksum, both as strings
	"""
	# TODO: add security checks
	
	path_to_file = target_dict["full_path"]
	blocksize = 65536
	target_dict["checksum"] = None
	target_dict["date_start"] = datetime.datetime.now()
	
	if not os.path.isfile(path_to_file):
		target_dict["date_end"] = datetime.datetime.now()
		return target_dict
	
	f = open(path_to_file, "rb")
	buf = f.read(blocksize)
	if checksum_method == "sha512":
		h = hashlib.sha512()
	else:
		h = hashlib.md5()
		
	while len(buf) > 0:
		h.update(buf)
		buf = f.read(blocksize)
	result = h.hexdigest()
	f.close()
	target_dict["checksum"] = result
	target_dict["date_end"] = datetime.datetime.now()
	print(f"D checksum: {result}")
	return target_dict



def normalize_path_to_dir(path_to_dir):
	if path_to_dir.startswith(" "):
		path_to_dir = path_to_dir[1:]
	if path_to_dir.endswith("/"):
		return path_to_dir[:-1]
	else:
		return path_to_dir


def empty_on_None(ivar):
	"""Jinja2 filter for handling empty str"""
	if ivar is None:
		return ""
	else:
		return ivar


def newline_to_br(istr):
	"""Jinja2 filter, converts None to empty string"""
	if istr is None:
		return ""
	else:
		return istr.replace("\n", "<br>\n")

	
def run_command(cmdstring):
	import subprocess
	import shlex
	
	if len(cmdstring) == 0:
		return -1
	args = shlex.split(cmdstring)
	run_proc = subprocess.Popen(args, stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
	result = subprocess.Popen.communicate(run_proc)[0].decode("utf-8")
	return result



class MetaSingleton(type):
	"""metaclass that creates singletone object"""
	
	_instances = {}
	# _dbfs = {}
	
	def __call__(cls, *args, **kwargs):
		# print("D will search class for db_file " + kwargs["db_file"])
		if cls not in cls._instances or kwargs["db_file"] not in cls._dbfs:
			cls._instances[cls] = super(MetaSingleton, cls).__call__(*args, **kwargs)
			# cls._dbfs.append(kwargs["db_file"])
			# print("D new instance of class created - " + str(cls._instances[cls]))
		# print("D total instances - " + str(cls._instances))
		return cls._instances[cls]



class MetaSingletonByDBFile(type):
	"""metaclass that creates singletone object. Singletone for each db file. This is usefull due to SQLite multiprocessing and multithreading limitation"""
	
	
	_dbfiles = {}
	
	def __call__(cls, *args, **kwargs):
		print("D will search class for db_file " + kwargs["db_file"])
		if kwargs["db_file"] not in cls._dbfiles:
			cls._dbfiles[kwargs["db_file"]] = super(MetaSingletonByDBFile, cls).__call__(*args, **kwargs)
			# print("D new instance of class created - " + str(cls._dbfiles[kwargs["db_file"]]))
		# print("D total instances - " + str(cls._dbfiles))
		return cls._dbfiles[kwargs["db_file"]]




# TODO: remove this, unused
class db_handler_singleton(object, metaclass = MetaSingletonByDBFile):
	"""DB access class that is singletone"""
	
	def __init__(self, db_file = None, log_file = "./duplicate_checker.log", logger = None):
		# super(db_handler, self).__init__()
		if hasattr(self, "DB_FILE"):
			# self._logger.debug("__init__: not initing, using existing object with DB_FILE " + str(self.DB_FILE))
			return
		# else:
		# 	self._logger.debug("__init__: initing new object")
		
		if db_file == None :
			self.DB_FILE = "./duplicate_checker.db"
		else:
			self.DB_FILE = db_file
		print("using DB " + self.DB_FILE)
		
		
		self._db_conn = None
		self._cursor = None
		
		self.lastrowid = None
		
		self.LOG_QUERIES = False
		self.LOG_FILE = log_file
		self._logger = None
		if self._logger == None:
			if logger != None:
				self._logger = logger
			else:
				self._logger = logging.getLogger("db_handler")
				self._logger.setLevel(logging.DEBUG)
				fh = logging.FileHandler(self.LOG_FILE)
				fh.setLevel(logging.DEBUG)
				formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
				fh.setFormatter(formatter)
				self._logger.addHandler(fh)
				self._logger.debug("logger inited directly")
		
		self._logger.debug("__init__: inited with db file " + str(self.DB_FILE) + ", self " + str(self))
		
		self.init_db()
		self.create_new_db()
	
	
	def init_db(self):
		self._db_conn = sqlite3.connect(self.DB_FILE, detect_types = sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
		# self._logger.debug("init_db: DB inited")
	
	
	def execute_db_query(self, query, *argv):
		"""thread-safe version, will open db first, and close it afterwards
		arguments:
		returns: list"""
		
		start_time = datetime.datetime.now()
		# if self.LOG_QUERIES:
		# 	self._logger.debug("execute_db_query: got query " + str(query) + ", args: " + str(argv))
		db_conn = sqlite3.connect(self.DB_FILE, detect_types = sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
		with db_conn:
			if len(argv) > 0:
				cursor = db_conn.execute(query, argv[0])
			else:
				cursor = db_conn.execute(query)
			
			result = cursor.fetchall()
		self.lastrowid = cursor.lastrowid
		db_conn.commit()
		db_conn.close()
		end_time = datetime.datetime.now()
		if self.LOG_QUERIES:
			self._logger.debug("execute_db_query: query " + str(query) + ", args: " + str(argv) + " - complete in " + str((end_time - start_time).total_seconds()))
		return result
	
	
	def deinit_db(self):
		self._db_conn.commit()
		self._db_conn.close()
		self._logger.debug("deinit_db: DB committed and closed")
	
	
	def execute_db_query_unsafe(self, query, *argv):
		"""execute db query, should be runned after self.init_db and before self.deinit_db"""
		# if self.LOG_QUERIES:
		# 	self._logger.debug("execute_db_query: got query " + str(query) + ", args: " + str(argv))
		# start_time = datetime.datetime.now()
		result = None
		try:
			if len(argv) > 0:
				self._cursor = self._db_conn.execute(query, argv[0])
			else:
				self._cursor = self._db_conn.execute(query)
			
			result = self._cursor.fetchall()
			self.lastrowid = self._cursor.lastrowid
			# self._db_conn.commit()
			# self._logger.debug("execute_db_query: query complete successfully")
		
		except Exception as e:
			self._logger.error("execute_db_query_unsafe: error occured while executing query: " + str(query) + " with args: " + str(argv) + ", error: " + str(e) + ", traceback: " + traceback.format_exc())
			pass
			
		# db_conn.close()
		# end_time = datetime.datetime.now()
		# if self.LOG_QUERIES:
		# 	self._logger.debug("execute_db_query: query " + str(query) + ", args: " + str(argv) + " - complete in " + str((end_time - start_time).total_seconds()))
		
		return result
	
	
	def commit(self):
		self._db_conn.commit()
	
	
	def create_new_db(self):
		self._logger.debug("create_new_db: creating new db")
		
		self.execute_db_query("""CREATE TABLE IF NOT EXISTS files(
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			full_path TEXT,
			checksum TEXT,
			is_etalon INTEGER,
			date_added timestamp,
			date_checked timestamp,
			comment TEXT,
			deleted INTEGER DEFAULT 0,
			dir_id INTEGER)""")
		
		self.execute_db_query("""CREATE TABLE IF NOT EXISTS dirs(
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			full_path TEXT,
			date_added timestamp,
			date_checked timestamp,
			is_etalon INTEGER,
			comment TEXT,
			deleted INTEGER DEFAULT 0)""")
		
		# self.execute_db_query("""CREATE TABLE IF NOT EXISTS dir_file(
		# 	id INTEGER PRIMARY KEY AUTOINCREMENT,
		# 	dir_id INTEGER,
		# 	file_id INTEGER,
		# 	deleted INTEGER DEFAULT 0)""")
		
		# self.execute_db_query("""CREATE TABLE IF NOT EXISTS file_to_file_link(
		# 	id INTEGER PRIMARY KEY AUTOINCREMENT,
		# 	file_id1 INTEGER,
		# 	file_id2 INTEGER,
		# 	deleted INTEGER DEFAULT 0)""")
		
		# self.execute_db_query("""CREATE TABLE IF NOT EXISTS dir_to_dir_link(
		# 	id INTEGER PRIMARY KEY AUTOINCREMENT,
		# 	dir_id1 INTEGER,
		# 	dir_id2 INTEGER,
		# 	deleted INTEGER DEFAULT 0)""")
		
		# self.execute_db_query("""""")



class BaseReport(object):
	"""docstring for BaseReport
	
	report will consist of 2 parts:
	
	1st part - summary report
	2nd part - extended report
	"""
	
	def __init__(self, name = ""):
		super(BaseReport, self).__init__()
		
		self.list = []
		self.name = name
		self.DO_PRINT = False
		self.DELIMETER_LINE = "======================================================================"
		
		self.summory = []
		
		self.extended = []
		pass
	
	
	def __str__(self):
		result = ""
		for s in self.list:
			result += s + "\n"
		return result
		
	
	def add(self, _str, part = "regular"):
		"""add line to report
		
		arguments: _str - 
		summory - str, "summory"|"extended"|"regular"  """
		# if part == "regular":
		self.list.append(_str)
		if part == "summory":
			self.summory.append(_str)
		elif part == "extended":
			self.extended.append(_str)
		if self.DO_PRINT:
			print(_str)
	
	
	def save_to_file(self, filename = None):
		if filename is None:
			filename = os.path.join(os.path.abspath(os.path.dirname(__file__)), "reports","report_" + self.name + "_" + datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S") + ".txt")
		with open(filename, "w") as f:
			f.write("report:\n\n" + str("\n".join(self.list)) + "\n" )
			# print("D report saved to " + str(filename))
	
	
	def save(self):
		self.save_to_file()
		
	
	@property
	def result_html(self):
		return "<br>\n".join(self.list)
	

