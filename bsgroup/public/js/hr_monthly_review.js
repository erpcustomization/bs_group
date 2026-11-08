/* HR monthly evidence and reviewed actions. Automatic sending awaits approved rules. */
window.bsHRMonthlyReview=async function(main){
    const root=$('<div class="hr-review">').appendTo(main), esc=v=>frappe.utils.escape_html(String(v??''));
    const number=v=>v===null||v===undefined?'—':Number(v).toLocaleString(undefined,{maximumFractionDigits:2});
    const hours=v=>v===null||v===undefined?'—':`${Math.floor(Math.round(v)/60)}h ${Math.round(v)%60}m`;
    const link=(dt,id,label)=>`<a href="/desk/${frappe.router.slug(dt)}/${encodeURIComponent(id)}">${esc(label||id)}</a>`;
    let month=frappe.datetime.get_today().slice(0,7), data, search='',company='',department='',request=0;
    if(!document.getElementById('hr-review-style'))$('<style id="hr-review-style">').text(`
      .hr-review-controls{display:flex;gap:10px;align-items:end;flex-wrap:wrap;margin:14px 0}.hr-review-controls label{font-size:11px;color:#60778a;margin:0}.hr-review-controls .form-control{min-width:155px;max-width:250px}.hr-review-note{border:1px solid #d8e6ed;background:#f0f7fb;border-radius:10px;padding:14px 16px;font-size:12px;color:#42637a;margin-bottom:16px}.hr-review-table{min-width:1480px}.hr-review-table th{white-space:normal!important;max-width:130px}.hr-review-table td{vertical-align:top;white-space:nowrap}.hr-review-table th:first-child,.hr-review-table td:first-child{position:sticky;left:0;background:#fff;z-index:1;min-width:190px;max-width:230px;white-space:normal;box-shadow:2px 0 3px #15334b08}.hr-review-table button{font-size:12px;padding:0;border:0;background:none;text-align:left;color:#1a5674;font-weight:650}.hr-review-small{font-size:10px;display:block;color:#718394;margin-top:4px;white-space:normal}.hr-review-badge{font-size:10px;color:#90651c;background:#fff4da;padding:3px 6px;border-radius:5px;display:inline-block;margin-top:6px}.hr-review-details{margin-top:20px}.hr-review-details h3{font-size:17px}.hr-review-actions{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}.hr-review-days{min-width:1050px}.hr-review-days td{vertical-align:top}.hr-review-rules td{vertical-align:top;white-space:normal}.hr-review-bar{height:5px;background:#e9eff3;border-radius:9px;overflow:hidden;margin-top:8px}.hr-review-bar span{display:block;height:100%;background:#14867a}.hr-review-count{font-size:12px;color:#5c7486;margin:12px 0}.hr-review-warning{color:#966817}
    `).appendTo(document.head);
    function rules(){
        const d=new frappe.ui.Dialog({title:'Automatic message rules — awaiting your approval',size:'extra-large',fields:[{fieldtype:'HTML',options:`<p>These are proposals only. No automatic warnings, reminders or manager emails are enabled.</p><table class="hrm-table hr-review-rules"><thead><tr><th>Message</th><th>Proposed trigger</th><th>Recipient / frequency</th><th>Safeguards</th></tr></thead><tbody>${data.rules.map(r=>`<tr><td>${esc(r.title)}</td><td>${esc(r.trigger)}</td><td>${esc(r.delivery)}</td><td>${esc(r.safeguard)}</td></tr>`).join('')}</tbody></table><p class="hrm-foot">All rules require your approval before activation. Existing attendance, leave approvals and payroll controls remain authoritative. Historical punch source labels are incomplete; uncertain records need HR review before disciplinary action.</p>`}],primary_action_label:'Close',primary_action:()=>d.hide()});d.show();
    }
    function evidence(e,kind){
        const a=e.annual,t=e.totals;
        let subject,opening,rows;
        if(kind==='annual'){
            subject=`Annual leave planning · ${e.employee_name}`;
            opening=`Dear ${e.employee_name}, your HRMS annual-leave balance is ${number(a.balance)} days, with ${number(a.available)} days available after ${number(a.pending)} pending days, as of ${a.as_of}. Please discuss suitable leave dates with your manager and submit your application through Time Off. Leave remains subject to approval.`;
            rows=[];
        }else if(kind==='after'){
            subject=`After-hours duty review · ${e.employee_name} · ${month}`;
            opening=`Dear ${e.manager?.employee_name||'Manager'}, please review the recorded work after 6 PM for ${e.employee_name}: ${number(t.after_day)} days, ${hours(t.after_minutes)} during ${month}. Please confirm the business reason and whether the duty was authorized. These are recorded punch durations, not approved overtime or a payroll entitlement.`;
            rows=e.days.filter(d=>d.after_minutes>0);
        }else{
            subject=`Attendance review · ${e.employee_name} · ${month}`;
            opening=`Dear ${e.employee_name}, the ${month} attendance report records ${number(t.late_day)} completed late-arrival days (${hours(t.late_minutes)} after the scheduled start) and ${number(t.hr_absent)} submitted HR Absent days. Please review the dates below and provide any relevant explanation or correction request to HR. Missing or conflicting punches require HR review. This message does not change your attendance or pay.`;
            rows=e.days.filter(d=>d.late_day||d.hr_absent);
        }
        const daily=rows.length?`<table border="1" cellpadding="6" cellspacing="0"><tr><th>Date</th><th>In</th><th>Out</th><th>Late</th><th>After 6 PM</th><th>HR status / review</th></tr>${rows.map(d=>`<tr><td>${esc(d.date)}</td><td>${esc(d.first_in||'—')}</td><td>${esc(d.last_out||'—')}</td><td>${esc(hours(d.late_minutes))}</td><td>${esc(hours(d.after_minutes))}</td><td>${esc([...d.attendance.map(x=>x.status),...d.flags].join('; '))}</td></tr>`).join('')}</table>`:'';
        return{subject,message:`<p>${esc(opening)}</p>${daily}<p>Regards,<br>HR</p>`};
    }
    function actions(e,holder){
        if(data.can_warning)$('<button class="btn btn-default btn-sm">').text('Prepare attendance warning').on('click',()=>{
            const draft=evidence(e,'warning');frappe.new_doc('HR Warning',{employee:e.employee,company:e.company,subject:draft.subject,status:'Draft',warning_type:'Attendance',details:draft.message});
        }).appendTo(holder);
        const compose=async kind=>{
            if(kind==='annual'&&e.annual.source!=='hrms'){frappe.msgprint('A verified current HRMS annual-leave balance is required. Review the allocation first.');return;}
            const recipient=kind==='after'?e.manager?.email:e.email;
            if(!recipient||!recipient.includes('@')){frappe.msgprint(kind==='after'?'A reporting manager with a business email is not recorded or is outside your access.':'A business email or linked ERP login is not recorded.');return;}
            const draft=evidence(e,kind);
            await frappe.model.with_doctype('Employee');
            new frappe.views.CommunicationComposer({doc:{doctype:'Employee',name:e.employee},recipients:recipient,subject:draft.subject,message:draft.message});
        };
        if(data.can_email){
            $('<button class="btn btn-default btn-sm">').text('Compose attendance message').on('click',()=>compose('warning')).appendTo(holder);
            $('<button class="btn btn-default btn-sm">').text('Compose annual-leave reminder').on('click',()=>compose('annual')).appendTo(holder);
            $('<button class="btn btn-default btn-sm">').text('Compose manager after-hours review').on('click',()=>compose('after')).appendTo(holder);
        }
        if(data.can_request)$('<button class="btn btn-default btn-sm">').text('Record HR follow-up').on('click',()=>{
            const draft=evidence(e,'after');frappe.new_doc('HR Service Request',{employee:e.employee,company:e.company,subject:`Attendance follow-up · ${e.employee_name} · ${month}`,status:'Draft',request_type:'Other',details:draft.message});
        }).appendTo(holder);
    }
    function detail(e){
        root.find('.hr-review-details').remove();const box=$('<section class="hrm-panel hr-review-details">').appendTo(root);
        const head=$('<div class="hrm-panel-head">').appendTo(box);$('<h3>').text(`${e.employee_name} · ${month}`).appendTo(head);
        $('<button class="btn btn-default btn-sm">').text('Close details').on('click',()=>box.remove()).appendTo(head);
        const body=$('<div style="padding:16px 20px">').appendTo(box);
        $('<p class="hrm-muted">').text(`${e.department||'No department'} · Manager: ${e.manager?.employee_name||'Not recorded / restricted'} · ${e.company}`).appendTo(body);
        const a=e.annual;
        $('<p>').html(`<b>Annual leave:</b> allocated ${number(a.allocated)} · balance ${esc(a.balance??'—')} · available ${number(a.available)} · pending ${number(a.pending)} · used in allocation ${number(a.used_in_allocation)}<br><small>${esc(a.note||'Live HRMS balance as of '+a.as_of+'. Allocated includes the HRMS allocation/carry-forward balance; it may differ from annual contractual entitlement.')}</small>`).appendTo(body);
        actions(e,$('<div class="hr-review-actions">').appendTo(body));
        $('<p class="hrm-muted">').text('Actions prepare a draft or email composer for HR review. Automatic messages are not enabled. Review any data flags before sending.').appendTo(body);
        box.append(`<div class="hrm-table-wrap"><table class="hrm-table hr-review-days"><thead><tr><th>Date / schedule</th><th>Check-in / out</th><th>Office hours</th><th>Late</th><th>After 6 PM</th><th>Leave</th><th>HR attendance</th><th>Review notes</th></tr></thead><tbody>${e.days.map(d=>`<tr><td>${esc(d.date)}<span class="hr-review-small">${esc(d.shift||'No shift')} ${esc(d.shift_start||'')}–${esc(d.shift_end||'')}${d.holiday?' · Holiday':''}${d.future?' · Upcoming':''}${d.on_duty?' · On duty / WFH':''}</span></td><td>${d.punches.map(p=>link('Employee Checkin',p.name,`${p.log_type||'?'} ${p.time.slice(11,19)}`)).join('<br>')||'—'}</td><td>${hours(d.office_minutes)}</td><td>${hours(d.late_minutes)}</td><td>${hours(d.after_minutes)}</td><td>${d.leave_records.map(l=>link('Leave Application',l.name,`${l.leave_type} · ${l.status}${l.docstatus===0?' (draft)':''}`)).join('<br>')||'—'}</td><td>${d.attendance.map(a=>link('Attendance',a.name,`${a.status}${a.docstatus===0?' (draft)':''}`)).join('<br>')||'—'}</td><td class="hr-review-warning">${esc(d.flags.join('; '))}${d.missing_checkin?'<br>No check-in after shift ended':''}</td></tr>`).join('')}</tbody></table></div>`);
        box[0].scrollIntoView({block:'start',behavior:'smooth'});
    }
    function render(){
        root.empty();
        $('<div class="hr-review-note">').html('<b>Monthly HR review</b> · Full 9 AM–6 PM office window; no lunch deduction. Hours use completed recorded IN/OUT pairs. After-hours work is shown separately from approved overtime.').appendTo(root);
        const controls=$('<div class="hr-review-controls">').appendTo(root);
        $('<label>Month</label>').append($('<input class="form-control input-sm" type="month" aria-label="Review month">').val(month).on('change',function(){month=this.value;load();})).appendTo(controls);
        const companyInput=$('<select class="form-control input-sm" aria-label="Review company">').append('<option value="">All permitted companies</option>');
        [...new Set(data.employees.map(e=>e.company))].sort().forEach(x=>$('<option>').val(x).text(x).appendTo(companyInput));companyInput.val(company).on('change',()=>{company=companyInput.val();drawRows();});$('<label>Company</label>').append(companyInput).appendTo(controls);
        const deptInput=$('<select class="form-control input-sm" aria-label="Review department">').append('<option value="">All teams</option>');
        [...new Set(data.employees.map(e=>e.department).filter(Boolean))].sort().forEach(x=>$('<option>').val(x).text(x).appendTo(deptInput));deptInput.val(department).on('change',()=>{department=deptInput.val();drawRows();});$('<label>Team</label>').append(deptInput).appendTo(controls);
        $('<label>Employee</label>').append($('<input class="form-control input-sm" type="search" aria-label="Find employee in monthly review" placeholder="Name or employee ID">').val(search).on('input',function(){search=this.value;drawRows();})).appendTo(controls);
        $('<button class="btn btn-default btn-sm">').text('Refresh report').on('click',load).appendTo(controls);
        $('<button class="btn btn-default btn-sm">').text('Review proposed automatic rules').on('click',rules).appendTo(controls);
        $('<p class="hrm-muted">').text(`Automatic sending: awaiting approval · Data as of ${data.as_of?.slice(0,19).replace('T',' ')} Dubai time.`).appendTo(root);
        if(data.restricted.length)$('<p class="hr-review-note">').text('Restricted sources: '+data.restricted.join(', ')+'. A dash means unavailable, not zero.').appendTo(root);
        $('<div class="hr-review-count">').appendTo(root);
        const panel=$('<section class="hrm-panel"><div class="hrm-table-wrap"><table class="hrm-table hr-review-table"><thead><tr><th>Employee / details</th><th>Annual allocated / available</th><th>Leave taken this month</th><th>HR absent days</th><th>Late days / time</th><th>Scheduled hours — full month</th><th>Expected hours due</th><th>Recorded office hours</th><th>After 6 PM days / hours</th><th>Missing check-in / review</th></tr></thead><tbody></tbody></table></div></section>').appendTo(root);
        function drawRows(){
            const rows=data.employees.filter(e=>(!company||e.company===company)&&(!department||e.department===department)&&(!search||`${e.employee_name} ${e.employee}`.toLowerCase().includes(search.toLowerCase())));
            root.find('.hr-review-count').text(`${rows.length} employees · Select an employee for daily evidence and HR actions.`);
            const tbody=panel.find('tbody').empty();
            rows.forEach(e=>{const t=e.totals,a=e.annual;const tr=$('<tr>').appendTo(tbody),cell=$('<td>').appendTo(tr);
                $('<button>').text(e.employee_name).on('click',()=>detail(e)).appendTo(cell);$('<span class="hr-review-small">').text(`${e.employee} · ${e.department||'No team'}`).appendTo(cell);
                if(e.review_days)$('<span class="hr-review-badge">').text(`${e.review_days} dates need review`).appendTo(cell);
                tr.append(`<td>${number(a.allocated)} / <b>${number(a.available)}</b><span class="hr-review-small">Balance: ${esc(a.balance??'—')} · ${esc(a.source==='hrms'?'HRMS':a.source==='reference'?'Excel reference':a.source)}</span></td><td>${number(e.leave_taken)}<span class="hr-review-small">Annual: ${number(e.annual_taken)}</span></td><td>${number(t.hr_absent)}</td><td>${number(t.late_day)} / ${hours(t.late_minutes)}</td><td>${hours(t.scheduled_minutes)}</td><td>${hours(t.expected_due_minutes)}<span class="hr-review-small">To date; approved leave deducted</span></td><td>${hours(t.office_minutes)}<span class="hr-review-small">Completed pairs only</span></td><td>${number(t.after_day)} / ${hours(t.after_minutes)}</td><td>${number(t.missing_checkin)} / ${e.review_days}<span class="hr-review-small">Missing punches ≠ confirmed absence</span></td>`);
            });
            if(!rows.length)tbody.append('<tr><td colspan="10">No matching employee records.</td></tr>');
        }
        drawRows();
        $('<p class="hrm-foot">').text('Scheduled hours follow the assigned shift and holiday calendar, within joining/relieving dates. Late time is measured from the scheduled start, without a grace deduction, only on complete days without approved leave/on-duty. Older check-in records may not identify their source; the report does not assume they are genuine app punches or change them.').appendTo(root);
    }
    async function load(){const id=++request;root.html('<div class="hrm-empty">Loading employee attendance and leave…</div>');try{const r=await frappe.call({method:'bsgroup.hr_monthly_review.report',args:{month}});if(id!==request||!root[0].isConnected)return;data=r.message;render();}catch(e){if(id===request&&root[0].isConnected)root.html('<div class="hrm-empty">The monthly review could not load. Please use Refresh or check HR access.</div>');}}
    await load();
};
