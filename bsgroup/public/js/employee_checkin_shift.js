// Keep the standard Employee Checkin list on the same shift-aware state as BS ERP.
// Native confirmation, location collection and insertion remain unchanged.
if (typeof refresh_checkin_state === 'function' && typeof get_next_checkin === 'function') {
    refresh_checkin_state = async function (listview) {
        if (!listview?.checkin_employee) return;
        try {
            const state = await frappe.xcall('bsgroup.dashboard_punch.context');
            listview.next_checkin = get_next_checkin(state.can_check_out ? 'IN' : 'OUT');
            listview.set_primary_action();
            listview.page.btn_primary.prop('disabled', !state.allowed);
        } catch (error) {
            listview.page.btn_primary.prop('disabled', true);
        }
    };
}
