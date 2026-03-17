import json
import frappe


def _get_assigned_item_codes(user_email):
    stock_taker_records = frappe.db.get_list(
        "Stock Taker",
        filters={"stock_taker": user_email},
        fields=["name"],
        limit=1000,
    )

    item_codes = set()
    for record in stock_taker_records:
        items = frappe.get_all(
            "Stock Taker Item",
            filters={"parent": record["name"]},
            fields=["item"],
        )
        for row in items:
            item_code = (row.get("item") or "").strip()
            if item_code:
                item_codes.add(item_code)

    return sorted(item_codes)


@frappe.whitelist()
def get_warehouses_grouped_by_company():
    # Ensure the user is authenticated
    user_email = frappe.session.user
    if not user_email or user_email == "Guest":
        frappe.response["message"] = "User must be logged in to access this resource."
        return

    warehouses = frappe.db.get_list("Warehouse", fields=["name", "company"], limit=1000)

    if not warehouses:
        frappe.response["message"] = "No warehouses found."
        return

    companies = frappe.db.get_list("Company", fields=["name"], limit=1000)

    if not companies:
        frappe.response["message"] = "No companies found."
        return

    company_warehouse_map = {}
    for wh in warehouses:
        company = wh.get("company")
        warehouse_name = wh.get("name")
        if company not in company_warehouse_map:
            company_warehouse_map[company] = []
        company_warehouse_map[company].append(warehouse_name)

    frappe.response["message"] = {
        "warehouses_by_company": company_warehouse_map,
        "companies": [comp.get("name") for comp in companies],
    }


@frappe.whitelist()
def get_user_assigned_items():
    user_email = frappe.session.user
    if not user_email or user_email == "Guest":
        frappe.response["message"] = "User must be logged in to access this resource."
        return

    stock_taker_records = frappe.db.get_list(
        "Stock Taker",
        filters={"stock_taker": user_email},
        fields=["name", "stock_taker"],
        limit=1000,
    )

    if not stock_taker_records:
        frappe.response["message"] = "No assigned items found for this user."
        return

    assigned_items = []
    for record in stock_taker_records:
        items = frappe.get_all(
            "Stock Taker Item",
            filters={"parent": record["name"]},
            fields=["name", "item"],
        )
        assigned_items.extend(items)

    frappe.response["message"] = {"assigned_items": assigned_items}


@frappe.whitelist()
def get_scan_reference_masters():
    user_email = frappe.session.user
    if not user_email or user_email == "Guest":
        frappe.response["message"] = "User must be logged in to access this resource."
        return

    item_codes = _get_assigned_item_codes(user_email)
    if not item_codes:
        frappe.response["message"] = {
            "items": [],
            "barcodes": [],
            "batches": [],
            "serial_nos": [],
        }
        return

    items = frappe.get_all(
        "Item",
        filters={"name": ["in", item_codes]},
        fields=["name as item_code", "item_name", "has_serial_no", "has_batch_no"],
        limit=5000,
    )

    barcodes = frappe.get_all(
        "Item Barcode",
        filters={"parent": ["in", item_codes]},
        fields=["parent as item_code", "barcode"],
        limit=20000,
    )

    batch_filters = {"item": ["in", item_codes]}
    if frappe.get_meta("Batch").has_field("disabled"):
        batch_filters["disabled"] = 0

    batches = frappe.get_all(
        "Batch",
        filters=batch_filters,
        fields=["name as batch_no", "item as item_code"],
        limit=20000,
    )

    serial_filters = {"item_code": ["in", item_codes]}
    if frappe.get_meta("Serial No").has_field("status"):
        serial_filters["status"] = ["!=", "Inactive"]

    serial_nos = frappe.get_all(
        "Serial No",
        filters=serial_filters,
        fields=["name as serial_no", "item_code", "batch_no"],
        limit=50000,
    )

    frappe.response["message"] = {
        "items": items,
        "barcodes": barcodes,
        "batches": batches,
        "serial_nos": serial_nos,
    }


