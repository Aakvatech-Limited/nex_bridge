import json
import frappe


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
def sync_entry():
    api_call_type = frappe.form_dict.get("api_call_type")
    if api_call_type == "sync_bulk_entries":
        try:
            frappe.log_error(
                title="Sync Bulk Entries Started",
                message=f"Full Data: {frappe.request.data}",
            )

            data = json.loads(frappe.request.data)
            entries = data.get("entries", [])
            synced_entries = []

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

                frappe.log_error(
                    "Processing Entry", f"Processing entry with local_id {local_id}"
                )

                try:
                    existing_entry = frappe.get_all(
                        "Stock Take Entry",
                        filters={"local_id": local_id},
                        fields=["name"],
                    )
                    if existing_entry:
                        doc = frappe.get_doc("Stock Take Entry", existing_entry[0].name)
                        doc.company = company
                        doc.set_warehouse = set_warehouse
                        doc.posting_date = posting_date
                        doc.posting_time = posting_time
                        doc.scan_mode = scan_mode
                    else:
                        doc = frappe.get_doc(
                            {
                                "doctype": "Stock Take Entry",
                                "company": company,
                                "set_warehouse": set_warehouse,
                                "posting_date": posting_date,
                                "posting_time": posting_time,
                                "scan_mode": scan_mode,
                                "local_id": local_id,
                                "items": [],
                            }
                        )

                    for item in entry_items:
                        barcode = (item.get("barcode") or "").strip()
                        item_code = (item.get("item_code") or "").strip()
                        item_name = None
                        warehouse = item.get("warehouse")
                        qty = item.get("qty")
                        local_item_id = item.get("local_id")

                        if barcode and not item_code:
                            item_code = frappe.db.get_value(
                                "Item Barcode", {"barcode": barcode}, "parent"
                            )
                            if item_code:
                                item_name = frappe.db.get_value(
                                    "Item", item_code, "item_name"
                                )
                                barcode = ""
                        elif item_code:
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
                            existing_item.warehouse = warehouse
                            existing_item.qty = qty
                        else:
                            doc.append(
                                "items",
                                {
                                    "barcode": barcode,
                                    "item_code": item_code or None,
                                    "item_name": item_name,
                                    "warehouse": warehouse,
                                    "qty": qty,
                                    "local_id": local_item_id,
                                },
                            )

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
                    frappe.log_error(
                        f"Failed to process entry with local_id {local_id}", str(e)
                    )
                    continue

            frappe.db.commit()

            frappe.response["message"] = {
                "status": "success",
                "message": "Bulk entries synced successfully",
                "synced_entries": synced_entries or [],
            }

        except Exception as e:
            frappe.log_error("Exception during bulk sync", str(e))
            frappe.response["message"] = {"status": "error", "message": str(e)}

    elif api_call_type == "get_entries":
        try:
            auth_user = frappe.session.user

            entries = frappe.get_all(
                "Stock Take Entry",
                filters={"owner": auth_user},
                fields=[
                    "name",
                    "company",
                    "set_warehouse",
                    "posting_date",
                    "posting_time",
                    "local_id",
                    "owner",
                ],
            )

            for entry in entries:
                entry_items = frappe.get_all(
                    "Stock Take Entry Item",
                    filters={"parent": entry["name"]},
                    fields=[
                        "name",
                        "barcode",
                        "warehouse",
                        "qty",
                        "current_qty",
                        "local_id",
                        "owner",
                    ],
                )
                entry["items"] = entry_items

            frappe.log_error(f"entries", str(entries))

            frappe.response["message"] = {"entries": entries}

        except Exception as e:
            frappe.log_error(f"e", str(e))

            frappe.response["message"] = {"status": "error", "message": str(e)}

    else:

        frappe.response["message"] = {
            "status": "error",
            "message": "Invalid API call type",
        }
