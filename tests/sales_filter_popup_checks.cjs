const fs=require('fs'),vm=require('vm'),assert=require('assert');
const settings={Lead:{},Opportunity:{}};
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
(async()=>{await check('Lead',[]);await check('Opportunity',[['Opportunity','status','=','Open']]);console.log('PASS restored filters, conflicting hidden status, route filters, and refresh ordering');})().catch(e=>{console.error(e);process.exitCode=1;});
