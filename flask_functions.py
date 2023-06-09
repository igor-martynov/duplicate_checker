#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 

import urllib

def get_path_to_new_dirs_from_request(request):
	path_to_new_dirs_list = [normalize_path_to_dir(d) for d in request.args.getlist("path_to_new_dir")]
	return path_to_new_dirs_list


def get_full_path_from_request(request):
	return normalize_path_to_dir(request.args.get("full_path"))


def get_is_etalon_from_request(request):
	return True if request.args.get("is_etalon") == "1" else False


def get_enabled_from_request(request):
	return True if request.args.get("enabled") == "1" else False


def get_comment_from_request(request):
	return request.args.get("comment")


def get_add_options_for_new_dirs_from_request(request):
	is_etalon = True if request.args.get("is_etalon") == "1" else False
	add_subdirs = True if request.args.get("add_subdirs") == "1" else False
	return (is_etalon, add_subdirs)


def get_dir_objects_from_request(request, get_by_id = None):
	dirs_list = []
	dir_ids_list = request.args.getlist("dir_id")
	for dir_id in dir_ids_list:
		dir_obj = get_by_id(dir_id)
		if dir_obj is not None:
			dirs_list.append(dir_obj)
		else:
			pass
	return dirs_list


def get_task_objects_from_request(request, get_by_id = None):
	tasks_list = []
	task_ids_list = request.args.getlist("task_id")
	for task_id in task_ids_list:
		task_obj = get_by_id(task_id)
		if task_obj is not None:
			tasks_list.append(task_obj)
		else:
			pass
	return tasks_list


def get_dir_objects_and_new_dir_from_request(request, get_by_id = None):
	dirs_list = get_dir_objects_from_request(request, get_by_id = get_by_id)
	path_to_new_dir = urllib.parse.unquote(request.args.get("new_dir"))
	return dirs_list, path_to_new_dir


def get_file_objects_from_request(request, get_by_id = None):
	files_list = []
	file_ids_list = request.args.getlist("file_id")
	for file_id in file_ids_list:
		file_obj = get_by_id(file_id)
		if file_obj is not None:
			files_list.append(file_obj)
		else:
			pass
	return files_list


def get_dir_dict_from_request(request):
	#id
	_id = request.args.get("dir_id")
	full_path = urllib.parse.unquote(request.args.get("full_path"))
	is_etalon = True if request.args.get("is_etalon") == "1" else False
	enabled = True if request.args.get("enabled") == "1" else False
	# date_added = request.args.get("")
	# date_checked = request.args.get("")
	# name = request.args.get("")
	comment = urllib.parse.unquote(request.args.get("comment"))
	# deleted = request.args.get("")
	drive = urllib.parse.unquote(request.args.get("drive")) if request.args.get("drive") is not None else None
	host = urllib.parse.unquote(request.args.get("host")) if request.args.get("host") is not None else None
	files_id_list = request.args.getlist("file_id")
	res = {"id": _id, "full_path": full_path, "is_etalon": is_etalon, "enabled": enabled, "comment": comment, "drive": drive, "host": host, "file_ids": files_id_list}
	return res





