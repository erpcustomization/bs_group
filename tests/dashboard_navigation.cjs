const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
class Element {
 constructor(){this.children=[];this.style={};this.className='';this.dataset={};this.classList={contains:c=>this.className.split(' ').includes(c),toggle:(c,on)=>{const s=new Set(this.className.split(' ').filter(Boolean));on?s.add(c):s.delete(c);this.className=[...s].join(' ');},remove:c=>this.classList.toggle(c,false)};}
 append(child){child.parent=this;this.children.push(child);}
 prepend(child){child.parent=this;this.children.unshift(child);}
 remove(){this.parent.children=this.parent.children.filter(x=>x!==this);}
 querySelector(selector){return this.children.find(x=>x.classList.contains(selector.slice(1))) || null;}
}
for(const scoped of [false,true]) {
 const host=new Element(),native=new Element();host.append(native);
 const document={body:{},head:new Element(),createElement:()=>new Element(),querySelectorAll:s=>s.includes('data-title')?[]:[host]};
 const location={href:'https://erp.bitssecureit.com/desk/private/my-work-dashboard',pathname:'/desk/private/my-work-dashboard'};
 const window={};window.top=window;window.self=window;
 const observers=[],changes=[],timers=[];
 const context={document,location,window,URL,__:s=>s,sessionStorage:{getItem:()=>null,setItem(){}},
  frappe:{session:{user:'employee@example.com'},boot:{bs_work_dashboard:true,bs_app_destinations:{'BS Project':'/desk/bs-group/project','BS HR':null},bs_scoped_screens:scoped?['Quotation']:null},router:{on:(_,fn)=>changes.push(fn)}},
  setTimeout:fn=>timers.push(fn),MutationObserver:class{constructor(fn){observers.push(fn);}observe(){}},$:()=>({on(){}})};
 const run=()=>{for(const fn of changes)fn();while(timers.length)timers.shift()();};
 for(const name of ['scoped_sales_access','app_sidebar'])vm.runInNewContext(fs.readFileSync('bsgroup/public/js/'+name+'.js','utf8'),context);
 const menu=host.querySelector('.bs-dashboard-modules');
 assert(menu);assert.equal(menu.children.length,7);assert(native.classList.contains('bs-dashboard-hidden'));
 assert.equal(menu.children.filter(x=>x.className==='bs-dashboard-category').length,4);
 for(const section of menu.children.filter(x=>x.className==='bs-dashboard-category'))assert.equal(section.children.length,3);
 assert.equal(menu.children[1].children[0].textContent,'All apps');
 for(let i=0;i<5;i++){observers.forEach(fn=>fn());while(timers.length)timers.shift()();}
 assert.equal(host.children.filter(x=>x.classList.contains('bs-dashboard-modules')).length,1);
 location.pathname='/desk/bs-group/project';location.href='https://erp.bitssecureit.com'+location.pathname;run();
 assert(!host.querySelector('.bs-dashboard-modules'));assert(!native.classList.contains('bs-dashboard-hidden'));
 location.pathname='/desk/my-work-dashboard';location.href='https://erp.bitssecureit.com'+location.pathname;run();
 assert(host.querySelector('.bs-dashboard-modules'));assert.equal(host.querySelector('.bs-dashboard-modules').style.display,undefined);
}
console.log('PASS Private dashboard, scoped and normal users, repeated rendering, no duplicates, navigation away and return');
