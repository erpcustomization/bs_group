const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('bsgroup/public/js/attendance_widget.js','utf8');
const iso=t=>`2026-11-02T${t}:00+04:00`;
async function render(t,extra={},module='sales') {
 const now=new Date(iso(t)).getTime(),elements=[];
 const data={visible:true,shift_start:iso('09:00'),shift_end:iso('18:00'),lunch_start:iso('12:30'),lunch_end:iso('13:00'),wrapup_start:iso('17:30'),late_minutes:0,...extra};
 class Clock extends Date {static now(){return now;}}
 const document={body:{},querySelectorAll:s=>s==='.bs-attendance-widget'?elements:[],addEventListener(){},createElement:()=>({dataset:{}})};
 // Frappe returns a jQuery-style thenable, not a native Promise. In
 // particular it lacks finally(): the original first-load bug needs this.
 function deferred(promise) {
  return {then:(yes,no)=>deferred(promise.then(yes,no)),catch:no=>deferred(promise.catch(no))};
 }
 const frappe={utils:{escape_html:s=>s.replaceAll('<','&lt;')},call:()=>deferred(Promise.resolve({message:data})),get_route:()=>[],router:{on(){}}};
 const context={window:{},document,frappe,Date:Clock,MutationObserver:class{observe(){}},setInterval(){},setTimeout(){},clearTimeout(){}};
 vm.runInNewContext(source,context);
 context.window.bsAttendance.mount({querySelector:()=>null,prepend:el=>elements.push(el)},module);
 // Do not call refresh a second time: first mount must render by itself.
 await new Promise(resolve=>setImmediate(resolve));
 return elements[0];
}
(async()=>{
 assert((await render('08:30')).innerHTML.includes('check in on time'));
 assert((await render('09:01')).innerHTML.includes('NOT CHECKED IN'));
 assert((await render('10:00',{first_in:iso('09:01'),checked_in:true,late_minutes:1})).innerHTML.includes('LATE · 1 min'));
 assert((await render('12:45',{first_in:iso('09:00'),checked_in:true})).innerHTML.includes('LUNCH BREAK'));
 assert((await render('13:01',{first_in:iso('09:00'),checked_in:true})).innerHTML.includes('keep the momentum'));
 for(const [module,phrase] of Object.entries({sales:'quotations',projects:'timesheet',procurement:'PRs and POs',accounts:"post today",helpdesk:'tickets'}))
  assert((await render('17:30',{first_in:iso('09:00'),checked_in:true},module)).innerHTML.includes(phrase));
 assert((await render('18:01',{first_in:iso('09:00'),checked_in:true})).innerHTML.includes('please check out'));
 const out=(await render('18:10',{first_in:iso('09:04'),last_out:iso('18:02'),worked_minutes:538,late_minutes:4})).innerHTML;
 assert(out.includes('8h 58m')&&out.includes('LATE · 4 min'));
 assert((await render('17:00',{first_in:iso('09:00'),last_out:iso('17:00'),worked_minutes:480,early_exit_minutes:60})).innerHTML.includes('LEFT EARLY'));
 assert(!(await render('10:00',{on_duty:true})).innerHTML.includes('NOT CHECKED IN'));
 assert((await render('10:00',{on_leave:true})).innerHTML.includes("You're on leave"));
 assert((await render('10:00',{is_holiday:true})).innerHTML.includes('Enjoy your day off'));
 assert((await render('10:00',{visible:false})).hidden);
 const located=(await render('18:10',{first_in:iso('09:00'),last_out:iso('18:00'),first_in_location:'GPS 25.00000, 55.00000',last_out_location:'GPS 26.00000, 56.00000'})).innerHTML;
 assert(located.includes('Check-in:</strong> 9:00 AM \u00b7 GPS 25.00000, 55.00000'));
 assert(located.includes('Check-out:</strong> 6:00 PM \u00b7 GPS 26.00000, 56.00000'));
 assert((await render('10:00',{first_in:iso('09:00'),checked_in:true})).innerHTML.includes('Location not recorded'));
 console.log('PASS: shift phases, 9:01 lateness, five module messages, checkout, leave, duty, holiday and hidden missing profile');
})();
