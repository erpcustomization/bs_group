// Column resizing is a personal preference, never a shared List View Settings edit.
(() => {
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
