<script setup>
import {ref,computed,watch,nextTick,onBeforeUnmount} from 'vue'
import {UserRound,Building2,LockKeyhole,Plus,Check,CheckCircle2,Trash2,X} from 'lucide-vue-next'
import {request} from './client'
const props=defineProps({data:Object,locked:Boolean})
const emit=defineEmits(['join','changed'])
const busy=ref(''),error=ref(''),confirmCancel=ref(''),notice=ref(''),actionsFor=ref('')
const confirmDialog=ref(null),keepButton=ref(null),noticeDialog=ref(null),okButton=ref(null),joinButton=ref(null),cancelledInstitute=ref('')
const popup=computed(()=>notice.value?'notice':confirmCancel.value?'confirm':'')
const confirming=computed(()=>props.data?.choices?.find(item=>item.institute===confirmCancel.value))
watch(confirming,item=>{
 if(confirmCancel.value&&(!item||item.status!=='Pending')){
  confirmCancel.value='';notice.value='Your institute request has changed. Your workspaces are up to date.'
 }
})
let previousOverflow
function dismissConfirmation(){if(!busy.value)confirmCancel.value=''}
function dismissNotice(){notice.value='';cancelledInstitute.value=''}
watch(popup,async(value,previous)=>{
 if(value){
  if(!previous){previousOverflow=document.body.style.overflow;document.body.style.overflow='hidden'}
  await nextTick()
  if(popup.value!==value)return
  if(value==='notice'){confirmDialog.value?.close?.();noticeDialog.value?.showModal?.();okButton.value?.focus()}
  else{noticeDialog.value?.close?.();confirmDialog.value?.showModal?.();keepButton.value?.focus()}
 }else{
  confirmDialog.value?.close?.();noticeDialog.value?.close?.();document.body.style.overflow=previousOverflow||''
  if(previous==='notice')joinButton.value?.focus()
 }
})
onBeforeUnmount(()=>{if(popup.value)document.body.style.overflow=previousOverflow||''})

