(() => {
    const settings = frappe.listview_settings.Opportunity;
    const options = [
        'Open', 'Open with Site Survey Team', 'Pending from Site Survey Team',
        'Open with Presales', 'Delayed by Presales', 'Deal Cost Sheet in Progress',
        'Delayed Deal Cost Sheet', 'Site Survey Cancelled', 'Deal Cost Sheet Submitted',
        'Submitted to Sales', 'Ready for Quotation', 'Quoted', 'Quotation',
        'Completed', 'Won', 'Lost', 'Closed', 'Converted', 'Replied', 'Draft', 'Costing in Progress'
    ];
    function configureFilter(filter) {
        const fields = filter.fieldselect?.fields_by_name?.Opportunity;
        if (!fields?.status) return;
        // Copy only this filter's field definition, never the form's metadata.
        fields.status = {...fields.status, options: '\n' + options.join('\n')};
        if (filter.field?.df.fieldname === 'status' && filter.field.df.fieldtype === 'Select') {
            const value = filter.field.get_value();
            filter.field.df.options = fields.status.options;
            filter.field.refresh();
            if (value) filter.field.set_value(value);
        }
    }
    function install(listview) {
        const group = listview.filter_area?.filter_list;
        if (!group || listview._bsi_progress_filter) return;
        listview._bsi_progress_filter = true;
        listview.method = 'bsgroup.opportunity_progress_filter.get';
        const create = group._push_new_filter;
        group._push_new_filter = function(...args) {
            const filter = create.apply(this, args);
            if (filter) configureFilter(filter);
            return filter;
        };
        group.filters.forEach(configureFilter);
        const nativeCount = listview.get_count_str;
        listview.get_count_str = async function() {
            const filters = this.get_filters_for_args();
            if (!filters.some(f => f[0] === 'Opportunity' && f[1] === 'status')) {
                return nativeCount.call(this);
            }
            const response = await frappe.call({method:'bsgroup.opportunity_progress_filter.get_count',
                args:{doctype:'Opportunity',filters}});
            this.total_count = response.message;
            return __('{0} of {1}', [this.data.length, this.total_count]);
        };
    }
    const onload = settings.onload;
    settings.onload = function(listview) { onload?.call(this,listview); install(listview); };
    const refresh = settings.refresh;
    settings.refresh = function(listview) { install(listview); return refresh?.call(this,listview); };
})();
