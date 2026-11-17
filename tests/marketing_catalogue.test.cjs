const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../marketing/app.js'),'utf8').split('const marqueeItems=')[0]+'return {plans,html:pricingBlock("Plans","",true)};})();';
const names=['Individual','Silver','Gold','Platinum'];
const catalog=(prices=[5,5000,15000,22000])=>({currency:'LKR',plans:Object.fromEntries(names.map((n,i)=>[n,{monthly_lkr:prices[i],active_student_lkr:i?50:100,card_features:['Do not replace the original feature design']}]))});
async function render(message,pathname='/',fail=false){
 let requests=0;
 const result=await vm.runInNewContext(source,{window:{SISU_CONFIG:{appUrl:''}},location:{pathname},AbortSignal,fetch:async(url,options)=>{
  requests++;assert.equal(url,'/api/method/institute_lms.plan_catalog.public_catalog');assert.equal(options.cache,'no-store');
  if(fail)throw Error('Offline');return{ok:true,json:async()=>({message})};
 }});
 return{...result,requests};
}
test('all public pricing pages use configured prices and retain detailed features',async()=>{
 for(const route of ['/','/teachers/','/institutes/']){
  const r=await render(catalog(),route);
  assert.deepEqual(Array.from(r.plans,p=>p[2]),[5,5000,15000,22000]);
  assert.match(r.html,/LKR 5 \/ month/);assert.doesNotMatch(r.html,/LKR 2,500/);
  assert.equal((r.html.match(/<details class="plan-full-features">/g)||[]).length,4);
  assert.match(r.html,/Dynamic PDF watermark/);assert.match(r.html,/Unlimited courses and exams/);
  assert.doesNotMatch(r.html,/Do not replace the original feature design/);
 }
});
test('a changed catalogue updates cards, comparison values and calculator initial total',async()=>{
 const r=await render(catalog([35,6000,16000,23000]));
 assert.deepEqual(Array.from(r.plans,p=>p[2]),[35,6000,16000,23000]);
 assert.match(r.html,/id="calc-total">LKR 35<\/span>/);
 assert.match(r.html,/LKR 23,000 \/ month/);
});
test('missing or invalid prices show unavailable instead of stale prices',async()=>{
 for(const invalid of [null,{currency:'USD',plans:{}},catalog([null,5000,15000,22000]),catalog([-1,5000,15000,22000]),catalog(['5',5000,15000,22000])]){
  const r=await render(invalid);assert.match(r.html,/temporarily unavailable/);assert.doesNotMatch(r.html,/class="plan tier/);
 }
});
test('network failure leaves a useful refresh message',async()=>{
 const r=await render(null,'/',true);assert.match(r.html,/refresh this page/);
});
test('student and contact pages do not wait for an unused catalogue',async()=>{
 for(const route of ['/students/','/contact/'])assert.equal((await render(null,route)).requests,0);
});