function select(item){
 if(busy.value)return
 confirmCancel.value='';error.value=''
 if(item.status==='Pending'&&item.request){actionsFor.value=actionsFor.value===item.institute?'':item.institute;return}
 actionsFor.value='';open(item)
}
async function open(item){
 if(item.locked||busy.value||item.institute===props.data.selected)return
 busy.value=item.institute;error.value=''
 try{await request('campus_context','select',{institute:item.institute});location.assign('/campus')}
 catch(e){error.value=e.message;busy.value=''}
}
async function cancel(item){
 if(busy.value||item.status!=='Pending'||!item.request)return
 busy.value=item.institute;error.value='';notice.value=''
 try{
  await request('teacher_workspace','cancel_request',{request:item.request})
  confirmCancel.value='';actionsFor.value='';cancelledInstitute.value=item.title;notice.value=`Request to ${item.title} cancelled. You can apply again whenever you’re ready.`
  window.dispatchEvent(new Event('sisu-membership-cancelled'))
  emit('changed')
 }catch(e){error.value=e.message}finally{busy.value=''}
}
</script>
<template>
 <section class="teacher-workspaces" aria-label="Switch teaching workspace" @keydown.esc="!confirmCancel&&(actionsFor='')">
  <nav aria-label="Teaching workspaces">
   <div v-for="item in data?.choices||[]" :key="item.institute" class="workspace-choice"><button type="button" :disabled="(item.locked&&!(item.status==='Pending'&&item.request))||!!busy" :aria-expanded="item.status==='Pending'&&item.request?actionsFor===item.institute:undefined" :aria-pressed="data.selected===item.institute" :title="item.locked?`${item.title}: ${item.status==='Pending'?'Pending approval. Click to manage this request':'Membership unavailable'}`:`Open ${item.title} workspace`" @click="select(item)">
    <span class="workspace-circle" :class="{'workspace-circle--locked':item.locked}"><img v-if="item.image" :src="item.image" alt=""/><UserRound v-else-if="item.kind==='Personal'" :size="21"/><Building2 v-else :size="21"/><span v-if="item.locked" class="workspace-mark"><LockKeyhole :size="12"/></span><span v-else-if="data.selected===item.institute" class="workspace-mark"><Check :size="12"/></span></span>
    <span class="workspace-label">{{item.title}}<small v-if="item.locked">{{item.status==='Pending'?'Pending approval':'Unavailable'}}</small><small v-else-if="busy===item.institute">Opening…</small><small v-else-if="data.selected===item.institute" class="workspace-current">Current workspace</small></span>
   </button>
   <template v-if="item.status==='Pending'&&item.request">
    <button v-if="actionsFor===item.institute" type="button" class="request-bin" :aria-label="`Cancel request to ${item.title}`" title="Cancel request" :disabled="!!busy" @click="confirmCancel=item.institute;error='';notice=''"><Trash2 :size="15" aria-hidden="true"/></button>
   </template></div>
   <button ref="joinButton" type="button" :disabled="locked||!!busy" @click="emit('join')" title="Find an institute to join"><span class="workspace-circle workspace-circle--add"><Plus :size="17" aria-hidden="true"/></span><span class="workspace-label">Join institute</span></button>
  </nav>
  <p v-if="error&&!confirmCancel" role="alert">{{error}}</p>
  <dialog ref="noticeDialog" class="request-confirm-dialog request-success-dialog" aria-labelledby="request-notice-title" aria-describedby="request-notice-description" @cancel.prevent="dismissNotice">
   <template v-if="notice">
    <button type="button" class="request-confirm-close" aria-label="Close notification popup" @click="dismissNotice"><X :size="20"/></button>
    <span class="request-confirm-icon request-success-icon"><CheckCircle2 :size="28" aria-hidden="true"/></span>
    <h2 id="request-notice-title">{{cancelledInstitute?'Request cancelled':'Request updated'}}</h2>
    <p id="request-notice-description">{{notice}}</p>
    <div class="request-confirm-actions"><button ref="okButton" type="button" class="request-notice-ok" @click="dismissNotice">OK</button></div>
   </template>
  </dialog>
  <dialog ref="confirmDialog" class="request-confirm-dialog" aria-labelledby="request-cancel-title" aria-describedby="request-cancel-description" @cancel.prevent="dismissConfirmation">
   <template v-if="confirming">
    <button type="button" class="request-confirm-close" aria-label="Close cancellation popup" :disabled="!!busy" @click="dismissConfirmation"><X :size="20"/></button>
    <span class="request-confirm-icon"><Trash2 :size="24" aria-hidden="true"/></span>
    <h2 id="request-cancel-title">Cancel your institute request?</h2>
    <p id="request-cancel-description">Your pending request to <strong>{{confirming.title}}</strong> will be withdrawn. You can apply again later.</p>
    <p v-if="error" class="request-confirm-error" role="alert">{{error}}</p>
    <div class="request-confirm-actions">
     <button ref="keepButton" type="button" class="request-keep" :disabled="!!busy" @click="dismissConfirmation">Keep request</button>
     <button type="button" class="request-remove" :disabled="!!busy" @click="cancel(confirming)">{{busy?'Cancelling…':'Cancel request'}}</button>
    </div>
   </template>
  </dialog>
 </section>
