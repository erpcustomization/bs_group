// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

// ============================================================
// Cheque Register — Enterprise Party & Workflow Script
// ============================================================

frappe.ui.form.on('Cheque Register', {

  // ── On form load: set up field visibility & queries ──────────────────────
  onload: function(frm) {
    setup_party_section(frm);
    set_cheque_type(frm);
  },

  refresh: function(frm) {
    setup_party_section(frm);
    set_cheque_type(frm);

    // Workflow action buttons (only for saved docs)
    if (!frm.is_new()) {
      frappe.model.with_doc('Workflow', 'Cheque Register Workflow', function() {
        frappe.call({
          method: 'frappe.model.workflow.get_transitions',
          args: { doc: frm.doc },
          callback: function(r) {
            if (!r.message) return;
            frm.clear_custom_buttons();
            r.message.forEach(function(t) {
              var btnClass = 'btn-default';
              if (['Finance Approve','Mark as Signed','Issue / Release Cheque','Mark as Cheque Prepared'].includes(t.action)) {
                btnClass = 'btn-primary';
              } else if (['Reject','Reject Signing','Cancel'].includes(t.action)) {
                btnClass = 'btn-danger';
              }
              frm.add_custom_button(t.action, function() {
                frappe.call({
                  method: 'frappe.model.workflow.apply_workflow',
                  args: { doc: frm.doc, action: t.action },
                  callback: function(r) {
                    if (r.message) {
                      frappe.model.sync(r.message);
                      frm.refresh();
                    }
                  }
                });
              }).addClass(btnClass);
            });
          }
        });
      });
    }
  },

  // ── Cheque Date changed: auto-detect cheque type ──────────────────────────
  cheque_date: function(frm) {
    set_cheque_type(frm);
  },

  // ── Party Type changed: reset party, toggle field visibility ─────────────
  party_type: function(frm) {
    frm.set_value('party', '');
    frm.set_value('party_name', '');
    frm.set_value('purchase_order', '');
    frm.set_value('purchase_invoice', '');
    frm.set_value('po_number', '');
    setup_party_section(frm);
  },

  // ── Party selected: fetch display name & related docs ────────────────────
  party: function(frm) {
    if (!frm.doc.party || !frm.doc.party_type) return;

    var pt = frm.doc.party_type;
    var p  = frm.doc.party;

    if (pt === 'Supplier') {
      frappe.db.get_value('Supplier', p, 'supplier_name', function(d) {
        frm.set_value('party_name', d && d.supplier_name ? d.supplier_name : p);
      });
    } else if (pt === 'Customer') {
      frappe.db.get_value('Customer', p, 'customer_name', function(d) {
        frm.set_value('party_name', d && d.customer_name ? d.customer_name : p);
      });
    } else if (pt === 'Employee') {
      frappe.db.get_value('Employee', p, 'employee_name', function(d) {
        frm.set_value('party_name', d && d.employee_name ? d.employee_name : p);
      });
    } else if (pt === 'Individual') {
      frappe.db.get_value('Contact', p, 'full_name', function(d) {
        frm.set_value('party_name', d && d.full_name ? d.full_name : p);
      });
    }
  },

  // ── Purchase Order selected: auto-fill supplier ───────────────────────────
  purchase_order: function(frm) {
    if (!frm.doc.purchase_order) return;
    frappe.db.get_value('Purchase Order', frm.doc.purchase_order, ['supplier', 'supplier_name'], function(d) {
      if (d && d.supplier_name) {
        if (!frm.doc.party_type) frm.set_value('party_type', 'Supplier');
        if (!frm.doc.party)      frm.set_value('party', d.supplier);
        frm.set_value('party_name', d.supplier_name);
      }
    });
  },

  // ── Purchase Invoice selected: auto-fill supplier ─────────────────────────
  purchase_invoice: function(frm) {
    if (!frm.doc.purchase_invoice) return;
    frappe.db.get_value('Purchase Invoice', frm.doc.purchase_invoice, ['supplier', 'supplier_name'], function(d) {
      if (d && d.supplier_name) {
        if (!frm.doc.party_type) frm.set_value('party_type', 'Supplier');
        if (!frm.doc.party)      frm.set_value('party', d.supplier);
        frm.set_value('party_name', d.supplier_name);
      }
    });
  }

});

