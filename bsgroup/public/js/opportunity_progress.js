(() => {
    async function render(frm) {
        const root = frm.wrapper[0] || frm.wrapper;
        const bar = root.querySelector('.bsi-opportunity-status');
        if (!bar) return;
        frm.set_df_property('status', 'hidden', 1);
        let badge = bar.querySelector('.bsi-progress-status');
        if (!badge) {
            const label = document.createElement('span');
            label.textContent = __('Status');
            label.style.cssText = 'align-self:center;font-weight:600;margin-right:10px';
            badge = document.createElement('span');
            badge.className = 'bsi-progress-status';
            badge.setAttribute('role', 'status');
            badge.style.cssText = 'padding:8px 12px;border-radius:8px;font-weight:600;line-height:18px;max-width:100%;white-space:normal';
            bar.append(label, badge);
        }
        let progress = {label:'Open', color:'purple'};
        if (!frm.is_new()) {
            const name = frm.doc.name;
            const result = await frappe.call({method:'bsgroup.opportunity_progress.statuses',args:{names:[name]}});
            if (name !== frm.doc.name || !result.message?.[name]) return;
            progress = result.message[name];
        }
        badge.textContent = __(progress.label);
        const colors = {purple:['#ddd6fe','#5b21b6'],blue:['#e3edff','#174e9b'],red:['#fee2e2','#b91c1c'],green:['#dcfce7','#166534'],orange:['#fff0d6','#9a5700']};
        const palette = colors[progress.color] || colors.blue;
        badge.style.background = palette[0];
        badge.style.color = palette[1];
        badge.title = progress.started ? __('Stage started') + ': ' + frappe.datetime.str_to_user(progress.started) : '';
        frm.page.set_indicator(__(progress.label), progress.color);
    }
    frappe.ui.form.on('Opportunity', {
        refresh(frm) {
            clearInterval(frm._progress_timer);
            render(frm);
            frm._progress_timer = setInterval(() => {
                const root = frm.wrapper[0] || frm.wrapper;
                if (!root.isConnected || !root.getClientRects().length) { clearInterval(frm._progress_timer); return; }
                render(frm);
            }, 60000);
        },
        status(frm) { render(frm); }
    });
})();
