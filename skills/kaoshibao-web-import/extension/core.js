(function(root){
'use strict';
const allowed=url=>{try{const u=new URL(url);return u.protocol==='https:'&&/(^|\.)(kaoshibao\.com|zaixiankaoshi\.com)$/.test(u.hostname)}catch{return false}};
function counter(text){
 const s=String(text).replace(/,/g,'');
 const m=s.match(/(?:第\s*)?(\d+)\s*\/\s*(\d+)/)||s.match(/第\s*(\d+)\s*题[\s\S]{0,15}?共\s*(\d+)\s*题/);
 if(!m||+m[1]<1||+m[2]<1||+m[1]>+m[2])throw Error('无法确认当前题号与总题数');
 return {number:+m[1],total:+m[2]};
}
const canonical=r=>JSON.stringify([r.bankTitle,r.number,r.total,r.id||'',r.question,r.options,r.answer,r.analysis,r.qtype,r.analysisMissing]);
async function fingerprint(record){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(record))))].map(x=>x.toString(16).padStart(2,'0')).join('')}
function validate(r,total){
 if(!r||typeof r.id!=='string'||!r.id||r.id.length>255||typeof r.bankTitle!=='string'||!r.bankTitle.trim()||!Number.isInteger(r.number)||r.number<1||r.number>total||r.total!==total||typeof r.question!=='string'||!r.question.trim()||typeof r.answer!=='string'||!r.answer.trim()||typeof r.analysis!=='string'||(!r.analysis.trim()&&r.analysisMissing!==true)||!Array.isArray(r.options))throw Error('题干、答案、解析或题号不完整');
 const keys=r.options.map(o=>o.Key);
 if(keys.some(k=>!/^([A-Z])$/.test(k))||new Set(keys).size!==keys.length||r.options.some(o=>typeof o.Value!=='string'))throw Error('选项字母缺失或重复');
 if(['1','2'].includes(r.qtype)&&(!keys.length||!/^[A-Z]+$/.test(r.answer)||[...r.answer].some(k=>!keys.includes(k))||(r.qtype==='1'&&r.answer.length!==1)))throw Error('正确答案与选项不对应');
 if(r.quality!=='stable-visible-dom')throw Error('题目未完成稳定性检查');
 return r;
}
root.CaptureCore={allowed,counter,canonical,fingerprint,validate};
if(typeof module!=='undefined')module.exports=root.CaptureCore;
})(typeof globalThis!=='undefined'?globalThis:this);
