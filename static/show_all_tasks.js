// 
// 

console.log("loaded JS show_all_tasks");

function get_current_status() {
	const URL = "/api/get_running_task_to_js"
	const RELOAD_DELAY = 2
	
	while (true) {
		let response = fetch(URL);
		console.log(response.status);
		let task_obj = response.json;
		console.log(task_obj);
		sleep(RELOAD_DELAY);
	};
};

window.onload = get_current_status;

