import hashlib
import sys
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



class BaseTask(object):
	"""BaseTask"""
	
	def __init__(self, logger = None, file_manager = None, dir_manager = None):
		super(BaseTask, self).__init__()
		
		self._file_manager = file_manager
		self._dir_manager = dir_manager
		self._logger = logger
		
		self.date_start = None
		self.date_end = None
		self.running = None
		self.complete = None
		self.OK = None
		self.error_message = ""
		self._progress = 0.0
		self.__report = ""
		
		self.save_results = True
		
		
	@property		
	def state(self):
		if self.date_start is None and not self.running:
			return "PENDING"
		if self.complete and self.OK and self.date_end is not None:
			return "COMPLETE OK"
		if not self.complete and self.OK:
			return f"IN PROGRESS ({(self.progress * 100):.1f}%)"
		if not self.OK and self.running:
			return f"IN PROGRESS, FAIL ({(self.progress * 100):.1f}%)"
		if not self.OK and not self.running:
			return "COMPLETE FAILED"
	
	
	@property
	def progress(self):
		return self._progress
	
	
	@property
	def descr(self):
		return ""
	
	
	def run(self):
		raise NotImplemented
	
	
	def start(self):
		# raise NotImplemented
		# self.mark_start()
		self._logger.debug("start: starting task")
		self.__thread = threading.Thread(target = self.run)
		self.__thread.start()
		# self.run()
		self._logger.debug("start: task started in thread")
	
	
	def abort(self):
		raise NotImplemented
	
	
	def end(self):
		raise NotImplemented
	
	
	def mark_start(self):
		self.date_start = datetime.datetime.now()
		self.running = True
		self.complete = False
		self.OK = True
		self._progress = 0.0
	
	
	def mark_end(self):
		self.date_end = datetime.datetime.now()
		self.running = False
		self.complete = True
		self._progress = 1.0
	
	
	def save(self):
		raise NotImplemented
	
	
	@property
	def preview_html(self):
		return f"Preview of {self.__name__}<br>"
	
	
	@property
	def result_html(self):
		return f"status: {self.state}"
	
	
	@property
	def duration(self):
		return (self.date_end - self.date_start).total_seconds() if self.date_start is not None and self.date_end is not None else 0.0
	


