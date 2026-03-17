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
        """Populate missing item_code values from scanned reference before submit."""
        for row in self.items or []:
            if not row.warehouse and self.set_warehouse:
                row.warehouse = self.set_warehouse

            if row.qty is None:
                row.qty = 0

            mode = (getattr(row, "scan_reference_mode", None) or self.scan_reference_mode or "").strip()
            scan_value = (
                getattr(row, "scan_value", None)
                or row.barcode
                or row.item_code
                or getattr(row, "batch_no", None)
                or getattr(row, "serial_no", None)
                or ""
            ).strip()

            if hasattr(row, "scan_value") and not row.scan_value:
                row.scan_value = scan_value

            if row.item_code:
                continue

            if mode == "Item Code":
                item_code = scan_value
                if not item_code or not frappe.db.exists("Item", item_code):
                    frappe.throw(
                        _("Row #{0}: Item Code {1} not found.").format(
                            row.idx, frappe.bold(scan_value or "")
                        )
                    )
                row.item_code = item_code
                row.item_name = frappe.db.get_value("Item", row.item_code, "item_name")
                row.barcode = ""
                continue

            if mode == "Batch No":
                batch_no = getattr(row, "batch_no", None) or scan_value
                item_code = frappe.db.get_value("Batch", batch_no, "item") if batch_no else None
                if not item_code:
                    frappe.throw(
                        _("Row #{0}: Batch {1} was not found.").format(
                            row.idx, frappe.bold(batch_no or "")
                        )
                    )
                row.batch_no = batch_no
                row.item_code = item_code
                row.item_name = frappe.db.get_value("Item", row.item_code, "item_name")
                row.barcode = ""
                continue

            if mode == "Serial No":
                serial_no = getattr(row, "serial_no", None) or scan_value
                serial_data = (
                    frappe.db.get_value(
                        "Serial No",
                        serial_no,
                        ["item_code", "batch_no"],
                        as_dict=True,
                    )
                    if serial_no
                    else None
                )
                if not serial_data or not serial_data.get("item_code"):
                    frappe.throw(
                        _("Row #{0}: Serial No {1} was not found.").format(
                            row.idx, frappe.bold(serial_no or "")
                        )
                    )
                row.serial_no = serial_no
                if hasattr(row, "batch_no") and not row.batch_no:
                    row.batch_no = serial_data.get("batch_no")
                row.item_code = serial_data.get("item_code")
                row.item_name = frappe.db.get_value("Item", row.item_code, "item_name")
                row.barcode = ""
                continue

            if not row.barcode:
                continue

            if frappe.db.exists("Item", row.barcode):
                row.item_code = row.barcode
                row.item_name = frappe.db.get_value("Item", row.item_code, "item_name")
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

        batch_no = row.batch_no
        serial_no = row.serial_no
        qty = row.qty or 0

        stock_reco.append(
            "items",
            {
                "item_code": row.item_code,
                "warehouse": warehouse,
                "qty": qty,
                "barcode": row.barcode,
                "batch_no": batch_no,
                "serial_no": serial_no,
                "use_serial_batch_fields": 1 if batch_no or serial_no else 0,
                "allow_zero_valuation_rate": 1,
            },
        )

    stock_reco.flags.ignore_validate = True
    stock_reco.insert()
    doc.db_set("stock_reconciliation", stock_reco.name, update_modified=False)

    return stock_reco.name
