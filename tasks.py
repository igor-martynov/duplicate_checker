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
from sqlalchemy_declarative import TaskRecord



class BaseTask(TaskRecord):
	"""BaseTask - base class for all tasks"""
	
	def __init__(self, logger = None, file_manager = None, dir_manager = None, task_manager = None):
		super(BaseTask, self).__init__()
		
		self._file_manager = file_manager
		self._dir_manager = dir_manager
		self._task_manager = task_manager
		self._logger = logger
		
		self._type = self.__class__.__name__
		self.date_start = None
		self.date_end = None
		
		# self._progress = 0.0
		self._prev_progress = None
		self._prev_datetime = None
		self._prev_ETA_S = 0
		
		self.save_results = True
		self.__result_html_complete = False
	
	
	def run(self):
		"""main task method, sync, will return when result is ready"""
		raise NotImplemented
	
	
	def start(self):
		"""start self.run() in parallel thread. async, will return before result is ready"""
		self._logger.debug("start: starting task")
		self.__thread = threading.Thread(target = self.run)
		self.__thread.start()
		self._logger.debug("start: task started in thread")
	
	
	def abort(self):
		raise NotImplemented
	
	
	def end(self):
		raise NotImplemented
	
	
	def mark_task_start(self):
		self.date_start = datetime.datetime.now()
		self.running = True
		self.complete = False
		self.OK = True
		self.pending = False
		self._progress = 0.0
	
	
	def mark_task_end(self):
		self.date_end = datetime.datetime.now()
		self.running = False
		self._progress = 1.0
	
	
	def mark_task_OK(self):
		self.complete = True
		self.OK = True
		self.running = False
	
	
	def mark_task_failure(self):
		self.complete = False
		self.OK = False
		self.running = False
	
	
	def save(self):
		raise NotImplemented
	
	
	def mark_result_OK(self):
		self.result_OK = True
	
	
	def mark_result_failure(self):
		self.result_OK = False
	
	
	# @property
	# def preview_html(self):
	# 	return f"Preview of {self.__class__.__name__}<br>"
	
	
	def generate_report(self):
		self._logger.debug("generate_report: default generate_report called, normally this should not happen")
		self.__report = f"Task: {self.descr}, status: {self.state}"
		return self.__report
	
	

class AddDirTask(BaseTask):
	"""Task to add new dir.
	
	"""
	
	def __init__(self, target_dir, logger = None, file_manager = None, dir_manager = None, task_manager = None, is_etalon = False, checksum_algorithm = "md5"):
		super(AddDirTask, self).__init__(logger = logger, file_manager = file_manager, dir_manager = dir_manager, task_manager = task_manager)
		self.target_dir_path = target_dir
		self.file_list = []
		self.is_etalon = is_etalon
		self._sleep_delay = 1
		self.dir = None
		self.checksum_algorithm = checksum_algorithm # default is md5, but sha512 also is supported
		self.__thread = None
		self.__pool = None
		
		if self._logger is not None:
			self._logger.debug(f"__init__: init complete with target_dir_path {self.target_dir_path}")
	
	
	@property
	def descr(self):
		return f"Task {self.task_type} for {self.target_dir_path}"
	
	
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
		if self.checksum_algorithm == "sha512":
			result = self.__pool.imap_unordered(get_file_checksum_sha512, dict_list)
		else:
			result = self.__pool.imap_unordered(get_file_checksum, dict_list)
		self.__pool.close()
		self._logger.debug("create_multiprocessing_pool: pool created and closed")
		return result
	
	
	def _wait_till_complete(self, result, dict_list):
		dict_length = len(dict_list)
		complete = result._index
		while complete != dict_length:
			self._logger.debug(f"_wait_till_complete: waiting for pool, complete: {complete} of {dict_length}...")
			time.sleep(self._sleep_delay)
			complete = result._index
			self._progress = complete / dict_length
		self._logger.debug(f"_wait_till_complete: pool results ready: {result}")
		return
	
	
	def _create_directory_and_files(self, result, save = True):
		now = datetime.datetime.now()
		new_dir = self._dir_manager.create(self.target_dir_path, is_etalon = self.is_etalon, date_added = now, date_checked = now, save = save, name = os.path.basename(self.target_dir_path))
		files = []
		for r in result:
			files.append(self._file_manager.create(r['full_path'], checksum = r['checksum'], date_added = r["date_end"], date_checked = r["date_end"], is_etalon = self.is_etalon, save = save))
		new_dir.files = files
		self._logger.info(f"_create_directory_and_files: created dir {new_dir.full_path} with {len(files)} files: {[f.full_path for f in files]}")
		self.dir = new_dir
		return new_dir
	
	
	def save(self):
		"""save task results to DB"""
		self._logger.debug(f"save: currently dirty records are: {self._dir_manager.db_stats()['dirty']}, new: {self._dir_manager.db_stats()['new']}")
		self._dir_manager.db_commit()
		self._logger.debug(f"save: commited, after commit dirty records are: {self._dir_manager.db_stats()['dirty']}, new: {self._dir_manager.db_stats()['new']}")
		
	
	def run(self):
		self._logger.info(f"run: starting, target_dir_path: {self.target_dir_path}")
		self.mark_task_start()
		try:
			self.file_list = self.get_dir_listing(self.target_dir_path)
			self._logger.debug(f"run: got file list: {self.file_list}")
			
			dict_list = self._create_input_list()
			dict_length = len(dict_list)
			result = self._create_multiprocessing_pool(dict_list)
			self._wait_till_complete(result, dict_list)
			new_dir = self._create_directory_and_files(result)
			if self.save_results:
				self.save()	
			else:
				self._logger.info("run: not saving results because save == False")	
			self.mark_task_OK()
			self.mark_result_OK()
			self._logger.debug("run: complete")
			self.mark_task_end()
			return new_dir
		except Exception as e:
			self._logger.error(f"run: got error {e}, traceback: {traceback.format_exc()}")
			self.mark_task_failure()
			self.mark_result_failure()
			self.mark_task_end()
		# TODO: should call genetate_report here
		
	
	@property
	def result_html(self):
		if self.dir is None:
			return f"full_path: {self.target_dir_path}<br>status: {self.state}, result is not ready yet."
		else:
			result_str = f"Dir: {self.dir.full_path}, total files: {len(self.dir.files)}" + "<br>\n<br>\n"
			for f in self.dir.files:
				result_str += f"f: {f.full_path} - {f.checksum}" + "<br>\n"
			result_str += f"Task took: {secs_to_hrf(self.duration)}"
			return result_str