class AddDirTask(BaseTask):
	"""Task to add new dir.
	
	"""
	
	def __init__(self, target_dir, logger = None, file_manager = None, dir_manager = None, is_etalon = False):
		super(AddDirTask, self).__init__(logger = logger, file_manager = file_manager, dir_manager = dir_manager)
		self.target_dir = target_dir
		self.file_list = []
		self.is_etalon = is_etalon
		self._sleep_delay = 1
		self.new_dir = None
		
		self.__thread = None
		self.__pool = None
		
		if self._logger is not None:
			self._logger.debug(f"__init__: init complete with target_dir {self.target_dir}")
		pass
	
	
	@property
	def descr(self):
		return f"AddDirTask for {self.target_dir}"
	
	
	def get_dir_listing(self, path_to_dir):
		glob_str = os.path.join(path_to_dir, "**")
		file_list = glob.glob(glob_str, recursive = True)
		self._logger.debug(f"get_dir_listing: got list {file_list} for glob pattern {glob_str}")
		return file_list
	
	
	def _create_input_list(self):
		# compile list of dicts
		dict_list = []
		dict_length = 0
		for f in self.file_list:
			if os.path.isdir(f):
				continue
			dict_list.append({"full_path": f})
		dict_length = len(dict_list)
		self._logger.debug(f"_create_input_list: created dict_list: {dict_list}, total {dict_length} items")
		return dict_list
	
	
	def _create_multiprocessing_pool(self, dict_list):
		# create and start Pool
		self.__pool = multiprocessing.Pool(processes = 2)
		result = self.__pool.imap_unordered(get_file_checksum, dict_list)
		self.__pool.close()
		self._logger.debug("create_multiprocessing_pool: pool created and closed")
		return result
	
	
	def wait_till_complete(self, result, dict_list):
		dict_length = len(dict_list)
		complete = result._index
		while complete != dict_length:
			# print(f"D waiting for pool, complete: {complete} of {dict_length}...")
			self._logger.debug(f"wait_till_complete: waiting for pool, complete: {complete} of {dict_length}...")
			time.sleep(self._sleep_delay)
			complete = result._index
			self._progress = complete / dict_length
		# print(f"D complete, result: {result}")
		self._logger.debug(f"wait_till_complete: pool results ready: {result}")
		return
	
	
	def create_directory_and_files(self, result, save = True):
		now = datetime.datetime.now()
		new_dir = self._dir_manager.create(self.target_dir, is_etalon = self.is_etalon, date_added = now, date_checked = now, save = save)
		files = []
		for r in result:
			# print(f"R: {r['full_path']}: {r['checksum']}")
			files.append(self._file_manager.create(r['full_path'], checksum = r['checksum'], date_added = r["date_end"], date_checked = r["date_end"], is_etalon = self.is_etalon), save = save)
		new_dir.files = files
		self._logger.info(f"create_directory_and_files: created dir {new_dir.full_path} with {len(files)} files: {[f.full_path for f in files]}")
		self.new_dir = new_dir
		return new_dir
	
	
	def save(self):
		# save to DB
		self._logger.debug(f"save: currently dirty records are: {self._dir_manager.db_stats()['dirty']}, new: {self._dir_manager.db_stats()['new']}")
		self._dir_manager.db_commit()
		self._logger.debug(f"save: commited, after commit dirty records are: {self._dir_manager.db_stats()['dirty']}, new: {self._dir_manager.db_stats()['new']}")
		
	
	def run(self):
		self._logger.info(f"run: starting, target_dir: {self.target_dir}")
		self.mark_start()
		self.file_list = self.get_dir_listing(self.target_dir)
		self._logger.debug(f"run: got file list: {self.file_list}")
		
		dict_list = self._create_input_list()
		dict_length = len(dict_list)
		result = self._create_multiprocessing_pool(dict_list)
		self.wait_till_complete(result, dict_list)
		self.create_directory_and_files(result)
		if self.save_results:
			self.save()	
		else:
			self._logger.info("run: not saving results because save == False")	
		self.OK = True
		self._logger.debug("run: complete")
		self.mark_end()
	
	
	@property
	def result_html(self):
		if self.new_dir is None:
			return f"full_path: {self.target_dir}<br>status: {self.state}, result is not ready yet."
		else:
			result_str = f"Dir: {self.new_dir.full_path}, total files: {len(self.new_dir.files)}" + "<br>\n<br>\n"
			for f in self.new_dir.files:
				result_str += f"f: {f.full_path} - {f.checksum}" + "<br>\n"
			result_str += f"Task took: {self.duration}s"
			return result_str



