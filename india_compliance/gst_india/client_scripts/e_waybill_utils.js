function trigger_file_download(file_content, file_name) {
    let type = "application/json;charset=utf-8";

    if (!file_name.endsWith(".json")) {
        type = "application/octet-stream";
    }

    const blob = new Blob([file_content], { type: type });

    // Create a link and set the URL using `createObjectURL`
    const link = document.createElement("a");
    link.style.display = "none";
    link.href = URL.createObjectURL(blob);
    link.download = file_name;

    // It needs to be added to the DOM so it can be clicked
    document.body.appendChild(link);
    link.click();

    // To make this work on Firefox we need to wait
    // a little while before removing it.
    setTimeout(() => {
        URL.revokeObjectURL(link.href);
        link.parentNode.removeChild(link);
    }, 0);
}


function get_e_waybill_file_name(docname) {
    let prefix = "Bulk";
    if (docname) {
        prefix = docname.replaceAll(/[^\w_.)( -]/g, "");
    }

    return `${prefix}_e-Waybill_Data_${frappe.utils.get_random(5)}.json`;
}
