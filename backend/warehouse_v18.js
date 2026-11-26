/* Beta v18 — mobile shell, desktop workspace and optional tools. */
function installV18(openRoleMenu){
  installLongPressCopy();
  'use strict';
  const paths={home:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',pin:'<path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',ship:'<path d="M3 13 12 9l9 4-3 6H6zM7 11V5h10v6M12 5V2M2 22q2-3 5 0 3-3 5 0 3-3 5 0 3-3 5 0"/>',box:'<path d="m3 7 9-4 9 4v13H3zM8 20V10h8v10M8 15h8"/>',settings:'<circle cx="12" cy="12" r="3"/><path d="m10 2-.5 3L7 6l-2-1.5-2 3L5 10v4l-2 2.5 2 3L7 18l2.5 1 .5 3h4l.5-3 2.5-1 2 1.5 2-3-2-2.5v-4l2-2.5-2-3L17 6l-2.5-1L14 2z"/>',left:'<path d="m15 18-6-6 6-6"/>',right:'<path d="m9 18 6-6-6-6"/>',sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2"/>',moon:'<path d="M20 15A9 9 0 0 1 9 4 9 9 0 1 0 20 15Z"/>',scan:'<path d="M3 8V3h5m8 0h5v5m0 8v5h-5m-8 0H3v-5M3 12h18"/>',take:'<path d="M4 5h16v15H4zM4 10h16m-8-7v7m-4 5 4 4 4-4"/>',star:'<path d="m12 3 2.8 5.7 6.3.9-4.6 4.4 1.1 6.3-5.6-3-5.6 3 1.1-6.3L3 9.6l6.2-.9z"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',bell:'<path d="M5 17h14l-2-4V8a5 5 0 0 0-10 0v5zm5 3h4"/>',calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6M17 2v6M3 10h18"/>',grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',edit:'<path d="m4 16 12-12 4 4L8 20H4zm10-10 4 4"/>',user:'<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',chart:'<path d="M3 3v18h18M7 16v-5m5 5V7m5 9V3"/>',web:'<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M9 21h6m-3-4v4"/>',file:'<path d="M6 2h8l4 4v16H6zM14 2v5h4M9 12h6m-6 4h6"/>',refresh:'<path d="M20 10a8 8 0 1 0-2 8m2-14v6h-6"/>',search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',archive:'<path d="M4 7h16v14H4zM3 3h18v4H3zm6 9h6"/>',plus:'<path d="M12 4v16M4 12h16"/>',close:'<path d="m6 6 12 12M18 6 6 18"/>'};
  const ico=k=>'<svg class="v18-icon" viewBox="0 0 24 24" aria-hidden="true">'+(paths[k]||paths.grid)+'</svg>';
  const btn=(label,fn,k,cls='secondary')=>{const el=document.createElement('button');el.type='button';el.className=cls;el.innerHTML=(k?ico(k)+' ':'')+safe(label);el.onclick=async e=>{if(el.disabled)return;el.disabled=true;try{await fn(e)}catch(error){notify(error.message||String(error))}finally{el.disabled=false}};return el};
  const iconButton=(label,fn,k)=>{const el=btn('',fn,k,'v18-icon-btn');el.title=label;el.setAttribute('aria-label',label);return el};
  const dark=()=>document.documentElement.dataset.theme==='dark'||(!document.documentElement.dataset.theme&&matchMedia('(prefers-color-scheme:dark)').matches);
  const themeButtons=[];
  const updateTheme=()=>themeButtons.forEach(el=>{el.innerHTML=ico(dark()?'sun':'moon');el.title=dark()?'Светлая тема':'Тёмная тема';el.setAttribute('aria-label',el.title)});
  cycleTheme=()=>{const next=dark()?'light':'dark';document.documentElement.dataset.theme=next;try{localStorage.setItem('warehouse_main_theme',next)}catch(e){}updateTheme();haptic('light')};
  const theme=()=>{const el=iconButton('Тема',cycleTheme,'moon');themeButtons.push(el);return el};
  document.querySelectorAll('.sticky-header').forEach(h=>{const title=h.querySelector('.sticky-title');if(!title)return;const left=document.createElement('div'),right=document.createElement('div');left.className='v18-header-left';right.className='v18-header-right';const children=[...h.children];const t=children.indexOf(title);for(let i=0;i<children.length;i++){const c=children[i];if(c===title)continue;if(c.classList.contains('sticky-back')){c.innerHTML=ico('left');c.title='Назад';c.setAttribute('aria-label','Назад');left.append(c)}else if(c.tagName==='BUTTON'){if(c.classList.contains('sticky-scan')){c.innerHTML=ico('scan');c.title='Сканировать';c.setAttribute('aria-label','Сканировать')}right.append(c)}else if(c.textContent.trim())(i<t?left:right).append(c)}right.append(theme());h.replaceChildren(left,title,right)});
  updateTheme();matchMedia('(prefers-color-scheme:dark)').addEventListener?.('change',updateTheme);
  const accentKey='warehouse_main_accent';function accent(v){document.documentElement.style.setProperty('--primary',v);try{localStorage.setItem(accentKey,v)}catch(e){}}
  try{const v=localStorage.getItem(accentKey);if(/^#[0-9a-f]{6}$/i.test(v||''))accent(v)}catch(e){}
  const nav=$('nav-main').parentElement;const navNames=[['nav-main','home','Главная'],['nav-platforms','pin','Площадки'],['nav-th','ship','Теплоходы'],['nav-rooms','box','Склад'],['nav-settings','settings','Настройки']];
  for(const [id,k,label] of navNames){const n=$(id);n.querySelector('.icon').innerHTML=ico(k);n.lastElementChild.textContent=label;n.tabIndex=0;n.setAttribute('role','button');n.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();n.click()}}}
  const brand=document.createElement('div');brand.className='v18-desktop-only v18-laptop-title';brand.textContent='Склад';nav.prepend(brand);
  function navExtra(label,k,fn,admin=false){const el=document.createElement('div');el.className='nav-item v18-desktop-only'+(admin?' v18-admin hidden':'');el.innerHTML='<span class="icon">'+ico(k)+'</span><span>'+safe(label)+'</span>';el.tabIndex=0;el.setAttribute('role','button');el.onclick=()=>{fn()};el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();el.click()}};nav.append(el);return el}
  const selectKind=k=>{if(currentScreen!=='screen-main')backToMain();$('filter-kind').value=k;$('filter-status').value='';window.dispatchEvent(new CustomEvent('warehouse-kind-selected',{detail:{kind:k}}));filterItems();$('items-list').scrollIntoView({block:'start',behavior:'smooth'})};
  navExtra('Оборудование','take',()=>selectKind('equipment'));navExtra('Расходники','box',()=>selectKind('consumable'));navExtra('Финансы','chart',()=>showExtra('finance'),true);
  const main=$('screen-main'),qr=main.querySelector('.qr-btn-main'),take=main.querySelector('.take-btn');const quick=document.createElement('div');quick.className='v18-quick';qr.before(quick);quick.append(qr,take);qr.innerHTML=ico('scan')+' Сканировать';take.innerHTML=ico('take')+' Взять технику';
  const shortcuts=document.createElement('div');shortcuts.className='v18-shortcuts';quick.after(shortcuts);shortcuts.append(btn('Избранное',()=>showCollection('favorites'),'star'),btn('Недавние',()=>showCollection('recent'),'clock'),btn('Комплекты',showKits,'grid'),btn('Уведомления',showNotifications,'bell'),btn('Обновить',()=>refresh(true),'refresh'));
  const mainHeading=document.createElement('div');mainHeading.className='v18-desktop-heading';mainHeading.textContent='Склад';main.querySelector('.v18-header-left').append(mainHeading);
  const workspace=document.createElement('div');workspace.className='v18-workspace';const inventory=document.createElement('section');inventory.className='v18-inventory';const aside=document.createElement('aside');aside.className='v18-overview';
  const tableHead=document.createElement('div');tableHead.className='v18-title-row';const tableTitle=document.createElement('h2');tableTitle.textContent='Товары';tableHead.append(tableTitle);const addDesktop=btn('Добавить товар',()=>openAddItemModal(),'plus','v18-admin hidden v18-desktop-only');addDesktop.style.cssText='width:auto;margin:0;min-height:38px;font-size:13px';tableHead.append(addDesktop);
  inventory.append(tableHead,main.querySelector('.search-wrapper'),main.querySelector('.filters'),$('items-list'));
  quick.after($('main-activity'));
  $('main-history-btn').innerHTML=ico('clock')+'<span>История</span>';
  aside.append($('my-bookings-section'));
  workspace.append(inventory,aside);main.append(workspace);
  // Retain both login controls; move the site button into Settings. Employees use their profile.
  const settings=$('screen-settings'),settings_header=settings.querySelector('.sticky-header'),site=$('web-login-btn');site.textContent='Сайт';const oldAction=main.querySelector('.header-actions');oldAction.classList.add('hidden');
  const byAction=action=>[...settings.querySelectorAll('button')].find(b=>b.getAttribute('onclick')===action);
  const groups=document.createElement('div');groups.className='v18-settings-layout';
  function group(title,entries,owner=false){
    const wrap=document.createElement('details');
    wrap.name='warehouse-settings';
    wrap.className='v18-settings-group beta-setting-details'+(owner?' owner-only hidden':'');
    const heading=document.createElement('summary');
    heading.className='v18-section-label';
    heading.append(document.createTextNode(title));
    heading.insertAdjacentHTML('beforeend',ico('right'));
    const list=document.createElement('div');
    list.className='v18-settings-list';
    for(const [control,label,k] of entries){
      if(!control)continue;
      if(control.tagName==='BUTTON'){
        control.innerHTML='<span class="v18-setting-icon">'+ico(k)+'</span><span class="v18-setting-label">'+safe(label)+'</span>'+ico('right');
        control.lastElementChild.classList.add('v18-chevron');
      }
      list.append(control);
    }
    wrap.append(heading,list);
    groups.append(wrap);
    return list;
  }
  const action=(attr,label,k)=>[byAction(attr),label,k];
  group('Приложение',[[site,'Сайт','web'],[btn('',showSessions),'Активные сеансы сайта','user'],[btn('',showAccent),'Акцентный цвет','sun'],[btn('',showChangelog),'Что нового в v18.5.2','file']]);
  group('Управление',[action('showUsers()','Пользователи','user'),action("showExtra('categories')",'Категории','grid'),[btn('',showBulk),'Массовое редактирование','edit'],action("showExtra('archive')",'Архив и восстановление','archive'),[btn('',showTemplates),'Шаблоны товаров','file']]);
  const roomsInput=$('new-location-name').closest('.input-group');group('Помещения',[[roomsInput],[byAction('createLocation()'),'Добавить помещение','plus'],[$('locations-list')]]);
  group('Учёт и аналитика',[action("showExtra('finance')",'Финансы','chart'),action("showExtra('purchases')",'Закупки','take'),[btn('',showUsage),'Использование техники','chart'],action('showInventory()','Инвентаризация','scan'),action("showExtra('inventorylog')",'История инвентаризаций','clock')]);
  const adminHistory=btn('',()=>showSettingsHistory('audit'));
  adminHistory.classList.add('owner-only','hidden');
  group('История',[
    [btn('',()=>showSettingsHistory('payments')),'История оплат','clock'],
    [btn('',()=>showSettingsHistory('additions')),'История добавлений товаров','clock'],
    [btn('',()=>showSettingsHistory('buyouts')),'История выкупа','clock'],
    [adminHistory,'История администратора','clock']
  ]);
  group('Экспорт и печать',[[ $('export-stock-btn'),'Выгрузить склад в Excel','file'],[btn('',()=>downloadFile('/api/v18/history.xlsx','history.xlsx')),'История в Excel','file'],[$('export-qr-btn'),'Печать QR-этикеток','scan'],[btn('',configureLabels),'Размер этикетки','settings']]);
  const maintenance=group('Обслуживание',[[$('owner-terminal-btn'),'Терминал','web'],[btn('',sendOwnerBackup182),'Скачать резервную копию базы','file'],[btn('',()=>{if(confirm('Очистить настройки этого браузера?')){Object.keys(localStorage).filter(k=>k.startsWith('warehouse_main_')).forEach(k=>localStorage.removeItem(k));location.reload()}}),'Сбросить настройки браузера','refresh']],true);
  maintenance.id='beta-maintenance-settings';
  const footer=document.createElement('p');footer.className='v18-muted';footer.style.textAlign='center';footer.textContent='Склад v18.5.14';settings.replaceChildren(settings_header,groups,footer);
  $('screen-login').querySelector('.login-card p').textContent='Открой склад в Telegram, выбери «Сайт» в настройках или профиле и введи одноразовый код.';$('screen-login').querySelector('.login-card h1').textContent='Склад · v18.4';
  $('user-info').onclick=()=>{
    const {o,b}=overlay17('Мой профиль');
    const name=document.createElement('p');
    name.textContent=currentUser?.full_name||'';
    b.append(name);
    if(currentUser?.can_preview){
      btn17(b,'Сменить роль',()=>{
        o.remove();
        openRoleMenu();
      });
    }
    btn17(b,'Изменить имя',()=>{o.remove();editMyName()});
    if(tg.initData){
      btn17(b,'Сайт',()=>{o.remove();return issueWebCode()});
      btn17(b,'Приложение',()=>{o.remove();return issueWebCode('app')});
    }
    btn17(b,'Активные сеансы сайта',()=>{o.remove();showSessions()});
    btn17(b,'Акцентный цвет',()=>{o.remove();showAccent()});
  };
  const cleanButtons=root=>root.querySelectorAll('button').forEach(b=>{if(b.children.length||b.classList.contains('v18-icon-btn'))return;const old=b.textContent,txt=old.replace(/[\p{Extended_Pictographic}\uFE0F\u200D]/gu,'').trim();if(txt&&txt!==old.trim())b.textContent=txt});cleanButtons(document);
  const oldLoadLocations=loadLocations;loadLocations=async()=>{await oldLoadLocations();$('locations-list').querySelectorAll('.card').forEach(c=>{c.classList.add('v18-place-row');const b=c.querySelector('button');if(b){b.innerHTML=ico('edit');b.title='Переименовать';b.setAttribute('aria-label',b.title)}})};
  const oldShowRooms=showRooms;showRooms=async()=>{await oldShowRooms();$('rooms-list').querySelectorAll('.room-arrow-circle').forEach(e=>e.innerHTML=ico('right'))};
  const oldScreen=showScreen;showScreen=id=>{oldScreen(id);updateTheme();cleanButtons($(id)||document);if(id==='screen-main'&&currentUser)filterItems()};
  let profile={favorites:[],recent:[],kits:{},templates:{}},profileReady=false,profileQueue=Promise.resolve();
  async function loadProfile(){try{profile=await api('/api/v18/profile');cacheSet17('v18_profile',JSON.stringify(profile));profileReady=true}catch(e){try{profile=JSON.parse(cacheGet17('v18_profile')||'null')||profile}catch(_){}profileReady=false;showToast('Настройки профиля недоступны','error')}}
  function saveProfile(){const snapshot=JSON.stringify(profile);cacheSet17('v18_profile',snapshot);if(!profileReady)return;profileQueue=profileQueue.catch(()=>{}).then(()=>api('/api/v18/profile',{method:'PUT',body:snapshot})).catch(e=>notify('Не сохранено на сервере: '+e.message))}
  syncRenamedItemProfile=(oldCode,newCode)=>{
    const replace=codes=>[...new Set(codes.map(code=>code===oldCode?newCode:code))];
    profile.favorites=replace(profile.favorites||[]);
    profile.recent=replace(profile.recent||[]);
    for(const [name,codes] of Object.entries(profile.kits||{}))profile.kits[name]=replace(codes);
    saveProfile();
  };
  function toggleFavorite(code){const n=profile.favorites.indexOf(code);if(n>=0)profile.favorites.splice(n,1);else profile.favorites.unshift(code);profile.favorites=profile.favorites.slice(0,300);saveProfile();renderFavorite();if(currentScreen==='screen-main')filterItems()}
  function renderFavorite(){const f=$('v18-favorite');if(!f||!currentItem)return;const on=profile.favorites.includes(currentItem.code);f.innerHTML=ico('star')+' '+(on?'В избранном':'В избранное');f.classList.toggle('v18-star',on);f.setAttribute('aria-pressed',String(on))}
  const favorite=btn('В избранное',()=>{if(currentItem)toggleFavorite(currentItem.code)},'star');favorite.id='v18-favorite';$('beta-item-tools').prepend(favorite);
  const oldOpenItem=openItem;openItem=async code=>{await oldOpenItem(code);if(currentItem?.code===code&&currentScreen==='screen-item'){profile.recent=[code,...profile.recent.filter(x=>x!==code)].slice(0,30);saveProfile();renderFavorite()}};
  function showCollection(key){const {o,b}=overlay17(key==='favorites'?'Избранное':'Недавно просмотренные');const rows=profile[key].map(c=>allItems.find(i=>i.code===c)).filter(Boolean);if(!rows.length)card17(b,'Пока пусто',key==='favorites'?'Добавляйте товары в избранное из карточки.':'Открывайте карточки товаров.');for(const i of rows){const c=card17(b,i.name,i.code);btn17(c,'Открыть',()=>{o.remove();openItem(i.code)});if(key==='favorites')btn17(c,'Убрать',()=>{toggleFavorite(i.code);o.remove();showCollection(key)})}}
  function norm(v){return String(v??'').toLocaleLowerCase('ru').replace(/ё/g,'е').trim()}
  function distance(a,b){let prev=Array.from({length:b.length+1},(_,i)=>i);for(let i=1;i<=a.length;i++){const row=[i];for(let j=1;j<=b.length;j++)row[j]=Math.min(prev[j]+1,row[j-1]+1,prev[j-1]+(a[i-1]===b[j-1]?0:1));prev=row}return prev[b.length]}
  function match(i,q){q=norm(q);if(!q)return true;const text=norm([i.name,i.code,i.serial_number,i.site,i.vessel,i.category,...(i.holders||[]).map(h=>h.full_name)].join(' '));if(text.includes(q))return true;const words=text.split(/[^\p{L}\p{N}]+/u).filter(Boolean);return q.split(/\s+/).every(t=>text.includes(t)||(t.length>=4&&t.length<=32&&words.some(w=>Math.abs(w.length-t.length)<=2&&distance(w,t)<=(t.length>=7?2:1))))}
  const sortRows=rows=>[...rows].sort((a,b)=>{const p=i=>i.kind==='equipment'&&i.needs_repair?4:!i.holders?.length?1:i.holders.some(h=>h.taken_for?.trim())?3:2;return p(a)-p(b)||a.name.localeCompare(b.name,'ru')});
  const wide=()=>document.body.classList.contains('web-mode')&&matchMedia('(min-width:900px)').matches;
  const oldGrid=renderItemsGrid;renderItemsGrid=(rows,id)=>{if(id!=='items-list'||!wide()){oldGrid(rows,id);return}const list=$(id);list.replaceChildren();if(!rows.length){const p=document.createElement('p');p.className='v18-muted';p.textContent='Ничего не найдено';list.append(p);return}const wrap=document.createElement('div');wrap.className='v18-table-wrap';const table=document.createElement('table');table.className='v18-table';const cols=['','Название','Код','Помещение / сотрудник','Статус','Количество'];if(currentUser?.role==='admin')cols.push('Цена');table.innerHTML='<thead><tr>'+cols.map(c=>'<th scope="col">'+safe(c)+'</th>').join('')+'</tr></thead>';const body=document.createElement('tbody');for(const i of sortRows(rows)){const r=document.createElement('tr');const cell=()=>{const td=document.createElement('td');r.append(td);return td};const star=iconButton('Избранное',e=>{e.stopPropagation();toggleFavorite(i.code)},'star');star.style.cssText='width:28px!important;height:28px;min-height:28px;min-width:0;flex:none';star.classList.toggle('v18-star',profile.favorites.includes(i.code));star.setAttribute('aria-pressed',String(profile.favorites.includes(i.code)));cell().append(star);const name=btn(i.name,e=>{e.stopPropagation();openItem(i.code)},null,'v18-link');cell().append(name);cell().textContent=i.code;cell().textContent=i.holders?.length?i.holders.map(h=>h.full_name||'—').join(', '):i.stocks?.map(s=>s.location_name).join(', ')||'—';const st=i.needs_repair?['Ремонт','repair']:i.holders?.length?['На руках','held']:booked17.has(i.code)?['Бронь','booked']:i.is_low?['Мало','low']:(i.total>0||i.quantity_many)?['Свободно','free']:['Нет','low'];const s=document.createElement('span');s.className='v18-state '+st[1];s.textContent=st[0];cell().append(s);cell().textContent=i.quantity_many?'Много':i.total+' '+(i.unit||'шт.');if(currentUser?.role==='admin')cell().textContent=i.price===undefined?'—':money17(i.price);r.onclick=()=>openItem(i.code);body.append(r)}table.append(body);wrap.append(table);list.append(wrap)};
  filterItems=()=>{const q=$('search-input').value,loc=Number($('filter-location').value),k=$('filter-kind').value,c=$('filter-category').value,s=$('filter-status').value;renderItemsGrid(allItems.filter(i=>match(i,q)&&(!loc||i.stocks.some(v=>v.location_id===loc))&&(!k||i.kind===k)&&(!c||(c==='__without_category__'?!i.category:i.category===c))&&(!s||matchesStatus17(i,s))),'items-list')};
  matchMedia('(min-width:900px)').addEventListener?.('change',()=>{if(currentUser)filterItems()});
  function chooseItems(b,rows,pre=[]){const box=document.createElement('div');box.className='v18-choices';const q=document.createElement('input');q.placeholder='Найти товар';const map=new Map();for(const i of rows){const l=document.createElement('label'),c=document.createElement('input'),span=document.createElement('span');c.type='checkbox';c.checked=pre.includes(i.code);span.textContent=i.name+' · '+i.code;l.append(c,span);box.append(l);map.set(i.code,{c,l,i})}q.oninput=()=>map.forEach(v=>v.l.classList.toggle('hidden',!match(v.i,q.value)));b.append(q,box);return ()=>[...map].filter(([,v])=>v.c.checked).map(([code])=>code)}
  function ask(title,message,label='Подтвердить',value=null){return new Promise(resolve=>{const {o,b}=overlay17(title);const done=v=>{o.remove();resolve(v)};b.querySelector('button').onclick=()=>done(null);if(message){const p=document.createElement('p');p.textContent=message;b.append(p)}const input=value===null?null:field17(b,'Значение',value);btn17(b,label,()=>done(input?input.value:true),'ok');btn17(b,'Отмена',()=>done(null));input?.focus()})}
  function showKits(){const {o,b}=overlay17('Комплекты');btn17(b,'Создать комплект',()=>{o.remove();editKit()});const entries=Object.entries(profile.kits);if(!entries.length)card17(b,'Нет комплектов','Соберите часто используемый набор оборудования.');for(const [name,codes] of entries){const c=card17(b,name,codes.map(code=>allItems.find(i=>i.code===code)?.name||code).join('\n'));btn17(c,'Взять весь комплект',async()=>{if(!await ask('Взять комплект?',name,'Взять'))return;const r=await api('/api/v18/checkout-kit',{method:'POST',body:JSON.stringify({codes})});o.remove();showToast('Выдано: '+r.success_count);refresh(true)},'ok');btn17(c,'Редактировать',()=>{o.remove();editKit(name,codes)});btn17(c,'Удалить комплект',async()=>{if(!await ask('Удалить комплект?',name,'Удалить'))return;delete profile.kits[name];saveProfile();o.remove();showKits()})}}
  function editKit(name='',codes=[]){const {o,b}=overlay17('Комплект оборудования');const n=field17(b,'Название комплекта',name);const selected=chooseItems(b,allItems.filter(i=>i.kind==='equipment'),codes);btn17(b,'Сохранить',()=>{const next=n.value.trim(),items=selected();if(!next||next.length>100||!items.length||items.length>50)throw Error('Укажите название и 1–50 товаров');if(next!==name&&Object.hasOwn(profile.kits,next))throw Error('Такое название уже есть');if(name)delete profile.kits[name];Object.defineProperty(profile.kits,next,{value:items,enumerable:true,writable:true,configurable:true});saveProfile();o.remove();showKits()},'ok')}
  function showBulk(){return showBulk183()}
  const templateFields=['name','kind','category','unit','supplier','qty','min-stock','price','location-desc','price-eq','budget-tag','kit-body','kit-lens','kit-flash','kit-acc','kit-add','price-body','price-lens','price-flash','price-acc','price-add'];
  function showTemplates(){if(currentUser?.role!=='admin')return;const {o,b}=overlay17('Шаблоны товаров');for(const [name,values] of Object.entries(profile.templates)){const c=card17(b,name,values.name||'');btn17(c,'Создать по шаблону',()=>{o.remove();openAddItemModal();for(const [key,v]of Object.entries(values))if(templateFields.includes(key)&&$('add-'+key))$('add-'+key).value=v;$('add-code').value='';toggleFields();onNameInput()});btn17(c,'Удалить',async()=>{if(!await ask('Удалить шаблон?',name,'Удалить'))return;delete profile.templates[name];saveProfile();o.remove();showTemplates()})}if(!Object.keys(profile.templates).length)card17(b,'Нет шаблонов','Заполните новую карточку товара и нажмите «Сохранить шаблон».');btn17(b,'Новый товар',()=>{o.remove();openAddItemModal()},'ok')}
  const templateButton=btn('Сохранить как шаблон',async()=>{const name=await ask('Название шаблона','Код и серийный номер не сохраняются.','Сохранить',$('add-name').value.trim());if(!name?.trim())return;if(name.trim().length>100)throw Error('Название слишком длинное');const vals=Object.fromEntries(templateFields.filter(k=>$('add-'+k)).map(k=>[k,$('add-'+k).value]));Object.defineProperty(profile.templates,name.trim(),{value:vals,enumerable:true,writable:true,configurable:true});saveProfile();showToast('Шаблон сохранён')},'file');templateButton.classList.add('warehouse-save-template');$('save-item-btn').before(templateButton);
  async function showUsage(){if(currentUser?.role!=='admin')return;const {b}=overlay17('Использование оборудования');const rows=await api('/api/v18/usage');const un=rows.filter(r=>!r.last_checkout||Date.now()-Date.parse(r.last_checkout.replace(' ','T')+'Z')>90*864e5);card17(b,'Не использовалось 90 дней или дольше',String(un.length));for(const r of rows){const c=card17(b,r.name,`Выдач за всё время: ${r.checkouts}\nПоследняя: ${r.last_checkout||'Не выдавалось'}`);btn17(c,'Открыть',()=>{b.parentElement.remove();openItem(r.code)})}}
  async function showNotifications(){const {b}=overlay17('Уведомления');const rows=allItems.filter(i=>i.is_low||i.needs_repair);if(!rows.length)card17(b,'Всё в порядке','Нет предупреждений о ремонте или низком остатке.');for(const i of rows){const c=card17(b,i.name,i.needs_repair?'В ремонте':`Остаток ${i.total}, минимум ${i.min_stock}`);btn17(c,'Открыть товар',()=>{b.parentElement.remove();openItem(i.code)})}}
  async function showSessions(){const {b}=overlay17('Активные сеансы сайта');try{const rows=await api('/api/v18/sessions');if(!rows.length)card17(b,'Нет активных браузерных сеансов');for(const r of rows){const c=card17(b,r.current?'Текущий браузер':'Другой браузер',`Действует до ${new Date(r.expires*1000).toLocaleString('ru-RU')}`);btn17(c,'Завершить сеанс',async()=>{if(!await ask('Завершить сеанс?','Потребуется новый код входа.','Завершить'))return;await api('/api/v18/sessions/'+r.id,{method:'DELETE'});if(r.current&&!tg.initData)location.reload();else c.remove()})}}catch(e){notify(e.message)}}
  function showAccent(){const {b}=overlay17('Акцентный цвет');const row=document.createElement('div');row.style.cssText='display:flex;flex-wrap:wrap;gap:7px';for(const v of ['#007aff','#5856d6','#0b8862','#c45d20','#b53b7b','#42647e']){const e=btn('',()=>accent(v),null,'v18-accent');e.style.background=v;e.setAttribute('aria-label','Цвет '+v);row.append(e)}b.append(row);btn17(b,'По умолчанию',()=>accent('#007aff'))}
  function showChangelog(){const {b}=overlay17('Что нового · v18.5.2');for(const [t,d]of [['v18.5.2','Реалистичные иллюстрации, Telegram-ники, блокировка по ID, обновлённые стили.'],['v18.4','Кнопки под обзором; расходники отдельным разделом; возврат расходников; автоматическое обновление площадок и теплоходов; массовые действия.'],['Liquid Glass','Компактная навигация, тема в верхнем углу, новая страница настроек.'],['Сайт','Боковая панель и таблица товаров для компьютера.'],['Рабочие инструменты','Избранное, недавние, комплекты, шаблоны, массовое редактирование, Excel.'],['Этикетки','Настраиваемая ширина и высота; PNG и PDF.']])card17(b,t,d)}
  const labelQuery=(kind='consumable')=>{const d=labelSettings(kind);return 'width_mm='+d.width+'&height_mm='+d.height};
  function configureLabels(){const {o,b}=overlay17('Размер QR-этикетки расходников');const d=labelSettings(),w=field17(b,'Ширина, мм (30–100)',d.width,'number'),h=field17(b,'Высота, мм (40–150)',d.height,'number');btn17(b,'Сохранить',()=>{const width=Number(w.value),height=Number(h.value);if(!Number.isInteger(width)||!Number.isInteger(height)||width<30||width>100||height<40||height>150)throw Error('Проверьте размеры');cacheSet17('label_dimensions',JSON.stringify({width,height}));o.remove();showToast('Размер сохранён')},'ok');btn17(b,'По умолчанию 50 × 80 мм',()=>{w.value=50;h.value=80})}
  showLabelPreview17=async(code,name,img,kind=$('add-kind')?.value||'consumable')=>image17(img,'/api/label/'+encodeURIComponent(code)+'?'+new URLSearchParams({name,kind})+'&'+labelQuery(kind));
  showQr=async()=>{const {code,name,kind}=currentItem;if(currentUser.role==='admin')return showLabelPrint17([{code,name,kind}]);const {b}=overlay17('Этикетка');const d=labelSettings(kind);card17(b,name,code+' · '+d.width+' × '+d.height+' мм');const img=document.createElement('img');img.className='label-img';img.alt='QR-этикетка';b.append(img);const p='/api/label/'+encodeURIComponent(code)+'?'+labelQuery(kind);try{await image17(img,p)}catch(e){img.remove();card17(b,'Не удалось создать этикетку',e.message)}btn17(b,'Копировать код',()=>copyText(code));btn17(b,'Копировать название',()=>copyText(name))};
  $('export-qr-btn').onclick=()=>{const {o,b}=overlay17('Печать QR-этикеток');btn17(b,'Техника · 30 × 50 мм',()=>{o.remove();chooseConsumableLabels17('equipment')});btn17(b,'Расходники',()=>{o.remove();chooseConsumableLabels17()});btn17(b,'Все этикетки (PDF)',()=>downloadFile('/api/export_labels','labels.pdf'))};exportStock=()=>downloadFile('/api/v18/stock.xlsx','warehouse_stock.xlsx');
  downloadFile=async(url,filename)=>{try{const response=await fetch(url,{headers:authHeaders17(),credentials:'same-origin'});if(!response.ok){const e=await response.json().catch(()=>({}));throw Error(e.detail||'HTTP '+response.status)}const blob=await response.blob(),a=document.createElement('a'),obj=URL.createObjectURL(blob);a.href=obj;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(obj),10000)}catch(e){notify('Ошибка скачивания: '+e.message)}};
  deleteItemFromEdit=async()=>{const {code,name}=currentItem;if(!await ask('Отправить в архив?',name,'В архив'))return;try{await api('/api/items/'+encodeURIComponent(code),{method:'DELETE'});backToMain();const {o,b}=overlay17('Товар в архиве');card17(b,name,'Можно восстановить без потери остатка.');btn17(b,'Отменить архивирование',async()=>{await api('/api/archive/'+encodeURIComponent(code)+'/restore',{method:'POST'});o.remove();showToast('Товар восстановлен');refresh(true)},'ok')}catch(e){notify(e.message)}};
  renameLocation=async(id,oldName)=>{const name=await ask('Переименовать помещение','','Сохранить',oldName);if(!name?.trim()||name===oldName)return;try{await api('/api/locations/update',{method:'POST',body:JSON.stringify({id,name:name.trim()})});await loadLocations();showToast('Обновлено')}catch(e){notify(e.message)}};
  document.addEventListener('click',e=>{const img=e.target.closest?.('img');if(!img||!['Фото товара','Фото ремонта'].includes(img.alt))return;const o=document.createElement('div');o.className='v18-photo-overlay';const large=new Image();large.src=img.src;large.alt=img.alt;const close=btn('Закрыть',()=>o.remove(),'close');o.append(large,close);o.onclick=ev=>{if(ev.target===o)o.remove()};document.body.append(o)});
  const oldInit=init;let refreshing=false;
  async function refresh(manual=false){if(!currentUser?.is_registered||refreshing||!navigator.onLine)return;refreshing=true;try{await Promise.all([loadItems(),loadStats(),loadLowStock(),loadDashboard17(),loadMyBookings()]);if(manual)showToast('Обновлено')}catch(e){if(manual)notify(e.message)}finally{refreshing=false}}
  init=async()=>{await oldInit();if(!currentUser?.is_registered)return;clearInterval(autoRefreshInterval);autoRefreshInterval=setInterval(()=>{if(document.visibilityState==='visible'&&currentScreen==='screen-main')refresh()},60000);document.querySelectorAll('.v18-admin').forEach(e=>e.classList.toggle('hidden',currentUser.role!=='admin'));await loadProfile();filterItems()};
  window.addEventListener('keydown',e=>{if(e.target.matches?.('input,select,textarea,[contenteditable]')||document.querySelector('.modal-overlay:not(.hidden),.v18-photo-overlay,dialog[open]'))return;if(e.key==='/'&&currentUser){e.preventDefault();if(currentScreen!=='screen-main')backToMain();$('search-input').focus()}if(e.key==='Escape'&&currentUser&&currentScreen!=='screen-main')goBack();if(e.key.toLowerCase()==='r'&&e.altKey&&currentUser){e.preventDefault();refresh(true)}});
  let start=0;document.addEventListener('touchstart',e=>{start=window.scrollY===0&&currentScreen==='screen-main'&&!document.querySelector('.modal-overlay:not(.hidden)')?e.touches[0].clientY:0},{passive:true});document.addEventListener('touchend',e=>{if(start&&e.changedTouches[0].clientY-start>95&&window.scrollY===0)refresh(true);start=0},{passive:true});
  const search=main.querySelector('.search-icon');if(search)search.innerHTML=ico('search');
}

