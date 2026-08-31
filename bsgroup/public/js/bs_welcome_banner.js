(function () {
  if (window.__bsWelcomeBannerInjected) return;
  window.__bsWelcomeBannerInjected = true;

  var MODULES = [
    { name: 'Accounting',       slug: 'invoicing',             grad: 'linear-gradient(135deg,#10b981,#059669)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>' },
    { name: 'Assets',           slug: 'assets',                grad: 'linear-gradient(135deg,#6366f1,#4f46e5)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>' },
    { name: 'Buying',           slug: 'buying',                grad: 'linear-gradient(135deg,#f59e0b,#d97706)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z"/></svg>' },
    { name: 'Manufacturing',    slug: 'manufacturing',         grad: 'linear-gradient(135deg,#ec4899,#be185d)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>' },
    { name: 'Projects',         slug: 'projects',              grad: 'linear-gradient(135deg,#8b5cf6,#6d28d9)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/></svg>' },
    { name: 'Quality',          slug: 'quality',               grad: 'linear-gradient(135deg,#14b8a6,#0d9488)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg>' },
    { name: 'Selling',          slug: 'selling',               grad: 'linear-gradient(135deg,#22c55e,#15803d)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/></svg>' },
    { name: 'Stock',            slug: 'stock',                 grad: 'linear-gradient(135deg,#0ea5e9,#0369a1)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>' },
    { name: 'Subcontracting',   slug: 'subcontracting',        grad: 'linear-gradient(135deg,#ef4444,#b91c1c)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>' },
    { name: 'ERPNext Settings', slug: 'erpnext-settings',      grad: 'linear-gradient(135deg,#64748b,#334155)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>' },
    { name: 'Frappe HR',        slug: 'people',                grad: 'linear-gradient(135deg,#06b6d4,#0e7490)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/></svg>' },
    { name: 'Organization',     slug: 'users',                 grad: 'linear-gradient(135deg,#a855f7,#7e22ce)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>' },
    { name: 'Helpdesk',         slug: 'helpdesk',              grad: 'linear-gradient(135deg,#f43f5e,#9f1239)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M18.364 5.636l-3.536 3.536m0 5.656l3.536 3.536M9.172 9.172L5.636 5.636m3.536 9.192l-3.536 3.536M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-5 0a4 4 0 11-8 0 4 4 0 018 0z"/></svg>' },
    { name: 'Framework',        slug: 'build',                 grad: 'linear-gradient(135deg,#3b82f6,#1d4ed8)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/></svg>' },
    { name: 'Sales',            slug: 'bs-group---sales',      grad: 'linear-gradient(135deg,#f97316,#c2410c)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"/></svg>' },
    { name: 'BS Helpdesk',      slug: 'bs-group---helpdesk',   grad: 'linear-gradient(135deg,#f43f5e,#9f1239)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M18.364 5.636l-3.536 3.536m0 5.656l3.536 3.536M9.172 9.172L5.636 5.636m3.536 9.192l-3.536 3.536M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-5 0a4 4 0 11-8 0 4 4 0 018 0z"/></svg>' },
    { name: 'BS Project',       slug: 'bs-group---project',    grad: 'linear-gradient(135deg,#8b5cf6,#6d28d9)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/></svg>' },
    { name: 'Approval',         slug: 'labor-preapproval',     grad: 'linear-gradient(135deg,#84cc16,#4d7c0f)',
      svg: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>' }
  ];

  function dismiss() {
    var c = document.getElementById('bs-welcome-cover');
    if (!c) return;
    c.style.transition = 'opacity 0.35s ease';
    c.style.opacity = '0';
    setTimeout(function () {
      c.remove();
      document.body.classList.remove('bs-cover-active');
    }, 350);
  }

  function inject() {
    if (document.getElementById('bs-welcome-cover')) return;
    var path = window.location.pathname;
    if (!(path === '/desk' || path === '/desk/' || path === '/app' || path === '/app/')) return;

    var userName = (window.frappe && frappe.session && frappe.session.user_fullname) || 'User';
    var firstName = userName.split(' ')[0];
    var hour = new Date().getHours();
    var greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

    var cover = document.createElement('div');
    cover.id = 'bs-welcome-cover';
    cover.innerHTML =
      '<div class="bs-blob bs-blob1"></div>' +
      '<div class="bs-blob bs-blob2"></div>' +
      '<button class="bs-close" aria-label="Close">&times;</button>' +
      '<div class="bs-header">' +
        '<div class="bs-logo-slot">' +
          '<div class="bs-logo"><img src="/assets/bsgroup/img/logo.png" alt="Bits Secure"/></div>' +
        '</div>' +
        '<div class="bs-header-text">' +
          '<p class="bs-greeting">' + greeting + ', ' + firstName + ' 👋</p>' +
          '<h1 class="bs-title">Bits Secure - Digital Control Tower</h1>' +
        '</div>' +
        '<div></div>' +
      '</div>' +
      '<div class="bs-grid"></div>';

    var grid = cover.querySelector('.bs-grid');
    MODULES.forEach(function (m) {
      var card = document.createElement('a');
      card.className = 'bs-card';
      card.href = '/app/' + m.slug;
      card.innerHTML =
        '<div class="bs-icon" style="background:' + m.grad + '">' + m.svg + '</div>' +
        '<span class="bs-label">' + m.name + '</span>';
      card.addEventListener('click', dismiss);
      grid.appendChild(card);
    });

    cover.querySelector('.bs-close').addEventListener('click', dismiss);

    document.body.appendChild(cover);
    document.body.classList.add('bs-cover-active');
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') dismiss();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }

  if (window.frappe && frappe.router) {
    frappe.router.on('change', inject);
  }
})();
