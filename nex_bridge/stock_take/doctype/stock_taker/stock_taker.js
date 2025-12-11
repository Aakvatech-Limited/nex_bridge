// Copyright (c) 2025, Sydney Kibanga and contributors
// For license information, please see license.txt

frappe.ui.form.on('Stock Taker', {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__('Add Items by Group'), () => {
			new frappe.ui.form.MultiSelectDialog({
				doctype: 'Item Group',
				target: frm,
				get_query: () => ({ filters: {} }),
				primary_action_label: __('Add Items'),
				action: (groups) => {
					if (!groups || !groups.length) return;

					frappe.call({
						method: 'nex_bridge.stock_take.doctype.stock_taker.stock_taker.get_items_by_groups',
						args: { groups, include_child_groups: 1 },
						freeze: true,
						freeze_message: __('Fetching items...'),
						callback: (r) => {
							const items = r.message || [];
							if (!items.length) {
								frappe.msgprint(__('No items found for the selected groups.'));
								return;
							}

							const existing = new Set((frm.doc.assigned_items || []).map((row) => row.item));

							items.forEach((item_code) => {
								if (existing.has(item_code)) return;
								existing.add(item_code);
								const child = frm.add_child('assigned_items');
								child.item = item_code;
							});

							frm.refresh_field('assigned_items');
							frappe.msgprint(
								__('Added {0} items from selected groups.', [items.length])
							);
						},
					});
				},
			});
		});
	},
});