class CompareDirsTask(BaseTask):
	"""Task to compare two dirs.
	
	"""
	
	def __init__(self, dir_a, dir_b, logger = None, file_manager = None, dir_manager = None, task_manager = None):
		super(CompareDirsTask, self).__init__(logger = logger, file_manager = file_manager, dir_manager = dir_manager, task_manager = task_manager)
		self.dir_a = dir_a
		self.dir_b = dir_b
		self.files_on_both = []
		self.files_a_on_b = []
		self.files_b_on_a = []
		self.files_only_on_a = []
		self.files_only_on_b = []
		self.equal_names_diff_checsums = []
		self.dirs_are_equal = None
		pass
	
	
	@property
	def descr(self):
		return f"Task {self.task_type} for {self.dir_a.full_path} and {self.dir_b.full_path}"
	
	
	@property
	def a_is_subset_of_b(self):
		return True if len(self.files_a_on_b) == len(self.dir_a.files) else False
	
	
	@property
	def b_is_subset_of_a(self):
		return True if len(self.files_b_on_a) == len(self.dir_b.files) else False
		
	
	def run(self):
		self._logger.info(f"run: starting comparing dir_a {self.dir_a.full_path} and dir_b {self.dir_b.full_path}")
		self.mark_task_start()
		self._logger.debug("run: checking files on both A and B")
		try:
			len_dir_a_files = len(self.dir_a.files)
			len_dir_b_files = len(self.dir_b.files)
			len_all_files = len_dir_a_files + len_dir_b_files
			
			for fa in self.dir_a.files:
				self._progress += 0.25 / len_all_files
				self._logger.debug(f"run: checking for both A and B file {fa.full_path} - {fa.checksum}")
				candidates = self._file_manager.get_by_checksum(fa.checksum, idir = self.dir_b)
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
				self._progress += 0.25 / len_all_files
				self._logger.debug(f"run: checking for both A and B file {fb.full_path} - {fb.checksum}")
				candidates = self._file_manager.get_by_checksum(fb.checksum, idir = self.dir_a)
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
				self._progress += 0.25 / len_all_files
				self._logger.debug(f"run: checking for only on A and B file {fa.full_path} - {fa.checksum}")
				if fa not in self.files_on_both:
					self._logger.debug(f"run: adding to files_only_on_a: {fa.full_path}")
					self.files_only_on_a.append(fa)
			for fb in self.dir_b.files:
				self._progress += 0.25 / len_all_files
				self._logger.debug(f"run: checking for only on A and B file {fb.full_path} - {fb.checksum}")
				if fb not in self.files_on_both:
					self._logger.debug(f"run: adding to files_only_on_b: {fb.full_path}")
					self.files_only_on_b.append(fb)
			self.check_dirs_equal()
			self._logger.info(f"run: Totals: files_on_both: {len(self.files_on_both)}, files_a_on_b: {len(self.files_a_on_b)}, files_b_on_b: {len(self.files_b_on_a)}, files_only_on_a: {len(self.files_only_on_a)}, files_only_on_b: {len(self.files_only_on_b)}")
			self._logger.debug("run: complete")
			self.mark_task_OK()
		except Exception as e:
			self._logger.error(f"run: got error while running: {e}, traceback: {traceback.format_exc()}")
			self.mark_task_failure()
		self.mark_task_end()
		self.generate_report()
	
	
	def check_dirs_equal(self):
		if len(self.files_on_both) == (len(self.dir_a.files) + len(self.dir_b.files)) and len(self.files_only_on_a) == 0 and len(self.files_only_on_b) == 0:
			self._logger.info("run: dir A equal dir B")
			self.dirs_are_equal = True
			self.mark_result_OK()
		else:
			self._logger.info("run: dir A NOT equal dir B")
			self.dirs_are_equal = False
			self.mark_result_failure()
	
	
	def generate_report(self):
		if len(self.files_on_both) == 0 and len(self.files_a_on_b) == 0 and len(self.files_b_on_a) == 0:
			self._logger.debug("result_html: result requested but seems to be empty. returning status from parent class")
			# return f"Task result is not ready. Current task status: {self.state}"
		self.__report = ""
		self.__report += f"Directory comparation status: {self.state}" + ".\n"
		self.__report += f"Directory A: {self.dir_a.full_path}, {len(self.dir_a.files)} files." + "\n"
		self.__report += f"Directory B: {self.dir_b.full_path}, {len(self.dir_b.files)} files." + "\n"
		self.__report += "\n\n"
		if self.dirs_are_equal:
			self.__report += "DIRS ARE EQUAL.\n\n"
		else:
			self.__report += "Dirs are not equal.\n\n"
			if self.a_is_subset_of_b:
				self.__report += "A is subset of B.\n\n"
			if self.b_is_subset_of_a:
				self.__report += "B is subset of A.\n\n"
			
		self.__report += f"Files on both A and B: {len(self.files_on_both)}" + "\n"
		# for f in self.files_on_both:
		# 	self.__report += f"f: {f.full_path} - {f.checksum}" + "\n"
		# self.__report += "\n\n"
		self.__report += f"Files of A that exist in B: {len(self.files_a_on_b)}" + "\n"
		# for f in self.files_a_on_b:
		# 	self.__report += f"f: {f.full_path} - {f.checksum}" + "\n"
		# self.__report += "\n\n"
		self.__report += f"Files of B that exist in A: {len(self.files_b_on_a)}" + "\n"
		# for f in self.files_b_on_a:
		# 	self.__report += f"f: {f.full_path} - {f.checksum}" + "\n"
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
		return self.__report
	
	
	
