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

import cProfile
import pstats
from pstats import SortKey


	

def get_file_checksum(target_dict, checksum_method = "md5"):
	"""calculate checksum of file
	
	arguments: path_to_file - string with path to file
		checksum_method - string with checksum algorhytm, currently supperted: "md5" or "sha512"
	returns: tuple of path and checksum, both as strings
	"""
	
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
	return target_dict


def get_file_checksum_sha512(target_dict):
	return get_file_checksum(target_dict, checksum_method = "sha512")


def normalize_path_to_dir(path_to_dir):
	if path_to_dir.startswith(" "):
		path_to_dir = path_to_dir[1:]
	if path_to_dir.endswith("/"):
		return path_to_dir[:-1]
	else:
		return path_to_dir


def empty_on_None(ivar):
	"""Jinja2 filter, converts None to empty string"""
	if ivar is None:
		return ""
	else:
		return ivar


def newline_to_br(istr):
	"""Jinja2 filter, converts newline to <br>"""
	if istr is None:
		return ""
	else:
		return istr.replace("\n", "<br>\n")

	
def secs_to_hrf(secs):
	"""convert seconds to human-readable time form"""
	S = "s"
	M = "m"
	H = "h"
	D = "d"
	if secs < 1:
		return f"{round(secs, 3)}{S}"
	elif secs < 60:
		return f"{int(secs)}{S}"
	elif secs < 3600:
		minutes = int(secs / 60)
		seconds = int(secs - minutes * 60)
		return f"{minutes}{M} {seconds}{S}"
	elif secs < 3600 * 24:
		hours = int(secs / 3600)
		minutes = int((secs - hours * 3600) / 60)
		seconds = int((secs - 3600 * hours - 60 * minutes))
		return f"{hours}{H} {minutes}{M} {seconds}{S}"
	else:
		days = int(secs / (3600 * 24))
		remains = secs - days * (3600 * 24)
		hours = int((secs - days * 3600 * 24) / 3600)
		minutes = int((secs - days * 3600 * 24 - hours * 3600) / 60)
		seconds = int(secs - days * 3600 * 24 - 3600 * hours - 60 * minutes)
		return f"{days}{D} {hours}{H} {minutes}{M} {seconds}{S}"
	

def datetime_to_str(dt):
	"""dumb fixed conversion"""
	if type(dt) != type(datetime.datetime.now()):
		return ""
	return dt.strftime("%Y-%m-%d %H:%M:%S")

	
def run_command(cmdstring):
	"""run command using subprocess"""
	import subprocess
	import shlex
	
	if len(cmdstring) == 0:
		return -1
	args = shlex.split(cmdstring)
	run_proc = subprocess.Popen(args, stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
	result = subprocess.Popen.communicate(run_proc)[0].decode("utf-8")
	return result


def cProfile_wrapper(func):
	def wrapper(*args, **kwargs):
		FILENAME = f"./profile/{func.__name__}.profile"
		profiler = cProfile.Profile()
		result = profiler.runcall(func, *args, **kwargs)
		profiler.dump_stats(FILENAME)
		p = pstats.Stats(FILENAME)
		p.strip_dirs().sort_stats(SortKey.TIME).print_stats()
		return result
	return wrapper



class MetaSingleton(type):
	"""metaclass that creates singletone object"""
	
	_instances = {}
	def __call__(cls, *args, **kwargs):
		if cls not in cls._instances or kwargs["db_file"] not in cls._dbfs:
			cls._instances[cls] = super(MetaSingleton, cls).__call__(*args, **kwargs)
		return cls._instances[cls]



class MetaSingletonByDBFile(type):
	"""metaclass that creates singletone object, one singletone for each db file. This is usefull due to SQLite multiprocessing and multithreading limitation"""
	
	_dbfiles = {}
	
	def __call__(cls, *args, **kwargs):
		print("D will search class for db_file " + kwargs["db_file"])
		if kwargs["db_file"] not in cls._dbfiles:
			cls._dbfiles[kwargs["db_file"]] = super(MetaSingletonByDBFile, cls).__call__(*args, **kwargs)
		return cls._dbfiles[kwargs["db_file"]]	