class CompareDirsTask(BaseTask):
	"""Task to compare two dirs.
	
	"""
	
	def __init__(self, dir_a, dir_b, logger = None, file_manager = None, dir_manager = None):
		super(CompareDirsTask, self).__init__(logger = logger, file_manager = file_manager, dir_manager = dir_manager)
		
		self.dir_a = dir_a
		self.dir_b = dir_b
		
		self.files_on_both = []
		self.files_a_on_b = []
		self.files_b_on_a = []
		self.files_only_on_a = []
		self.files_only_on_b = []
		self.equal_names_diff_checsums = []
		
		self._dirs_equal = None
		# self._a_is_subset_of_b = None
		self._b_is_subset_of_a = None
		pass
	
	
	@property
	def descr(self):
		return f"CompareDirs task for {self.dir_a.full_path} and {self.dir_b.full_path}"
	
	
	@property
	def a_is_subset_of_b(self):
		# if self._a_is_subset_of_b is not None:
		# 	return self._a_is_subset_of_b
		
		return True if len(self.files_a_on_b) == len(self.dir_a.files) else False
	
	
	@property
	def b_is_subset_of_a(self):
		# if self._b_is_subset_of_a is not None:
		# 	return self._b_is_subset_of_a
		
		# self._b_is_subset_of_a
		return True if len(self.files_b_on_a) == len(self.dir_a.files) else False
		
	
	def run(self):
		self._logger.info(f"run: starting comparing dir_a {self.dir_a.full_path} and dir_b {self.dir_b.full_path}")
		self.mark_start()
		self._logger.debug("run: checking files on both A and B")
		
		for fa in self.dir_a.files:
			self._progress += 0.25 / (len(self.dir_a.files) + len(self.dir_b.files))
			self._logger.debug(f"run: checking for both A and B file {fa.full_path} - {fa.checksum}")
			candidates = self._file_manager.get_by_checksum(fa.checksum)
			# fa_has_copy = False
			tmp_c_str = "input_checksum is " + fa.checksum + "; "
			for c in candidates:
				tmp_c_str += c.full_path + " - " + c.checksum + ", "
			self._logger.debug(f"got candidates: {tmp_c_str}")
			for c in candidates:
				if c.dir == self.dir_b:
					# 
					if fa not in self.files_on_both:
						self._logger.debug(f"run: added to files_on_both fa: {fa.full_path} because {fa.checksum} == {c.checksum}, candidate: {c.full_path}")
						self.files_on_both.append(fa)
						self.files_a_on_b.append(fa)
					if c not in self.files_on_both:
						self._logger.debug(f"run: added to files_on_both c: {c.full_path} because {c.checksum} == {fa.checksum}, fa: {fa.full_path}")
						self.files_on_both.append(c)
						self.files_b_on_a.append(c)
		for fb in self.dir_b.files:
			self._progress += 0.25 / (len(self.dir_a.files) + len(self.dir_b.files))
			self._logger.debug(f"run: checking for both A and B file {fb.full_path} - {fb.checksum}")
			candidates = self._file_manager.get_by_checksum(fb.checksum)
			# fb_has_copy = False
			tmp_c_str = "input_checksum is " + fb.checksum + "; "
			for c in candidates:
				tmp_c_str += c.full_path + " - " + c.checksum + ", "
			self._logger.debug(f"got candidates: {tmp_c_str}")
			for c in candidates:
				if c.dir == self.dir_a:
					# 
					if fb not in self.files_on_both:
						self._logger.debug(f"run: added to files_on_both fb: {fb.full_path} because {fb.checksum} == {c.checksum}, candidate: {c.full_path}")
						self.files_on_both.append(fb)
						self.files_b_on_a.append(fb)
					if c not in self.files_on_both:
						self._logger.debug(f"run: added to files_on_both c: {c.full_path} because {c.checksum} == {fb.checksum}, fa: {fb.full_path}")
						self.files_on_both.append(c)
						self.files_a_on_b.append(c)
		
			
		self._logger.debug("run: checking files only on A and B")
		for fa in self.dir_a.files:
			self._progress += 0.25 / (len(self.dir_a.files) + len(self.dir_b.files))
			self._logger.debug(f"run: checking for only on A and B file {fa.full_path} - {fa.checksum}")
			if fa not in self.files_on_both:
				self._logger.debug(f"run: adding to files_only_on_a: {fa.full_path}")
				self.files_only_on_a.append(fa)
		for fb in self.dir_b.files:
			self._progress += 0.25 / (len(self.dir_a.files) + len(self.dir_b.files))
			self._logger.debug(f"run: checking for only on A and B file {fb.full_path} - {fb.checksum}")
			if fb not in self.files_on_both:
				self._logger.debug(f"run: adding to files_only_on_b: {fb.full_path}")
				self.files_only_on_b.append(fb)
		
		if len(self.files_on_both) == (len(self.dir_a.files) + len(self.dir_b.files)) and len(self.files_only_on_a) == 0 and len(self.files_only_on_b) == 0:
			self._logger.info("run: A equal B")
			self._dirs_equal = True
		else:
			self._logger.info("run: A NOT equal B")
		
		self._logger.info(f"run: Totals: files_on_both: {len(self.files_on_both)}, files_a_on_b: {len(self.files_a_on_b)}, files_b_on_b: {len(self.files_b_on_a)}, files_only_on_a: {len(self.files_only_on_a)}, files_only_on_b: {len(self.files_only_on_b)}")
		self._logger.debug("run: complete")
		self.mark_end()
	
	
	@property
	def result_html(self):
		if len(self.files_on_both) == 0 and len(self.files_a_on_b) == 0 and len(self.files_b_on_a) == 0:
			self._logger.debug("result_html: result requested but seems to be empty. returning status from parent class")
			# return f"Task result is not ready. Current task status: {self.state}"
			
		self.__report = ""
		
		self.__report += f"Directory comparation status: {self.state}" + ".\n"
		self.__report += f"Directory A: {self.dir_a.full_path}, {len(self.dir_a.files)} files." + "\n"
		self.__report += f"Directory B: {self.dir_b.full_path}, {len(self.dir_b.files)} files." + "\n"
		self.__report += "\n\n"
		if self._dirs_equal:
			self.__report += "DIRS ARE EQUAL.\n\n"
		else:
			self.__report += "Dirs are not equal.\n\n"
			if self.a_is_subset_of_b:
				self.__report += "A is subset of B.\n\n"
			if self.b_is_subset_of_a:
				self.__report += "B is subset of A.\n\n"
			
		self.__report += f"Files on both A and B: {len(self.files_on_both)}" + "\n"
		for f in self.files_on_both:
			self.__report += f"f: {f.full_path} - {f.checksum}" + "\n"
		self.__report += "\n\n"
		self.__report += f"Files of A that exist in B: {len(self.files_a_on_b)}" + "\n"
		for f in self.files_a_on_b:
			self.__report += f"f: {f.full_path} - {f.checksum}" + "\n"
		self.__report += "\n\n"
		self.__report += f"Files of B that exist in A: {len(self.files_b_on_a)}" + "\n"
		for f in self.files_b_on_a:
			self.__report += f"f: {f.full_path} - {f.checksum}" + "\n"
		self.__report += "\n\n"
		self.__report += f"Files that exist only in A: {len(self.files_only_on_a)}" + "\n"
		for f in self.files_only_on_a:
			self.__report += f"f: {f.full_path} - {f.checksum}" + "\n"
		self.__report += "\n\n"
		self.__report += f"Files that exist only in B: {len(self.files_only_on_b)}" + "\n"
		for f in self.files_only_on_b:
			self.__report += f"f: {f.full_path} - {f.checksum}" + "\n"
		self.__report += "\n\n"
		self.__report += f"Files with equal names but different checsums: {len(self.equal_names_diff_checsums)}" + "\n"
		for f in self.equal_names_diff_checsums:
			self.__report += f"f: {f.full_path} - {f.checksum}" + "\n"
		self.__report += "\n\n"
		self.__report += f"Task took: {self.duration}s"
		self.__report += "\n\n"
		return self.__report.replace("\n", "<br>\n")
	
	