class FindCopiesTask(BaseTask):
	"""Task to find copies of files of one dir"""
	
	def __init__(self, target_dir, logger = None, file_manager = None, dir_manager = None, task_manager = None):
		super(FindCopiesTask, self).__init__(logger = logger, file_manager = file_manager, dir_manager = dir_manager, task_manager = task_manager)
		self.dir = target_dir
		self.file_dict = {} # key: original file object, value: list of copies (file objects)
		self.copies_dict = {} # key: dir that contains copy, value: 
		self.no_copies_list = [] # list of files without copies
		# self.__result_html_complete = False
		self.dir_has_full_copy = False
	
	
	@property
	def descr(self):
		return f"Task {self.task_type} for {self.dir.full_path}"
	
	
	def run(self):
		self._logger.info(f"run: starting with dir {self.dir.full_path}")
		self.mark_task_start()
		self.file_dict = {}
		for f in self.dir.files:
			self.file_dict[f] = []
		self._logger.debug("run: file_dict pre-created, checking files...")
		total_files = len(self.dir.files)
		try:
			progress_increase = (1 / total_files) if total_files != 0 else 1.0
			for f in self.dir.files:
				self._logger.debug(f"run: checking file {f.full_path}... progress: {self._progress}")
				candidates = self._file_manager.find_copies(f)
				self._progress += progress_increase
				for c in candidates:
					if c.dir == self.dir or c.dir.full_path == self.dir.full_path:
						self._logger.debug(f"run: ignoring candidate {c.id} - {c.full_path} because it has the same dir {c.dir.full_path}. progress: {self._progress}")
						continue
					if f.name == c.name:
						self.file_dict[f].append(c)
					else:
						self._logger.info(f"run: should add file {c.full_path} as copy, but it has different name. original name is {f.name}. So did not add. progress: {self._progress}")
			self._logger.debug("run: file checking complete, file_dict filled.")
			self._logger.debug("run: run complete.")
			self.mark_task_OK()
		except Exception as e:
			self._logger.error(f"run: got error {e}, traceback: {traceback.format_exc()}")
			self.mark_task_failure()
		self.mark_task_end()
		self.generate_report()
	
	
	def get_copies_stats(self):
		"""transpose file_dict into copies_dict, and accumulate no_copies_list"""
		self._logger.debug("get_copies_stats: starting")
		self.copies_dict = {}
		self.no_copies_list = []
		for k, v in self.file_dict.items():
			if len(v) == 0:
				self.no_copies_list.append(k)
			for _copy in v:
				_copy_dir = _copy.dir
				if _copy_dir not in self.copies_dict.keys():
					self.copies_dict[_copy_dir] = [k, ]
				else:
					self.copies_dict[_copy_dir].append(k)
		self._logger.debug("get_copies_stats: complete")
	
	
	# @cProfile_wrapper
	def generate_report(self):
		self._logger.debug("generate_report: starting")
		self.__report = "\n\nStatus: " + str(self.state) + "\n"
		self.__report += "\nDir: " + self.dir.full_path + "\n"
		self.__report += f"({len(self.dir.files)} files)" + "\n\n"
		self.get_copies_stats()
		self._logger.debug("generate_report: stage 1 complete")
		self.__report += f"files without copies: {len(self.no_copies_list)}" + "\n"
		for f in self.no_copies_list:
			self.__report += f.full_path + "\n"
		self.__report += "\n\n"
		
		self._logger.debug("generate_report: stage 2 complete")
		self.__report += "Copies:\n"
		
		for d in self.copies_dict.keys():
			# will generate sets for readability 
			set_path_origin = set([f.full_path for f in self.dir.files])
			set_checksum_origin = set([f.checksum for f in self.dir.files])
			set_path_copy = set([f.full_path for f in self.copies_dict[d]])
			set_checksum_copy = set([f.checksum for f in self.copies_dict[d]])
			set_path_copy_dir = set([f.full_path for f in d.files])
			set_checksum_copy_dir = set([f.checksum for f in d.files])
			# then use these sets
			if set_path_copy == set_path_origin and set_checksum_copy_dir == set_checksum_origin:
				self.dir_has_full_copy = True
				self.__report += f"Copy: {d.full_path} - [<a href='{d.url}' title='show dir'>show dir</a>] -- IS EXACT FULL COPY -- (copy) {len(self.copies_dict[d])} files of (orig) {len(self.dir.files)}, copy dir has {len(d.files)} files" + "\n"
			elif set_checksum_copy_dir > set_checksum_origin:
				self.dir_has_full_copy = True
				self.__report += f"Copy: {d.full_path} - [<a href='{d.url}' title='show dir'>show dir</a>] -- COPY CONTAINS FULL ORIGINAL -- (copy) {len(self.copies_dict[d])} files of (orig) {len(self.dir.files)}, copy dir has {len(d.files)} files" + "\n"
			elif set_checksum_copy_dir < set_checksum_origin:
				self.__report += f"Copy: {d.full_path} - [<a href='{d.url}' title='show dir'>show dir</a>] -- copy is partial subset -- (copy) {len(self.copies_dict[d])} files of (orig) {len(self.dir.files)}, copy dir has {len(d.files)} files" + "\n"
			elif len(set_checksum_origin.intersection(set_checksum_copy_dir)) != 0 and len(d.files) != len(self.dir.files):
				self.__report += f"Copy: {d.full_path} - [<a href='{d.url}' title='show dir'>show dir</a>] -- intersection of copy and original - {len(set_checksum_origin.intersection(set_checksum_copy_dir))} files -- (copy) {len(self.copies_dict[d])} files of (orig) {len(self.dir.files)}, copy dir has {len(d.files)} files" + "\n"
			else:
				self.__report += f"Copy: {d.full_path} - [<a href='{d.url}' title='show dir'>show dir</a>] -- ERROR! -- (copy) {len(self.copies_dict[d])} files of (orig) {len(self.dir.files)}, copy dir has {len(d.files)} files" + "\n"
		
		self.__report += "\n\n"
		self._logger.debug("generate_report: stage 3 complete")
		self.__report += "All files:\n"
		for k, v in self.file_dict.items():
			self.__report += f"f: {k.full_path}: copies {len(v)}: {[f.full_path for f in v]}" + "\n"
		self.__report += "\n\n" + f"Task took: {self.duration}s"
		self._logger.debug(f"generate_report: report length: {len(self.__report)}")
		return self.__report.replace("\n", "<br>\n")
		