@frappe.whitelist()
def sync_entry():
    request_payload = {}
    if frappe.request and frappe.request.data:
        try:
            request_payload = json.loads(frappe.request.data)
        except Exception:
            request_payload = {}

    api_call_type = frappe.form_dict.get("api_call_type") or request_payload.get(
        "api_call_type"
    )
    if api_call_type == "sync_bulk_entries":
        try:
            data = request_payload or {}
            entries = data.get("entries", [])
            synced_entries = []
            failed_entries = []
            has_scan_reference_mode = frappe.get_meta("Stock Take Entry").has_field(
                "scan_reference_mode"
            )
            entry_item_meta = frappe.get_meta("Stock Take Entry Item")
            has_item_scan_reference_mode = entry_item_meta.has_field(
                "scan_reference_mode"
            )
            has_scan_value = entry_item_meta.has_field("scan_value")
            has_batch_no = entry_item_meta.has_field("batch_no")
            has_serial_no = entry_item_meta.has_field("serial_no")
            current_user = frappe.session.user

            if not entries:
                frappe.log_error("Sync Bulk Entries Error", "No entries to sync")
                frappe.response["message"] = {
                    "status": "error",
                    "message": "No entries to sync",
                }
                return

            for entry_data in entries:
                entry = entry_data.get("entry")
                entry_items = entry_data.get("entry_items")

                local_id = entry.get("local_id")
                company = entry.get("company")
                set_warehouse = entry.get("set_warehouse")
                posting_date = entry.get("posting_date")
                posting_time = entry.get("posting_time")
                scan_mode = entry.get("scan_mode", 0)
                scan_reference_mode = (entry.get("scan_reference_mode") or "").strip()

                try:
                    existing_entry = frappe.get_all(
                        "Stock Take Entry",
                        filters={
                            "local_id": local_id,
                            "owner": current_user,
                            "docstatus": 0,
                        },
                        fields=["name"],
                        order_by="creation desc",
                        limit=1,
                    )
                    if existing_entry:
                        doc = frappe.get_doc("Stock Take Entry", existing_entry[0].name)
                        doc.company = company
                        doc.set_warehouse = set_warehouse
                        doc.posting_date = posting_date
                        doc.posting_time = posting_time
                        doc.scan_mode = scan_mode
                        if has_scan_reference_mode:
                            doc.scan_reference_mode = scan_reference_mode
                    else:
                        payload = {
                            "doctype": "Stock Take Entry",
                            "company": company,
                            "set_warehouse": set_warehouse,
                            "posting_date": posting_date,
                            "posting_time": posting_time,
                            "scan_mode": scan_mode,
                            "local_id": local_id,
                            "items": [],
                        }
                        if has_scan_reference_mode:
                            payload["scan_reference_mode"] = scan_reference_mode
                        doc = frappe.get_doc(payload)

                    for item in entry_items:
                        item_scan_reference_mode = (
                            item.get("scan_reference_mode") or scan_reference_mode or ""
                        ).strip()
                        scan_value = (item.get("scan_value") or "").strip()
                        barcode = (item.get("barcode") or "").strip()
                        item_code = (item.get("item_code") or "").strip()
                        batch_no = (item.get("batch_no") or "").strip()
                        serial_no = (item.get("serial_no") or "").strip()
                        item_name = None
                        warehouse = item.get("warehouse")
                        qty = item.get("qty")
                        local_item_id = item.get("local_id")

                        if not scan_value:
                            if item_scan_reference_mode == "Item Code":
                                scan_value = item_code or barcode
                            elif item_scan_reference_mode == "Batch No":
                                scan_value = batch_no or barcode
                            elif item_scan_reference_mode == "Serial No":
                                scan_value = serial_no or barcode
                            else:
                                scan_value = barcode or item_code or batch_no or serial_no

                        if item_scan_reference_mode == "Item Code":
                            if not item_code and scan_value:
                                item_code = scan_value
                            barcode = ""
                        elif item_scan_reference_mode == "Batch No":
                            if not batch_no and scan_value:
                                batch_no = scan_value
                            if batch_no and not item_code:
                                item_code = frappe.db.get_value("Batch", batch_no, "item")
                            barcode = ""
                        elif item_scan_reference_mode == "Serial No":
                            if not serial_no and scan_value:
                                serial_no = scan_value
                            if serial_no:
                                serial_data = frappe.db.get_value(
                                    "Serial No",
                                    serial_no,
                                    ["item_code", "batch_no"],
                                    as_dict=True,
                                )
                                if serial_data:
                                    if not item_code:
                                        item_code = serial_data.get("item_code")
                                    if not batch_no:
                                        batch_no = serial_data.get("batch_no")
                            barcode = ""
                        elif barcode and not item_code:
                            item_code = frappe.db.get_value(
                                "Item Barcode", {"barcode": barcode}, "parent"
                            )
                            if item_code:
                                barcode = ""
                            elif frappe.db.exists("Item", barcode):
                                # Assigned items from mobile can come as Item Code.
                                item_code = barcode
                                barcode = ""

                        if item_code:
                            item_name = frappe.db.get_value(
                                "Item", item_code, "item_name"
                            )

                        existing_item = None
                        for existing in doc.items:
                            if existing.local_id == local_item_id:
                                existing_item = existing
                                break

                        if existing_item:
                            existing_item.barcode = barcode
                            if item_code:
                                existing_item.item_code = item_code
                            if item_name:
                                existing_item.item_name = item_name
                            if has_item_scan_reference_mode:
                                existing_item.scan_reference_mode = (
                                    item_scan_reference_mode
                                )
                            if has_scan_value:
                                existing_item.scan_value = scan_value
                            if has_batch_no:
                                existing_item.batch_no = batch_no
                            if has_serial_no:
                                existing_item.serial_no = serial_no
                            existing_item.warehouse = warehouse
                            existing_item.qty = qty
                        else:
                            item_payload = {
                                "barcode": barcode,
                                "item_code": item_code or None,
                                "item_name": item_name,
                                "warehouse": warehouse,
                                "qty": qty,
                                "local_id": local_item_id,
                            }
                            if has_item_scan_reference_mode:
                                item_payload["scan_reference_mode"] = (
                                    item_scan_reference_mode
                                )
                            if has_scan_value:
                                item_payload["scan_value"] = scan_value
                            if has_batch_no:
                                item_payload["batch_no"] = batch_no
                            if has_serial_no:
                                item_payload["serial_no"] = serial_no
                            doc.append("items", item_payload)

                    if existing_entry:
                        doc.save()
                    else:
                        doc.insert(ignore_permissions=True)

                    synced_entry = {
                        "local_id": local_id,
                        "server_id": doc.name,
                        "items": [],
                    }

                    for item in doc.items:
                        if item.local_id in [i["local_id"] for i in entry_items]:
                            synced_entry["items"].append(
                                {
                                    "local_id": item.local_id,
                                    "server_id": item.name,
                                }
                            )

                    synced_entries.append(synced_entry)

                except Exception as e:
                    failed_entries.append({"local_id": local_id, "error": str(e)})
                    frappe.log_error(
                        f"Failed to process entry with local_id {local_id}", str(e)
                    )
                    continue

            frappe.db.commit()

            status = "success"
            message = "Bulk entries synced successfully"
            if failed_entries and synced_entries:
                status = "partial_success"
                message = (
                    f"Synced {len(synced_entries)} entries and failed {len(failed_entries)} entries"
                )
            elif failed_entries and not synced_entries:
                status = "error"
                message = "No entries were synced"

            frappe.response["message"] = {
                "status": status,
                "message": message,
                "synced_entries": synced_entries or [],
                "failed_entries": failed_entries or [],
            }

        except Exception as e:
            frappe.log_error("Exception during bulk sync", str(e))
            frappe.response["message"] = {"status": "error", "message": str(e)}

    elif api_call_type == "get_entries":
        try:
            auth_user = frappe.session.user
            has_scan_reference_mode = frappe.get_meta("Stock Take Entry").has_field(
                "scan_reference_mode"
            )
            entry_fields = [
                "name",
                "company",
                "set_warehouse",
                "posting_date",
                "posting_time",
                "scan_mode",
                "local_id",
                "owner",
            ]
            if has_scan_reference_mode:
                entry_fields.append("scan_reference_mode")

            entries = frappe.get_all(
                "Stock Take Entry",
                filters={"owner": auth_user},
                fields=entry_fields,
            )

            for entry in entries:
                entry_item_fields = [
                    "name",
                    "barcode",
                    "item_code",
                    "item_name",
                    "warehouse",
                    "qty",
                    "current_qty",
                    "local_id",
                    "owner",
                ]
                entry_item_meta = frappe.get_meta("Stock Take Entry Item")
                if entry_item_meta.has_field("scan_reference_mode"):
                    entry_item_fields.append("scan_reference_mode")
                if entry_item_meta.has_field("scan_value"):
                    entry_item_fields.append("scan_value")
                if entry_item_meta.has_field("batch_no"):
                    entry_item_fields.append("batch_no")
                if entry_item_meta.has_field("serial_no"):
                    entry_item_fields.append("serial_no")

                entry_items = frappe.get_all(
                    "Stock Take Entry Item",
                    filters={"parent": entry["name"]},
                    fields=entry_item_fields,
                )
                entry["items"] = entry_items

            frappe.response["message"] = {"entries": entries}

        except Exception as e:
            frappe.log_error("Error fetching sync entries", str(e))
            frappe.response["message"] = {"status": "error", "message": str(e)}

    else:

        frappe.response["message"] = {
            "status": "error",
            "message": "Invalid API call type",
        }
