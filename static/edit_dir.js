// 
// 



function edit_dir() {
	var urlList = window.location.href.split("/")
	var dir_id = urlList[urlList.length - 1]
	let full_path = document.getElementsByName("full_path")[0].value
	let full_path_encoded = encodeURIComponent(full_path)
	var is_etalon_num = 0;
	if (document.getElementsByName("is_etalon")[0].checked == true) {
		is_etalon_num = 1;
	}
	else {
		is_etalon_num = 0;
	}
	var enabled_num = 1;
	if (document.getElementsByName("enabled")[0].checked == true) {
		enabled_num = 1;
	}
	else {
		enabled_num = 0;
	}	
	let comment = document.getElementsByName("comment")[0].value;
	let comment_encoded = encodeURIComponent(comment)
	console.log("full_path:", full_path, ", is_etalon:", is_etalon_num, ", comment:", comment, ", enabled:", enabled_num)
	document.location.href = "/api/edit-dir?dir_id=" + dir_id + "&full_path=" + full_path_encoded + "&is_etalon=" + is_etalon_num + "&enabled=" + enabled_num + "&comment=" + comment_encoded
}
