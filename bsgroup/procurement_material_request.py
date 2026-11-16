"""Defer warehouse selection for draft sales handovers only.

The native v16 MaterialRequest.validate calls a module-level item validator,
which requires warehouses even on drafts. Keep its other checks, without
patching global ERPNext functions or inventing a receiving warehouse.
"""
from erpnext.buying import utils
from erpnext.controllers.buying_controller import BuyingController
from erpnext.controllers.status_updater import validate_status


def deferred_warehouse(doc):
    return (doc.docstatus == 0 and doc.material_request_type == "Purchase"
            and bool(doc.get("custom_bsp_managed"))
            and bool(doc.get("custom_bsp_source_snapshot"))
            and bool(doc.get("custom_bsp_quotation"))
            and bool(doc.get("custom_deal_cost_sheet")))


def validate_draft_items(doc):
    for row in doc.get("items"):
        utils.set_stock_levels(row=row)
        item = utils.validate_item_and_get_basic_data(row=row)
        if row.warehouse:
            utils.validate_stock_item_warehouse(row=row, item=item)
        utils.validate_end_of_life(row.item_code, item.end_of_life, item.disabled)
    utils.validate_duplicate_items(doc)


class SalesHandoverRequestMixin:
    def validate(self):
        if not deferred_warehouse(self):
            return super().validate()

        # Matched to ERPNext v16.55 MaterialRequest.validate (8e10a34).
        # Source snapshot integrity and access remain enforced by the existing
        # bsgroup.procurement.validate_mr document hook. Submission uses native
        # validation above and still requires a warehouse for stock items.
        self.clear_source_warehouse()
        self.validate_material_request_type()
        BuyingController.validate(self)
        self.validate_schedule_date()
        self.check_for_on_hold_or_closed_status("Sales Order", "sales_order")
        self.validate_with_previous_doc()
        self.validate_uom_is_integer("uom", "qty")
        self.validate_uom_is_integer("stock_uom", "stock_qty")
        if not self.status:
            self.status = "Draft"
        validate_status(self.status, ["Draft", "Submitted", "Stopped", "Cancelled",
                                     "Pending", "Partially Ordered", "Ordered",
                                     "Issued", "Transferred", "Received"])
        validate_draft_items(self)
        self.set_title()
        self.reset_default_field_value("set_warehouse", "items", "warehouse")
        self.reset_default_field_value("set_from_warehouse", "items", "from_warehouse")
        self.validate_pp_qty()
        self.set_buying_price_list()