function labelSettings(kind='consumable'){
  if(kind==='equipment')return {width:30,height:50};
  try{
    const settings=JSON.parse(cacheGet17('label_dimensions')||'{}');
    if(settings.width>=30&&settings.width<=100&&settings.height>=40&&settings.height<=150)return settings;
  }catch(error){}
  return {width:50,height:80};
}

async function chooseConsumableLabels17(kind='consumable'){
  if(currentUser?.role!=='admin')return;
  const equipment=kind==='equipment';
  const {o,b}=overlay17(equipment?'QR техники':'QR расходников');
  const search=field17(b,equipment?'Найти технику':'Найти расходник','');
  search.type='search';
  const list=document.createElement('div');
  list.className='warehouse-label-picker';
  const status=document.createElement('p');
  status.className='meta';
  status.setAttribute('aria-live','polite');
  b.append(list,status);
  const selected=new Set();
  let items=[];
  const next=btn17(b,'Продолжить',()=>{
    if(!selected.size)return;
    o.remove();
    showLabelPrint17(items.filter(item=>selected.has(item.code)));
  },'ok');
  next.disabled=true;
  list.textContent='Загрузка…';
  function updateSelection(){
    status.textContent=selected.size?'Выбрано: '+selected.size:'';
    next.disabled=!selected.size;
  }
  function render(){
    const query=search.value.trim().toLocaleLowerCase('ru-RU');
    const shown=items.filter(item=>(item.name+' '+item.code).toLocaleLowerCase('ru-RU').includes(query));
    list.replaceChildren(...shown.map(item=>{
      const row=document.createElement('label');
      row.className='warehouse-label-row';
      const checkbox=document.createElement('input');
      checkbox.type='checkbox';
      checkbox.checked=selected.has(item.code);
      checkbox.onchange=()=>{
        if(checkbox.checked)selected.add(item.code);
        else selected.delete(item.code);
        updateSelection();
      };
      const text=document.createElement('span');
      text.className='warehouse-label-info';
      const name=document.createElement('span');
      name.textContent=item.name;
      const code=document.createElement('small');
      code.className='meta';
      code.textContent=item.code;
      text.append(name,code);
      row.append(checkbox,text);
      return row;
    }));
    if(!shown.length)list.textContent=items.length?'Ничего не найдено':equipment?'На складе нет техники':'На складе нет расходников';
  }
  try{
    items=(await api('/api/items')).filter(item=>item.kind===kind);
    search.addEventListener('input',render);
    render();
  }catch(error){list.textContent=error.message}
}

