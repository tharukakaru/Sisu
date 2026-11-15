export const ownerSections = [
  {name:'Overview',group:'Workspace',icon:'LayoutDashboard',description:'Review your campuses and the work that needs attention.'},
  {name:'Organizations',group:'Workspace',icon:'Building2',description:'Register and manage institutes with their own hosted website.'},
  {name:'Plans',group:'Workspace',icon:'Package',description:'Manage subscription prices, included tools and plan descriptions.'},
  {name:'Billing',group:'Finance',icon:'Receipt',description:'Review provider accounts, invoices and payment records.'},
  {name:'Commerce',group:'Finance',icon:'Wallet',description:'Review commercial reports from your hosted websites.'},
  {name:'Site policies',group:'Platform',icon:'Settings2',description:'Manage website policies and check their delivery status.'},
  {name:'Provisioning',group:'Platform',icon:'Globe2',description:'Track institute website setup and operator tasks.'},
  {name:'Admin access',group:'Platform',icon:'ShieldCheck',description:'Review administrator access and primary-owner permissions.'},
  {name:'Audit log',group:'Platform',icon:'ListChecks',description:'Review who changed platform settings and why.'},
  {name:'Readiness',group:'Platform',icon:'CircleCheck',description:'Check local services, reporting connections and email delivery.'},
  {name:'Platform guide',group:'Help',icon:'CircleHelp',description:'Find the right controls for your administration tasks.'},
]
export function ownerSection(hash='') {
  try { const name=decodeURIComponent(hash.replace(/^#/,'')); return ownerSections.some(s=>s.name===name)?name:'Overview' }
  catch { return 'Overview' }
}
export function isLocalOwner(location) {
  return location.protocol==='http:' && ['127.0.0.1','localhost'].includes(location.hostname) && location.port==='5401'
}
export function campusAdminUrl(campus,location) {
  if(isLocalOwner(location)) {
    const port={'sisuacademylk.com':'5400','staging.sisuacademylk.com':'5402','teen.sisuacademylk.com':'5403'}[campus.site]
    return port?`http://${location.hostname}:${port}/campus`:null
  }
  try {const url=new URL(campus.url);return url.protocol==='https:'&&url.hostname===campus.site&&!url.username&&!url.password?url.href:null}
  catch {return null}
}
