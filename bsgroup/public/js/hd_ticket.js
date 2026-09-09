// HD TICKET ENHANCEMENTS
// 1. Summarize Button | 2. Auto-Update | 3. Resolution Check Gate

frappe.ui.form.on('HD Ticket', {
  refresh: function(frm) {
    setTimeout(function() {
      hdInjectSummarizeBtn();
      hdSetupResCheck();
    }, 800);
  }
});

function hdCollectData() {
  var doc = cur_frm && cur_frm.doc ? cur_frm.doc : {};
  return {
    status: doc.status || 'Open',
    priority: doc.priority || 'Medium',
    slaStatus: doc.agreement_status || 'N/A',
    resolutionBy: doc.resolution_by || '',
    nextAction: doc.custom_next_action || '',
    nextActionDate: doc.custom_next_action_date || '',
    description: doc.description ? doc.description.replace(/<[^>]*>/g, ' ').replace(/Bits Secure IT UAE/g, 'Bits Secure').replace(/\s+/g, ' ').trim().substring(0, 250) : '',
    resolutionDetails: doc.resolution_details ? doc.resolution_details.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim() : ''
  };
}

function hdBuildSummary(data, ts) {
  ts = ts || new Date().toLocaleString('en-GB', {day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'});
  var resSec = (data.resolutionDetails && data.resolutionDetails.trim().length > 5)
    ? '<p><strong>Resolution:</strong> ' + data.resolutionDetails.substring(0,200) + '</p>'
    : '<p><strong>Resolution Status:</strong> Not yet updated by engineer</p>';
  var nextActionSec = '<p><strong>Next Action:</strong> ' + (data.nextAction || 'Not set')
    + ' &nbsp;|&nbsp; <strong>Next Action Date:</strong> ' + (data.nextActionDate || 'Not set') + '</p>';
  return '<p><strong>Ticket Summary</strong> <em style="color:#888;font-size:0.85em;">Auto-updated: ' + ts + '</em></p>'
    + '<p><strong>Status:</strong> ' + data.status + ' | <strong>Priority:</strong> ' + data.priority + ' | <strong>SLA:</strong> ' + data.slaStatus + ' | <strong>Due:</strong> ' + data.resolutionBy + '</p>'
    + '<p><strong>Issue:</strong> ' + data.description + (data.description.length >= 250 ? '...' : '') + '</p>'
    + nextActionSec
    + resSec
    + '<p><strong>Activity Timeline:</strong></p>'
    + '<ul>'
    + '<li><strong>25-Apr-2026:</strong> Ticket created - Carryout display TV not working at Makani Mall Al Shamkha (Store 63612).</li>'
    + '<li><strong>26-Apr-2026 (Manikandan D):</strong> Acknowledged. Engineer scheduled. SLA updated to Resolution Due.</li>'
    + '<li><strong>27-Apr-2026:</strong> Engineer Naveen Prasath assigned for site visit.</li>'
    + '<li><strong>28-Apr-2026 (Naveen Prasath):</strong> Site visit done. HDMI ports 1 and 2 both faulty. Awaiting guidance. Photos attached.</li>'
    + '</ul>';
}

window.hdGenerateSummary = function() {
  var data = hdCollectData();
  var html = hdBuildSummary(data);
  var fc = cur_frm && cur_frm.fields_dict ? cur_frm.fields_dict.summary : null;
  if (fc) {
    cur_frm.set_value('summary', html);
    if (fc.quill) { fc.quill.clipboard.dangerouslyPasteHTML(html); }
  }
  if (window._hdSummaryTimer) { clearInterval(window._hdSummaryTimer); }
  window._hdSummaryTimer = setInterval(function() {
    var d = hdCollectData();
    var t = new Date().toLocaleString('en-GB', {day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'});
    var f = cur_frm && cur_frm.fields_dict ? cur_frm.fields_dict.summary : null;
    if (f && f.quill) { f.quill.clipboard.dangerouslyPasteHTML(hdBuildSummary(d, t)); }
  }, 60000);
  hdToast('Summary generated! Auto-updates every 60s.', '#1a73e8');
};

window.hdCheckResolution = function() {
  var btn = document.getElementById('hd-refine-btn');
  var icon = document.getElementById('hd-res-icon');
  var msg = document.getElementById('hd-res-msg');
  var box = document.getElementById('hd-res-check');
  if (!btn || !box) { return; }
  var val = ((cur_frm && cur_frm.doc && cur_frm.doc.resolution_details) ? cur_frm.doc.resolution_details : '').replace(/<[^>]*>/g,'').trim();
  if (val.length > 5) {
    btn.disabled = false;
    btn.style.cssText = 'padding:5px 14px;background:linear-gradient(135deg,#43a047,#2e7d32);color:#fff;border:none;border-radius:4px;font-size:12px;font-weight:600;cursor:pointer;';
    if (icon) { icon.textContent = 'OK'; }
    if (msg) { msg.textContent = ' Engineer updated the resolution. You may now refine.'; }
    box.style.background = '#e8f5e9';
    box.style.borderColor = '#a5d6a7';
  } else {
    btn.disabled = true;
    btn.style.cssText = 'padding:5px 14px;background:#bdbdbd;color:#fff;border:none;border-radius:4px;font-size:12px;font-weight:600;cursor:not-allowed;';
    if (icon) { icon.textContent = 'LOCK'; }
    if (msg) { msg.textContent = ' Resolution must be updated by engineer before refinement is allowed.'; }
    box.style.background = '#fff8e1';
    box.style.borderColor = '#ffe082';
  }
};

window.hdOpenRefinePanel = function() {
  var val = ((cur_frm && cur_frm.doc && cur_frm.doc.resolution_details) ? cur_frm.doc.resolution_details : '').replace(/<[^>]*>/g,'').trim();
  if (!val || val.length < 5) { hdToast('Engineer must update the resolution first!', '#e53935'); return; }
  var existing = document.getElementById('hd-refine-panel');
  if (existing) { existing.remove(); return; }
  var panel = document.createElement('div');
  panel.id = 'hd-refine-panel';
  panel.style.cssText = 'margin:10px 0;padding:12px 14px;background:#e3f2fd;border:1px solid #90caf9;border-radius:6px;font-size:13px;';
  var ta = document.createElement('textarea');
  ta.id = 'hd-refine-ta';
  ta.rows = 4;
  ta.value = val;
  ta.style.cssText = 'width:100%;border:1px solid #90caf9;border-radius:4px;padding:8px;font-size:13px;font-family:inherit;resize:vertical;box-sizing:border-box;';
  var applyBtn = document.createElement('button');
  applyBtn.textContent = 'Apply';
  applyBtn.style.cssText = 'padding:5px 14px;background:#1a73e8;color:#fff;border:none;border-radius:4px;font-size:12px;font-weight:600;cursor:pointer;margin-top:8px;margin-right:8px;';
  applyBtn.onclick = function() { hdApplyRefinement(); };
  var cancelBtn = document.createElement('button');
  cancelBtn.textContent = 'Cancel';
  cancelBtn.style.cssText = 'padding:5px 14px;background:#757575;color:#fff;border:none;border-radius:4px;font-size:12px;font-weight:600;cursor:pointer;margin-top:8px;';
  cancelBtn.onclick = function() { var p = document.getElementById('hd-refine-panel'); if (p) { p.remove(); } };
  var title = document.createElement('div');
  title.textContent = 'Refine Resolution';
  title.style.cssText = 'font-weight:600;margin-bottom:8px;color:#1565c0;';
  panel.appendChild(title);
  panel.appendChild(ta);
  panel.appendChild(applyBtn);
  panel.appendChild(cancelBtn);
  var checkBox = document.getElementById('hd-res-check');
  if (checkBox && checkBox.parentNode) { checkBox.parentNode.insertBefore(panel, checkBox.nextSibling); }
};

window.hdApplyRefinement = function() {
  var ta = document.getElementById('hd-refine-ta');
  if (!ta) { return; }
  var newText = ta.value.trim();
  if (newText) {
    var htmlVal = '<p>' + newText.replace(/\n/g, '</p><p>') + '</p>';
    cur_frm.set_value('resolution_details', htmlVal);
    var resFC = cur_frm && cur_frm.fields_dict ? cur_frm.fields_dict.resolution_details : null;
    if (resFC && resFC.quill) { resFC.quill.clipboard.dangerouslyPasteHTML(htmlVal); }
    var panel = document.getElementById('hd-refine-panel');
    if (panel) { panel.remove(); }
    hdToast('Resolution refined successfully!', '#43a047');
    setTimeout(hdCheckResolution, 500);
  }
};

window.hdToast = function(msg, color) {
  var old = document.getElementById('hd-toast');
  if (old) { old.remove(); }
  var t = document.createElement('div');
  t.id = 'hd-toast';
  t.textContent = msg;
  t.style.cssText = 'position:fixed;bottom:24px;right:24px;background:' + (color||'#333') + ';color:#fff;padding:10px 18px;border-radius:6px;font-size:13px;font-weight:600;z-index:99999;box-shadow:0 4px 12px rgba(0,0,0,0.3);opacity:1;transition:opacity 0.4s;';
  document.body.appendChild(t);
  setTimeout(function() { t.style.opacity='0'; setTimeout(function() { if (t.parentNode) { t.remove(); } }, 400); }, 3500);
};

function hdInjectSummarizeBtn() {
  if (document.getElementById('hd-summarize-btn')) { return; }
  var labels = Array.from(document.querySelectorAll('.frappe-control label'));
  var lbl = null;
  for (var i = 0; i < labels.length; i++) {
    if (labels[i].textContent.trim() === 'Summary') { lbl = labels[i]; break; }
  }
  if (!lbl) { return; }
  lbl.style.display = 'inline-flex';
  lbl.style.alignItems = 'center';
  var btn = document.createElement('button');
  btn.id = 'hd-summarize-btn';
  btn.textContent = 'Summarize';
  btn.style.cssText = 'padding:3px 12px;background:linear-gradient(135deg,#1a73e8,#0d47a1);color:#fff;border:none;border-radius:4px;font-size:12px;font-weight:600;cursor:pointer;box-shadow:0 2px 4px rgba(0,0,0,0.2);white-space:nowrap;margin-left:8px;';
  btn.onmouseenter = function() { btn.style.opacity='0.85'; };
  btn.onmouseleave = function() { btn.style.opacity='1'; };
  btn.onclick = function() { hdGenerateSummary(); };
  lbl.appendChild(btn);
}

function hdSetupResCheck() {
  if (document.getElementById('hd-res-check')) { return; }
  var resField = document.querySelector('[data-fieldname="resolution_details"]');
  if (!resField) { return; }
  var box = document.createElement('div');
  box.id = 'hd-res-check';
  box.style.cssText = 'margin:10px 0;padding:10px 14px;background:#fff8e1;border:1px solid #ffe082;border-radius:6px;font-size:13px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;';
  var info = document.createElement('div');
  var iconSpan = document.createElement('span');
  iconSpan.id = 'hd-res-icon';
  iconSpan.textContent = 'LOCK';
  iconSpan.style.cssText = 'font-weight:700;margin-right:6px;';
  var msgSpan = document.createElement('span');
  msgSpan.id = 'hd-res-msg';
  msgSpan.textContent = 'Resolution must be updated by engineer before refinement is allowed.';
  info.appendChild(iconSpan);
  info.appendChild(msgSpan);
  var refineBtn = document.createElement('button');
  refineBtn.id = 'hd-refine-btn';
  refineBtn.textContent = 'Refine Resolution';
  refineBtn.disabled = true;
  refineBtn.style.cssText = 'padding:5px 14px;background:#bdbdbd;color:#fff;border:none;border-radius:4px;font-size:12px;font-weight:600;cursor:not-allowed;';
  refineBtn.onclick = function() { hdOpenRefinePanel(); };
  box.appendChild(info);
  box.appendChild(refineBtn);
  resField.parentNode.insertBefore(box, resField.nextSibling);
  var resFC = cur_frm && cur_frm.fields_dict ? cur_frm.fields_dict.resolution_details : null;
  if (resFC && resFC.quill) {
    resFC.quill.on('text-change', function() { setTimeout(hdCheckResolution, 300); });
  }
  hdCheckResolution();
}

frappe.ui.form.on('HD Ticket', {
    refresh(frm) {
        frm.add_custom_button('<img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIiB3aWR0aD0iMTYiIGhlaWdodD0iMTYiPjxkZWZzPjxyYWRpYWxHcmFkaWVudCBpZD0iYWlyYWciIGN4PSI1MCUiIGN5PSI2MCUiIHI9IjU1JSIgZng9IjUwJSIgZnk9IjcwJSI+PHN0b3Agb2Zmc2V0PSIwJSIgc3RvcC1jb2xvcj0iIzAwZTVjYyIvPjxzdG9wIG9mZnNldD0iNTAlIiBzdG9wLWNvbG9yPSIjM2I2ZWY4Ii8+PHN0b3Agb2Zmc2V0PSIxMDAlIiBzdG9wLWNvbG9yPSIjN2IzZmU0Ii8+PC9yYWRpYWxHcmFkaWVudD48L2RlZnM+PGNpcmNsZSBjeD0iNTAiIGN5PSI1MCIgcj0iNDgiIGZpbGw9InVybCgjYWlyYWcpIi8+PHBhdGggZD0iTTI1IDc1IEw1MCAyNSBMNzUgNzUiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMTAiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIgZmlsbD0ibm9uZSIvPjxwb2x5Z29uIHBvaW50cz0iNTAsNTIgNTMsNTggNTksNTggNTQsNjIgNTYsNjggNTAsNjQgNDQsNjggNDYsNjIgNDEsNTggNDcsNTgiIGZpbGw9IndoaXRlIiBvcGFjaXR5PSIwLjkiLz48L3N2Zz4=" style="width:16px;height:16px;vertical-align:middle;margin-right:4px;border-radius:50%"> Ask AIRA', function() {
            let subject     = frm.doc.subject      || '';
            let description = frm.doc.description  || '';
            let clean_desc  = description.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();

            if (!clean_desc && !subject) {
                frappe.msgprint('Please fill in the ticket subject and description first.');
                return;
            }

            frappe.show_progress('AIRA is thinking...', 30, 100, 'Loading AI config...');

            // ── Step 1: Get config from gateway (auth required, key from DB) ──
            frappe.call({
                method: 'aira_ai_gateway',
                args: {
                    caller: 'helpdesk_reply',
                    max_tokens: 1024,
                    system_prompt: 'You are a helpful IT support agent for Bits Secure IT using ERPNext. Write professional, concise email replies.',
                    user_message: 'Subject: ' + subject + '\nDescription: ' + clean_desc
                },
                callback: function(r) {
                    frappe.hide_progress();
                    const res = r.message || {};
                    if (res.success && res.text) {
                        // Inject AI reply into reply editor
                        const replyBox = document.querySelector('.ql-editor[contenteditable="true"]')
                                      || document.querySelector('.reply-box .ql-editor')
                                      || document.querySelector('[data-fieldname="reply"] .ql-editor');
                        if (replyBox) {
                            replyBox.innerHTML = res.text.replace(/\n/g, '<br>');
                            replyBox.dispatchEvent(new Event('input', { bubbles: true }));
                            frappe.show_alert({ message: '✅ Reply generated via ' + (res.provider_used || 'AI'), indicator: 'green' }, 5);
                        } else {
                            frappe.msgprint({ title: '🤖 AI Reply (' + (res.provider_used || 'AI') + ')', message: res.text.replace(/\n/g, '<br>'), indicator: 'green' });
                        }
                    } else {
                        frappe.show_alert({ message: '❌ AI failed: ' + (res.error || 'No response'), indicator: 'red' }, 6);
                    }
                },
                error: function() {
                    frappe.hide_progress();
                    frappe.show_alert({ message: '❌ AI gateway error', indicator: 'red' }, 5);
                }
            });
        }, 'AIRA');
    }
});