async function downloadLabelExport17(items,format,settings={}){
  const excel=format==='xlsx';
  const response=await fetch('/api/export_labels'+(excel?'?format=xlsx':''),{
    method:'POST',
    credentials:'same-origin',
    headers:{...authHeaders17(),'Content-Type':'application/json'},
    body:JSON.stringify({codes:items.map(item=>item.code),...settings}),
  });
  if(!response.ok){
    const error=await response.json().catch(()=>({}));
    throw Error(typeof error.detail==='string'?error.detail:'Не удалось скачать этикетки');
  }
  const href=URL.createObjectURL(await response.blob());
  const link=document.createElement('a');
  link.href=href;
  link.download=excel?'B21S-qr-labels.xlsx':items.length===1?items[0].code+'.pdf':'qr-labels.pdf';
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(()=>URL.revokeObjectURL(href),10000);
}

function showLabelPrint17(items){
  if(currentUser?.role!=='admin'||!items.length)return;
  const {o,b}=overlay17('Печать QR');
  const header=document.createElement('p');
  header.className='warehouse-label-title';
  header.textContent=items.length===1?items[0].name+' · '+items[0].code:'Выбрано позиций: '+items.length;
  const image=document.createElement('img');
  image.className='label-img';
  image.alt='Предпросмотр QR-этикетки';
  const status=document.createElement('p');
  status.className='meta';
  status.setAttribute('aria-live','polite');
  b.append(header,image,status);
  const controls=document.createElement('div');
  controls.className='warehouse-label-controls';
  b.append(controls);
  const equipment=items.every(item=>item.kind==='equipment');
  const settings=labelSettings(equipment?'equipment':'consumable');
  const width=field17(controls,'Ширина, мм',settings.width,'number');
  const height=field17(controls,'Высота, мм',settings.height,'number');
  const copies=field17(controls,items.length===1?'Копий':'Копий на позицию',1,'number');
  width.setAttribute('aria-label','Ширина, мм');
  height.setAttribute('aria-label','Высота, мм');
  copies.setAttribute('aria-label','Копий');
  width.min=30;width.max=100;
  height.min=40;height.max=150;
  copies.min=1;copies.max=20;
  const density=document.createElement('label');
  density.textContent='Разрешение';
  const dpi=document.createElement('select');
  dpi.add(new Option('203 dpi',203));
  dpi.add(new Option('300 dpi',300));
  density.append(dpi);
  controls.append(density);

  function copyCount(){
    const n=copies.valueAsNumber;
    if(!Number.isInteger(n)||n<1||n>20)throw Error('Введите от 1 до 20 копий на позицию');
    return n;
  }

  function parameters(){
    const w=width.valueAsNumber,h=height.valueAsNumber,d=Number(dpi.value);
    if(!Number.isInteger(w)||!Number.isInteger(h)||w<30||w>100||h<40||h>150)throw Error('Введите размер от 30 × 40 до 100 × 150 мм');
    const n=copyCount();
    const pages=items.length*n;
    if(pages>500||pages*Math.round(w/25.4*d)*Math.round(h/25.4*d)>100000000)throw Error('Уменьшите число копий или размер этикетки');
    return {width_mm:w,height_mm:h,copies:n,dpi:d};
  }

  const previewPath=(code,p)=>'/api/label/'+encodeURIComponent(code)+'?'+new URLSearchParams({
    width_mm:p.width_mm,height_mm:p.height_mm,dpi:p.dpi,
  });
  let previewUrl='',previewVersion=0,previewTimer;
  async function preview(){
    const version=++previewVersion;
    try{
      const p=parameters();
      const blob=await blob17(previewPath(items[0].code,p));
      if(!o.isConnected||version!==previewVersion)return;
      if(previewUrl)URL.revokeObjectURL(previewUrl);
      previewUrl=URL.createObjectURL(blob);
      image.src=previewUrl;
      image.classList.remove('hidden');
      status.textContent=items.length>1?'Предпросмотр первой этикетки · '+items.length*p.copies+' стр.':'';
    }catch(error){
      if(version!==previewVersion)return;
      image.classList.add('hidden');
      status.textContent=error.message;
    }
  }
  controls.addEventListener('input',()=>{
    ++previewVersion;
    clearTimeout(previewTimer);
    previewTimer=setTimeout(preview,180);
  });
  o.querySelector('.field-row button').addEventListener('click',()=>{
    clearTimeout(previewTimer);
    if(previewUrl)URL.revokeObjectURL(previewUrl);
  });

  const actions=document.createElement('div');
  actions.className='warehouse-print-actions';
  b.append(actions);
  btn17(actions,'Печать',async()=>{
    const p=parameters();
    const host=document.createElement('div');
    host.className='warehouse-print-labels';
    const rules=document.createElement('style');
    rules.textContent='@page{size:'+p.width_mm+'mm '+p.height_mm+'mm;margin:0}';
    const images=[];
    const cleanup=()=>{
      host.remove();
      rules.remove();
      document.body.classList.remove('warehouse-printing');
      images.forEach(url=>URL.revokeObjectURL(url));
      window.removeEventListener('afterprint',cleanup);
    };
    try{
      for(const item of items){
        const url=URL.createObjectURL(await blob17(previewPath(item.code,p)));
        images.push(url);
        const label=new Image();
        label.src=url;
        await label.decode();
        label.style.width=p.width_mm+'mm';
        label.style.height=p.height_mm+'mm';
        label.alt=item.name;
        for(let n=0;n<p.copies;n++)host.append(label.cloneNode());
      }
      if(!o.isConnected){cleanup();return}
      document.head.append(rules);
      document.body.append(host);
      document.body.classList.add('warehouse-printing');
      window.addEventListener('afterprint',cleanup,{once:true});
      window.print();
    }catch(error){cleanup();throw error}
  },'ok');
  btn17(actions,'Скачать PDF',()=>downloadLabelExport17(items,'pdf',parameters()));
  btn17(actions,'Excel для B21S',()=>downloadLabelExport17(items,'xlsx',{copies:copyCount()}));
  if(items.length===1)btn17(b,'Скачать PNG',()=>{
    const path=previewPath(items[0].code,parameters());
    return downloadFile(path,items[0].code+'.png');
  });
  if(items.length===1){
    btn17(b,'Копировать код',()=>copyText(items[0].code));
    btn17(b,'Копировать название',()=>copyText(items[0].name));
  }
  const help=document.createElement('details');
  const summary=document.createElement('summary');summary.textContent='Как печатать в NIIMBOT';help.append(summary);
  const tip=document.createElement('p');tip.className='meta';
  tip.textContent=equipment
    ? 'PNG: вставьте готовую этикетку как изображение на всю наклейку. Excel: откройте шаблон 30 × 50 мм, привяжите верхний текст к «Название», нижний элемент QR-кода к «QR». Для точного внешнего вида используйте PNG или один раз сохраните аналогичный шаблон в NIIMBOT.'
    : 'PNG: вставьте готовую этикетку как изображение. Excel: подключите файл как источник данных, привяжите текстовые элементы к «Название» и «Код», элемент QR-кода к «QR».';
  help.append(tip);b.append(help);
  preview();
}