# TODO: testing
class CheckDirTask(BaseTask):
	"""docstring for CheckDirTask"""
	
	def __init__(self, target_dir, logger = None, file_manager = None, dir_manager = None, task_manager = None, checksum_algorithm = "md5"):
		super(CheckDirTask, self).__init__(logger = logger, file_manager = file_manager, dir_manager = dir_manager, task_manager = task_manager)
		self.dir = target_dir
		self.new_dir = None
		self.subtask_add = None
		self.subtask_compare = None
		self.checksum_algorithm = checksum_algorithm
		
	
	def init_subtask_add(self):
		self.subtask_add = AddDirTask(self.dir.full_path,
			logger = self._logger.getChild("SubTask_AddDirTask_"),
			file_manager = self._file_manager,
			dir_manager = self._dir_manager,
			is_etalon = self.dir.is_etalon,
			checksum_algorithm = self.checksum_algorithm)
		self.subtask_add.save_results = False
		self._logger.debug(f"init_subtask_add: adding subtask AddDirTask, target_dir_path is: {self.dir.full_path}")
	
	
	def init_subtask_compare(self):
		self.subtask_compare = CompareDirsTask(self.dir,
			self.subtask_add.dir,
			logger = self._logger.getChild("SubTask_CompareDirsTask_"),
			file_manager = self._file_manager,
			dir_manager = self._dir_manager)
		self._logger.debug(f"init_subtask_compare: adding subtask CompareDirsTask, dir A: {self.dir}, dir B: {self.subtask_add.dir}")
	
	
	def compare_dirs_old_and_new(self):
		self._logger.debug(f"compare_dirs_old_and_new: will create subtask CompareDirsTask for dir comparison: {self.dir} and {self.subtask_add.dir}")
		self.subtask_compare.run()
		self._logger.debug("compare_dirs_old_and_new: comparation complete")
		if self.subtask_compare.result_OK:
			self._logger.info("compare_dirs_old_and_new: dirs OLD and NEW are equal")
			self.mark_result_OK()
			return True
		else:
			self._logger.debug("compare_dirs_old_and_new: dirs OLD and NEW are NOT equal")
			self.mark_result_failure()
			return False

	
	def add_dir(self):
		return self.subtask_add.run()
	
	
	def run(self):
		self._logger.info(f"run: starting, target_dir: {self.dir.full_path}")
		self.mark_task_start()
		try:
			self.init_subtask_add()
			self._logger.debug(f"run: will get real checksums for dir...")
			self.new_dir = self.add_dir()
			self.init_subtask_compare()
			self._logger.debug(f"run: got real checksums. will compare real dir and dir from db...")
			self.compare_dirs_old_and_new() # marking result within this method
			self._logger.debug("run: complete")
			self.mark_task_OK()
		except Exception as e:
			self._logger.error(f"got error while running: {e}, traceback: {traceback.format_exc()}")
			self.mark_task_failure()
		self.mark_task_end()
		self.generate_report()
	
	
	@property
	def descr(self):
		return f"Task {self.task_type} for dir {self.dir.full_path}"
	
	
	def generate_report(self):
		self.__report = "CheckDirTask result:\n"
		self.__report += f"Origin dir: {self.dir.full_path}, {len(self.dir.files)} files" + "\n"
		self.__report += f"Actual dir: {self.new_dir.full_path}, {len(self.new_dir.files)} files" + "\n"
		if self.subtask_compare.dirs_are_equal:
			self.__report += "Dir is OK, all checksums are actual\n"
		else:
			self.__report += "DIR HAS CHENGED! Please check subtask CompareDirsTask.\n"
		self.__report += "\n"
		self.__report += "\n\n" + f"result of subtask AddDirTask: {self.subtask_add.result_html}" + "\n"
		self.__report += "\n\n" + f"result of subtask CompareDirsTask: {self.subtask_compare.result_html}" + "\n"
		self.__report += f"Task took: {self.duration}s"
		self._logger.debug(f"generate_report: report ready, length: {len(self.__report)}")
		return self.__report

	
	@property
	def progress(self):
		if self.subtask_add is not None and self.subtask_compare is not None:
			return (self.subtask_add._progress + self.subtask_compare._progress) / 2
		elif self.subtask_add is not None and self.subtask_compare is None:
			return self.subtask_add._progress / 2
		else:
			return 0.0
	

