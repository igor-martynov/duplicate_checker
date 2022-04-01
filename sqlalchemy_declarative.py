#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os

# logging
import logging
import logging.handlers

# SQL Alchemy
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine


DeclarativeBase = declarative_base()



class Directory(DeclarativeBase):
	"""Directory class"""
	
	__tablename__ = "dirs"
	id = Column(Integer, primary_key = True)
	is_etalon = Column(Boolean, nullable = False)
	date_added = Column(DateTime, nullable = False)
	date_checked = Column(DateTime, nullable = False)
	name = Column(String, nullable = False)
	full_path = Column(String, nullable = False)
	comment = Column(String, nullable = True)
	deleted = Column(Boolean, nullable = False, default = False)
	enabled = Column(Boolean, nullable = False, default = True)
	drive = Column(String, nullable = True)
	host = Column(String, nullable = True)
	files = relationship("File", back_populates = "dir")
	


class File(DeclarativeBase):
	"""File class"""
	
	__tablename__ = "files"
	id = Column(Integer, primary_key = True)
	is_etalon = Column(Boolean, nullable = False)
	date_added = Column(DateTime, nullable = False)
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

