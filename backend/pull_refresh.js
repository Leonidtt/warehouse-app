/* Pull-to-refresh and two-sided edge navigation. */
(function () {
  'use strict';
  const PULL_SCREENS=new Set(['screen-main','screen-take','screen-platforms','screen-th','screen-rooms','screen-settings']);
  const NO_BACK_SCREENS=new Set(['screen-main','screen-login','screen-register','screen-edit-item','screen-add','screen-move-item','screen-batch-move']);
  const EDGE=34, AXIS_START=12, PULL_TRIGGER=48, BACK_TRIGGER=82;
  const pullOffset=delta=>72*(1-Math.exp(-Math.max(0,delta-AXIS_START)/69));

  function install(){
    if(!('ontouchstart' in window)&&!navigator.maxTouchPoints)return;
    const style=document.createElement('style');
    style.textContent=`
      .warehouse-pull-indicator{position:fixed;left:50%;top:0;width:36px;height:36px;display:grid;place-items:center;z-index:190;pointer-events:none;opacity:0;transform:translate3d(-50%,0,0);color:var(--primary);background:var(--card-bg);border:1px solid var(--border);border-radius:50%;box-shadow:0 3px 12px #0002}
      .warehouse-pull-indicator.settling{transition:transform 240ms cubic-bezier(.2,.8,.2,1),opacity 170ms ease}
      .warehouse-pull-spinner{width:24px;height:24px}
      .warehouse-pull-indicator.loading .warehouse-pull-spinner{animation:warehouse-telegram-spin .72s linear infinite}
      .warehouse-edge-indicator{position:fixed;top:50%;width:37px;height:37px;display:grid;place-items:center;border:1px solid var(--border);border-radius:50%;background:var(--card-bg);color:var(--primary);box-shadow:var(--shadow);font:600 30px/1 system-ui;z-index:400;pointer-events:none;opacity:0;transform:translateY(-50%) scale(.72);transition:opacity .1s,transform .12s}
      .warehouse-edge-indicator.visible{opacity:1;transform:translateY(-50%) scale(1)}
      .warehouse-edge-indicator.left{left:9px}.warehouse-edge-indicator.right{right:9px}
      @keyframes warehouse-telegram-spin{to{transform:rotate(360deg)}}
      @media(prefers-reduced-motion:reduce){.warehouse-pull-indicator,.warehouse-edge-indicator{transition:none!important}.warehouse-pull-indicator.loading .warehouse-pull-spinner{animation:none}}
    `;
    document.head.append(style);
    const indicator=document.createElement('div');
    indicator.className='warehouse-pull-indicator';
    indicator.setAttribute('role','status');
    indicator.setAttribute('aria-label','Обновление данных');
    indicator.innerHTML='<svg class="warehouse-pull-spinner" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M 19.5 12 A 7.5 7.5 0 1 1 12 4.5" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>';
    const wheel=indicator.firstElementChild;
    document.body.append(indicator);
    const backHint=document.createElement('div');
    backHint.className='warehouse-edge-indicator';
    backHint.setAttribute('aria-hidden','true');
    backHint.textContent='‹';
    document.body.append(backHint);
    const tg=window.Telegram?.WebApp;
    if(tg?.initData&&typeof tg.disableVerticalSwipes==='function'){
      try{tg.disableVerticalSwipes()}catch(error){}
    }

    let gesture=null,frame=0,refreshing=false;
    let currentVersion=document.querySelector('meta[name="warehouse-app-version"]')?.content||'';
    const blocked=()=>!!document.querySelector('.modal-overlay:not(.hidden):not([inert]),dialog[open]');
    const editing=target=>!!target?.closest?.('input,textarea,select,[contenteditable="true"],[role="textbox"],.bottom-nav,.floating-bar,.modal-content');
    const pageTop=()=>window.scrollY<3;
    const resetTimers=new WeakMap();

    function ring(anchor,distance){
      indicator.style.opacity=String(Math.min(1,distance/24));
      indicator.style.transform='translate3d(-50%,'+(anchor+distance*.48)+'px,0)';
      wheel.style.transform='rotate('+distance*3+'deg)';
    }
    function hideRing(anchor){
      indicator.classList.add('settling');
      indicator.classList.remove('loading');
      ring(anchor,0);
    }
    function translateBack(root,amount){
      clearTimeout(resetTimers.get(root));
      root.style.transition='none';
      root.style.transform='translate3d('+amount+'px,0,0)';
    }
    function springBack(root){
      clearTimeout(resetTimers.get(root));
      root.style.transition='transform 270ms cubic-bezier(.2,.8,.2,1)';
      root.style.transform='translate3d(0,0,0)';
      resetTimers.set(root,setTimeout(()=>{
        root.style.removeProperty('transition');
        root.style.removeProperty('transform');
      },285));
    }
    function paint(){
      frame=0;
      if(!gesture)return;
      const {axis,amount,root,side,anchor}=gesture;
      if(axis==='y')ring(anchor,amount);
      if(axis==='x')translateBack(root,(side==='left'?1:-1)*Math.min(52,amount*.32));
    }
    function finishGesture(){
      if(frame){cancelAnimationFrame(frame);frame=0}
      const finished=gesture;
      gesture=null;
      backHint.classList.remove('visible','left','right');
      return finished;
    }
    function cancelGesture(){
      const finished=finishGesture();
      if(finished?.axis==='x')springBack(finished.root);
      if(finished?.axis==='y')hideRing(finished.anchor);
    }
    function readyFeedback(g,threshold){
      if(g.amount<threshold||g.ready)return;
      g.ready=true;
      try{tg?.HapticFeedback?.impactOccurred('light')}catch(error){}
    }

    async function serverVersion(){
      const response=await fetch('/app/version',{cache:'no-store',credentials:'same-origin'});
      if(!response.ok)throw Error('Сервер недоступен');
      const data=await response.json();
      if(typeof data.version!=='string'||!data.version)throw Error('Не удалось проверить версию');
      return data.version;
    }
    if(!currentVersion)serverVersion().then(version=>{currentVersion=version}).catch(()=>{});
    async function refresh(g){
      refreshing=true;
      ring(g.anchor,g.amount);
      indicator.classList.add('settling','loading');
      ring(g.anchor,PULL_TRIGGER);
      wheel.style.removeProperty('transform');
      try{
        const [version]=await Promise.all([serverVersion(),api('/api/me')]);
        if(currentVersion&&version!==currentVersion){
          location.reload();
          return;
        }
        currentVersion=version;
        const jobs=[loadItems(),loadLocations(),loadDashboard17({force:true}),loadMyBookings()];
        if(g.screenId==='screen-platforms')jobs.push(syncGoogle('кц',{silent:true}));
        if(g.screenId==='screen-th')jobs.push(syncGoogle('тх мск',{silent:true}));
        const results=await Promise.all(jobs);
        if(results.includes(false))throw Error('Данные обновились не полностью');
        try{tg?.HapticFeedback?.notificationOccurred('success')}catch(error){}
      }catch(error){
        if(error?.status===401||error?.status===403){location.reload();return}
        notify('Не удалось обновить данные');
      }finally{
        hideRing(g.anchor);
        refreshing=false;
      }
    }

    document.addEventListener('touchstart',event=>{
      if(event.touches.length!==1){cancelGesture();return}
      if(refreshing||blocked()||editing(event.target))return;
      const screenId=currentScreen;
      const root=document.getElementById(screenId);
      if(!root||root.classList.contains('hidden'))return;
      const touch=event.touches[0],width=document.documentElement.clientWidth;
      const side=touch.clientX<=EDGE?'left':touch.clientX>=width-EDGE?'right':null;
      const backAllowed=!!side&&!NO_BACK_SCREENS.has(screenId);
      const pullAllowed=PULL_SCREENS.has(screenId)&&pageTop();
      if(!backAllowed&&!pullAllowed)return;
      const header=root.querySelector('.sticky-header');
      const anchor=pullAllowed?Math.max(54,Math.round(header?.getBoundingClientRect().bottom||0)+8):0;
      gesture={root,screenId,x:touch.clientX,y:touch.clientY,axis:null,side,pullAllowed,backAllowed,anchor,amount:0};
    },{passive:true});
    document.addEventListener('touchmove',event=>{
      const g=gesture;
      if(!g)return;
      if(event.touches.length!==1||currentScreen!==g.screenId){cancelGesture();return}
      const touch=event.touches[0],dx=touch.clientX-g.x,dy=touch.clientY-g.y;
      const inward=g.side==='left'?dx:-dx;
      if(!g.axis){
        if(g.backAllowed&&inward>AXIS_START&&Math.abs(dx)>Math.abs(dy)*1.35){
          g.axis='x';
          backHint.classList.add('visible',g.side);
        }else if(g.pullAllowed&&dy>AXIS_START&&dy>Math.abs(dx)*1.3&&pageTop()){
          g.axis='y';
          indicator.classList.remove('settling');
        }else{
          if(Math.abs(dy)>26||Math.abs(dx)>26)gesture=null;
          return;
        }
      }
      if(event.cancelable)event.preventDefault();
      g.amount=g.axis==='y'?pullOffset(dy):Math.max(0,inward);
      readyFeedback(g,g.axis==='y'?PULL_TRIGGER:BACK_TRIGGER);
      if(!frame)frame=requestAnimationFrame(paint);
    },{passive:false});
    document.addEventListener('touchend',event=>{
      if(event.touches.length){cancelGesture();return}
      const g=finishGesture();
      if(g?.axis==='x'){
        springBack(g.root);
        if(g.amount>=BACK_TRIGGER)goBack();
      }else if(g?.axis==='y'){
        if(g.amount>=PULL_TRIGGER)refresh(g);
        else hideRing(g.anchor);
      }
    },{passive:true});
    document.addEventListener('touchcancel',cancelGesture,{passive:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
})();
