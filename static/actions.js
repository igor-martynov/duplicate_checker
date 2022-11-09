// v0.3

function get_selected_dirs(){
	var all_list = [];
	var checked_id_list = [];
	all_list = document.querySelectorAll(".dir_checkbox");
	for (var i = 0; i < all_list.length; i++) {
		if (all_list[i].checked == true) {
			checked_id_list.push(all_list[i].value.replace("dir_id_", ""));
		}
	}
	console.log("checked_id_list", checked_id_list);
	return checked_id_list;
}


function selected_dirs_to_args() {
	var selected_dirs_list = [];
	selected_dirs_list = get_selected_dirs();
	console.log(selected_dirs_list);
	var arg_str = "";
	for (var d = 0; d < selected_dirs_list.length; d++) {
		arg_str = arg_str + "dir_id=" + selected_dirs_list[d] + "&"
	}
	console.log(arg_str);
	return arg_str;
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
		console.log(dir_a_id);
		console.log(dir_b_id);
	}
}


function delete_dirs() {
	var arg_str = selected_dirs_to_args();
	document.location.href = "/api/delete-dirs?" + arg_str;
}


function check_dirs() {
	var arg_str = selected_dirs_to_args();
	document.location.href = "/api/check-dirs?" + arg_str;
}


function find_copies() {
	var arg_str = selected_dirs_to_args();
	document.location.href = "/api/find-copies?" + arg_str;
}


