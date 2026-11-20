/* Telegram-style pull-to-refresh and safe two-edge back navigation. */
(function () {
  'use strict';
  const PULL_SCREENS=new Set(['screen-main','screen-take','screen-platforms','screen-th','screen-rooms','screen-settings']);
  const NO_BACK_SCREENS=new Set(['screen-main','screen-login','screen-register','screen-edit-item','screen-add','screen-move-item','screen-batch-move']);
  const EDGE=34, PULL_TRIGGER=70, BACK_TRIGGER=82;
  const easePull=delta=>Math.min(110,Math.max(0,delta)*0.54);
  function install(){
    if(!('ontouchstart' in window)&&!(navigator.maxTouchPoints>0))return;
    const style=document.createElement('style');
    style.textContent=`
      .warehouse-pull-indicator{position:fixed;left:50%;top:calc(env(safe-area-inset-top) + 12px);width:34px;height:34px;display:grid;place-items:center;z-index:190;pointer-events:none;opacity:0;transform:translate3d(-50%,-12px,0);transition:opacity .12s ease}
      .warehouse-pull-spinner{width:25px;height:25px;border:2.5px solid color-mix(in srgb,var(--primary) 19%,transparent);border-top-color:var(--primary);border-right-color:var(--primary);border-radius:50%;box-sizing:border-box}
      .warehouse-pull-indicator.loading .warehouse-pull-spinner{animation:warehouse-telegram-spin .66s linear infinite}
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
    const wheel=document.createElement('span');
    wheel.className='warehouse-pull-spinner';
    indicator.append(wheel);
    document.body.append(indicator);
    const backHint=document.createElement('div');
    backHint.className='warehouse-edge-indicator';
    backHint.setAttribute('aria-hidden','true');
    backHint.textContent='‹';
    document.body.append(backHint);
    const tg=window.Telegram?.WebApp;
    if(tg?.initData&&typeof tg.disableVerticalSwipes==='function'){
      try{tg.disableVerticalSwipes()}catch(e){}
    }
    let gesture=null,refreshing=false,finishTimer=null;
    let currentVersion=document.querySelector('meta[name="warehouse-app-version"]')?.content||'';
    const screen=()=>typeof currentScreen==='string'?document.getElementById(currentScreen):null;
    const blocked=()=>!!document.querySelector('.modal-overlay:not(.hidden),dialog[open]');
    const editing=target=>!!target?.closest?.('input,textarea,select,[contenteditable="true"],[role="textbox"],.bottom-nav,.floating-bar,.modal-content');
    const pageTop=()=>window.scrollY<3&&document.scrollingElement?.scrollTop<3;
    function showRing(distance,loading=false){
      indicator.classList.toggle('loading',loading);
      indicator.style.opacity=loading?'1':String(Math.min(1,Math.max(0,(distance-13)/36)));
      indicator.style.transform='translate3d(-50%,'+Math.min(15,distance*.16)+'px,0)';
      if(!loading)wheel.style.transform='rotate('+Math.round(distance*4.5)+'deg)';
      else wheel.style.removeProperty('transform');
    }
    function hideIndicators(){
      indicator.style.opacity='0';
      indicator.classList.remove('loading');
      backHint.classList.remove('visible','left','right');
    }
    function translate(el,axis,distance,animate=false){
      if(!el?.isConnected)return;
      el.dataset.warehouseGestureTick='';
      el.style.transition=animate?'transform 330ms cubic-bezier(.2,.85,.2,1)':'none';
      el.style.transform='translate3d('+(axis==='x'?distance:0)+'px,'+(axis==='y'?distance:0)+'px,0)';
    }
    function springBack(el,axis){
      if(!el?.isConnected)return;
      translate(el,axis,0,true);
      const stamp=String(Date.now())+':'+String(Math.random());
      el.dataset.warehouseGestureTick=stamp;
      setTimeout(()=>{if(el.isConnected&&el.dataset.warehouseGestureTick===stamp){el.style.removeProperty('transform');el.style.removeProperty('transition');delete el.dataset.warehouseGestureTick;}},350);
    }
    function clearGesture(){
      if(gesture&&gesture.axis!=='none')springBack(gesture.root,gesture.axis);
      gesture=null;
      backHint.classList.remove('visible','left','right');
      if(!refreshing)hideIndicators();
    }
    async function serverVersion(){
      const response=await fetch('/app/version',{cache:'no-store',credentials:'same-origin'});
      if(!response.ok)throw Error('Сервер недоступен');
      const data=await response.json();
      if(typeof data.version!=='string'||!data.version)throw Error('Не удалось проверить версию');
      return data.version;
    }
    if(!currentVersion)serverVersion().then(v=>{currentVersion=v}).catch(()=>{});
    async function refresh(root){
      refreshing=true;
      showRing(80,true);
      translate(root,'y',80,true);
      try{
        const version=await serverVersion();
        if(currentVersion&&version!==currentVersion){
          location.reload();
          return;
        }
        currentVersion=version;
        if(typeof api==='function')await api('/api/me');
        const jobs=[];
        for(const name of ['loadItems','loadLocations','loadLowStock','loadStats','loadDashboard17','loadMyBookings']){
          const func=window[name];
          if(typeof func==='function')jobs.push(Promise.resolve().then(()=>func()));
        }
        await Promise.all(jobs);
        if(typeof currentScreen==='string'&&currentScreen==='screen-take'&&typeof renderTakeItems==='function')renderTakeItems();
        if(typeof currentScreen==='string'&&currentScreen==='screen-platforms'&&typeof syncGoogle==='function')await syncGoogle('кц');
        if(typeof currentScreen==='string'&&currentScreen==='screen-th'&&typeof syncGoogle==='function')await syncGoogle('тх мск');
        if(typeof tg?.HapticFeedback?.notificationOccurred==='function')tg.HapticFeedback.notificationOccurred('success');
      }catch(error){
        if(error?.status===401||error?.status===403){location.reload();return}
        if(typeof notify==='function')notify('Не удалось обновить: проверьте соединение');
      }finally{
        clearTimeout(finishTimer);
        finishTimer=setTimeout(()=>{springBack(root,'y');hideIndicators();refreshing=false},260);
      }
    }
    document.addEventListener('touchstart',event=>{
      if(refreshing||event.touches.length!==1||blocked())return;
      const root=screen();
      if(!root||root.classList.contains('hidden')||editing(event.target))return;
      const touch=event.touches[0],width=document.documentElement.clientWidth||window.innerWidth;
      const atLeft=touch.clientX<=EDGE,atRight=touch.clientX>=width-EDGE;
      const backAllowed=!NO_BACK_SCREENS.has(currentScreen)&&typeof goBack==='function'&&(atLeft||atRight);
      const pullAllowed=PULL_SCREENS.has(currentScreen)&&pageTop();
      if(!backAllowed&&!pullAllowed)return;
      gesture={root,x:touch.clientX,y:touch.clientY,axis:'none',side:atLeft?'left':atRight?'right':null,pullAllowed,backAllowed,amount:0};
    },{passive:true});
    document.addEventListener('touchmove',event=>{
      const g=gesture;
      if(!g)return;
      if(event.touches.length!==1||screen()!==g.root||blocked()){clearGesture();return;}
      const touch=event.touches[0],dx=touch.clientX-g.x,dy=touch.clientY-g.y;
      if(g.axis==='none'){
        const inward=g.side==='left'?dx:g.side==='right'?-dx:0;
        if(g.backAllowed&&inward>13&&Math.abs(dx)>Math.abs(dy)*1.35){g.axis='x';backHint.classList.add('visible',g.side);}
        else if(g.pullAllowed&&dy>13&&Math.abs(dy)>Math.abs(dx)*1.3&&pageTop())g.axis='y';
        else if(Math.abs(dy)>26||Math.abs(dx)>26){gesture=null;return;}
      }
      if(g.axis==='x'){
        const inward=g.side==='left'?dx:-dx;
        if(inward<=0){clearGesture();return;}
        if(event.cancelable)event.preventDefault();
        g.amount=inward;
        translate(g.root,'x',(g.side==='left'?1:-1)*Math.min(52,inward*.32));
        backHint.classList.toggle('visible',inward>13);
        if(inward>=BACK_TRIGGER&&!g.ready){g.ready=true;try{tg?.HapticFeedback?.impactOccurred('light')}catch(e){}}
      }else if(g.axis==='y'){
        if(dy<=0||!pageTop()){clearGesture();return;}
        if(event.cancelable)event.preventDefault();
        const distance=easePull(dy);
        g.amount=distance;
        translate(g.root,'y',distance);
        showRing(distance,false);
        if(distance>=PULL_TRIGGER&&!g.ready){g.ready=true;try{tg?.HapticFeedback?.impactOccurred('light')}catch(e){}}
      }
    },{passive:false});
    document.addEventListener('touchend',event=>{
      const g=gesture;
      if(!g)return;
      if(event.touches.length>0){clearGesture();return;}
      gesture=null;
      if(g.axis==='x'){
        springBack(g.root,'x');
        backHint.classList.remove('visible','left','right');
        if(g.amount>=BACK_TRIGGER&&typeof goBack==='function')goBack();
      }else if(g.axis==='y'){
        if(g.amount>=PULL_TRIGGER)refresh(g.root);
        else{springBack(g.root,'y');hideIndicators();}
      }else hideIndicators();
    },{passive:true});
    document.addEventListener('touchcancel',clearGesture,{passive:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
})();