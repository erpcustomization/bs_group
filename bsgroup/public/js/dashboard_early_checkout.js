/* Separate, overlapping attendance indicator: never inflate the arrival donut. */
(() => {
    if (window.bsEarlyCheckout) return;
    window.bsEarlyCheckout = {mount(wrapper) {
        if (!['mohan@bitssecureit.com', 'Administrator'].includes(frappe.session.user)) return;
        if (wrapper.bsEarlyCheckout) { wrapper.bsEarlyCheckout.refresh(); return; }
        const root = $(wrapper);
        const card = $('<section class="bs-early-checkout" aria-label="Early checkout">');
        const button = $('<button type="button" class="btn btn-default btn-sm" aria-label="Early checkout. Loading">').text('…');
        let data, serial=0, loadedDay='', lastFetch=0, pendingDay='', observedDay='';
        const executiveDate = () => root.find('input[aria-label="Executive reporting date"]');
        const dateInput = $('<input type="date" aria-label="Early checkout reporting date">').val(frappe.datetime.get_today()).attr('max',frappe.datetime.get_today());
        const day = () => executiveDate().val() || dateInput.val();
        const note = 'Before assigned shift end. May overlap on-time or late arrivals. Approved leave/duty and off days excluded. Checking back in clears the indicator.';
        function showDetails() {
            if (!data) return;
            const dialog = new frappe.ui.Dialog({title:__('Early checkout'),size:'large',fields:[{fieldname:'records',fieldtype:'HTML'}]});
            const body = dialog.fields_dict.records.$wrapper;
            $('<p>').text(`${data.day} · ${data.count} employee(s)`).appendTo(body);
            $('<p>').text(note).css({fontSize:'12px',color:'#64748b'}).appendTo(body);
            if (!data.details.length) $('<p>').text('No recorded early checkouts for this date.').appendTo(body);
            else {
                const table=$('<table class="table table-bordered">').appendTo($('<div>').css({overflowX:'auto'}).appendTo(body));
                const header=$('<tr>').appendTo($('<thead>').appendTo(table));
                ['Employee','Shift','Check-in','Check-out','Shift end','Minutes early'].forEach(label=>$('<th>').text(label).appendTo(header));
                const rows=$('<tbody>').appendTo(table);
                const stamp=value=>new Date(value).toLocaleString('en-GB',{timeZone:'Asia/Dubai',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
                data.details.forEach(item=>{
                    const row=$('<tr>').appendTo(rows);
                    [item.employee_name,item.shift,stamp(item.checkin),stamp(item.checkout),stamp(item.shift_end),item.minutes_early].forEach(value=>$('<td>').text(value).appendTo(row));
                });
            }
            dialog.show();
        }
        button.on('click',showDetails);
        function place() {
            if (card[0].isConnected) return;
            if (root.find('.bs-exec').length) {
                const rows=root.find('.ex-attendance').children().last();
                if (!rows.length) return;
                card.addClass('ex-att-row').css({borderTop:'1px solid #e7edf3',marginTop:'5px',paddingTop:'8px'});
                card.empty().append($('<span class="ex-dot">').css('background','#bd6d48'),$('<span>').text('Early checkout'),button);
                card.attr('title',note).appendTo(rows);
            } else {
                const work=root.find('.bs-work');
                if (!work.length) return;
                card.css({background:'#fff',border:'1px solid #dfe7ed',borderRadius:'12px',padding:'16px 20px',marginBottom:'16px'});
                const heading=$('<div>').css({display:'flex',alignItems:'center',gap:'14px',flexWrap:'wrap'});
                card.empty().append(heading,$('<p>').text(note).css({fontSize:'12px',color:'#64748b',margin:'8px 0 0'}));
                heading.append($('<strong>').text('Early checkout'),button,$('<label>').text('Reporting date ').append(dateInput));
                card.insertBefore(work);
            }
        }
        async function refresh(force=true) {
            place();
            const selected=day();
            if (!selected || pendingDay===selected || (!force && loadedDay===selected && Date.now()-lastFetch<300000)) return;
            observedDay=selected;
            const request=++serial;
            pendingDay=selected; data=null; button.text('…').prop('disabled',true);
            try {
                const response=await frappe.call({method:'bsgroup.dashboard_early_checkout.summary',args:{day:selected},quiet:true});
                if (request!==serial || selected!==day()) return;
                data=response.message; loadedDay=selected; lastFetch=Date.now();
                button.text(data.count).prop('disabled',false).attr({'aria-label':`Early checkout. Show ${data.count} matching records.`,title:note});
            } catch (error) {
                if(request===serial) button.text('Unavailable').prop('disabled',true).attr('aria-label','Early checkout unavailable');
            } finally { if(request===serial) pendingDay=''; }
        }
        const observer=new MutationObserver(()=>{place(); if(day()!==observedDay) refresh(false);});
        observer.observe(wrapper,{childList:true,subtree:true});
        root.on('change.bsEarlyCheckout','input[aria-label="Executive reporting date"],input[aria-label="Early checkout reporting date"]',()=>refresh());
        root.on('click.bsEarlyCheckout','button',event=>{if($(event.currentTarget).text().includes('↻ Refresh')) refresh();});
        setInterval(()=>{if(root.is(':visible')) refresh(false);},60000);
        wrapper.bsEarlyCheckout={refresh};
        refresh();
    }};
})();