class FindCopiesTask(BaseTask):
	"""Task to find copies of files of one dir"""
	
	def __init__(self, target_dir, logger = None, file_manager = None, dir_manager = None):
		super(FindCopiesTask, self).__init__(logger = logger, file_manager = file_manager, dir_manager = dir_manager)
		
		self.target_dir = target_dir
		self.file_dict = {} # key: original file object, value: list of copies (file objects)
		self.copies_dict = {} # key: dir that contains copy, value: 
		pass
	
	
	@property
	def descr(self):
		return f"FindCopiesTask for {self.target_dir.full_path}"
	
	
	def run(self):
		self._logger.info(f"run: starting with dir {self.target_dir.full_path}")
		self.mark_start()
		self.file_dict = {}
		for f in self.target_dir.files:
			self.file_dict[f] = []
		self._logger.debug("run: file_dict pre-created, checking files...")
		
		total_files = len(self.target_dir.files)
		for f in self.target_dir.files:
			self._logger.debug(f"run: checking file {f.full_path}...")
			# candidates = self._file_manager.get_by_checksum(f.checksum)
			candidates = self._file_manager.find_copies(f)
			self._progress = self.target_dir.files.index(f) / total_files
			for c in candidates:
				if c.dir == self.target_dir or c.dir.full_path == self.target_dir.full_path:
					self._logger.debug(f"run: ignoring candidate {c.id} - {c.full_path} because it has the same dir {c.dir.full_path}")
					continue
				if f.name == c.name:
					# self._logger.debug(f"run: adding copy {c.id} - {c.full_path} for target file {f.full_path}")
					self.file_dict[f].append(c)
				else:
					self._logger.info(f"run: should add file {c.full_path} as copy, but it as different name. original name is {f.name}. So did not add.")
		
		self._logger.debug("run: file checking complete, file_dict filled.")
		self._logger.debug(f"run: file_dict: {self.file_dict}")
		self._logger.debug("run: run complete.")
		self.mark_end()
	
	
	
	
	# def get_copies_stats(self):
	# 	self._logger.debug("get_copies_stats: starting")
	# 	self.copies_dict = {}
	# 	try:
	# 		for f in self.file_dict.keys():
	# 			_dir = os.path.dirname(f)
	# 			self._logger.debug(f"get_copies_stats: dir {_dir}")
	# 			if _dir not in self.copies_dict.keys():
	# 				self.copies_dict[_dir] = []
	# 				self._logger.debug(f"get_copies_stats: added empty list of files for dir {_dir}")
	# 			self.copies_dict[_dir].extend(f)
	# 			self._logger.debug(f"get_copies_stats: added file-copy {f} for dir {_dir}")
	# 		self._logger.debug(f"get_copies_stats: complete. ")
	# 		for d in self.copies_dict.keys():
	# 			self._logger.debug(f"get_copies_stats: dir: {d} - {len(self.copies_dict[d])} copies - full copy: {len(self.copies_dict[d]) == len(self.target_dir.files)}")
	# 	except Exception as e:
	# 		self._logger.error(f"get_copies_stats: got error {e}, traceback: {traceback.format_exc()}")
	# 	return self.copies_dict
	
	
	def get_copies_stats(self):
		"""just trasnpose file_dict into copies_dict"""
		self._logger.debug("get_copies_stats: starting")
		self.copies_dict = {}
		for k, v in self.file_dict.items():
			for _copy in v:
				_copy_dir = _copy.dir
				if _copy_dir not in self.copies_dict.keys():
					self.copies_dict[_copy_dir] = [k, ]
				else:
					self.copies_dict[_copy_dir].append(k)
		self._logger.debug("get_copies_stats: complete")
		pass
	
	
	@property
	def result_html(self):
		self._logger.debug("result_html: starting")
		self.__report = "\n\nStatus: " + str(self.state) + "\n"
		
		self.__report += "\nDir: " + self.target_dir.full_path + "\n"
		self.__report += f"({len(self.target_dir.files)} files.)" + "\n\n"
		
		self.get_copies_stats()
		
		no_copies_list = []
		for k, v in self.file_dict.items():
			if len(v) == 0:
				no_copies_list.append(k)
		self._logger.debug("result_html: stage 1 complete")
		self.__report += f"files without copies: {len(no_copies_list)}" + "\n"
		for f in no_copies_list:
			self.__report += f.full_path + "\n"
		self.__report += "\n\n"
		
		# self.__report += f"Copies dirs: {self.copies_dict.keys}" + "\n\n"
		self._logger.debug("result_html: stage 2 complete")
		self.__report += "Copies:\n"
		for d in self.copies_dict.keys():
			if len(self.copies_dict[d]) == len(self.target_dir.files):
				self.__report += f"Copy: {d.full_path} -- FULL COPY" + "\n"
			else:
				self.__report += f"Copy: {d.full_path} -- {len(self.copies_dict[d])} files of {len(self.target_dir.files)}" + "\n"
		self.__report += "\n\n"
		self._logger.debug("result_html: stage 3 complete")
		self.__report += "All files:\n"
		for k, v in self.file_dict.items():
			self.__report += f"f: {k.full_path}: copies {len(v)}: {[f.full_path for f in v]}" + "\n"
		self.__report += "\n\n" + f"Task took: {self.duration}s"
		self._logger.debug(f"result_html: report: {self.__report}")
		return self.__report.replace("\n", "<br>\n")
	


