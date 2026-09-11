frappe.ui.form.on('Quotation', {
    refresh: function(frm) {
        reduce_subject_height(frm)
        set_lead_name(frm)
        frm.set_df_property('customer_name', 'hidden', 1);
        setTimeout(function() {
            frm.remove_custom_button('Set as Lost');
        }, 500);
        if (frm.doc.__islocal) {
            apply_company_tax(frm);
        }
    },
    company: function(frm) {
        apply_company_tax(frm);
    },
    party_name: function(frm){
        set_lead_name(frm)
        frm.set_df_property('customer_name', 'hidden', 1);
    },
    custom_apply_exclude_to_all_items: function(frm) {
        exclude_all_items(frm);
    },
    custom_pipeline_stage: function(frm) {
        prompt_lost_reason_if_needed(frm);
    },
    onload: function(frm) {
        if (!frm.doc.custom_designation) {
            frappe.db.get_value("Employee",
                { user_id: frappe.session.user },
                [ "designation", "cell_number"]
            ).then(r => {
                if (r && r.message && r.message.designation) {
                    frm.set_value("custom_designation", r.message.designation);
                    frm.set_value("custom_phone__no", r.message.cell_number)
                }
            });
        }
    }
});

frappe.ui.form.on('Quotation Item', {
    item_code: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row.item_code) return;
        frappe.db.get_value("Item", row.item_code, ["item_name", "brand"]).then(r => {
            if (r && r.message) {
                frappe.model.set_value(cdt, cdn, "item_name", r.message.item_name);
                if (!row.brand) {
                    frappe.model.set_value(cdt, cdn, "brand", r.message.brand);
                }
            }
            set_customer_item(frm, cdt, cdn);
        });
    },
    item_name: function(frm, cdt, cdn) {
        set_customer_item(frm, cdt, cdn);
    },
    brand: function(frm, cdt, cdn) {
        set_customer_item(frm, cdt, cdn);
    },
    custom_exclude_item_name_and_brand: function(frm, cdt, cdn) {
        set_customer_item(frm, cdt, cdn);
    }
});

function set_lead_name(frm) {
    if (!frm.doc.party_name) return;

    if (frm.doc.quotation_to === "Lead") {
        frappe.db.get_value("Lead", frm.doc.party_name, ["lead_name", "company_name"])
            .then(r => {
                if (r.message) {
                    frm.set_value("custom_contact_person_name", r.message.lead_name);
                    frm.set_value("custom_organization_name", r.message.company_name || "");
                }
            });

    } else if (frm.doc.quotation_to === "Customer") {
        frappe.db.get_value("Customer", frm.doc.party_name, ["customer_name", "customer_primary_contact"])
            .then(r => {
                if (r.message) {
                    frm.set_value("customer_name", r.message.customer_name);
                    frm.set_value("custom_organization_name", r.message.customer_name || "");

                    if (r.message.customer_primary_contact) {
                        frappe.db.get_doc("Contact", r.message.customer_primary_contact)
                            .then(contact => {
                                let full_name = [
                                    contact.first_name,
                                    contact.middle_name,
                                    contact.last_name
                                ].filter(Boolean).join(" ");

                                frm.set_value("custom_contact_person_name", full_name);
                            });
                    } else {
                        frm.set_value("custom_contact_person_name", "");
                    }
                }
            });
    }
}

function set_customer_item(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    let value;
    if (row.custom_exclude_item_name_and_brand) {
        value = (row.item_name || "").trim();
    } else {
        const parts = [row.brand, row.item_code, row.item_name].filter(p => p);
        value = parts.join(" - ");
    }
    frappe.model.set_value(cdt, cdn, "custom_customer_item_name", value);
    setTimeout(() => {
        frappe.model.set_value(cdt, cdn, "description", value);
    }, 800);
}

