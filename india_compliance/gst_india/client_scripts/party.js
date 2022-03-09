let addresses;
erpnext.setup_gst_reminder_button = (doctype) => {
	frappe.ui.form.on(doctype, {
		refresh: (frm) => {
			if(!frm.is_new()) {
				var missing = false;
				frm.doc.__onload.addr_list && frm.doc.__onload.addr_list.forEach((d) => {
					if(!d.gstin) missing = true;
				});
				if (!missing) return;

				frm.add_custom_button('Send GST Update Reminder', () => {
					return new Promise((resolve) => {
						return frappe.call({
							method: 'india_compliance.gst_india.doctype.gst_settings.gst_settings.send_gstin_reminder',
							args: {
								party_type: frm.doc.doctype,
								party: frm.doc.name,
							}
						}).always(() => { resolve(); });
					});
				});
			}
		},
		gstin: function(frm){
			console.log("yes")
			frappe.call({
				'method': 'india_compliance.gst_india.overrides.party.get_linked_addresses',
				'args':{
					'party_type': frm.doc.doctype,
					'party': frm.doc.name,
				},
				'callback': function(r) {
					console.log(r.message);
					debugger;
					addresses = r.message;
				}
			});
		},
		validate: function(frm) {
			if (frm.doc.gstin) {
				let update_all, multiple_address;
				if (addresses[0]) {
					frappe.confirm('We shall update all linked records also, Proceed?',
					() => {
						console.log(addresses);
						let msg = "Addresses and linked doctypes updated successfully";
						update_gstin(frm, addresses, msg, update_all=1, multiple_address=1)
					}, 
					() => {
						// action to perform if No is selected
						let msg = "GSTIN in Addresses updated successfully";
						update_gstin(frm, addresses, msg, update_all=0, multiple_address=1)
					})
				}
				else {
					let msg = "GSTIN in Addresses updated successfully";
					update_gstin(frm, addresses, msg, update_all=0, multiple_address=0)
				}
			}
		}
	});
};

var update_gstin = function(frm, addresses, msg, update_all=0, multiple_address=0) {
	frappe.call({
		'method': 'india_compliance.gst_india.overrides.party.update_gstin',
		'args': {
			'gstin': frm.doc.gstin,
			'gst_category': frm.doc.gst_category,
			'addresses': addresses[1],
			'update_all': update_all,
			'multiple_address': multiple_address
		},
		'callback': function(r) {
			if (r.message) {
				frappe.msgprint(msg)
			}
			else {
				frappe.msgprint("No chanege in current doc")
			}
		}
	});
}