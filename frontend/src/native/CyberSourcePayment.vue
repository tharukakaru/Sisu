<script setup>
import {ref,computed,onMounted,onBeforeUnmount,nextTick,watch} from 'vue'
import {request} from './client'
import {loadCheckoutLibrary,paymentMessage,reusableCheckout} from './cybersourceCheckout'
import Icon from '../Icon.vue'

const props=defineProps({invoice:{type:String,required:true},kind:{type:String,default:'tuition'},visible:{type:Boolean,default:true},review:Boolean})
const emit=defineEmits(['changed','screen-change'])
const checkoutTargetId='cybs-checkout-'+crypto.randomUUID()
const checkoutScreenId=checkoutTargetId+'-screen'
const formOpen=ref(false)
function showForm(open){formOpen.value=open;emit('screen-change',open)}
let screenObserver,screenResize,openingStarted=0
function observeScreen(){
 const element=document.getElementById(checkoutScreenId)
 const selection=document.getElementById(checkoutTargetId)
 if(!element||!selection)return
 // The SDK owns visibility and sizing of its cross-origin frame. Do not hide
 // its container while waiting for an SDK event (that prevents initial sizing).
 const sync=()=>{
  if(!props.visible)return
  const formVisible=element.getBoundingClientRect().height>5
  showForm(formVisible)
  if(preparing.value&&(formVisible||props.visible&&selection.getBoundingClientRect().height>5)){
   preparing.value=false;measure('payment UI visible',openingStarted)
  }
 }
 screenObserver=new MutationObserver(sync)
 screenObserver.observe(element.parentNode,{childList:true,subtree:true,attributes:true,attributeFilter:['style','hidden']})
 screenResize=new ResizeObserver(sync);screenResize.observe(element);screenResize.observe(selection);sync()
}
const paused=ref(false),popup=ref(false),available=ref(false),busy=ref(false),message=ref('')
const attempt=ref(null),gatewayMode=ref('unavailable'),retained=ref(false),blocked=ref(false),paid=ref(false)
let submissionGrant=null
const heldStatus=ref(null),clock=ref(Date.now())
const preparing=ref(false),loadingText=ref(''),loadingSince=ref(0),retryLoading=ref(false)
const reloadRequired=ref(false)
let session,queuedContext,disposed=false,generation=0,clockTimer=setInterval(()=>{clock.value=Date.now()},1000)
function loadingStep(text){preparing.value=true;loadingText.value=text;loadingSince.value=Date.now();clock.value=Date.now()}
function measure(stage,started){if(['localhost','checkout.localhost','127.0.0.1'].includes(location.hostname))console.debug('[SISU checkout timing]',stage,Math.round(performance.now()-started)+'ms')}
const remaining=computed(()=>heldStatus.value?.status==='pending'&&!heldStatus.value?.transaction_id&&!['processing','completed'].includes(heldStatus.value?.browser_event)?Math.max(0,Math.ceil(((heldStatus.value?.retry_after||0)*1000-clock.value)/1000)):0)
const retryCountdown=computed(()=>`${Math.floor(remaining.value/60)}:${String(remaining.value%60).padStart(2,'0')}`)
const displayMessage=computed(()=>heldStatus.value?paymentMessage(heldStatus.value,props.kind,clock.value):message.value)
const awaitingVerification=computed(()=>!paid.value&&heldStatus.value?.status==='pending'&&(!!heldStatus.value?.transaction_id||['processing','completed'].includes(heldStatus.value?.browser_event)))
const needsReview=computed(()=>heldStatus.value?.status==='review'&&!heldStatus.value?.resume_allowed)
const buttonLabel=computed(()=>reloadRequired.value?'Reload page':paid.value?'Payment verified':busy.value?'Opening checkout…':heldStatus.value?.session_unavailable?'Retry opening checkout':retryLoading.value?'Retry loading checkout':retained.value?'Resume card checkout':remaining.value?`Retry available in ${retryCountdown.value}`:blocked.value?'Check and reopen checkout':props.review?'Continue to card payment':'Pay securely · LKR')
onMounted(async()=>{try{const r=await request('cybersource','availability',{kind:props.kind,invoice:props.invoice});available.value=r.available;paused.value=!!r.paused;gatewayMode.value=r.mode||'unavailable';await nextTick();if(!disposed&&props.review)observeScreen()}catch{available.value=false}})
function cleanup(){try{session?.destroy()}catch{}session=null;retained.value=false;showForm(false)}
function pause(){
 preparing.value=false
 // The parent hides this persistent dialog. Keep the SDK and its pending mount
 // intact: unmount/remount can leave orphaned provider frames and lose form state.
 // A full page refresh recovers the same unsubmitted attempt through the server.
}
watch(()=>props.visible,value=>{if(!value)pause()})
onBeforeUnmount(()=>{disposed=true;generation++;queuedContext=null;screenObserver?.disconnect();screenResize?.disconnect();clearInterval(clockTimer);cleanup()})
async function verify(){
 if(busy.value)return
 busy.value=true
 try{const r=await request('cybersource','reconcile',{attempt:attempt.value});heldStatus.value=r;message.value=paymentMessage(r,props.kind);blocked.value=!r.retry_allowed&&r.status!=='failed';if(r.status==='succeeded'){paid.value=true;cleanup();emit('changed')}}
 catch(e){message.value=e.message}finally{busy.value=false}
}
async function pay(){
 if(busy.value||paid.value||remaining.value)return
 if(reloadRequired.value){location.reload();return}
 if(paused.value){popup.value=true;return}
 busy.value=true
 heldStatus.value=null
 retryLoading.value=false
 loadingStep('Preparing your secure checkout…')
 const started=performance.now()
 openingStarted=started
 const current=++generation
 let stage='session-request'
 try{
  if(!session?.canResume()){
   cleanup()
   let r=queuedContext?.session_expires*1000>Date.now()?queuedContext:await request('cybersource','start',{kind:props.kind,invoice:props.invoice})
   if(r.retry_allowed)r=await request('cybersource','start',{kind:props.kind,invoice:props.invoice})
   measure('session response',started)
   attempt.value=r.name;gatewayMode.value=r.mode||gatewayMode.value
   submissionGrant=r.submission_grant||null
   message.value=paymentMessage(r,props.kind)
   if(!r.session){heldStatus.value=r;blocked.value=!r.retry_allowed&&r.status!=='failed';if(r.status==='succeeded'){paid.value=true;emit('changed')}return}
   queuedContext=r
   // A response arriving after close is retained only in this component, never in storage.
   stage='library-load'
   loadingStep('Loading secure card checkout…')
   const libraryStarted=performance.now()
   const VAS=await loadCheckoutLibrary(r.session,r.mode)
   measure('library loaded',libraryStarted)
   if(disposed)return
   stage='client-initialization'
   loadingStep('Connecting to the payment provider…')
   const client=await VAS.UnifiedCheckout(r.session)
   // Collect first, then explicitly mark submission before processing. A close
   // during collection can resume; an ambiguous submitted payment cannot.
   const checkout=await client.createCheckout({autoProcessing:false})
   queuedContext=null
   checkout.on('mounted',()=>{if(disposed)return;if(!props.review)preparing.value=false;measure('checkout mount requested',openingStarted)})
   checkout.on('paymentMethodSelected',()=>{if(!disposed)showForm(true)})
   checkout.on('paymentMethodCancelled',()=>{if(!disposed)showForm(false)})
   session=reusableCheckout(client,checkout,r.session_expires)
   retained.value=true;blocked.value=false
  }
  if(current!==generation||!props.visible){message.value='Checkout is ready. Resume card checkout when you are ready.';return}
  stage='checkout-display'
  loadingStep('Opening your card payment options…')
  message.value='Choose Checkout with card to continue. Keep this browser tab open until you finish.'
  await nextTick()
  const outcome=await session.mount(props.review?{paymentSelection:'#'+checkoutTargetId,paymentScreen:'#'+checkoutScreenId}:'#'+checkoutTargetId)
  if(disposed||outcome.detached||current!==generation)return
  stage='payment-processing';retained.value=false;blocked.value=true
  preparing.value=false;message.value='Processing your payment. Keep this tab open; please do not pay again.'
  await request('cybersource','browser_event',{attempt:attempt.value,event:'processing',submission_grant:submissionGrant})
  await session.complete(outcome.result)
  stage='payment-verification'
  await request('cybersource','browser_event',{attempt:attempt.value,event:'completed'})
  cleanup();busy.value=false
  await verify()
 }catch(e){
  if(disposed||current!==generation)return
  const cancelled=/CANCEL|CLOSE/i.test(e?.reason||e?.code||e?.name||'')
  if(cancelled&&session?.canResume()){
   try{session.pause()}catch{cleanup()}
   retained.value=!!session?.canResume()
   message.value='Checkout closed. Payment is not completed. Resume card checkout when you are ready.'
  }else if(stage==='library-load'&&e?.code==='CHECKOUT_RELOAD_REQUIRED'){
   reloadRequired.value=true;blocked.value=false
   message.value='The secure checkout library was updated. Reload this page, then open your plan checkout again. No payment was submitted.'
  }else if(stage==='library-load'&&queuedContext?.session_expires*1000>Date.now()){
   retryLoading.value=true;blocked.value=false
   message.value='The secure checkout could not load. Check your connection, then retry here. Your existing checkout will be reused.'
  }else{
   queuedContext=null
   cleanup();blocked.value=!!attempt.value
   message.value=stage==='session-request'?(e.message||'Checkout could not be opened. Try again.'):'Checkout could not finish. Check payment status before trying again.'
  }
  if(attempt.value&&!retryLoading.value&&!reloadRequired.value)try{await request('cybersource','browser_event',{attempt:attempt.value,event:cancelled?'cancelled':'failed'})}catch{}
 }finally{if(current===generation){busy.value=false;preparing.value=false}}
}
</script>
<template><div v-if="available||paused" class="cybs-payment" :class="{'review-payment':review}">
 <button v-if="!needsReview&&!awaitingVerification&&!(review&&busy&&retained)" type="button" class="checkout-primary" :class="review ? '' : 'button primary small'" :disabled="busy||paid||remaining>0" @click="pay"><Icon v-if="review" :name="paid?'CircleCheck':remaining?'Clock3':'LockKeyhole'" :size="18"/><span>{{buttonLabel}}</span><Icon v-if="review&&!busy&&!paid&&!remaining" name="ArrowRight" :size="18"/></button>
 <button v-if="attempt&&!retained&&!paid" type="button" class="checkout-status-button" :class="review?'':'button subtle small'" :disabled="busy" @click="verify">Check payment status</button>
 <div v-if="popup" role="alertdialog" aria-modal="true" aria-label="Payment unavailable" class="payment-unavailable"><p>Online checkout is temporarily unavailable. No payment has been taken.</p><button type="button" @click="popup=false">Close</button></div>
 <div v-if="preparing" class="checkout-loading" role="status" aria-live="polite"><span class="checkout-spinner" aria-hidden="true"></span><div><strong>{{loadingText}}</strong><p>{{clock-loadingSince>8000?'This is taking a little longer. Keep this tab open; you won’t be charged just for opening checkout.':'Your payment details stay with the secure payment provider.'}}</p></div></div>
 <p v-else-if="displayMessage&&!formOpen" class="checkout-message" role="status">{{displayMessage}}</p>
 <small v-if="!review||gatewayMode==='sandbox'">{{gatewayMode==='sandbox'?'Sandbox: test payments only.':'Customer-authorized LKR payments only.'}} No automatic renewals.</small>
 <div v-show="!formOpen" :id="checkoutTargetId" class="cybs-checkout-target"></div>
 <div v-if="review" :id="checkoutScreenId" class="cybs-checkout-screen"></div>