function exclude_all_items(frm) {
    const value = frm.doc.custom_apply_exclude_to_all_items ? 1 : 0;
    (frm.doc.items || []).forEach(row => {
        frappe.model.set_value(row.doctype, row.name, "custom_exclude_item_name_and_brand", value);
        set_customer_item(frm, row.doctype, row.name);
    });
    frm.refresh_field("items");
}

function apply_company_tax(frm) {
    if (!frm.doc.company) return;

    frappe.db.get_list("Sales Taxes and Charges Template", {
        filters: [["company", "=", frm.doc.company], ["name", "like", "%UAE VAT 5%%"]],
        fields: ["name"],
        limit: 1
    }).then(list => {
        if (list && list.length) {
            frm.set_value("taxes_and_charges", list[0].name);
        }
    });
}

function prompt_lost_reason_if_needed(frm) {
    const stagesNeedingReason = ["Lost", "Cancelled"];
    if (!stagesNeedingReason.includes(frm.doc.custom_pipeline_stage)) return;
    if (frm.doc.custom_lost_reason) return;

    frappe.prompt(
        [
            {
                fieldname: "custom_lost_reason",
                fieldtype: "Small Text",
                label: "Reason",
                reqd: 1,
            },
        ],
        (values) => {
            frm.set_value("custom_lost_reason", values.custom_lost_reason);
        },
        `Reason for marking as ${frm.doc.custom_pipeline_stage}`,
        "Save"
    );
}

function reduce_subject_height(frm){
    setTimeout(() => {
        frm.fields_dict.custom_subject.$wrapper
            .find('textarea')
            .css({
                "height": "30px",
                "min-height": "27px"
            });
    }, 300);
}

// Quotation List View - Hide cancelled (amended) records by default
frappe.listview_settings["Quotation"] = {
    onload: function(listview) {
        listview.filter_area.add([
            ["Quotation", "docstatus", "!=", "2"]
        ]);
    }
};

frappe.ui.form.on(cur_frm ? cur_frm.doctype : 'Quotation', {
  refresh() { window.__installLiteTheme && window.__installLiteTheme(); }
});

