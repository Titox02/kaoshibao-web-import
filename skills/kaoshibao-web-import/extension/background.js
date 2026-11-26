'use strict';
importScripts('core.js');
const C=CaptureCore, store=chrome.storage.local;
let queue=Promise.resolve();
const metaKey='capture-meta';
const recordKey=(id,n)=>`capture:${id}:${String(n).padStart(8,'0')}`;
async function meta(){return (await store.get(metaKey))[metaKey]||null}
function summary(m){return m?{name:m.name,saved:m.saved,total:m.total,lastNumber:m.saved,status:m.status,error:m.error||'',runId:m.runId}:null}
async function handle(message,sender){
 if(!message||!['new','status','save','state','export','config','rebind'].includes(message.command))throw Error('未知操作');
 if(message.command==='config'){if(sender.tab)throw Error('配置只能从扩展面板设置');await store.set({'capture-config':message.config});return {ok:true}}
 if(message.command==='status')return {ok:true,summary:summary(await meta()),config:(await store.get('capture-config'))['capture-config']||null};
 if(message.command==='new'){
  if(sender.tab||!C.allowed(message.url)||message.number!==1||!Number.isInteger(message.total)||message.total<1||message.total>50000)throw Error('新存档必须从已授权考试宝页面第 1 题开始');
  const m={runId:crypto.randomUUID(),name:String(message.name||'考试宝题库').slice(0,100),bankTitle:String(message.bankTitle||''),origin:new URL(message.url).origin,tabId:message.tabId,total:message.total,saved:0,status:'已创建',created:new Date().toISOString(),reviewed:false};
  await store.set({[metaKey]:m});return {ok:true,summary:summary(m)};
 }
 const m=await meta();if(!m)throw Error('请先从第 1 题新建存档');
 if(message.runId!==m.runId)throw Error('存档已切换，请重新打开面板');
 if(message.command==='rebind'){
  if(sender.tab||!C.allowed(message.url)||new URL(message.url).origin!==m.origin||message.number!==m.saved||message.bankTitle!==m.bankTitle||m.saved<1)throw Error('请在原题库打开最后保存的题号后再验证');
  const checkpoint=(await store.get(recordKey(m.runId,m.saved)))[recordKey(m.runId,m.saved)];
  if(!checkpoint||checkpoint.fingerprint!==message.fingerprint)throw Error('当前题目与原存档断点内容不一致，不能恢复');
  m.tabId=message.tabId;m.status='断点核对通过，可继续';m.error='';await store.set({[metaKey]:m});return {ok:true,summary:summary(m)};
 }
 if(message.command==='export'){
  if(sender.tab)throw Error('请从扩展面板导出');
  const data=await store.get(Array.from({length:m.saved},(_,i)=>recordKey(m.runId,i+1)));
  const questions=Array.from({length:m.saved},(_,i)=>data[recordKey(m.runId,i+1)]);
  if(questions.some(r=>!r))throw Error('存档存在缺题，停止导出');
  return {ok:true,data:{name:m.name,sourceOrigin:m.origin,expectedCount:m.total,exportedCount:questions.length,complete:questions.length===m.total,exportMethod:'当前可见 DOM 逐题采集，无主动题库接口请求',contentVerification:'稳定 DOM 检查，仍需抽查，不代表原题答案已校订',questions}};
 }
 if(!sender.tab||sender.tab.id!==m.tabId||!C.allowed(sender.tab.url)||new URL(sender.tab.url).origin!==m.origin)throw Error('不是本次存档的原网页标签');
 if(message.command==='state'){
  m.status=String(message.status||'已停止').slice(0,120);m.error=String(message.error||'').slice(0,200);await store.set({[metaKey]:m});return {ok:true};
 }
 const r=C.validate(message.record,m.total);if(r.bankTitle!==m.bankTitle)throw Error('题库名称发生变化，已停止');const hash=await C.fingerprint(r);
 if(hash!==r.fingerprint)throw Error('题目指纹不一致');
 const key=recordKey(m.runId,r.number),existing=(await store.get(key))[key];
 if(existing){if(existing.fingerprint!==hash)throw Error('此题与已保存版本不一致，已停止以保留原记录');return {ok:true,saved:m.saved,duplicate:true}}
 const idKey=`capture-id:${m.runId}:${encodeURIComponent(r.id)}`,priorId=(await store.get(idKey))[idKey];
 if(priorId&&priorId!==r.number)throw Error('原始题目 ID 重复，请检查是否错误选到整份试卷 ID');
 if(r.number!==m.saved+1)throw Error(`应保存第 ${m.saved+1} 题，当前为 ${r.number}，不能跳题`);
 m.saved=r.number;m.status=m.saved===m.total?'题数已齐，待抽查':'已保存';m.error='';m.updated=new Date().toISOString();
 await store.set({[key]:r,[idKey]:r.number,[metaKey]:m});return {ok:true,saved:m.saved};
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
 const task=queue.then(()=>handle(message,sender));queue=task.catch(()=>{});
 task.then(respond,error=>respond({ok:false,error:error.message}));return true;
});
