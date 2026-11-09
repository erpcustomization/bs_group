const fs=require('fs'),vm=require('vm'),assert=require('assert');
const doctypes=['Lead','Opportunity','Presales Request','Deal Cost Sheet','Quotation'];
const settings=Object.fromEntries(doctypes.map(dt=>[dt,{}]));
vm.runInNewContext(fs.readFileSync(require('path').join(__dirname,'../bsgroup/public/js/sales_filter_popup.js'),'utf8'),{frappe:{listview_settings:settings}});
async function check(doctype,popup){
    let hidden='Converted', refreshed=false;
    const area={trigger_refresh:true,get_standard_filters:()=>[[doctype,'status','=','Converted']],
        filter_list:{get_filters:()=>popup,async add_filters(filters){popup.push(...filters);},update_filter_button(){}}};
    const view={filter_area:area,page:{fields_dict:{status:{async set_value(v){assert(!area.trigger_refresh);hidden=v;}}}},before_refresh(){refreshed=true;}};
    settings[doctype].onload(view);
    await view.before_refresh();
    assert.equal(hidden,'');assert(refreshed);assert(area.trigger_refresh);
    assert.equal(popup.length,1,'a restored filter is visible exactly once');
    assert.equal(popup[0][3],doctype==='Lead'?'Converted':'Open','explicit popup selection takes precedence over stale hidden state');
    const routed=[[doctype,'status','=','Closed']];
    assert.equal(area.set_standard_filter(routed).non_standard_filters,routed);
}
(async()=>{
    await check('Lead',[]);
    for(const dt of doctypes.slice(1)) await check(dt,[[dt,'status','=','Open']]);
    for(const [dt,field,operator,value] of [
        ['Quotation','customer_name','like','%al zo%'],
        ['Quotation','custom_pipeline_stage','=','Won'],
        ['Deal Cost Sheet','name','like','%aki%'],
        ['Presales Request','status','=','Open'],
    ]) {
        const saved=[[dt,field,operator,value]], popup=[[dt,'docstatus','!=','2']];
        let hidden=value, counted, refreshed=false, previousCalled=false;
        const area={trigger_refresh:true,get_standard_filters:()=>saved,
            filter_list:{get_filters:()=>popup,async add_filters(filters){popup.push(...filters);},update_filter_button(){counted=popup.length;}}};
        const view={filter_area:area,page:{fields_dict:{[field]:{async set_value(v){assert(!area.trigger_refresh);hidden=v;}}}},
            before_refresh(){previousCalled=true;assert.equal(counted,2);refreshed=true;}};
        settings[dt].onload(view);
        await view.before_refresh();
        assert.equal(hidden,'');assert.deepEqual(popup,[ [dt,'docstatus','!=','2'], ...saved ]);
        assert(refreshed && previousCalled && area.trigger_refresh);
        settings[dt].onload(view);
        await view.before_refresh();
        assert.equal(popup.length,2,'repeated initialization must not duplicate filters');
        const routed=[[dt,field,operator,value]];
        assert.equal(area.set_standard_filter(routed).non_standard_filters,routed);
    }
    console.log('PASS all five lists: restored filters, customer/pipeline/ID filters, counts, route filters, conflicts, repeated initialization and refresh ordering');
})().catch(e=>{console.error(e);process.exitCode=1;});
