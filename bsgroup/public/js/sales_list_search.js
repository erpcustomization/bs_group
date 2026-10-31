(() => {
  const fields = {
    Lead:['name','lead_name','company_name','title'],
    Opportunity:['name','customer_name','party_name','custom_subject'],
    'Presales Request':['name','organisation_name','customer','subject','opportunity'],
    'Deal Cost Sheet':['name','organisation_name','customer','subject','opportunity'],
    Quotation:['name','customer_name','party_name','custom_subject','opportunity']
  };
  const extraLists = ['Presales Request','Deal Cost Sheet','Quotation'];
  const style = document.createElement('style');
  style.textContent = '.bs-search-header .list-page-form{display:none!important}.bs-search-header .bs-search-filter{display:inline-flex!important;align-items:center;justify-content:center;width:34px;height:34px;padding:0!important;border-radius:8px!important;margin-right:8px}.bs-search-header .bs-search-filter .button-label{display:none!important}.bs-search-header .bs-search-filter .filter-icon{margin:0!important}';
  document.head.append(style);
  function mount(view) {
    if (!fields[view.doctype]) return;
    const area = view.page.wrapper[0] || view.page.wrapper;
    if (extraLists.includes(view.doctype)) {
      const actions = area.querySelector('.standard-actions');
      const button = area.querySelector('.filter-button');
      if (actions && button) {
        if (button.parentElement !== actions) {
          const primary = actions.querySelector('.primary-action');
          if (primary) primary.before(button); else actions.append(button);
        }
        button.classList.add('bs-search-filter');
        button.setAttribute('aria-label','Filter');
        area.classList.add('bs-search-header');
        const sorter = area.querySelector('.sort-selector');
        if (sorter && !view._bs_search_sort) {
          view._bs_search_sort = true;
          const home = document.createElement('div');
          home.hidden = true;
          sorter.before(home);
          home.append(sorter);
          $(button).on('shown.bs.popover.bs_search', () => {
            const body = document.getElementById(button.getAttribute('aria-describedby'))?.querySelector('.popover-body');
            if (!body) return;
            let row = body.querySelector('.bs-search-sort');
            if (!row) {
              row = document.createElement('div');
              row.className = 'bs-search-sort';
              row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:12px;padding-bottom:12px;';
              const label = document.createElement('span');
              label.textContent = __('Sort by');
              row.append(label);
              body.prepend(row);
            }
            row.append(sorter);
            $(button).popover('update');
          });
          $(button).on('hide.bs.popover.bs_search', () => home.append(sorter));
        }
      }
    }
    if (!view._bs_search_observer) {
      view._bs_search_observer = new MutationObserver(() => mount(view));
      view._bs_search_observer.observe(area, {childList:true, subtree:true});
    }
    const filter = area.querySelector('.standard-actions .filter-button') || area.querySelector('.filter-section .filter-selector');
    if (!filter) return;
    const existing = area.querySelector('.bs-sales-search');
    if (existing) {
      if (existing.nextElementSibling !== filter) filter.before(existing);
      return;
    }
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
