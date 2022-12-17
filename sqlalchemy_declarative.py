#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os

# logging
import logging
import logging.handlers

# SQL Alchemy
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine

from base import secs_to_hrf, datetime_to_str


DeclarativeBase = declarative_base()



class Directory(DeclarativeBase):
	"""Directory class"""
	
	__tablename__ = "dirs"
	id = Column(Integer, primary_key = True)
	is_etalon = Column(Boolean, nullable = False)
	date_added = Column(DateTime, nullable = True)
	date_checked = Column(DateTime, nullable = True)
	name = Column(String, nullable = False)
	full_path = Column(String, nullable = False)
	comment = Column(String, nullable = True)
	deleted = Column(Boolean, nullable = False, default = False)
	enabled = Column(Boolean, nullable = False, default = True)
	drive = Column(String, nullable = True)
	host = Column(String, nullable = True)
	files = relationship("File", back_populates = "dir")
	
	
	@property
	def url(self):
		return f"/ui/show-dir/{self.id}"
	
	@property
	def url_html_code(self):
		return f"<a href='{self.url}' title='show dir'>{self.id} - {self.full_path}</a>"

	
	@property
	def dict_for_json(self):
		return {"id": self.id, "full_path": self.full_path, "files": [f.id for f in self.files], "is_etalon": self.is_etalon}
		


class File(DeclarativeBase):
	"""File class"""
	
	__tablename__ = "files"
	id = Column(Integer, primary_key = True)
	is_etalon = Column(Boolean, nullable = False)
	date_added = Column(DateTime, nullable = True)
	date_checked = Column(DateTime, nullable = True)
	# name = Column(String(250), nullable = False)
	full_path = Column(String, nullable = False)
	checksum = Column(String, nullable = True)
	comment = Column(String, nullable = True)
	deleted = Column(Boolean, nullable = False, default = False)
	enabled = Column(Boolean, nullable = False, default = True)
	dir_id = Column(Integer, ForeignKey("dirs.id"))
	dir = relationship("Directory", back_populates = "files")
	
	
	@property
	def name(self):
		return os.path.basename(self.full_path) if (self.full_path is not None and len(self.full_path) != 0) else None\
		
	
	@property
	def url(self):
		return f"/ui/show-file/{self.id}"
	
	
	@property
	def url_html_code(self):
		return f"<a href='{self.url}' title='show file'>{self.id} - {self.full_path}</a>"
	
	
	@property
	def dict_for_json(self):
		return {"id": self.id, "full_path": self.full_path, "checksum": self.checksum, "dir": self.dir.id, "is_etalon": self.is_etalon}
	


# TODO: under development
class TaskRecord(DeclarativeBase):
	"""TaskRecord"""
	
	__tablename__ = "tasks"
	id = Column(Integer, primary_key = True)
	_type = Column(String, nullable = True)
	date_start = Column(DateTime, nullable = True)
	date_end = Column(DateTime, nullable = True)
	task_result = Column(String, nullable = True)
	target_dir_id = Column(Integer, ForeignKey("dirs.id"))
	target_file_list = Column(String, nullable = True)
	pending = Column(Boolean, nullable = False, default = True)
	running = Column(Boolean, nullable = True, default = None)
	complete = Column(Boolean, nullable = True, default = None)
	OK = Column(Boolean, nullable = True, default = None)
	error_message = Column(String, nullable = True, default = "")
	result_OK = Column(Boolean, nullable = True, default = None) # True == result OK (as expexted), False == result unexpected
	report = Column(String, nullable = True, default = "")
	progress = Column(Float, nullable = True, default = 0.0)
	
	
	@property
	def url(self):
		return f"/ui/show-task/{self.id}"
	
	@property
	def url_html_code(self):
		return f"<a href='{self.url}' title='show task'>{self.id} - {self.descr}</a>"
	

	@property
	def dict_for_json(self):
		return {"id": self.id, "task_type": self.task_type, "date_start": self.date_start, "date_end": self.date_end}
	
	
	@property		
	def state(self):
		"""returns text description of current task state"""
		# self._logger.debug("state: requested")
		if self.date_start is None and not self.running:
			return "PENDING"
		if self.complete and self.OK and self.date_end is not None and not self.running:
			return "COMPLETE OK"
		if not self.complete and self.OK:
			return f"IN PROGRESS ({(self.progress * 100):.1f}%, time left: {secs_to_hrf(self.ETA_s)}, ETA: {datetime_to_str(self.ETA_datetime)})"
		if not self.OK and self.running:
			return f"IN PROGRESS, FAILURE ({(self.progress * 100):.1f}%)"
		if (not self.OK and not self.running) or (not self.OK and not self.complete):
			return "COMPLETE FAILED"
		return f"UNKNOWN (OK: {self.OK}, running: {self.running}, complete: {self.complete}, start: {datetime_to_str(self.date_start)}, end: {datetime_to_str(self.date_end)})"
	
	
	@property
	def result_html(self):
		if self.report is not None or len(self.report) != 0:
			# self._logger.debug("result_html: returning pre-generated report")
			return self.report.replace("\n", "<br>\n")
		return self.generate_report().replace("\n", "<br>\n")	
	
	
	@property
	def descr(self):
		# return f"Task {self._type}"
		return f"Task {self.__class__.__name__}"

		
	@property
	def duration(self):
		return (self.date_end - self.date_start).total_seconds() if self.date_start is not None and self.date_end is not None else 0.0
		
	
	@property
	def ETA_s(self):
		"""Estimated Time Arrival in seconds"""
		if self._prev_progress is None:
			self._prev_progress = 0.0
			self._prev_datetime = self.date_start
		curr_progress = self.progress
		curr_datetime = datetime.datetime.now()
		progress_speed = (curr_progress - self._prev_progress) / (curr_datetime - self._prev_datetime).total_seconds() # % in 1 second
		if progress_speed == 0.0:
			eta = self._prev_ETA_S
		else:
			eta = (1.0 - curr_progress) / progress_speed
			self._prev_ETA_S = eta
		self._prev_progress = curr_progress
		self._prev_datetime = curr_datetime
		# self._logger.debug(f"ETA: current eta: {eta} seconds")
		return eta
	
	
	@property
	def ETA_datetime(self):
		res = datetime.datetime.now() +  datetime.timedelta(seconds = self.ETA_s)
		# self._logger.debug(f"ETA_datetime: will return {res}")
		return res
	
	