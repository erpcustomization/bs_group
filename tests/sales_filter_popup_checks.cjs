const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('path').join(__dirname,'../bsgroup/public/js/sales_filter_popup.js'),'utf8');
class ListView { before_refresh(...args) {this.refreshed=(this.refreshed||0)+1;this.args=args;return 'native';} }
const context={frappe:{views:{ListView},listview_settings:{}}};
vm.runInNewContext(source,context);
const installed=ListView.prototype.before_refresh;
vm.runInNewContext(source,context);
assert.equal(ListView.prototype.before_refresh,installed,'reloading the shared script must not wrap twice');
function fixture(dt,saved,popup=[]) {
    const view=new ListView();view.doctype=dt;
    view.filter_area={trigger_refresh:true,get_standard_filters:()=>saved,
        filter_list:{get_filters:()=>popup,async add_filters(filters){popup.push(...filters);},update_filter_button(){view.count=popup.length;}}};
    view.values=Object.fromEntries(saved.map(f=>[f[1],f[3]]));
    view.page={fields_dict:Object.fromEntries(saved.map(f=>[f[1],{async set_value(v){assert.equal(view.filter_area.trigger_refresh,false);view.values[f[1]]=v;}}]))};
    view.popup=popup;return view;
}
(async()=>{
    for(const dt of ['Lead','Opportunity','Presales Request','Deal Cost Sheet','Quotation']) {
        const saved=[[dt,'status','=','Open']],view=fixture(dt,saved);
        assert.equal(await view.before_refresh('keep'), 'native');
        assert.equal(view.values.status,'');assert.deepEqual(view.popup,saved);assert.equal(view.count,1);
        assert.deepEqual(view.args,['keep']);assert.equal(view.filter_area.trigger_refresh,true);
        await view.before_refresh();assert.equal(view.popup.length,1);
        const routed=[[dt,'status','=','Closed']];
        assert.equal(view.filter_area.set_standard_filter(routed).non_standard_filters,routed);
    }
    for(const [dt,field,op,value] of [
        ['Quotation','customer_name','like','%al zo%'],['Quotation','custom_pipeline_stage','=','Won'],
        ['Deal Cost Sheet','name','like','%aki%'],['Presales Request','status','=','Open']
    ]) {
        const saved=[[dt,field,op,value]],popup=[[dt,'docstatus','!=','2']],view=fixture(dt,saved,popup);
        // Reproduce UAE's database Client Script replacing the entire settings object.
        context.frappe.listview_settings[dt]={onload(v){v.hide_cancelled_retained=true;}};
        context.frappe.listview_settings[dt].onload(view);
        await Promise.all([view.before_refresh(),view.before_refresh()]);
        assert(view.hide_cancelled_retained);assert.equal(view.count,2);
        assert.deepEqual(view.popup,[[dt,'docstatus','!=','2'],...saved]);
        assert.equal(view.filter_area.trigger_refresh,true);assert.equal(view.values[field],'');
    }
    const conflict=fixture('Opportunity',[['Opportunity','status','=','Converted']],[['Opportunity','status','=','Open']]);
    await conflict.before_refresh();assert.equal(conflict.popup.length,1);assert.equal(conflict.popup[0][3],'Open');
    const other=fixture('Customer',[['Customer','customer_name','like','%indian%']]);
    await other.before_refresh();assert.equal(other.popup.length,0);assert.equal(other.values.customer_name,'%indian%');
    const noArea=new ListView();noArea.doctype='Quotation';await noArea.before_refresh();assert.equal(noArea.refreshed,1);
    const failed=fixture('Quotation',[['Quotation','customer_name','like','%test%']]);
    failed.filter_area.filter_list.add_filters=async()=>{throw Error('test failure');};
    await assert.rejects(failed.before_refresh(),/test failure/);assert.equal(failed.filter_area.trigger_refresh,true);
    console.log('PASS five lists, UAE handler replacement, saved/route filters, counts, conflicts, concurrent refresh, repeated installation, native return and failure cleanup');
})().catch(e=>{console.error(e);process.exitCode=1;});
