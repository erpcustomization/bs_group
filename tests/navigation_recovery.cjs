const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('bsgroup/public/js/navigation_recovery.js','utf8');
function scenario({mobile=false,iframe=false,dock=false}={}) {
 let collapsed=true,clicks=0,created,observer;const timers=[];
 const toggle={click(){clicks++;collapsed=!collapsed;}};
 const sidebar={querySelector:s=>s.includes('collapse')?toggle:{href:'/desk/allowed-only'}};
 const body={dataset:{route:'my-work-dashboard'},classList:{contains:()=>collapsed},appendChild:e=>created=e};
 const document={body,createElement:()=>({setAttribute(){},addEventListener(type,fn){this[type]=fn;}}),querySelector:s=>s.includes('collapse')?toggle:sidebar,querySelectorAll:()=>dock?[{getBoundingClientRect:()=>({width:30,height:30})}]:[]};
 const window={innerWidth:mobile?600:1280,addEventListener(){}};window.self=window;window.top=iframe?{}:window;
 vm.runInNewContext(source,{window,document,__:s=>s,getComputedStyle:()=>({display:'block',visibility:'visible'}),setTimeout:fn=>timers.push(fn),MutationObserver:class{constructor(fn){observer=fn;}observe(){}}});
 const tick=()=>{while(timers.length)timers.shift()();};tick();
 return {tick,body,get collapsed(){return collapsed;},get clicks(){return clicks;},get button(){return created;},change(){observer();},collapse(){collapsed=true;observer();tick();}};
}
let s=scenario();assert.equal(s.clicks,1);assert.equal(s.collapsed,false);
s.change();s.tick();assert.equal(s.button.hidden,true);
s.collapse();assert.equal(s.clicks,1);assert.equal(s.button.hidden,false);s.button.click();assert.equal(s.collapsed,false);
s=scenario({dock:true});assert.equal(s.clicks,0);assert.equal(s.button.hidden,false);
s=scenario({mobile:true});assert.equal(s.clicks,0);s.button.click();assert.equal(s.collapsed,false);
s=scenario({iframe:true});assert.equal(s.clicks,0);assert.equal(s.button,undefined);
console.log('PASS empty-rail recovery, deliberate collapse, visible rail, mobile reopening and popup exclusion');