# TODO: under development
class SplitDirTask(BaseTask):
	"""Task to split dir into individual subdirs and add them to the DB"""
	
	def __init__(self, target_dir, logger = None, file_manager = None, dir_manager = None, task_manager = None):
		super(SplitDirTask, self).__init__(logger = logger, file_manager = file_manager, dir_manager = dir_manager, task_manager = task_manager)
		self.dir_obj = target_dir
		self.subdirs = []
		self.subdir_path_dict = dict()
	
	
	@property
	def descr(self):
		return f"Task {self.task_type} for dir {self.dir_obj.full_path}"
	
	
	def get_dict_of_subdirs(self):
		self.subdir_path_dict = {}
		target_dir_path = self.dir_obj.full_path
		for f in self.dir_obj.files:
			dirname = os.path.dirname(f.full_path)
			if dirname == target_dir_path:
				self._logger.debug(f"get_dict_of_subdirs: file {f.full_path} is in dir root, ignoring this file")
				continue
			if os.path.dirname(dirname) != target_dir_path:
				dirname = target_dir_path + os.path.split(dirname)[-2] # error
				self._logger.debug(f"get_dict_of_subdirs: detected next level of subdirs, using {dirname}")
			if dirname != target_dir_path:
				if dirname not in self.subdir_path_dict.keys():
					self.subdir_path_dict[dirname] = []
					self._logger.debug(f"get_dict_of_subdirs: created empty dict item for subdir {dirname}")
				self.subdir_path_dict[dirname].append(f)
				self._logger.debug(f"get_dict_of_subdirs: added file {f.full_path} to subdir {dirname}")
		self._logger.info(f"get_dict_of_subdirs: got subdirs: {self.subdir_path_dict.keys()}, total: {len(self.subdir_path_dict.keys())}")	
		return self.subdir_path_dict
	
	
	def create_subdirs(self):
		self._logger.debug(f"create_subdirs: will create subdirs for dict keys: {self.subdir_path_dict.keys()}")
		progress_increment = 1 / len(self.subdir_path_dict.keys()) if len(self.subdir_path_dict.keys()) != 0 else 0.0
		for subdir_path, subdir_files in self.subdir_path_dict.items():
			self._logger.debug(f"create_subdirs: creating objects for subdir {subdir_path}")
			now = datetime.datetime.now()
			new_dir = self._dir_manager.create(subdir_path, is_etalon = self.dir_obj.is_etalon, date_added = now, date_checked = self.dir_obj.date_checked)
			new_dir_files = []
			for f in subdir_files:
				# copy file into new object
				new_file = self._file_manager.create(f.full_path, is_etalon = f.is_etalon, date_added = now, date_checked = f.date_checked)
				new_file.checksum = f.checksum
				new_dir_files.append(new_file)
				pass
			new_dir.files = new_dir_files
			self.subdirs.append(new_dir)
			self._progress += progress_increment
	
	
	def save(self):
		self._logger.debug(f"save: currently dirty records are: {self._dir_manager.db_stats()['dirty']}, new: {self._dir_manager.db_stats()['new']}")
		self._dir_manager.db_commit()
		self._logger.debug(f"save: commited, after commit dirty records are: {self._dir_manager.db_stats()['dirty']}, new: {self._dir_manager.db_stats()['new']}")
		self.mark_task_OK()
	
	
	@property
	def preview_html(self):
		result = f"Will split dir {self.dir_obj.full_path} into dirs:" + "\n"
		t_dict = self.get_dict_of_subdirs()
		for k, v in t_dict:
			result += "k\n"
		result += "\n\n"
		return result.replace("\n", "<br>\n")
	
	
	def generate_report(self):
		self.__report = ""
		self.__report += f"Directory {self.dir_obj.full_path} split status: {self.state}" + ".\n\n"
		self.__report += "Added dirs:"
		for d in self.subdirs:
			self.__report += f"Dir {d.full_path} ({len(d.files)} files)"
		self.__report += "\n" + f"Task took: {secs_to_hrf(self.duration)}"
		return self.__report
	
	
	def run(self):
		self.mark_task_start()
		self.get_dict_of_subdirs()
		self.create_subdirs()
		self.save()
		self.mark_task_end()
		if len(self.subdirs) != 0:
			self.mark_result_OK()
		else:
			self.mark_result_failure()
		self.generate_report()
		