class CheckDirTask(AddDirTask):
	"""docstring for CheckDirTask"""
	
	def __init__(self, target_dir, logger = None, file_manager = None, dir_manager = None):
		super(CheckDirTask, self).__init__(target_dir.full_path, logger = logger, file_manager = file_manager, dir_manager = dir_manager)
		
		self.dir_obj = target_dir
		self.subtask = None
		pass
	
	
	def compare_dirs_old_and_new(self):
		self._logger.debug(f"compare_dirs_old_and_new: will create subtask CompareDirsTask for dir comparison: {self.dir_obj} and {self.new_dir}")
		self.subtask = CompareDirsTask(self.dir_obj, self.new_dir, logger = self._logger.getChild("CompareDirsTask"), file_manager = self._file_manager, dir_manager = self._dir_manager)
		self.subtask.run()
		self._logger.debug("compare_dirs_old_and_new: comparation complete")
	
	
	def run(self):
		self.mark_start()
		self._logger.info(f"run: starting, target_dir: {self.target_dir}")
		
		self.file_list = self.get_dir_listing(self.target_dir)
		self._logger.debug(f"run: got file list: {self.file_list}")
		
		dict_list = self._create_input_list()
		dict_length = len(dict_list)
		result = self._create_multiprocessing_pool(dict_list)
		self.wait_till_complete(result, dict_list)
		self.create_directory_and_files(result, save = False)
		# not saving temporal dir - to keep DB clean
		# self._progress = 0.5	
		self.compare_dirs_old_and_new()
		self.OK = True
		self._logger.debug("run: complete")
		self.mark_end()
	
	
	@property
	def descr(self):
		return f"CheckDirTask for {self.target_dir.full_path}"
	
	
	@property
	def result_html(self):
		result = f"Origin dir: {self.dir_obj.full_path}, {len(self.dir_obj.files)} files" + "\n"
		result += f"Actual dir: {self.new_dir.full_path}, {len(self.new_dir.files)} files" + "\n"
		result += "\n\n" + f"result of subtask: {self.subtask.result_html}" + "\n"
		result += f"Task took: {self.duration}s"
		return result.replace("\n", "<br>\n")

	
	@property
	def progress(self):
		if self.subtask is not None:
			return (self._progress + self.subtask._progress) / 2
		else:
			return (self._progress) / 2
	


