(() => {
  // Read the authoritative unread total after native read actions and new arrivals.
  if (!window.bsUnreadBadge) {
    window.bsUnreadBadge = true;
    let badgeTimer, pending = false;
    const refreshUnread = async () => {
      if (pending || document.hidden || !frappe.session?.user || frappe.session.user === 'Guest') return;
      pending = true;
      try {
        const r = await frappe.call({method:'bsgroup.notification_badge.unread_count',quiet:true});
        const count = Number(r.message) || 0;
        document.querySelectorAll('.notification-count').forEach(el => {
          el.textContent = String(count);
          el.classList.toggle('hidden', count === 0);
          el.setAttribute('aria-label', `${count} unread notifications`);
        });
      } finally { pending = false; }
    };
    const scheduleUnread = () => { clearTimeout(badgeTimer); badgeTimer = setTimeout(() => refreshUnread().catch(()=>{}), 250); };
    const reading = new Set();
    document.addEventListener('click', event => {
      const item = event.target.closest?.('.notification-item[data-name]');
      const name = item?.dataset.name;
      if (!name || !item.classList.contains('unread') || reading.has(name)) return;
      reading.add(name);
      Promise.resolve(frappe.call({
        method:'frappe.desk.doctype.notification_log.notification_log.mark_as_read',
        args:{docname:name}
      })).then(() => {
        document.querySelectorAll('.notification-item[data-name]').forEach(el => {
          if (el.dataset.name === name) el.classList.remove('unread');
        });
        scheduleUnread();
      }).catch(()=>{}).finally(() => reading.delete(name));
    }, true);
    $(document).ajaxComplete((event, xhr, settings) => {
      const request = String(settings.url || '') + ' ' + String(settings.data || '');
      if (/notification_log\.(mark_as_read|mark_all_as_read|get_notification_logs)/.test(request)) scheduleUnread();
    });
    frappe.realtime?.on('notification', scheduleUnread);
    window.addEventListener('focus', scheduleUnread);
    document.addEventListener('visibilitychange', scheduleUnread);
    setInterval(scheduleUnread, 30000);
    scheduleUnread();
  }
  // Keep the native notification button and its event handlers in the dock,
  // while positioning it in the top bar above the active list's Filter button.
  let notificationFrame;
  function positionNotification() {
    notificationFrame = null;
    const bell = document.querySelector('#desk-dock .sidebar-notification');
    if (!bell) return;
    const visible = selector => Array.from(document.querySelectorAll(selector)).find(e => e.getClientRects().length);
    const header = visible('.page-head');
    if (!header) {
      bell.classList.remove('bs-header-notification');
      return;
    }
    const filter = visible('.standard-actions .filter-button');
    const h = header.getBoundingClientRect();
    const f = filter?.getBoundingClientRect();
    const left = Math.max(0, Math.min(innerWidth - 42, f ? f.left + f.width / 2 - 17 : innerWidth - 58));
    const top = Math.max(0, h.top + (h.height - 34) / 2);
    if (!bell.classList.contains('bs-header-notification')) bell.classList.add('bs-header-notification');
    if (bell.style.left !== `${left}px`) bell.style.left = `${left}px`;
    if (bell.style.top !== `${top}px`) bell.style.top = `${top}px`;
  }
  const scheduleNotification = () => {
    if (!notificationFrame) notificationFrame = requestAnimationFrame(positionNotification);
  };
  new MutationObserver(scheduleNotification).observe(document.body, {childList:true, subtree:true, attributes:true, attributeFilter:['class','style']});
  window.addEventListener('resize', scheduleNotification);
  window.addEventListener('scroll', scheduleNotification, true);
  scheduleNotification();
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
    if (view.doctype === 'Deal Cost Sheet') {
      const names = (view.data || []).map(doc => doc.name);
      const signature = JSON.stringify(names);
      if (names.length && view._bs_owner_signature !== signature) {
        view._bs_owner_signature = signature;
        frappe.call({method:'bsgroup.lead_lifecycle.list_owner_labels', args:{names,doctype:view.doctype}, callback:result => {
          view._bs_owner_labels = {...view._bs_owner_labels, ...result.message};
          mount(view);
        }});
      }
      area.querySelectorAll('.list-row [data-fieldname="deal_owner"] a[data-filter]').forEach(link => {
        const owner = link.getAttribute('data-filter').split(',=,').slice(1).join(',=,');
        const profile = view._bs_owner_labels?.[owner];
        const label = profile?.first_name || profile?.full_name?.split(/\s+/)[0];
        if (label && link.textContent !== label) {
          link.textContent = label;
          link.title = profile.full_name;
          if (link.parentElement) link.parentElement.title = `Deal Owner: ${profile.full_name}`;
        }
      });
      const count = area.querySelector('.list-row-head .list-count');
      const heading = area.querySelector('.bs-list-heading h1');
      if (count && heading) {
        let holder = area.querySelector('.bs-dcs-list-count');
        if (!holder) {
          holder = document.createElement('span');
          holder.className = 'bs-dcs-list-count';
          holder.style.cssText = 'font-size:11px;font-weight:400;color:#60718b;margin-left:12px;white-space:nowrap;letter-spacing:0;';
          heading.append(holder);
        }
        if (holder.textContent !== count.textContent) holder.textContent = count.textContent;
      }
    }
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
