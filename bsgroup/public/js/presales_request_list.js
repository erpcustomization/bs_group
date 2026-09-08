frappe.listview_settings['Presales Request'] = {
    get_indicator: function(doc) {
        var color_map = {
            'Draft': 'red',
            'Open': 'blue',
            'Assigned': 'purple',
            'In Progress': 'orange',
            'Awaiting Sales Input': 'yellow',
            'Awaiting Customer Input': 'yellow',
            'Costing in Progress': 'orange',
            'Ready for Quotation': 'cyan',
            'Submitted to Sales': 'green',
            'Completed': 'green',
            'On Hold': 'grey',
            'Won': 'green',
            'Lost': 'red',
            'Cancelled': 'red'
        };
        var status = doc.status || 'Draft';
        return [status, color_map[status] || 'grey', 'status,=,' + status];
    }
};

// ===== Presales Dashboard Status Count Section =====
(function() {
  var ALL_STATUSES = [
    {label:'Draft',color:'#6c757d'},{label:'Open',color:'#17a2b8'},{label:'Assigned',color:'#007bff'},
    {label:'In Progress',color:'#fd7e14'},{label:'Awaiting Sales Input',color:'#ffc107'},
    {label:'Awaiting Customer Input',color:'#e83e8c'},{label:'Costing in Progress',color:'#20c997'},
    {label:'Ready for Quotation',color:'#6610f2'},{label:'Submitted to Sales',color:'#28a745'},
    {label:'Completed',color:'#155724'},{label:'On Hold',color:'#856404'},{label:'Won',color:'#1a7a4a'},
    {label:'Lost',color:'#dc3545'},{label:'Cancelled',color:'#343a40'}
  ];
  function injectStatusSection(sd) {
    if (document.getElementById('psd-status-section')) return;
    var body = document.getElementById('psd-body');
    if (!body) return;
    var grids = body.querySelectorAll('.psd-kpi-grid');
    var before = grids.length >= 2 ? grids[1].nextSibling : null;
    var sec = document.createElement('div');
    sec.id = 'psd-status-section';
    sec.style.cssText = 'margin:18px 0 10px 0;';
    var h = document.createElement('div');
    h.style.cssText = 'font-weight:600;font-size:14px;color:#333;margin-bottom:10px;padding:0 4px;';
    h.textContent = 'Requests by Status';
    sec.appendChild(h);
    var g = document.createElement('div');
    g.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;';
    ALL_STATUSES.forEach(function(s) {
      var cnt = (sd && sd[s.label]) || 0;
      var c = document.createElement('div');
      c.style.cssText = 'background:#fff;border-radius:8px;padding:12px 14px;box-shadow:0 1px 4px rgba(0,0,0,.08);border-left:4px solid '+s.color+';cursor:pointer;';
      c.innerHTML = '<div style="font-size:22px;font-weight:700;color:'+s.color+'">'+cnt+'</div>'
        + '<div style="font-size:11px;color:#555;margin-top:4px;">'+s.label+'</div>';
      c.onclick = function(){ frappe.set_route('List','Presales Request','List',{status:s.label}); };
      g.appendChild(c);
    });
    sec.appendChild(g);
    body.insertBefore(sec, before);
  }
  function loadAndInject() {
    if (!document.getElementById('psd-body') || document.getElementById('psd-status-section')) return;
    frappe.call({
      method: 'bsgroup.bs_group.page.presales_request_das.presales_request_das.get_dashboard_data',
      callback: function(r) {
        var sd = {};
        if (r.message && r.message.status_data) {
          r.message.status_data.forEach(function(x){ sd[x.status] = x.count; });
        }
        injectStatusSection(sd);
      }
    });
  }
  function onRouteChange() {
    var h = window.location.hash || '';
    if (h.indexOf('presales-request-das') !== -1) {
      setTimeout(loadAndInject, 800);
    }
  }
  // Use MutationObserver to catch when psd-body is added
  new MutationObserver(function(muts) {
    muts.forEach(function(m) {
      m.addedNodes.forEach(function(n) {
        if (n.id === 'psd-body' || (n.querySelector && n.querySelector('#psd-body'))) {
          setTimeout(loadAndInject, 400);
        }
      });
    });
  }).observe(document.body, {childList: true, subtree: true});
  frappe.router.on('change', onRouteChange);
  // Run immediately if already on dashboard
  setTimeout(loadAndInject, 500);
})();
