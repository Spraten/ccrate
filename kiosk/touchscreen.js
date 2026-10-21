(() => {
  const CLIENT_KEY = 'ccrate-touchscreen-client';
  const clientId = localStorage.getItem(CLIENT_KEY) || (() => { const id = crypto.randomUUID(); localStorage.setItem(CLIENT_KEY, id); return id; })();
  const state = {generation:null, instance:null, flow:null, draft:[], epoch:0, timer:null};
  const home = document.querySelector('#home'), flow = document.querySelector('#flow'), title = document.querySelector('#flow-title'), message = document.querySelector('#flow-message'), member = document.querySelector('#member'), done = document.querySelector('#done');
  async function api(path, options={}) { return fetch(path,{...options,headers:{...(options.headers||{}),'X-Homebox-Client':clientId}}); }
  function clearDraft(){state.draft=[];state.flow=null;state.epoch++;home.hidden=false;flow.hidden=true;done.hidden=true;member.textContent='No active member';}
  function adopt(session){const gen=session?.generation??null, inst=session?.instance??null;if(state.generation!==gen||state.instance!==inst){state.generation=gen;state.instance=inst;clearDraft();}if(session?.user){member.textContent=session.user.name||session.user.displayName||'Active member';}else if(gen===null){member.textContent='No active member';}}
  async function refresh(){const epoch=state.epoch;try{const res=await api('/api/session');if(!res.ok)return;const session=await res.json();if(epoch!==state.epoch)return;adopt(session);}catch(_){}}
  document.querySelectorAll('[data-flow]').forEach(button=>button.addEventListener('click',()=>{state.flow=button.dataset.flow;home.hidden=true;flow.hidden=false;title.textContent=state.flow==='checkout'?'Check out':'Return';message.textContent='Scan your member badge to begin.';}));
  done.addEventListener('click',async()=>{const generation=state.generation,instance=state.instance;try{await api('/session/end',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({generation,instance})});}finally{clearDraft();state.generation=null;state.instance=null;}});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  refresh();setInterval(refresh,5000);
})();