// ── Helper: auto-detect cheque type from date ────────────────────────────────
function set_cheque_type(frm) {
  if (!frm.doc.cheque_date) {
    frm.set_value('cheque_type', '');
    return;
  }

  var today     = frappe.datetime.get_today();         // 'YYYY-MM-DD'
  var chequeDay = frm.doc.cheque_date;

  var chequeType = '';
  if (chequeDay > today) {
    chequeType = 'Post-Dated Cheque';
  } else if (chequeDay === today) {
    chequeType = 'Current Cheque';
  } else {
    chequeType = 'Back-Dated Cheque';
  }

  if (frm.doc.cheque_type !== chequeType) {
    frm.set_value('cheque_type', chequeType);
    // Visual indicator color via indicator dot
    frm.set_indicator_formatter && frm.refresh_fields && frm.refresh_field('cheque_type');
  }
}

// ── Helper: configure Party section based on party_type ─────────────────────
function setup_party_section(frm) {
  var pt = frm.doc.party_type;

  if (pt === 'Supplier') {
    frm.set_query('party', function() {
      return { doctype: 'Supplier', filters: [['Supplier', 'disabled', '=', 0]] };
    });
    frm.set_df_property('purchase_order',   'hidden', 0);
    frm.set_df_property('purchase_invoice', 'hidden', 0);
    frm.set_df_property('po_number',        'hidden', 0);
    frm.fields_dict['party'].df.label = 'Supplier';

  } else if (pt === 'Customer') {
    frm.set_query('party', function() {
      return { doctype: 'Customer', filters: [['Customer', 'disabled', '=', 0]] };
    });
    frm.set_df_property('purchase_order',   'hidden', 1);
    frm.set_df_property('purchase_invoice', 'hidden', 1);
    frm.set_df_property('po_number',        'hidden', 1);
    frm.fields_dict['party'].df.label = 'Customer';

  } else if (pt === 'Employee') {
    frm.set_query('party', function() {
      return { doctype: 'Employee', filters: [['Employee', 'status', '=', 'Active']] };
    });
    frm.set_df_property('purchase_order',   'hidden', 1);
    frm.set_df_property('purchase_invoice', 'hidden', 1);
    frm.set_df_property('po_number',        'hidden', 1);
    frm.fields_dict['party'].df.label = 'Employee';

  } else if (pt === 'Individual') {
    frm.set_query('party', function() {
      return { doctype: 'Contact' };
    });
    frm.set_df_property('purchase_order',   'hidden', 1);
    frm.set_df_property('purchase_invoice', 'hidden', 1);
    frm.set_df_property('po_number',        'hidden', 1);
    frm.fields_dict['party'].df.label = 'Individual Name';

  } else {
    frm.set_df_property('purchase_order',   'hidden', 0);
    frm.set_df_property('purchase_invoice', 'hidden', 0);
    frm.set_df_property('po_number',        'hidden', 0);
  }

  frm.refresh_field('party');
  frm.refresh_field('purchase_order');
  frm.refresh_field('purchase_invoice');
  frm.refresh_field('po_number');
}

// Global fix for NaN in Number Cards - runs on every page
if (!window._pdcNanFixed) {
  window._pdcNanFixed = true;

  // Patch frappe.format.currency to handle null
  if (frappe.format && frappe.format.currency) {
    const origFormat = frappe.format.currency.bind(frappe.format);
    frappe.format.currency = function(value, ...args) {
      if (value === null || value === undefined || (typeof value === 'number' && isNaN(value))) {
        value = 0;
      }
      return origFormat(value, ...args);
    };
  }

  // Also patch format_currency
  if (frappe.utils && frappe.utils.fmt_money) {
    const origFmt = frappe.utils.fmt_money.bind(frappe.utils);
    frappe.utils.fmt_money = function(value, ...args) {
      if (value === null || value === undefined || (typeof value === 'number' && isNaN(value))) {
        value = 0;
      }
      return origFmt(value, ...args);
    };
  }
}
