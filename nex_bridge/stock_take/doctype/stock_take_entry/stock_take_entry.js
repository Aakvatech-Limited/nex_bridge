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

	refresh(frm) {
		frm.clear_custom_buttons();
		if (frm.doc.docstatus !== 1) return;
		if (frm.doc.stock_reconciliation) return;

		frm.add_custom_button(__('Create Stock Reconciliation'), () => {
			frappe.prompt(
				[
					{
						label: __('What do you want to do?'),
						fieldname: 'purpose',
						fieldtype: 'Select',
						options: [
							{ label: __('Open Stock'), value: 'Opening Stock' },
							{ label: __('Reconcile'), value: 'Stock Reconciliation' },
						],
						default: 'Stock Reconciliation',
						reqd: 1,
					},
				],
				(values) => {
					frappe.call({
						method: 'nex_bridge.stock_take.doctype.stock_take_entry.stock_take_entry.create_stock_reconciliation',
						args: {
							stock_take_entry: frm.doc.name,
							purpose: values.purpose,
						},
						freeze: true,
						freeze_message: __('Creating Stock Reconciliation...'),
						callback: (r) => {
							if (!r.message) return;

							frm.set_value('stock_reconciliation', r.message);
							frm.clear_custom_buttons();

							frappe.msgprint({
								message: __('Stock Reconciliation {0} created.', [r.message]),
								indicator: 'green',
							});

							frappe.set_route('Form', 'Stock Reconciliation', r.message);
						},
					});
				},
				__('Create Stock Reconciliation'),
				__('Create'),
			);
		});
	},
});
