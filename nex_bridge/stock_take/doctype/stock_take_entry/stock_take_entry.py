# Copyright (c) 2025, Sydney Kibanga and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import (
    get_difference_account,
)


class StockTakeEntry(Document):
    def before_submit(self):
        self._resolve_items_from_barcodes()

    def _resolve_items_from_barcodes(self):
        """Populate missing item_code values from scanned barcodes before submit."""
        for row in self.items or []:
            if not row.warehouse and self.set_warehouse:
                row.warehouse = self.set_warehouse

            if row.qty is None:
                row.qty = 0

            if row.item_code:
                continue

            if not row.barcode:
                continue

            matches = frappe.get_all(
                "Item Barcode",
                filters={"barcode": row.barcode},
                fields=["parent"],
                limit=2,
            )

            if not matches:
                frappe.throw(
                    _("Row #{0}: No Item found for barcode {1}").format(
                        row.idx, frappe.bold(row.barcode)
                    )
                )

            if len(matches) > 1:
                frappe.throw(
                    _(
                        "Row #{0}: Multiple Items found for barcode {1}. Please set the Item Code."
                    ).format(row.idx, frappe.bold(row.barcode))
                )

            row.item_code = matches[0].parent
            row.item_name = frappe.db.get_value("Item", row.item_code, "item_name")


@frappe.whitelist()
def create_stock_reconciliation(stock_take_entry: str, purpose: str):
    doc = frappe.get_doc("Stock Take Entry", stock_take_entry)

    if doc.docstatus != 1:
        frappe.throw(
            _("Only submitted Stock Take Entries can create a Stock Reconciliation.")
        )

    purpose = (purpose or "").strip()
    purpose_map = {
        "Open Stock": "Opening Stock",
        "Opening Stock": "Opening Stock",
        "Reconcile": "Stock Reconciliation",
        "Stock Reconciliation": "Stock Reconciliation",
    }

    purpose_value = purpose_map.get(purpose)
    if not purpose_value:
        frappe.throw(_("Invalid purpose. Choose either Open Stock or Reconcile."))

    if not doc.items:
        frappe.throw(_("No items found on this Stock Take Entry."))

    difference_account = get_difference_account(purpose_value, doc.company)
    if not difference_account:
        frappe.throw(
            _(
                "Please set a Difference Account (For Opening or Stock Adjustment for Reconciliation) for company {0}."
            ).format(frappe.bold(doc.company))
        )

    stock_reco = frappe.new_doc("Stock Reconciliation")
    stock_reco.company = doc.company
    stock_reco.purpose = purpose_value
    stock_reco.posting_date = doc.posting_date
    stock_reco.posting_time = doc.posting_time
    stock_reco.set_posting_time = 1
    stock_reco.set_warehouse = doc.set_warehouse
    stock_reco.expense_account = difference_account

    for row in doc.items:
        if not row.item_code:
            frappe.throw(
                _(
                    "Row #{0}: Item Code is required to create a Stock Reconciliation."
                ).format(row.idx)
            )

        warehouse = row.warehouse or doc.set_warehouse
        if not warehouse:
            frappe.throw(
                _(
                    "Row #{0}: Please set a Warehouse on the row or Default Warehouse on the entry."
                ).format(row.idx)
            )

        stock_reco.append(
            "items",
            {
                "item_code": row.item_code,
                "warehouse": warehouse,
                "qty": row.qty or 0,
                "barcode": row.barcode,
                "allow_zero_valuation_rate": 1,
            },
        )

    stock_reco.insert()
    stock_reco.submit()

    return stock_reco.name
