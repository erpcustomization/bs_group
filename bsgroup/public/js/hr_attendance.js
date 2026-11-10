/* HR monthly calendar: recorded punches, leave decisions and HR attendance. */
window.bsHRAttendance = function(main) {
    const esc = value => frappe.utils.escape_html(String(value ?? ''));
    const host = $('<div class="hrcal">').appendTo(main);
    const controls = $('<div class="hrcal-controls">').appendTo(host);
    const employee = $('<select class="form-control" aria-label="Employee">').appendTo($('<label>Employee</label>').appendTo(controls));
    const month = $('<input type="month" class="form-control" aria-label="Attendance month">').val(frappe.datetime.get_today().slice(0,7)).appendTo($('<label>Month</label>').appendTo(controls));
    const body = $('<div>').appendTo(host);
    let data, sequence=0;
    if(!document.getElementById('hrcal-style')) $('<style id="hrcal-style">').text(`
      .hrcal-controls{display:flex;gap:14px;flex-wrap:wrap;margin:0 0 18px}.hrcal-controls label{font-size:12px;color:#627587;min-width:180px}.hrcal-controls select{min-width:280px}.hrcal-controls .form-control{margin-top:6px}
      .hrcal-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:6px;margin:14px 0}.hrcal-weekday{padding:8px;font-size:11px;color:#738496;text-align:center}.hrcal-day{border:1px solid #dfe7ed;border-radius:10px;background:#fff;min-height:106px;padding:10px;text-align:left;color:#193047;display:flex;flex-direction:column;gap:5px;cursor:pointer}.hrcal-day:hover{border-color:#27948e;box-shadow:0 2px 10px #16334612}.hrcal-day strong{font-size:14px}.hrcal-day small{font-size:10px;line-height:1.4;overflow-wrap:anywhere}.hrcal-day.has-punch{border-top:3px solid #268b7f}.hrcal-day.has-leave{background:#eff4fb;border-top:3px solid #6487b5}.hrcal-day.has-pending{border-bottom:3px solid #caa266}.hrcal-day.is-future{color:#718294;background:#fafbfd}.hrcal-day.is-today strong{color:#087c75}.hrcal-note{font-size:11px;color:#738496;margin:10px 0}.hrcal-summary{display:flex;gap:12px;flex-wrap:wrap}.hrcal-summary span{background:#edf3f7;border-radius:7px;padding:7px 10px;font-size:12px}.hrcal-detail h5{margin:18px 0 8px;font-size:13px}.hrcal-detail p{font-size:12px}.hrcal-detail a{color:#215b79}.hrcal-time{font-variant-numeric:tabular-nums}
      @media(max-width:760px){.hrcal-day{padding:6px;min-height:90px}.hrcal-day small{font-size:9px}.hrcal-grid{gap:3px}.hrcal-controls select{min-width:200px}}
    `).appendTo(document.head);
    const link = (dt,name,label) => `<a href="/desk/${frappe.router.slug(dt)}/${encodeURIComponent(name)}">${esc(label || name)}</a>`;
    const clock = row => String(row.time).slice(11,16);
    const leaveLabel = row => `${row.leave_type} · ${row.approved?'Approved':row.status==='Approved'?'Approved · not submitted':row.status}${row.is_half_day?' · half day':''}`;
    function detail(day) {
        const d = new frappe.ui.Dialog({title: `${employee.find(':selected').text()} · ${frappe.datetime.str_to_user(day.date)}`,size:'large',fields:[{fieldname:'details',fieldtype:'HTML'}]});
        let html='<div class="hrcal-detail"><h5>Recorded check-in / check-out</h5>';
        html += day.punches.length ? `<table class="hrm-table"><tr><th>Type</th><th>Time</th><th>Location</th><th>Record</th></tr>${day.punches.map(p=>`<tr><td>${esc(p.log_type || 'Unspecified')}</td><td class="hrcal-time">${esc(clock(p))}</td><td>${esc(p.location || 'Location not recorded')}</td><td>${link('Employee Checkin',p.name)}</td></tr>`).join('')}</table>` : '<p>No check-in or check-out records for this date.</p>';
        html += '<h5>Leave applications</h5>' + (day.leaves.length ? day.leaves.map(l=>`<p>${link('Leave Application',l.name,leaveLabel(l))}</p>`).join('') : '<p>No leave application for this date.</p>');
        html += '<h5>HR attendance records</h5>' + (day.attendance.length ? day.attendance.map(a=>`<p>${link('Attendance',a.name,`${a.status} · ${a.docstatus===1?'Submitted':'Draft'} · ${a.name}`)}</p>`).join('') : '<p>No HR attendance record.</p>');
        html += '<h5>Attendance requests</h5>' + (day.requests.length ? day.requests.map(r=>`<p>${link('Attendance Request',r.name,`${r.reason} · ${r.docstatus===1?'Submitted':'Draft'}${r.is_half_day?' · half day':''}`)}</p>`).join('') : '<p>No attendance request.</p>');
        html += '<p class="hrcal-note">HR attendance is shown separately from recorded punches. Missing punches do not automatically mean absence. Use the existing record’s correction or amendment process when attendance has already been recorded.</p></div>';
        d.fields_dict.details.$wrapper.html(html);
        if(data.can_record && !day.future && !day.attendance.length) d.set_primary_action('Record HR attendance',()=>{d.hide();manual(day);});
        d.show();
    }
    function manual(day) {
        const d = new frappe.ui.Dialog({title:'Record attendance upon employee request',fields:[
            {fieldname:'context',fieldtype:'HTML',options:`<p>${esc(employee.find(':selected').text())} · ${esc(frappe.datetime.str_to_user(day.date))}</p><p class="text-muted">This prepares an HR attendance draft. Review and submit it using the existing HRMS controls. It does not create or change check-in/out times.</p>`},
            {fieldname:'employee_request',label:'Employee request',fieldtype:'Link',options:'HR Service Request',reqd:1,get_query:()=>({filters:{employee:data.employee}}),description:'Select the HR request documenting the employee’s correction request.'},
            {fieldname:'status',label:'Attendance status',fieldtype:'Select',options:['Present','Absent','Half Day','Work From Home'],reqd:1},
            {fieldname:'reason',label:'HR reason / verification',fieldtype:'Small Text',reqd:1}
        ],primary_action_label:'Prepare attendance draft',primary_action:async values=>{
            d.get_primary_btn().prop('disabled',true);
            try {
                const r=await frappe.call({method:'bsgroup.hr_attendance.record_manual',type:'POST',freeze:true,args:{...values,employee:data.employee,attendance_date:day.date}});
                d.hide();frappe.set_route('Form','Attendance',r.message.name);
            } finally {d.get_primary_btn().prop('disabled',false);}
        }});
        d.show();
    }
    function render() {
        body.empty();
        if(!data.employees.length){body.html('<div class="hrm-empty">No employee profiles are available in your permitted view.</div>');return;}
        const days=data.days;
        if(data.repair_mithun) $('<button class="btn btn-default btn-sm">').text('Correct reviewed absences: 6–7 November').on('click',async function(){
            $(this).prop('disabled',true);
            try {
                const r=await frappe.call({method:'bsgroup.hr_attendance.repair_mithun_november',type:'POST',freeze:true});
                frappe.msgprint({title:'Attendance corrected',message:r.message.map(x=>`${esc(x.date)}: ${link('Attendance',x.name,x.status+' · '+x.name)}`).join('<br>')});
                await load();
            } finally {$(this).prop('disabled',false);}
        }).appendTo(body);
        const summary=$('<div class="hrcal-summary">').appendTo(body);
        const approved=days.filter(d=>d.leaves.some(l=>l.approved)).length;
        const pending=days.filter(d=>d.leaves.some(l=>!l.approved && !['Rejected','Cancelled'].includes(l.status))).length;
        [`${days.filter(d=>d.punches.some(p=>p.log_type==='IN')).length} days with check-in`,`${approved} dates with approved leave`,`${pending} dates with pending leave`].forEach(text=>$('<span>').text(text).appendTo(summary));
        if(data.restricted.length)$('<p class="hrcal-note">').text(`Restricted by your access: ${data.restricted.join(', ')}. This calendar may be incomplete.`).appendTo(body);
        const grid=$('<div class="hrcal-grid" aria-label="Monthly employee attendance calendar">').appendTo(body);
        ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].forEach(day=>$('<div class="hrcal-weekday">').text(day).appendTo(grid));
        const offset=(new Date(month.val()+'-01T12:00:00').getDay()+6)%7;
        for(let i=0;i<offset;i++)$('<div aria-hidden="true">').appendTo(grid);
        days.forEach(day=>{
            const ins=day.punches.filter(p=>p.log_type==='IN'), outs=day.punches.filter(p=>p.log_type==='OUT');
            const approved=day.leaves.filter(l=>l.approved), pending=day.leaves.filter(l=>!l.approved && !['Rejected','Cancelled'].includes(l.status));
            const labels=[];
            if(ins.length)labels.push(`IN ${clock(ins[0])} · ${ins[0].location || 'Location not recorded'}`);
            if(outs.length)labels.push(`OUT ${clock(outs[outs.length-1])} · ${outs[outs.length-1].location || 'Location not recorded'}`);
            if(!day.punches.length) labels.push(day.future?'Upcoming':'No punches recorded');
            if(day.punches.length>2)labels.push(`${day.punches.length} punch records`);
            approved.forEach(l=>labels.push(`${l.is_half_day?'½ day ':''}${l.leave_type} · approved`));
            if(pending.length)labels.push('Leave pending');
            day.attendance.forEach(a=>labels.push(`HR: ${a.status}${a.docstatus===0?' · draft':''}`));
            day.requests.forEach(r=>labels.push(`${r.reason}${r.docstatus===0?' · draft':''}`));
            $('<button type="button" class="hrcal-day">').toggleClass('has-punch',!!day.punches.length).toggleClass('has-leave',!!approved.length).toggleClass('has-pending',!!pending.length).toggleClass('is-future',day.future).toggleClass('is-today',day.date===data.today)
                .attr('aria-label',`${day.date}: ${labels.join('; ')}`).attr('title',labels.join('\n')).html(`<strong>${Number(day.date.slice(-2))}</strong>${labels.map(t=>`<small>${esc(t)}</small>`).join('')}`).on('click',()=>detail(day)).appendTo(grid);
        });
        $('<p class="hrcal-note">').text('Select a date for every recorded check-in/out, leave decision and HR attendance record. Times follow the ERP site timezone. No punches recorded is not an absence decision. Manual HR attendance does not replace original punches.').appendTo(body);
    }
    async function load() {
        const token=++sequence;
        body.html('<div class="hrm-empty">Loading monthly attendance…</div>');
        try {
            const r=await frappe.call({method:'bsgroup.hr_attendance.month_view',args:{month:month.val(),employee:employee.val() || undefined}});
            if(token!==sequence || !host[0].isConnected)return;
            data=r.message;
            employee.empty();
            data.employees.forEach(e=>$('<option>').val(e.name).text(`${e.employee_name} · ${e.name}${e.status==='Active'?'':' · '+e.status}`).appendTo(employee));
            employee.val(data.employee);render();
        }catch(e){if(token===sequence && host[0].isConnected)body.html('<div class="hrm-empty">Attendance could not load. Check your access or refresh.</div>');}
    }
    employee.on('change',load);month.on('change',()=>{if(month.val())load();});
    load();
};
