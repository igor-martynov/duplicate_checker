// actions
// author: Igor Martynov


function get_selected_dirs(){
	var all_list = [];
	var checked_id_list = [];
	all_list = document.querySelectorAll(".dir_checkbox");
	for (var i = 0; i < all_list.length; i++) {
		if (all_list[i].checked == true) {
			checked_id_list.push(all_list[i].value.replace("dir_id_", ""));
		}
	}
	return checked_id_list;
}

function selected_dirs_to_args() {
	var selected_dirs_list = [];
	selected_dirs_list = get_selected_dirs();
	var arg_str = "";
	for (var d = 0; d < selected_dirs_list.length; d++) {
		if (d < (selected_dirs_list.length - 1)) {
			arg_str = arg_str + "dir_id=" + selected_dirs_list[d] + "&"
		}
		else {
			arg_str = arg_str + "dir_id=" + selected_dirs_list[d]
		}
	}
	return arg_str;
}


function get_selected_files() {
	var all_list = [];
	var checked_id_list = [];
	all_list = document.querySelectorAll(".file_checkbox");
	for (var i = 0; i < all_list.length; i++) {
		if (all_list[i].checked == true) {
			checked_id_list.push(all_list[i].value.replace("file_id_", ""));
		}
	}
	return checked_id_list;	
}


function selected_files_to_args() {
	var selected_files_list = [];
	selected_dirs_list = get_selected_files();
	var arg_str = "";
	for (var f = 0; f < selected_files_list.length; f++) {
		if (f < (selected_files_list.length - 1)) {
			arg_str = arg_str + "file_id=" + selected_files_list[f] + "&"
		}
		else {
			arg_str = arg_str + "file_id=" + selected_files_list[f]
		}
	}
	return arg_str;
}
