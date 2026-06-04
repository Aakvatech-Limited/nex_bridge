# Copyright (c) 2025, Sydney Kibanga and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


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



