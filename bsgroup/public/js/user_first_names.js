// Presentation only: never change User IDs, input values, document data or filters.
(() => {
  const userFields = new Set(['owner','modified_by','deal_owner','lead_owner','opportunity_owner','presales_owner','requested_by','assigned_to','allocated_to','prepared_by','approved_by','created_by','user','user_id','sales_person','custom_sales_person','employee_name','project_manager']);
  function render() {
    const profiles = new Map();
    for (const [id, info] of Object.entries(frappe.boot?.user_info || {})) {
      const full = info.fullname || info.full_name;
      if (!full) continue;
      const first = info.first_name || full.trim().split(/\s+/)[0];
      profiles.set(id, {full, first});
      profiles.set(full, {full, first});
    }
    const roots = Array.from(document.querySelectorAll('[data-fieldname]')).filter(e => userFields.has(e.dataset.fieldname));
    roots.push(...document.querySelectorAll('a[data-doctype="User"],a[href^="/desk/user/"],.notification-body .message strong:first-child,.comment-by,.user-full-name'));
    for (const root of roots) {
      if (root.closest('.print-format,.print-preview,[contenteditable="true"]')) continue;
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      const changes = [];
      while (walker.nextNode()) {
        const node = walker.currentNode;
        if (node.parentElement.closest('input,textarea,select,option,script,style,label,.control-label')) continue;
        const value = node.textContent.trim();
        const profile = profiles.get(value);
        if (profile && value !== profile.first) changes.push({node,profile});
      }
      for (const {node,profile} of changes) {
        node.parentElement.title = profile.full;
        node.textContent = node.textContent.replace(node.textContent.trim(), profile.first);
      }
    }
  }
  let timer;
  new MutationObserver(() => {clearTimeout(timer);timer=setTimeout(render,80);}).observe(document.body,{childList:true,subtree:true,characterData:true});
  render();
})();
