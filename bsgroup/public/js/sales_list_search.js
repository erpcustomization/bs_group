(() => {
  const fields = {Lead:['name','lead_name','company_name','title'], Opportunity:['name','customer_name','party_name','custom_subject']};
  function mount(view) {
    if (!fields[view.doctype]) return;
    const area = view.page.wrapper[0] || view.page.wrapper;
    const filter = area.querySelector('.filter-section .filter-selector');
    if (!filter || area.querySelector('.bs-sales-search')) return;
    const input = document.createElement('input');
    input.type = 'search';
    input.className = 'form-control input-sm bs-sales-search';
    input.placeholder = 'Search ID, name or subject';
    input.setAttribute('aria-label', `Search ${view.doctype}`);
    input.style.cssText = 'width:230px;min-width:160px;max-width:100%;margin-right:8px;';
    input.value = view._bs_search || '';
    let timer;
    const search = () => { clearTimeout(timer); view._bs_search=input.value.trim(); view.start=0; view.refresh(); };
    input.addEventListener('input', () => { clearTimeout(timer); timer=setTimeout(search,350); });
    input.addEventListener('search',search);
    input.addEventListener('keydown', e => {if(e.key==='Enter'){e.preventDefault();search();}});
    filter.before(input);
  }
  function install() {
    const proto=frappe.views?.ListView?.prototype;
    if(!proto) return false;
    if(proto._bs_search_installed) return true;
    proto._bs_search_installed=true;
    const render=proto.before_render, args=proto.get_args;
    proto.before_render=function(...a){const result=render.apply(this,a);mount(this);return result;};
    proto.get_args=function(...a){
      const result=args.apply(this,a);
      if(fields[this.doctype] && this._bs_search){
        const available=fields[this.doctype].filter(f=>f==='name'||frappe.meta.has_field(this.doctype,f));
        result.or_filters=[...(result.or_filters||[]),...available.map(f=>[this.doctype,f,'like',`%${this._bs_search}%`])];
      }
      return result;
    };
    return true;
  }
  if(!install()){const timer=setInterval(()=>{if(install())clearInterval(timer);},250);}
})();
