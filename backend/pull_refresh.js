/* Pull to refresh equipment and detect a newly deployed build. */
(function () {
  'use strict';
  function install() {
    if (!('ontouchstart' in window)) return;
    const allowed = new Set(['screen-main', 'screen-take', 'screen-platforms', 'screen-th', 'screen-rooms', 'screen-settings']);
    const style = document.createElement('style');
    style.textContent = [
      '.warehouse-pull-indicator{position:fixed;left:50%;top:max(8px,env(safe-area-inset-top));transform:translate(-50%,-140%);display:flex;align-items:center;gap:8px;border-radius:24px;padding:8px 12px;background:var(--card-bg);border:1px solid var(--border);box-shadow:var(--shadow);font:600 12px system-ui;color:var(--text);z-index:99999;pointer-events:none;transition:transform .16s ease,opacity .16s ease;opacity:0}',
      '.warehouse-pull-indicator.visible{opacity:1;transform:translate(-50%,0)}',
      '.warehouse-pull-spinner{width:17px;height:17px;border:2px solid var(--border);border-top-color:var(--primary);border-radius:50%;animation:warehouse-pull-spin .75s linear infinite}',
      '@keyframes warehouse-pull-spin{to{transform:rotate(360deg)}}'
    ].join('');
    document.head.appendChild(style);
    const indicator=document.createElement('div');
    indicator.className='warehouse-pull-indicator';
    indicator.setAttribute('role','status');
    indicator.setAttribute('aria-live','polite');
    indicator.innerHTML='<span class="warehouse-pull-spinner" aria-hidden="true"></span><span class="warehouse-pull-caption">Потяните для обновления</span>';
    document.body.appendChild(indicator);
    const caption=indicator.querySelector('.warehouse-pull-caption');
    const tg=window.Telegram?.WebApp;
    if(tg?.initData&&typeof tg.disableVerticalSwipes==='function')try{tg.disableVerticalSwipes()}catch(e){}
    let startY=0, pulled=0, tracking=false, refreshing=false;
    let initialVersion=document.querySelector('meta[name="warehouse-app-version"]')?.content || '';
    async function serverVersion(){
      const r=await fetch('/app/version',{cache:'no-store',credentials:'same-origin'});
      if(!r.ok)throw Error('Сервер временно недоступен');
      const data=await r.json();
      if(typeof data.version!=='string'||!data.version)throw Error('Не удалось проверить версию');
      return data.version;
    }
    if(!initialVersion)serverVersion().then(v=>{initialVersion=v}).catch(()=>{});
    function canPull(event){
      if(refreshing||!window.currentUser&&typeof currentUser==='undefined')return false;
      if(typeof currentScreen==='undefined'||!allowed.has(currentScreen))return false;
      if(window.scrollY>2||document.querySelector('.modal-overlay:not(.hidden),dialog[open]'))return false;
      const target=event.target;
      if(target?.closest?.('input,textarea,select,[contenteditable="true"],.modal-content'))return false;
      const active=document.activeElement;
      if(active?.matches?.('input,textarea,select,[contenteditable="true"]')&&active!==document.body)return false;
      return true;
    }
    function show(label){caption.textContent=label;indicator.classList.add('visible')}
    function hide(){indicator.classList.remove('visible')}
    function reset(){tracking=false;pulled=0;startY=0}
    async function refresh(){
      refreshing=true;
      show('Обновляем…');
      try{
        const version=await serverVersion();
        if(initialVersion&&version!==initialVersion){
          show('Устанавливаем обновление…');
          location.reload();
          return;
        }
        initialVersion=version;
        await api('/api/me');
        const tasks=[loadItems(), loadLocations(), loadDashboard17({force:true}), loadMyBookings()];
        if(currentScreen==='screen-platforms')tasks.push(syncGoogle('кц',{silent:true}));
        if(currentScreen==='screen-th')tasks.push(syncGoogle('тх мск',{silent:true}));
        const results=await Promise.all(tasks);
        show(results.includes(false)?'Не удалось обновить данные':'Данные обновлены');
      }catch(error){
        if(error?.status===401||error?.status===403){location.reload();return;}
        show(navigator.onLine?'Не удалось обновить данные':'Нет соединения');
      }finally{
        setTimeout(()=>{refreshing=false;hide()},850);
      }
    }
    document.addEventListener('touchstart',e=>{
      if(e.touches.length!==1||!canPull(e))return;
      tracking=true;startY=e.touches[0].clientY;pulled=0;
    },{passive:true});
    document.addEventListener('touchmove',e=>{
      if(!tracking)return;
      if(e.touches.length!==1){reset();hide();return;}
      const delta=e.touches[0].clientY-startY;
      if(delta<0){reset();hide();return;}
      if(window.scrollY>2){reset();hide();return;}
      pulled=Math.min(115,Math.max(0,delta));
      if(delta>14&&e.cancelable)e.preventDefault();
      if(delta>14)show(pulled>=74?'Отпустите для обновления':'Потяните для обновления');
    },{passive:false});
    document.addEventListener('touchend',()=>{
      if(!tracking)return;
      const go=pulled>=74;
      reset();
      if(go)refresh();else hide();
    },{passive:true});
    document.addEventListener('touchcancel',()=>{reset();hide()},{passive:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
})();