# TODO: check this
class CompileDirTask(BaseTask):
	"""docstring for CompileDirTask"""
	def __init__(self, path_to_new_dir, logger = None, file_manager = None, dir_manager = None, task_manager = None, input_dir_list = []):
		super(CompileDirTask, self).__init__(logger = logger, file_manager = file_manager, dir_manager = dir_manager, task_manager = task_manager)
		self.path_to_new_dir = path_to_new_dir
		self.new_dir = None
		self.input_dirs = input_dir_list
		self.all_files_list = [file for idir in self.input_dirs for file in idir.files] # TODO: check this
		self._logger.debug(f"__init__: got input dir list: {[idir.full_path for idir in self.input_dirs]}, path to new dir: {self.path_to_new_dir}")
		self._logger.debug(f"__init__: got all_files_list: {[f.full_path for f in self.all_files_list]}")
		self.unique_files = []
		self.dry_run = False
		self.CP_COMMAND = "/usr/bin/cp -p" if os.path.isfile("/usr/bin/cp") else "/bin/cp -p"
		self.MKDIR_COMMAND = "/usr/bin/mkdir -p" if os.path.isfile("/usr/bin/mkdir") else "/bin/mkdir -p"
		pass
	
	
	@property
	def descr(self):
		return f"Task {self.task_type} for new dir {self.path_to_new_dir}"
	
	
	def get_unique_file_list(self):
		unique_checksums = set([f.checksum for f in self.all_files_list])
		self._logger.info(f"get_unique_file_list: got {len(unique_checksums)} unique_checksums")
		self._logger.debug(f"get_unique_file_list: unique_checksums are: {unique_checksums}")
		
		# algo take 1 - simply by checksums
		for uc in unique_checksums:
			for file in self._file_manager.get_by_checksum(uc):
				if file.dir in self.input_dirs:
					self.unique_files.append(file)
					self._logger.debug(f"get_unique_file_list: added file {file.full_path} to target list because its dir {file.dir.full_path} exist in input dir list")
					break
		self._logger.debug(f"get_unique_file_list: got list of unique files ({len(self.unique_files)} total): {[file.full_path for file in self.unique_files]}")
		return self.unique_files
	
	
	def check_all_files_exist(self):
		for f in self.unique_files:
			if not self.dry_run and not os.path.isfile(f.full_path):
				self._logger.error(f"check_all_files_exist: file {f.full_path} is unavailable now, aborting")
				return False
		self._logger.info(f"check_all_files_exist: all files are available now")
		return True
	
	
	def create_copy_commands(self):
		cmd_list = []
		cmd_args_dict = {}
		# creating or not creating new dir
		if not os.path.isdir(self.path_to_new_dir):
			cmd_list.append(f"{self.MKDIR_COMMAND} '{self.path_to_new_dir}'")
			self._logger.debug(f"create_copy_commands: will create new dir {self.path_to_new_dir}")
		else:
			self._logger.debug(f"create_copy_commands: new dir {self.path_to_new_dir} already exist, will not create")
		# generating new filenames if necessary
		resulting_names = cmd_args_dict.keys()
		for f in self.unique_files:
			if f.name in resulting_names:
				# will try and ganerate new name
				new_name = f.name + f.checksum[-6:]
				self._logger.info(f"create_copy_commands: will use new name {new_name} for file {f.full_path}")
				cmd_args_dict[new_name] = f
			else:
				cmd_args_dict[f.name] = f
				self._logger.debug(f"create_copy_commands: will copy {f.full_path} without renaming")
		# compiling comands
		for new_filename, orig_file in cmd_args_dict.items():
			cmd_list.append(f"{self.CP_COMMAND} '{orig_file.full_path}' '{self.path_to_new_dir}/{new_filename}'")
		self._logger.debug(f"create_copy_commands: generated command list is: {cmd_list}")
		return cmd_list
	
	
	def run_commands(self, command_list):
		if self.dry_run:
			self._logger.debug("run_commands: will not execute any command due to dry_run == True")
			return True
		progress_increment = 1 / len(command_list)
		for cmd in command_list:
			try:
				run_command(cmd)
				self._logger.debug(f"run_commands: executing command: {cmd}")
				self._progress += progress_increment
			except Exception as e:
				self._logger.error(f"run_commands: got error white executing command: {cmd}. Error: {e}, traceback: {traceback.format_exc()}")
				self._logger.info("run_commands: stoping command execution due to error.")
				return False
		return True
	
	
	def generate_report(self):
		self.__report = f"CompileDirTask for new dir {self.path_to_new_dir}"
		return self.__report
	
	
	def run(self):
		self.mark_task_start()
		self.get_unique_file_list()
		if self.check_all_files_exist() is True:
			self._logger.debug("run: all files exist")
		else:
			self._logger.error(f"run: aborting dir compilation due to missing file.")
			self.mark_task_failure()
			self.mark_result_failure()
			self.mark_task_end()
			return
		# create copy commands list
		commands = self.create_copy_commands()
		if len(commands) == 0:
			self._logger.error("run: got zero length command list. Unexpected. returning.")
			self.mark_result_failure()
			return 
		# run all commands
		result = self.run_commands(commands)
		if result:
			self._logger.info("run: all commands executed OK")
			self.mark_result_OK()
			self.mark_task_OK()
		else:
			self._logger.error("run: got error while executing commands, exiting")
			self.mark_result_failure()
			self.mark_task_failure()
			return
		self.mark_task_end()
		self.generate_report()



