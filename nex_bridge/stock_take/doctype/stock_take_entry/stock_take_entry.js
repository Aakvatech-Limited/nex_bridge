// Copyright (c) 2025, Sydney Kibanga and contributors
// For license information, please see license.txt

frappe.ui.form.on('Stock Take Entry', {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

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

							frappe.msgprint({
								message: __('Stock Reconciliation {0} created and submitted.', [r.message]),
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