</div></template>
<style scoped>
.review-payment{gap:12px;margin:0}
.cybs-checkout-screen{width:100%;flex-basis:100%;min-width:0}.cybs-checkout-screen:deep(iframe){max-width:100%;border:0}
.checkout-loading{display:flex;align-items:flex-start;gap:12px;flex-basis:100%;padding:16px 0;min-height:72px;box-sizing:border-box;color:#51435f;font-size:14px;line-height:1.5}.checkout-loading strong{font-weight:600}.checkout-loading p{font-size:13px;margin:4px 0 0;color:#6b5f75}.checkout-spinner{width:18px;height:18px;flex-shrink:0;margin-top:2px;border:2px solid #dfd3ec;border-top-color:#572b91;border-radius:50%;animation:checkout-spin .8s linear infinite}@keyframes checkout-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.checkout-spinner{animation:none}}
.cybs-payment.review-payment .checkout-primary{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;min-height:52px;padding:14px 18px;border-radius:10px;background:#572b91;color:#fff;border:0;font-size:15px;font-weight:650;line-height:1.5;box-shadow:none;cursor:pointer;transition:background .15s}
.review-payment .checkout-primary>span{flex:1;text-align:center}.cybs-payment.review-payment .checkout-primary:hover:not(:disabled){background:#452074}.cybs-payment.review-payment .checkout-primary:disabled{background:#eee7f5;color:#665475;cursor:default;opacity:1}
.review-payment button:focus-visible{outline:2px solid #7544a8;outline-offset:4px}
.review-payment .checkout-status-button{min-height:44px;font-size:14px;border:0;background:transparent;color:#572b91;padding:8px 0;text-decoration:underline;text-underline-offset:3px}
.review-payment .checkout-message{font-size:14px;color:#655773;line-height:1.6;margin:0;max-width:100%;overflow-wrap:anywhere}
.review-payment .cybs-checkout-target{margin-top:4px}.review-payment .cybs-checkout-target:empty{display:none}
</style>
<style scoped>.cybs-payment{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}.cybs-checkout-target{flex-basis:100%;width:100%;min-width:0}.cybs-payment .checkout-message{flex-basis:100%;font-size:14px;line-height:1.6;margin:8px 0;white-space:normal}.cybs-payment small{flex-basis:100%;max-width:380px;white-space:normal;font-size:11px;line-height:1.6}</style>



<style scoped>.payment-unavailable{position:fixed;top:30%;left:50%;transform:translateX(-50%);width:min(480px,85vw);box-sizing:border-box;text-align:left;line-height:1.6;z-index:1000;padding:28px;background:white;color:#231c30;border:1px solid #ddd;border-radius:16px;box-shadow:0 0 0 100vmax #0006}</style>
