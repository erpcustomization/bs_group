const assert=require('node:assert/strict');
const {appForSection,chooseApp,routeMatches,groups}=require('../bsgroup/public/js/app_sidebar.js');
const url=p=>new URL(p,'https://erp.bitssecureit.com');
const candidates=[
 {app:'BS Sales',href:'/desk/bs-group/quotation'},
 {app:'BS Sales',href:'/desk/bs-group/lead'},
 {app:'BS Project',href:'/desk/bs-group/project'},
 {app:'BS Project',href:'/desk/bs-group/bs-project-modules?bs_module=infra&bs_section=projects'},
 {app:'BS HR',href:'/desk/bs-group/hr-dashboard'},
 {app:'BS Procurement',href:'/desk/bs-group/bs-procurement?bsp_view=list'},
 {app:'BS Approvals',href:'/desk/bs-group/material-request'},
 {app:'BS Procurement',href:'/desk/bs-group/material-request'},
];
assert.equal(chooseApp(url('/desk/bs-group/quotation/QTN-1'),candidates,'BS HR'),'BS Sales');
assert.equal(chooseApp(url('/desk/quotation/QTN-1'),candidates,'BS Project'),'BS Sales');
assert.equal(chooseApp(url('/desk/bs-group/project/P-1'),candidates,'BS Sales'),'BS Project');
assert.equal(chooseApp(url('/desk/bs-group/bs-project-modules?bs_module=infra&bs_section=projects'),candidates,'BS Sales'),'BS Project');
assert.equal(chooseApp(url('/desk/bs-group/hr-dashboard?hr_section=attendance'),candidates,'BS Sales'),'BS HR');
assert.equal(chooseApp(url('/desk/bs-group/material-request?bs_app=BS%20Procurement'),candidates,'BS Sales'),'BS Procurement');
assert.equal(chooseApp(url('/desk/bs-group/material-request/MR-1'),candidates,'BS Procurement'),'BS Procurement');
assert.equal(chooseApp(url('/desk/bs-group/material-request/MR-1'),candidates,'BS Approvals'),'BS Approvals');
assert.equal(chooseApp(url('/desk/my-work-dashboard'),candidates,'BS HR'),'BS HR');
assert.equal(chooseApp(url('/desk/lead?bs_app=Unknown'),candidates,'BS HR'),'BS Sales');
assert(!routeMatches(url('/desk/project-template'),url('/desk/project')));
assert(!routeMatches(url('/desk/bs-project-modules?bs_module=elv'),url('/desk/bs-project-modules?bs_module=infra')));
for(const section of groups['BS Project']) assert.equal(appForSection(section),'BS Project');
for(const app of ['BS HR','BS Support','BS AMC','BS PPM','BS Procurement','BS Approvals','BS Helpdesk']) assert.equal(appForSection(app),app);
assert.equal(appForSection(null),'BS Sales');
console.log('PASS app-scoped routes, direct records, app switching, project categories, shared routes and invalid context');
