// Show the business status of pilot offers while their native document is Draft.
(() => {
    if (!frappe.meta.has_field('Quotation','custom_oman_flow')) return;
    const proto=frappe.views.ListView.prototype;
    if(proto._oman_quote_indicator_installed) return;
    proto._oman_quote_indicator_installed=true;
    const getArgs=proto.get_args,beforeRender=proto.before_render;
    proto.get_args=function(...args){
        const result=getArgs.apply(this,args);
        if(this.doctype==='Quotation') {
            result.fields=[...(result.fields||[])];
            for(const field of ['custom_oman_flow','custom_pipeline_stage']) {
                const name='`tabQuotation`.`'+field+'`';
                if(!result.fields.includes(name)) result.fields.push(name);
            }
        }
        return result;
    };
    proto.before_render=function(...args){
        if(this.doctype==='Quotation' && !this.settings.get_indicator?._oman_pilot){
            const original=this.settings.get_indicator;
            const indicator=function(row){
                if(row.custom_oman_flow){
                    const stage=row.custom_pipeline_stage||'Draft';
                    const colors={Won:'green',Lost:'red',Delayed:'orange',Cancelled:'gray',Sent:'blue','Follow-up':'orange',Expired:'gray',Draft:'gray'};
                    return [stage,colors[stage]||'gray','custom_pipeline_stage,=,'+stage];
                }
                return original?.call(this,row);
            };
            indicator._oman_pilot=true;
            this.settings.get_indicator=indicator;
            this.settings.has_indicator_for_draft=true;
        }
        return beforeRender.apply(this,args);
    };
})();