(function () {
  if (window.__liteThemeInstalled) { window.__installLiteTheme(); return; }
  window.__liteThemeInstalled = true;

  var CSS = `
  html.lite-theme { --lt-primary:#1e66f5; --lt-primary-soft:#eaf1ff; --lt-accent:#7c3aed; --lt-green:#16a34a; --lt-green-soft:#dcfce7; --lt-red:#dc2626; }
  html.lite-theme .navbar { background:linear-gradient(90deg,#1e66f5 0%,#7c3aed 100%)!important; border-bottom:none!important; }
  html.lite-theme .navbar .navbar-brand, html.lite-theme .navbar a, html.lite-theme .navbar .nav-link { color:#fff!important; }
  html.lite-theme .btn-primary, html.lite-theme .primary-action { background:var(--lt-primary)!important; border-color:var(--lt-primary)!important; color:#fff!important; }
  html.lite-theme .btn-primary:hover, html.lite-theme .primary-action:hover { filter:brightness(.93); }
  html.lite-theme .standard-sidebar-item.selected, html.lite-theme .sidebar-item-label.selected { background:var(--lt-primary-soft)!important; border-radius:6px; }
  html.lite-theme .desk-sidebar .standard-sidebar-item.selected a { color:var(--lt-primary)!important; }
  html.lite-theme .list-row:hover, html.lite-theme .list-row-container:hover { background:var(--lt-primary-soft)!important; box-shadow:inset 3px 0 0 var(--lt-primary); }
  html.lite-theme .indicator-pill.green { background:var(--lt-green-soft)!important; color:#15803d!important; }
  html.lite-theme .indicator-pill.red { background:#fee2e2!important; color:#b91c1c!important; }
  html.lite-theme .indicator-pill.orange { background:#ffedd5!important; color:#c2410c!important; }
  html.lite-theme .indicator-pill.blue { background:#dbeafe!important; color:#1d4ed8!important; }
  html.lite-theme .section-head, html.lite-theme .form-section .section-head { color:var(--lt-primary)!important; font-weight:600; }
  html.lite-theme .form-layout table thead th, html.lite-theme .form-layout table thead td { background:var(--lt-primary)!important; color:#fff!important; font-weight:600!important; border-color:var(--lt-primary)!important; }
  html.lite-theme .form-layout table tbody tr:hover { background:var(--lt-primary-soft)!important; }
  html.lite-theme .form-layout table tbody tr:last-child { background:var(--lt-primary-soft)!important; font-weight:700!important; }
  html.lite-theme .form-layout table tbody tr:last-child td { border-top:2px solid var(--lt-primary)!important; color:#0b3d91!important; }
  html.lite-theme .form-layout table { border-radius:8px; overflow:hidden; }
  html.lite-theme .form-grid .grid-heading-row, html.lite-theme .form-grid .grid-heading-row .col, html.lite-theme .form-grid .grid-heading-row .grid-static-col, html.lite-theme .form-grid .grid-heading-row .row-index, html.lite-theme .form-grid .grid-heading-row .row-check { background-color:#1e66f5!important; background-image:none!important; border-color:#1e66f5!important; }
  html.lite-theme .form-grid .grid-heading-row .col { border-right:1px solid rgba(255,255,255,.15)!important; border-bottom:none!important; }
  html.lite-theme .form-grid .grid-heading-row .col:last-child { border-right:none!important; }
  html.lite-theme .form-grid .grid-heading-row, html.lite-theme .form-grid .grid-heading-row .col, html.lite-theme .form-grid .grid-heading-row .static-area, html.lite-theme .form-grid .grid-heading-row .field-area, html.lite-theme .form-grid .grid-heading-row span, html.lite-theme .form-grid .grid-heading-row div, html.lite-theme .form-grid .grid-heading-row .reqd { color:#fff!important; -webkit-text-fill-color:#fff!important; opacity:1!important; font-weight:600!important; }
  html.lite-theme .form-grid .grid-heading-row .grid-row-check input { filter:brightness(0) invert(1); }
  html.lite-theme .form-grid .grid-body .grid-row:hover { background:var(--lt-primary-soft)!important; }
  html.lite-theme .form-grid .grid-body .grid-row:nth-child(even) { background:#f8fafd; }
  html.lite-theme .frappe-control[data-fieldname="customer"], html.lite-theme .frappe-control[data-fieldname="customer_name"], html.lite-theme .frappe-control[data-fieldname="party_name"], html.lite-theme .frappe-control[data-fieldname="status"], html.lite-theme .frappe-control[data-fieldname="workflow_state"], html.lite-theme .frappe-control[data-fieldname="custom_organization_name"], html.lite-theme .frappe-control[data-fieldname="organization_name"], html.lite-theme .frappe-control[data-fieldname="custom_contact_person_name"], html.lite-theme .frappe-control[data-fieldname="contact_person"], html.lite-theme .frappe-control[data-fieldname="contact_display"], html.lite-theme .frappe-control[data-fieldname="custom_sales_person"], html.lite-theme .frappe-control[data-fieldname="sales_person"] { background:var(--lt-primary-soft)!important; border-left:3px solid var(--lt-primary)!important; border-radius:8px!important; padding:8px 10px!important; margin-bottom:8px!important; box-shadow:0 1px 3px rgba(30,102,245,.10); }
  html.lite-theme .frappe-control[data-fieldname="customer"] .control-label, html.lite-theme .frappe-control[data-fieldname="customer_name"] .control-label, html.lite-theme .frappe-control[data-fieldname="party_name"] .control-label, html.lite-theme .frappe-control[data-fieldname="status"] .control-label, html.lite-theme .frappe-control[data-fieldname="workflow_state"] .control-label, html.lite-theme .frappe-control[data-fieldname="custom_organization_name"] .control-label, html.lite-theme .frappe-control[data-fieldname="organization_name"] .control-label, html.lite-theme .frappe-control[data-fieldname="custom_contact_person_name"] .control-label, html.lite-theme .frappe-control[data-fieldname="contact_person"] .control-label, html.lite-theme .frappe-control[data-fieldname="contact_display"] .control-label, html.lite-theme .frappe-control[data-fieldname="custom_sales_person"] .control-label, html.lite-theme .frappe-control[data-fieldname="sales_person"] .control-label { color:var(--lt-primary)!important; font-weight:700!important; text-transform:uppercase; letter-spacing:.3px; font-size:11px; }
  html.lite-theme .frappe-control[data-fieldname="customer"] .control-input input, html.lite-theme .frappe-control[data-fieldname="customer_name"] .control-input input, html.lite-theme .frappe-control[data-fieldname="party_name"] .control-input input { font-weight:700!important; color:#0b3d91!important; }
  html.lite-theme .frappe-control[data-fieldname="grand_total"], html.lite-theme .frappe-control[data-fieldname="rounded_total"], html.lite-theme .frappe-control[data-fieldname="base_grand_total"] { background:var(--lt-green-soft)!important; border-left:3px solid var(--lt-green)!important; border-radius:8px!important; padding:8px 10px!important; margin-bottom:8px!important; box-shadow:0 1px 4px rgba(22,163,74,.15); }
  html.lite-theme .frappe-control[data-fieldname="grand_total"] .control-label, html.lite-theme .frappe-control[data-fieldname="rounded_total"] .control-label, html.lite-theme .frappe-control[data-fieldname="base_grand_total"] .control-label { color:#15803d!important; font-weight:700!important; text-transform:uppercase; font-size:11px; }
  html.lite-theme .frappe-control[data-fieldname="grand_total"] .control-input input, html.lite-theme .frappe-control[data-fieldname="rounded_total"] .control-input input, html.lite-theme .frappe-control[data-fieldname="base_grand_total"] .control-input input { font-weight:800!important; color:#15803d!important; font-size:15px!important; }
  html.lite-theme .page-head .indicator-pill, html.lite-theme .title-area .indicator-pill { font-weight:700!important; padding:3px 12px!important; border-radius:14px!important; font-size:11px!important; text-transform:uppercase; letter-spacing:.4px; border:1.5px solid transparent!important; box-shadow:0 1px 4px rgba(0,0,0,.12); }
  html.lite-theme .page-head .indicator-pill.blue, html.lite-theme .title-area .indicator-pill.blue { background:#dbeafe!important; color:#1d4ed8!important; border-color:#93c5fd!important; }
  html.lite-theme .page-head .indicator-pill.green, html.lite-theme .title-area .indicator-pill.green { background:#dcfce7!important; color:#15803d!important; border-color:#86efac!important; }
  html.lite-theme .page-head .indicator-pill.red, html.lite-theme .title-area .indicator-pill.red { background:#fee2e2!important; color:#b91c1c!important; border-color:#fca5a5!important; }
  html.lite-theme .page-head .indicator-pill.orange, html.lite-theme .title-area .indicator-pill.orange { background:#ffedd5!important; color:#c2410c!important; border-color:#fdba74!important; }
  html.lite-theme .page-head .indicator-pill.gray, html.lite-theme .page-head .indicator-pill.grey { background:#f1f5f9!important; color:#475569!important; border-color:#cbd5e1!important; }
    .form-grid .grid-body .data-row .col[data-fieldname="description"] { height:auto !important; max-height:none !important; }
      .form-grid .grid-body .data-row .col[data-fieldname="description"] .static-area,
        .form-grid .grid-body .data-row .col[data-fieldname="description"] .ellipsis,
          .form-grid .grid-body .data-row .col[data-fieldname="description"] .control-value,
            .form-grid .grid-body .data-row .col[data-fieldname="description"] .ql-editor { height:auto !important; max-height:none !important; overflow:visible !important; white-space:normal !important; -webkit-line-clamp:unset !important; display:block !important; }
              .form-grid .grid-body .data-row .col[data-fieldname="description"] .grid-static-col { white-space:normal !important; }
              `;

  function colorize() {
    if (!document.documentElement.classList.contains('lite-theme')) return;
    document.querySelectorAll('.form-layout table').forEach(function (tbl) {
      var heads = Array.from(tbl.querySelectorAll('thead th, thead td')).map(function (h) { return h.innerText.toLowerCase().trim(); });
      var cols = []; heads.forEach(function (h, i) { if (h.indexOf('margin') > -1) cols.push(i); });
      if (!cols.length) return;
      tbl.querySelectorAll('tbody tr').forEach(function (tr) {
        cols.forEach(function (ci) {
          var c = tr.children[ci]; if (!c) return;
          var n = parseFloat(c.innerText.replace(/[^\d.\-]/g, '')); if (isNaN(n)) return;
          c.style.fontWeight = '700';
          c.style.color = n > 0 ? '#15803d' : (n < 0 ? '#dc2626' : '#92400e');
        });
      });
    });
    var profit = ['gp_value', 'gp_percent', 'margin', 'margin_amount', 'margin_percent'];
    document.querySelectorAll('.form-grid .grid-body .grid-row .col[data-fieldname]').forEach(function (cell) {
      var df = cell.getAttribute('data-fieldname');
      var t = cell.querySelector('.static-area') || cell;
      if (profit.indexOf(df) > -1) {
        var n = parseFloat((t.innerText || '').replace(/[^\d.\-]/g, ''));
        if (isNaN(n)) { t.style.color = ''; t.style.fontWeight = ''; return; }
        t.style.fontWeight = '700';
        t.style.color = n > 0 ? '#15803d' : (n < 0 ? '#dc2626' : '#92400e');
      } else if (df === 'amount' || df === 'cost_amount' || df === 'selling_amount') {
        t.style.fontWeight = '600';
      }
    });
  }

  function buildToggle() {
    if (document.getElementById('lite-theme-toggle')) return;
    var w = document.createElement('div'); w.id = 'lite-theme-toggle';
    w.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:99999;display:flex;align-items:center;gap:8px;background:#fff;border:1px solid #e2e2e2;border-radius:20px;padding:6px 13px;box-shadow:0 3px 10px rgba(0,0,0,.15);font-size:12px;font-family:inherit;cursor:pointer;user-select:none;';
    function render() {
      var on = document.documentElement.classList.contains('lite-theme');
      w.innerHTML = '<span style="font-weight:600;color:#444;">Color Theme</span>' +
        '<span style="position:relative;width:34px;height:18px;border-radius:10px;transition:.2s;background:' + (on ? '#1e66f5' : '#ccc') + ';display:inline-block;">' +
        '<span style="position:absolute;top:2px;left:' + (on ? '18px' : '2px') + ';width:14px;height:14px;border-radius:50%;background:#fff;transition:.2s;"></span></span>' +
        '<span style="color:' + (on ? '#1e66f5' : '#999') + ';font-weight:600;">' + (on ? 'ON' : 'OFF') + '</span>';
    }
    w.onclick = function () {
      var on = document.documentElement.classList.toggle('lite-theme');
      localStorage.setItem('lite_theme_on', on ? '1' : '0'); render();
    };
    render(); document.body.appendChild(w);
  }

  window.__installLiteTheme = function () {
    if (!document.getElementById('lite-theme-style')) {
      var s = document.createElement('style'); s.id = 'lite-theme-style'; s.textContent = CSS; document.head.appendChild(s);
    }
    if (localStorage.getItem('lite_theme_on') !== '0') document.documentElement.classList.add('lite-theme');
    buildToggle();
  };

  window.__installLiteTheme();
  setInterval(function () {
    window.__installLiteTheme();
    if (document.documentElement.classList.contains('lite-theme')) colorize();
  }, 1500);
})();