function installLongPressCopy(){
  const holdTime=500, movementLimit=9;
  let press=null, skipClick=null;
  const editor='input,textarea,select,[contenteditable]:not([contenteditable=false])';

  function valueAt(target){
    if(!(target instanceof Element)||target.closest(editor))return '';
    const link=target.closest('a[href]');
    if(link)return link.href;
    if(target.closest('svg,img,canvas'))return '';
    const text=Array.from(target.childNodes).filter(node=>node.nodeType===Node.TEXT_NODE)
      .map(node=>node.textContent).join('').trim();
    if(text)return text;
    return target.childElementCount===0?(target.textContent||'').trim():'';
  }

  function clearPress(){
    if(press)press.target.classList.remove('warehouse-long-press');
    const previous=press;
    press=null;
    return previous;
  }

  document.addEventListener('pointerdown',event=>{
    clearPress();
    skipClick=null;
    if(!event.isPrimary||event.button!==0)return;
    const value=valueAt(event.target);
    if(!value)return;
    press={value,target:event.target,id:event.pointerId,x:event.clientX,y:event.clientY,started:performance.now()};
    press.target.classList.add('warehouse-long-press');
  },true);

  document.addEventListener('pointermove',event=>{
    if(press?.id===event.pointerId&&Math.hypot(event.clientX-press.x,event.clientY-press.y)>movementLimit)clearPress();
  },{passive:true,capture:true});

  document.addEventListener('pointerup',event=>{
    if(press?.id!==event.pointerId)return;
    const previous=clearPress();
    if(!previous.target.isConnected||performance.now()-previous.started<holdTime)return;
    if(Math.hypot(event.clientX-previous.x,event.clientY-previous.y)>movementLimit)return;
    event.preventDefault();
    skipClick={target:previous.target,until:performance.now()+500};
    copyText(previous.value);
  },true);

  document.addEventListener('click',event=>{
    if(!skipClick||performance.now()>skipClick.until||event.detail===0)return;
    if(!skipClick.target.contains(event.target)&&!event.target.contains(skipClick.target))return;
    skipClick=null;
    event.preventDefault();
    event.stopImmediatePropagation();
  },true);

  document.addEventListener('contextmenu',event=>{
    if(press?.target===event.target||skipClick?.target===event.target)event.preventDefault();
  },true);
  document.addEventListener('pointercancel',clearPress,true);
  document.addEventListener('scroll',clearPress,{passive:true,capture:true});
  window.addEventListener('blur',clearPress);
}
