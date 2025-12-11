# Copyright (c) 2025, Sydney Kibanga and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.data import cint
from frappe.utils.nestedset import get_descendants_of


class StockTaker(Document):
	pass


@frappe.whitelist()
def get_items_by_groups(groups, include_child_groups: int = 1):
	"""Return item codes for the selected item groups."""
	if not groups:
		frappe.throw(_("Please select at least one Item Group."))

	if isinstance(groups, str):
		groups = frappe.parse_json(groups)

	selected_groups = set(groups)

	if cint(include_child_groups):
		for group in groups:
			for child in get_descendants_of("Item Group", group):
				selected_groups.add(child)

	items = frappe.get_all(
		"Item",
		filters={"item_group": ("in", list(selected_groups))},
		fields=["name"],
		limit=10000,
	)

	return [item.name for item in items]
