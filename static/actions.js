// actions
// author: Igor Martynov







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


function delete_files() {
	var arg_str = selected_files_to_args();
	if (confirm("Delete selected files?")) {
		document.location.href = "/api/delete-file?" + arg_str;
	}
	else {
		document.location.href = "/actions"
	}
}


function enable_dirs() {
	var arg_str = selected_dirs_to_args();
	document.location.href = "/api/enable-dirs?" + arg_str;
}


function disable_dirs() {
	var arg_str = selected_dirs_to_args();
	document.location.href = "/api/disable-dirs?" + arg_str;
}