class DeleteDirTask(BaseTask):
	"""This task implements dir deletion via tasks mechanism, thus improving data integrity and reducing risks of race conditions"""
	def __init__(self, target_dir, logger = None, file_manager = None, dir_manager = None, task_manager = None):
		super(DeleteDirTask, self).__init__(logger = logger, file_manager = file_manager, dir_manager = dir_manager, task_manager = task_manager)
		self.target_dir = target_dir
		self.target_dir_path = target_dir.full_path
		self.target_dir_id = target_dir.id
	
	
	@property
	def descr(self):
		return f"Task {self.task_type} for dir {self.target_dir_path}"
		
	
	# @cProfile_wrapper
	def run(self):
		self.mark_task_start()
		self._logger.debug(f"run: starting deletion of dir {self.target_dir_id} - {self.target_dir_path}")
		try:
			num_files = len(self.target_dir.files)
			progress_increment = 1 / num_files if num_files != 0 else 1.0
			for f in self.target_dir.files:
				self._file_manager.delete(f)
				self._progress += progress_increment
			self._dir_manager.delete(self.target_dir)
			self._logger.debug(f"run: directory deleted")
			self.mark_result_OK()
			self.mark_task_OK()
		except Exception as e:
			self._logger.error(f"run: got error while deleting dir {self.target_dir_id} - {self.target_dir_path}. error: {e}, traceback: {traceback.format_exc()}")
			self.mark_result_failure()
			self.mark_task_failure()
		self.mark_task_end()
		self.generate_report()



# TODO: this should be extended
class DeleteFilesTask(BaseTask):
	"""docstring for DeleteFilesTask"""
	def __init__(self, file_list, logger = None, file_manager = None, dir_manager = None, task_manager = None):
		super(DeleteFilesTask, self).__init__(logger = logger, file_manager = file_manager, dir_manager = dir_manager, task_manager = task_manager)
		self.files_to_delete = file_list
	
	
	def descr(self):
		return f"Task {self.task_type} for {len(self.files_to_delete)} files"
	
	
	def run(self):
		self.mark_task_start()
		
		try:
			for f in self.files_to_delete:
				self._file_manager.delete(f)
			self.mark_task_OK()
			self.mark_result_OK()
		except Exception as e:
			self.mark_task_failure()
			self.mark_result_failure()
			self._logger.error(f"run: got error {e}, traceback: {traceback.format_exc()}")
		self.mark_task_end()
		self.generate_report()
	
	
	def generate_report(self):
		self.__report = "DeleteFilesTask result:\n Deleted files:\n"
		for f in self.files_to_delete:
			self.__report += f"{f.id} - {f.full_path} - {f.checksum}"
		
