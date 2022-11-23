// v0.4
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


function compare_dirs() {
	var selected_dirs_list = [];
	selected_dirs_list = get_selected_dirs();
	if (selected_dirs_list.length != 2) {
		alert("Only 2 dirs should be selected for this action");
	}
	else {
		var dir_a_id = selected_dirs_list[0];
		var dir_b_id = selected_dirs_list[1];
		document.location.href = "/api/compare-dirs?dir_a_id=" + dir_a_id + "&dir_b_id=" + dir_b_id;
	}
}


function delete_dirs() {
	var arg_str = selected_dirs_to_args();
	if (confirm("Delete selected dirs?")) {
		document.location.href = "/api/delete-dirs?" + arg_str;
	}
	else {
		document.location.href = "/actions"
	}
}


function check_dirs() {
	var arg_str = selected_dirs_to_args();
	document.location.href = "/api/check-dirs?" + arg_str;
}


function find_copies() {
	var arg_str = selected_dirs_to_args();
	document.location.href = "/api/find-copies?" + arg_str;
}

function split_dirs() {
	var arg_str = selected_dirs_to_args();
	document.location.href = "/api/split-dirs?" + arg_str;
}


function compile_dir() {
	var arg_str = selected_dirs_to_args();
	let prompt_dir = prompt("Plese enter path to new dir:");
	if (prompt_dir != null || prompt_dir != "") {
		path_to_new_dir_encoded = encodeURIComponent(prompt_dir);
		console.log("encoded dir path: " + path_to_new_dir_encoded)
		document.location.href = "/api/compile-dir?" + arg_str + "&new_dir=" + path_to_new_dir_encoded;
	}
	else {
		alert("Incorrect path to dir entered.")
	}
}

