// Loaded through native list metadata; never replace list settings or handlers.
// Scope every rule to the Lead list so cached styles cannot affect other pages.
(() => {
    const id = "bsi-lead-compact-list";
    if (document.getElementById(id)) return;
    const style = document.createElement("style");
    style.id = id;
    style.textContent = `
    @media screen {
      body.bs-sales-ui[data-route="List/Lead/List"] .bs-list-shell .layout-main-section { padding: 10px 14px 12px; }
      body.bs-sales-ui[data-route="List/Lead/List"] .bs-list-heading { margin-bottom: 8px; gap: 8px; }
      body.bs-sales-ui[data-route="List/Lead/List"] .bs-list-heading h1 { font-size: 20px; }
      body.bs-sales-ui[data-route="List/Lead/List"] .list-page-form { padding: 8px 10px; margin-bottom: 8px; gap: 8px 12px; }
      body.bs-sales-ui[data-route="List/Lead/List"] .standard-filter-section { gap: 6px 8px; }
      body.bs-sales-ui[data-route="List/Lead/List"] .standard-filter-section :is(.form-control,.match-type-dropdown-btn) { height: 30px; min-height: 30px; }
      body.bs-sales-ui[data-route="List/Lead/List"] .standard-filter-section :is(.select-icon,.placeholder) { top: 6px; }
      body.bs-sales-ui[data-route="List/Lead/List"] .filter-section { padding-left: 10px; gap: 6px; }
      body.bs-sales-ui[data-route="List/Lead/List"] .filter-section .btn { min-height: 30px; padding-top: 4px; padding-bottom: 4px; }
      body.bs-sales-ui[data-route="List/Lead/List"] .filter-section > * { margin-top: 0; margin-bottom: 0; }
      body.bs-sales-ui[data-route="List/Lead/List"] .result-container { margin: 0; width: 100%; }
      body.bs-sales-ui[data-route="List/Lead/List"] :is(.result,.list-row-container) { display: block !important; width: 100% !important; min-width: 0 !important; }
      body.bs-sales-ui[data-route="List/Lead/List"] .bs-list-shell :is(.list-row,.list-row-head) { width: 100%; min-height: 36px; padding: 2px 6px; margin: 0; }
      body.bs-sales-ui[data-route="List/Lead/List"] .bs-list-shell .list-row > .level-left,
      body.bs-sales-ui[data-route="List/Lead/List"] .list-header-subject { min-width: 0 !important; flex: 1 1 0%; gap: 6px; }
      body.bs-sales-ui[data-route="List/Lead/List"] .list-row-col { flex-shrink: 1 !important; min-width: 0 !important; margin-right: 0; padding-right: 6px; }
      body.bs-sales-ui[data-route="List/Lead/List"] .list-row-col[data-fieldname="status_field"] { max-width: 104px !important; }
      body.bs-sales-ui[data-route="List/Lead/List"] :is(.list-row,.list-row-head) > .level-right { width: 178px; min-width: 178px; flex: 0 0 178px; padding-left: 6px; }
      body.bs-sales-ui[data-route="List/Lead/List"] .list-row-activity { width: 100%; min-width: 0; gap: 5px; margin: 0; }
      body.bs-sales-ui[data-route="List/Lead/List"] .list-row-activity .modified { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      body.bs-sales-ui[data-route="List/Lead/List"] .list-row .level-left { min-height: 30px; }
      body.bs-sales-ui[data-route="List/Lead/List"] .list-paging-area { margin-top: 6px; }
      @media(max-width:1000px) {
        body.bs-sales-ui[data-route="List/Lead/List"] .list-page-form { gap: 6px; }
        body.bs-sales-ui[data-route="List/Lead/List"] .filter-section { padding: 6px 0 0; }
      }
      @media(max-width:767px) {
        body.bs-sales-ui[data-route="List/Lead/List"] :is(.list-row,.list-row-head) > .level-right { width: auto; min-width: 0; flex: 0 1 auto; }
      }
    }`;
    document.head.appendChild(style);
})();