# TODO: under development
class SplitDirTask(BaseTask):
	"""docstring for SplitDirTask"""
	
	def __init__(self, target_dir, logger = None, file_manager = None, dir_manager = None):
		super(SplitDirTask, self).__init__(logger = logger, file_manager = file_manager, dir_manager = dir_manager)
		
		self.dir_obj = target_dir
		
		self.subdirs = []
		self.subdir_path_dict = dict()
		
		pass
	
	
	@property
	def descr(self):
		return f"SplitDirTask for {self.dir_obj.full_path}"
	
	
	def get_dict_of_subdirs(self):
		self.subdir_path_dict = {}
		target_dir_path = self.dir_obj.full_path
		for f in self.dir_obj.files:
			basename = os.path.basename(f.full_path)
			if basename != target_dir_path:
				# self.subdir_path_list.add(basename)
				if basename not in self.subdir_path_dict.keys():
					self.subdir_path_dict[basename] = []
					self._logger.debug(f"get_dict_of_subdirs: created empty dict item for subdir {basename}")
				self.subdir_path_dict[basename].append(f)
				self._logger.debug(f"get_dict_of_subdirs: added file {f.full_path} to subdir {basename}")
		
		self._logger.info(f"get_dict_of_subdirs: got subdirs: {self.subdir_path_dict.keys()}, total: {len(self.subdir_path_dict.keys())}")	
		return self.subdir_path_dict
	
	
	def create_subdirs(self):
		self._logger.debug(f"create_subdirs: will create subdirs for dict keys: {self.subdir_path_dict.keys()}")
		for subdir_path, subdir_files in self.subdir_path_dict.items():
			self._logger.debug(f"create_subdirs: creating objects for subdir {subdir_path}")
			now = datetime.datetime.now()
			new_dir = self._dir_manager.create(subdir_path, is_etalon = self.dir_obj.is_etalon, date_added = now, date_checked = self.dir_obj.date_checked)
			new_dir_files = []
			for f in subdir_files:
				# copy file into new object
				new_file = self._file_manager.create(f.full_path, is_etalon = f.is_etalon, date_added = now, date_checked = f.date_checked)
				new_dir_files.append(new_file)
				pass
			new_dir.files = new_dir_files
			self.subdirs.append(new_dir)
			self.progress += 1 / len(self.subdir_path_dict.keys())
			pass
		pass
	
	
	def save(self):
		self._logger.debug(f"save: currently dirty records are: {self._dir_manager.db_stats()['dirty']}, new: {self._dir_manager.db_stats()['new']}")
		self._dir_manager.db_commit()
		self._logger.debug(f"save: commited, after commit dirty records are: {self._dir_manager.db_stats()['dirty']}, new: {self._dir_manager.db_stats()['new']}")
		pass
	
	
	@property
	def preview_html(self):
		result = f"Will split dir {self.dir_obj.full_path} into dirs:" + "\n"
		t_dict = self.get_dict_of_subdirs()
		for k, v in t_dict:
			result += "k\n"
		result += "\n\n"
		return result.replace("\n", "<br>\n")
		
	
	def run(self):
		self._logger.debug(f"run: starting for dir {self.dir_obj.full_path}")
		self.mark_start()
		self.get_dict_of_subdirs()
		self.create_subdirs()
		self.save()
		
		self.mark_end()
		self._logger.debug("run: complete")
		pass


