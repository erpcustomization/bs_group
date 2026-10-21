/* Keep withdrawn BS drafts visible as audit records, out of the active default list. */
(() => {
  const settings=frappe.listview_settings["Purchase Order"]||{};
  const previous=settings.get_indicator;
  settings.add_fields=[...new Set([...(settings.add_fields||[]),"custom_bsp_managed","custom_bsp_approval_state"])];
  settings.filters=[...(settings.filters||[]),["custom_bsp_approval_state","!=","Cancelled"]];
  settings.get_indicator=function(doc){
    if(doc.custom_bsp_managed&&doc.custom_bsp_approval_state==="Cancelled"&&doc.docstatus===0){
      return [__("Withdrawn"),"gray","custom_bsp_approval_state,=,Cancelled"];
    }
    return previous?.call(this,doc);
  };
  frappe.listview_settings["Purchase Order"]=settings;
})();
