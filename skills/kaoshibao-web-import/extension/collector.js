(function(){
'use strict';
if(window.__KSB_VISIBLE_CAPTURE__)return;
window.__KSB_VISIBLE_CAPTURE__=true;
const C=CaptureCore;let running=false,stopped=false;
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const visible=e=>Boolean(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none');
function one(scope,selector,label){if(!selector)throw Error(`缺少${label}选择器`);const matches=[...scope.querySelectorAll(selector)].filter(visible);if(matches.length!==1)throw Error(`${label}应唯一可见，当前 ${matches.length} 个`);return matches[0]}
function blocked(){
 if(document.hidden)throw Error('原题库标签进入后台，已停止；回到原页后继续');
 const dialogs=[...document.querySelectorAll('[role="dialog"],.el-message-box,.el-message,.ant-modal,.ant-message')].filter(visible).map(e=>e.innerText).join(' ');
 const text=dialogs+' '+document.title+' '+document.body.innerText.slice(0,2500);
 if(/(账号|帐号).{0,8}(禁用|封禁|异常)|操作过于频繁|访问过于频繁|请.{0,8}完成.{0,8}验证|人机验证|安全验证/.test(text)||[...document.querySelectorAll('iframe[src*="captcha"],iframe[src*="challenge"],input[name*="captcha"]')].some(visible))throw Error('检测到验证、频率限制或账号异常；停止，不重试或绕过');
}
function markup(node){
 const copy=node.cloneNode(true);
 for(const box of copy.querySelectorAll('mjx-container')){const math=box.querySelector('math');if(math)box.replaceWith(math.cloneNode(true));else throw Error('公式缺少可保存的 MathML，请人工处理')}
 for(const control of copy.querySelectorAll('button,script,style,iframe,object'))control.remove();
 for(const img of copy.querySelectorAll('img')){const src=img.getAttribute('src');if(src){try{img.setAttribute('src',new URL(src,location.href).href)}catch{}}for(const attr of [...img.attributes])if(attr.name.startsWith('on'))img.removeAttribute(attr.name)}
 return copy.innerHTML.trim();
}
function read(config){
 blocked();const root=one(document,config.root,'本题容器');
 if(root===document.body||root===document.documentElement)throw Error('本题容器不能选整个网页');
 if(config.loading&&[...document.querySelectorAll(config.loading)].some(visible))throw Error('WAIT: 页面仍在加载');
 if(config.ready&&!visible(document.querySelector(config.ready)))throw Error('WAIT: 本题尚未就绪');
 const before=C.counter(one(document,config.counter,'题号').innerText);
 const stem=one(root,config.question,'题干'),answer=one(root,config.answer,'正确答案区'),analysis=one(root,config.analysis,'原解析区');
 if(stem===answer||stem===analysis||answer===analysis||stem.contains(answer)||stem.contains(analysis)||answer.contains(stem)||analysis.contains(stem)||answer.contains(analysis)||analysis.contains(answer))throw Error('题干、答案与解析容器重叠，请缩小选择器');
 const answerText=answer.innerText.trim();
 if(!/正确答案/.test(answerText))throw Error('正确答案区缺少“正确答案”标签，不能使用你的答案或选项颜色推测');
 const analysisLabelText=analysis.innerText.trim();
 const answerContent=config.answerContent?one(answer,config.answerContent,'正确答案正文'):answer;
 const analysisContent=config.analysisContent?one(analysis,config.analysisContent,'原解析正文'):analysis;
 const analysisText=analysisContent.innerText.trim();
 if(!/解析/.test(analysisLabelText))throw Error('解析区缺少原解析标签，请展开背题模式并重新定位');
 const type=config.type?one(root,config.type,'题型').innerText.trim():'';
 const qtype=/多选/.test(type)?'2':/单选/.test(type)?'1':/简答/.test(type)?'5':'';
 const options=[...root.querySelectorAll(config.options)].filter(visible).map(option=>{
  const label=one(option,config.optionKey,'选项字母'),key=label.innerText.trim();
  if(!/^[A-Z][.、．:]?$/.test(key))throw Error('选项原字母无法辨认');
  const copy=option.cloneNode(true);for(const e of copy.querySelectorAll(config.optionKey))e.remove();
  return {Key:key[0],Value:markup(copy)};
 });
 let answerValue=answerContent.innerText.trim().replace(/^\s*正确答案\s*[:：]?\s*/,'').replace(/\s*纠错\s*$/,'').trim();
 if(['1','2'].includes(qtype)){answerValue=answerValue.replace(/[\s,，、;；]+/g,'');if(!/^[A-Z]+$/.test(answerValue))throw Error('答案区混入其他文字，请缩小到正确答案内容所在容器')}
 else answerValue=markup(answerContent).replace(/正确答案\s*[:：]?/,'');
 const confirmedEmpty=config.emptyAnalysisNumber===before.number&&!analysisText.replace(/^(?:试题解析|答案解析|解析)\s*[:：]?\s*/,'').trim();
 const analysisMissing=confirmedEmpty||/^(?:试题解析|答案解析|解析)\s*[:：]?\s*(?:暂无解析|暂无|无解析|未提供解析)[。.!！]?\s*$/.test(analysisText);
 if(!analysisMissing&&!analysisText.replace(/^(?:试题解析|答案解析|解析)\s*[:：]?\s*/,'').trim())throw Error('解析仍为空，无法确认已加载');
 const after=C.counter(one(document,config.counter,'题号').innerText);
 if(before.number!==after.number||before.total!==after.total)throw Error('WAIT: 读取时题号发生变化');
 const id=config.idAttribute?root.getAttribute(config.idAttribute)||'':'';
 const record={...before,bankTitle:one(document,config.bankTitle,'题库标题').innerText.trim(),id:id||String(before.number),qtype,question:markup(stem),options,answer:answerValue,analysis:analysisMissing?'':markup(analysisContent),analysisMissing,emptyAnalysisConfirmed:confirmedEmpty,quality:'stable-visible-dom'};
 C.validate(record,before.total);return record;
}
async function stable(config,expected){
 let previous='',count=0,latest,lastError='';const start=Date.now();
 while(!stopped&&Date.now()-start<20000){
  try{latest=read(config);if(expected&&latest.number!==expected)throw Error('WAIT: 正在等待目标题号');const value=C.canonical(latest);count=value===previous?count+1:1;previous=value;if(count>=4){latest.fingerprint=await C.fingerprint(latest);return latest}}
  catch(error){lastError=error.message;if(!lastError.startsWith('WAIT:'))throw error;count=0;previous=''}
  await sleep(800);
 }
 throw Error(stopped?'已由用户停止':lastError||'页面未稳定，已停止');
}
async function state(runId,status,error=''){await chrome.runtime.sendMessage({command:'state',runId,status,error})}
async function run(message){
 if(running)throw Error('采集正在运行');
 if(!C.allowed(location.href))throw Error('仅限 HTTPS 考试宝网页');
 running=true;stopped=false;const {config,runId,saved,total}=message;
 try{
  let current=await stable(config),written=saved;
  if(current.total!==total||![saved||1,saved+1].includes(current.number))throw Error(`请回到第 ${saved||1} 题，或尚未保存的第 ${saved+1} 题继续`);
  for(let i=0;i<message.batchSize&&!stopped;i++){
   const result=await chrome.runtime.sendMessage({command:'save',runId,record:current});if(!result.ok)throw Error(result.error);written=result.saved;
   if(written===total||i===message.batchSize-1||stopped)break;
   await sleep(1600);if(stopped)break;
   const before=await stable(config,current.number);if(before.fingerprint!==current.fingerprint)throw Error('保存后页面内容发生变化，停止以防异步错位');
   const next=one(document,config.next,'下一题按钮');if(next.disabled||next.getAttribute('aria-disabled')==='true')throw Error('下一题按钮不可用');
   next.click();current=await stable(config,written+1);
  }
  await state(runId,written===total?'题数已齐，待抽查':`已暂停，保存至第 ${written} 题`);
 }catch(error){await state(runId,'已停止',error.message)}finally{running=false}
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
 if(message.command==='stop'){stopped=true;respond({ok:true});return}
 if(message.command==='preview'){if(running){respond({ok:false,error:'采集运行时不允许预览'});return}stopped=false;stable(message.config).then(r=>respond({ok:true,bankTitle:r.bankTitle,number:r.number,total:r.total,questionPreview:r.question.replace(/<[^>]*>/g,' ').slice(0,100),optionKeys:r.options.map(o=>o.Key).join(''),answer:r.answer.replace(/<[^>]*>/g,' ').slice(0,50),analysisCharacters:r.analysis.length,analysisMissing:r.analysisMissing,fingerprint:r.fingerprint}),e=>respond({ok:false,error:e.message}));return true}
 if(message.command==='run'){if(running){respond({ok:false,error:'正在采集，请勿重复开始'});return}void run(message);respond({ok:true});return}
});
})();
