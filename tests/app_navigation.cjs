const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('bsgroup/public/js/app_navigation.js','utf8');
const tile=(id)=>({dataset:{id},href:'/desk/bs-group/lead',getAttribute(){return this.href;},setAttribute(k,v){this[k]=v;}});
const sales=tile('BS Sales'),hr=tile('BS HR'),project=tile('BS Project'),native=tile('Buying');
const routes={'BS Sales':'/desk/bs-group/lead','BS HR':null,'BS Project':'/desk/bs-group/project'};
let click,observer,change;const destinations=[],timers=[];
const window={location:{assign:r=>destinations.push(r)}};window.self=window;window.top=window;
const document={body:{},querySelectorAll:()=>[sales,hr,project,native],addEventListener:(e,fn)=>click=fn};
vm.runInNewContext(source,{window,document,frappe:{boot:{bs_app_destinations:routes},router:{on:(e,fn)=>change=fn}},setTimeout:fn=>timers.push(fn),MutationObserver:class{constructor(fn){observer=fn;}observe(){}}});
assert.equal(project.href,routes['BS Project']);assert.equal(hr.hidden,true);assert.equal(native.hidden,undefined);
function activate(t,extra={}){let stopped=false;click({target:{closest:s=>s==='.hide-button'?null:t},preventDefault(){stopped=true;},stopImmediatePropagation(){},...extra});return stopped;}
assert(activate(project));assert.deepEqual(destinations,[routes['BS Project']]);
assert(activate(hr));assert.equal(destinations.length,1);assert.equal(activate(native),false);
assert.equal(activate(project,{ctrlKey:true}),false);assert.equal(destinations.length,1);
project.href='/desk/bs-group/lead';observer();change();while(timers.length)timers.shift()();assert.equal(project.href,routes['BS Project']);
console.log('PASS module destinations, denied tiles, native apps, modified clicks and async rerender');