</template>
<style scoped>
.teacher-workspaces{padding:12px 28px 14px;border-bottom:1px solid var(--student-border,#e6dff0);background:var(--student-card,#fff)}.teacher-workspaces nav{display:flex;flex-direction:row;justify-content:flex-end;align-items:flex-start;gap:12px;flex-wrap:wrap}.teacher-workspaces nav button{width:auto;opacity:1}.teacher-workspaces nav button:disabled{opacity:1}button{border:0;background:none;color:var(--student-ink,#49335c);font:inherit;display:flex;flex-direction:column;align-items:center;gap:6px;min-width:76px;max-width:140px;padding:4px 8px;cursor:pointer;border-radius:10px}.workspace-circle{position:relative;display:grid;place-items:center;width:42px;height:42px;border:1px solid #cdbbdf;border-radius:50%;background:#f8f4fc;color:#623894}.workspace-circle img{width:100%;height:100%;object-fit:cover;border-radius:50%}.workspace-label{font-size:12px;line-height:1.4;text-align:center;overflow-wrap:anywhere}.workspace-label small{display:block;font-size:10px;color:#786187;margin-top:2px}button[aria-pressed=true] .workspace-circle{background:#217448;color:white;border-color:#217448}button[aria-pressed=true] .workspace-label{font-weight:700;color:#21603f}button[aria-pressed=true] .workspace-mark{background:#217448}button[aria-pressed=true] .workspace-current{color:#21603f}.workspace-mark{position:absolute;bottom:-2px;right:-3px;border:2px solid white;background:#56288d;color:white;border-radius:50%;width:20px;height:20px;display:grid;place-items:center}.workspace-circle--locked{background:#f1eff3;color:#807487;border-color:#d7cddf}.workspace-circle--locked .workspace-mark{background:#776780}.workspace-circle--add{width:32px;height:32px;margin:5px;border-style:dashed;background:transparent}button:disabled{cursor:default}button:disabled .workspace-label{color:#766781}button:not(:disabled):hover{background:#f4eef9}button:focus-visible{outline:2px solid #7853a4;outline-offset:2px}p{font-size:13px;color:#a51d32;text-align:right;margin:10px 0 0}@media(max-width:600px){.teacher-workspaces{padding:10px 12px}nav{gap:6px}button{min-width:68px;max-width:105px;padding:4px}.workspace-label{font-size:11px}}
.workspace-choice{position:relative;display:flex;flex-direction:column;align-items:center;max-width:140px}.workspace-choice:has(button[aria-pressed=true]){background:#f0f8f2;border-radius:12px;padding-bottom:5px}@media(max-width:600px){.workspace-choice{max-width:105px}}
.teacher-workspaces nav .request-bin{position:absolute;top:-5px;right:-5px;display:grid;place-items:center;width:32px;height:32px;min-width:32px;max-width:32px;padding:0;border:1px solid #f3c5ca;border-radius:50%;background:#fff1f2;color:#ba293e;z-index:1}.teacher-workspaces nav .request-bin:hover{background:#ffe0e5;color:#9d1930}.teacher-workspaces nav .request-bin:focus-visible{outline:2px solid #ba293e;outline-offset:2px}@media(pointer:coarse){.teacher-workspaces nav .request-bin{width:44px;height:44px;max-width:44px;top:-9px;right:-7px}}
.request-confirm-dialog{position:fixed;inset:0;margin:auto;width:min(460px,calc(100vw - 32px));max-height:calc(100dvh - 32px);overflow:auto;box-sizing:border-box;border:0;border-radius:16px;padding:32px;background:#fff;color:#30243d;box-shadow:0 24px 70px #25173638;text-align:left}.request-confirm-dialog::backdrop{background:#20132a80}.request-confirm-dialog:not([open]){display:none}.request-confirm-dialog .request-confirm-close{position:absolute;right:14px;top:14px;display:grid;place-items:center;width:40px;height:40px;min-width:40px;padding:0;color:#675574}.request-confirm-icon{display:grid;place-items:center;width:48px;height:48px;border-radius:12px;background:#fff0f2;color:#b52d43;margin-bottom:20px}.request-confirm-dialog h2{font-size:24px;line-height:1.25;letter-spacing:-.025em;margin:0 24px 14px 0;color:#30243d}.request-confirm-dialog p{font-size:14px;line-height:1.7;text-align:left;margin:0;color:#65566e;overflow-wrap:anywhere}.request-confirm-dialog strong{color:#30243d;font-weight:650}.request-confirm-actions{display:flex;gap:12px;margin-top:28px}.request-confirm-actions button{flex:1;min-width:0;max-width:none;min-height:46px;padding:12px 16px;font-size:14px;font-weight:650;display:flex;justify-content:center;align-items:center;border-radius:9px}.request-confirm-actions .request-keep{background:#f5f0fa;color:#56288d;border:1px solid #d8c9e7}.request-confirm-actions .request-remove{background:#b52d43;color:white;border:1px solid #b52d43}.request-confirm-actions .request-remove:hover{background:#982237}.request-confirm-actions .request-keep:hover{background:#eae0f4}.request-confirm-dialog button:disabled{opacity:.6;cursor:wait}.request-confirm-dialog .request-confirm-error{background:#fff0f2;color:#a02137;padding:12px;margin-top:16px;border-radius:8px}@media(max-width:480px){.request-confirm-dialog{padding:26px 22px}.request-confirm-dialog h2{font-size:22px}.request-confirm-actions{flex-direction:column-reverse;gap:10px}.request-confirm-actions button{width:100%}}
.request-success-dialog{width:min(420px,calc(100vw - 32px));text-align:center}.request-success-dialog .request-success-icon{margin:0 auto 20px;background:#eaf5ef;color:#217448;border-radius:50%;width:56px;height:56px}.request-success-dialog h2{margin:0 18px 12px;text-align:center}.request-success-dialog p{text-align:center}.request-confirm-actions .request-notice-ok{background:#592b91;color:#fff;min-height:46px}.request-confirm-actions .request-notice-ok:hover{background:#482172}
</style>
