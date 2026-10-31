// Column resizing is a personal preference, never a shared List View Settings edit.
(() => {
  // Compact-list theme rules use !important. Preserve the explicit pixel widths
  // set by the native drag handler, including while the pointer is moving.
  const enforce = element => {
    if (!element.matches?.('.list-row-col')) return;
    const width = element.style.width;
    if (!/^\d+(\.\d+)?px$/.test(width)) return;
    for (const [property, value] of Object.entries({width, flex: `0 0 ${width}`, 'min-width': width, 'max-width': width})) {
      if (element.style.getPropertyValue(property) !== value || element.style.getPropertyPriority(property) !== 'important') {
        element.style.setProperty(property, value, 'important');
      }
    }
  };
  const observer = new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'attributes') enforce(record.target);
      else for (const node of record.addedNodes) {
        if (node.nodeType !== 1) continue;
        enforce(node);
        node.querySelectorAll('.list-row-col[style]').forEach(enforce);
      }
    }
  });
  observer.observe(document.body, {subtree:true, childList:true, attributes:true, attributeFilter:['style']});
  document.querySelectorAll('.list-row-col[style]').forEach(enforce);
  const key = 'bs_column_widths';
  const named = view => view.list_filter?.active_layout_name && view.list_filter.active_layout_name !== 'default_layout';
  function install() {
    const proto = frappe.views?.ListView?.prototype;
    if (!proto) return false;
    if (proto._bs_personal_widths) return true;
    proto._bs_personal_widths = true;
    const save = proto.save_column_width;
    const render = proto.before_render;
    proto.save_column_width = function(fieldname, width) {
      if (named(this)) return save.call(this, fieldname, width);
      if (!fieldname || !Number.isFinite(Number(width))) return;
      width = Math.max(50, Math.min(400, Number(width)));
      this._bs_widths = {...frappe.get_user_settings(this.doctype, key), ...this._bs_widths, [fieldname]: width};
      return frappe.model.user_settings.save(this.doctype, key, this._bs_widths);
    };
    proto.before_render = function(...args) {
      const result = render.apply(this, args);
      if (!named(this)) {
        const widths = {...frappe.get_user_settings(this.doctype, key), ...this._bs_widths};
        for (const col of this.columns || []) {
          const field = col.type === 'Status' ? 'status_field' : col.df?.fieldname;
          if (col.df && Number.isFinite(Number(widths[field]))) {
            const width = Math.max(50, Math.min(400, Number(widths[field])));
            col.df = {...col.df, width};
            this.column_max_widths[field] = width;
          }
        }
      }
      return result;
    };
    return true;
  }
  if (!install()) {
    const timer = setInterval(() => { if (install()) clearInterval(timer); }, 250);
  }
})();
