// Copyright (c) 2025, Sydney Kibanga and contributors
// For license information, please see license.txt

frappe.ui.form.on('Stock Take Entry', {
	setup(frm) {
		frm.set_query('batch_no', 'items', (doc, cdt, cdn) => {
			const row = locals[cdt][cdn] || {};
			const filters = {};
			if (row.item_code) filters.item = row.item_code;
			return { filters };
		});

		frm.set_query('serial_no', 'items', (doc, cdt, cdn) => {
			const row = locals[cdt][cdn] || {};
			const filters = {};
			if (row.item_code) filters.item_code = row.item_code;
			if (row.warehouse || doc.set_warehouse) {
				filters.warehouse = row.warehouse || doc.set_warehouse;
			}
			return { filters };
		});
	},

});
