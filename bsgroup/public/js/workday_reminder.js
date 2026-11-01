// Runs throughout Desk, not just while the dashboard is visible.
(() => {
  let busy=false;
  async function check() {
    if(busy || !frappe.session?.user || frappe.session.user==='Guest') return;
    const parts=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Dubai',hour:'2-digit',minute:'2-digit',year:'numeric',month:'2-digit',day:'2-digit',hourCycle:'h23'}).formatToParts(new Date()).map(p=>[p.type,p.value]));
    if(parts.hour!=='17'||Number(parts.minute)<30) return;
    const key=`bs-wrapup:${frappe.session.user}:${parts.year}-${parts.month}-${parts.day}`;
    try {if(localStorage.getItem(key))return;}catch(e){}
    busy=true;
    try {
      const r=await frappe.call({method:'bsgroup.dashboard_attendance.wrap_up_reminder',type:'POST'});
      if(r.message?.due){
        frappe.show_alert({message:__('Time to wrap up: finish your priority tasks and update their status before 6:00 PM.'),indicator:'orange'},20);
        try{localStorage.setItem(key,'1');}catch(e){}
      }
    } catch(error) {
      // Retry on the next minute if the connection is temporarily unavailable.
    } finally {busy=false;}
  }
  setInterval(check,60000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)check();});
  check();
})();
