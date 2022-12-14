// 
// 



function edit_dir() {
	let full_path = document.getElementsByName("full_path")[0].value
	let full_path_encoded = encodeURIComponent(full_path)
	var is_etalon = false;
	if (document.getElementsByName("is_etalon")[0].checked == true) {
		is_etalon = true;
	}
	else {
		is_etalon = false;
	}
	var enabled = false;
	if (document.getElementsByName("enabled")[0].checked == true) {
		enabled = true;
	}
	else {
		enabled = false;
	}
	
	let comment = document.getElementsByName("comment")[0].value;
	let comment_encoded = encodeURIComponent(comment)
	console.log("full_path:", full_path, ", is_etalon:", is_etalon, ", comment:", comment, ", enabled:", enabled)
	
}
