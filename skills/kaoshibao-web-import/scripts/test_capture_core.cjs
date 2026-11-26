const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const extension=path.resolve(__dirname,'../extension');
const C=require(path.join(extension,'core.js'));
const record=(n=1)=>({bankTitle:'测试题库',number:n,total:2,id:String(n),qtype:'1',question:'题干'+n,options:[{Key:'A',Value:'一'},{Key:'B',Value:'二'}],answer:'A',analysis:'原解析'+n,analysisMissing:false,quality:'stable-visible-dom'});

test('only intended HTTPS origins and real counters are accepted',()=>{
 for(const url of ['https://www.zaixiankaoshi.com/online','https://www.kaoshibao.com/test'])assert.equal(C.allowed(url),true);
 for(const url of ['http://www.zaixiankaoshi.com','https://kaoshibao.com.evil.example','https://evilzaixiankaoshi.com','file:///x'])assert.equal(C.allowed(url),false);
 assert.deepEqual(C.counter('314/1340、'),{number:314,total:1340});
 assert.deepEqual(C.counter('第 3 题，共 10 题'),{number:3,total:10});
 assert.throws(()=>C.counter('12/10'));assert.throws(()=>C.counter('第 3 题'));
});
test('missing answers, unknown options and unmarked empty analysis are rejected',()=>{
 assert.equal(C.validate(record(),2).answer,'A');
 for(const change of [{answer:''},{answer:'C'},{analysis:''},{total:4},{quality:'unchecked'},{bankTitle:''},{options:[{Key:'A',Value:'1'},{Key:'A',Value:'2'}]}])assert.throws(()=>C.validate({...record(),...change},2));
 C.validate({...record(),analysis:'',analysisMissing:true},2);
});
test('fingerprints cover the title, question, choices, correct answer and original explanation',async()=>{
 const original=await C.fingerprint(record());assert.equal(original.length,64);
 for(const field of ['bankTitle','question','answer','analysis'])assert.notEqual(await C.fingerprint({...record(),[field]:field==='answer'?'B':'changed'}),original);
});
function environment(){
 let handler;const values={};
 const chrome={storage:{local:{async get(keys){if(typeof keys==='string')keys=[keys];const out={};for(const k of keys)if(k in values)out[k]=structuredClone(values[k]);return out},async set(v){Object.assign(values,structuredClone(v))}}},runtime:{onMessage:{addListener(fn){handler=fn}}}};
 const context=vm.createContext({chrome,crypto,TextEncoder,URL,console,structuredClone});
 context.importScripts=file=>vm.runInContext(fs.readFileSync(path.join(extension,file),'utf8'),context);
 vm.runInContext(fs.readFileSync(path.join(extension,'background.js'),'utf8'),context);
 return {values,call:(message,sender={id:'test'})=>new Promise(resolve=>handler(message,sender,resolve))};
}
test('durable per-question checkpoints refuse gaps, wrong tabs, mixed banks and conflicting repeats',async()=>{
 const e=environment(),sender={tab:{id:7,url:'https://www.zaixiankaoshi.com/online'}};
 const created=await e.call({command:'new',url:sender.tab.url,tabId:7,name:'测试',bankTitle:'测试题库',number:1,total:2});assert.equal(created.ok,true);const runId=created.summary.runId;
 const send=async r=>{r.fingerprint=await C.fingerprint(r);return e.call({command:'save',runId,record:r},sender)};
 assert.equal((await send(record(2))).ok,false);
 assert.equal((await send({...record(),bankTitle:'另一题库'})).ok,false);
 const first=record();first.fingerprint=await C.fingerprint(first);
 assert.equal((await e.call({command:'save',runId,record:first},{tab:{id:8,url:sender.tab.url}})).ok,false);
 assert.equal((await send(record())).saved,1);
 assert.equal((await send(record())).duplicate,true);
 assert.equal((await send({...record(),answer:'B'})).ok,false);
 assert.equal((await send(record(2))).saved,2);
 const exported=await e.call({command:'export',runId});assert.equal(exported.data.complete,true);assert.equal(exported.data.questions.length,2);assert.equal(exported.data.questions[1].analysis,'原解析2');
 const wrongResume=await e.call({command:'rebind',runId,tabId:8,url:sender.tab.url,number:2,bankTitle:'测试题库',fingerprint:'wrong'});assert.equal(wrongResume.ok,false);
 const resume=await e.call({command:'rebind',runId,tabId:8,url:sender.tab.url,number:2,bankTitle:'测试题库',fingerprint:await C.fingerprint(record(2))});assert.equal(resume.ok,true);
 assert.equal((await e.call({command:'state',runId,status:'old tab'},sender)).ok,false);
 const oldKeys=Object.keys(e.values).filter(k=>k.startsWith('capture:'));
 await e.call({command:'new',url:sender.tab.url,tabId:7,name:'新存档',bankTitle:'测试题库',number:1,total:2});
 for(const k of oldKeys)assert.ok(e.values[k]);
});
