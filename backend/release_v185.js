/* Local generated illustrations; no external URL, no changes to item records. */
function catalog185(item){
  const category=String(item.category||'').toLowerCase(), name=String(item.name||'').toLowerCase(), body=String(item.kit_body||'').toLowerCase();
  const meaningful=v=>!['','-','—','нет','none','0','n/a','без'].includes(String(v||'').trim().toLowerCase());
  const text=(meaningful(body)?body:name).replace(/[αа]/g,'a').replace(/[–—]/g,'-');
  const combined=category+' '+name, dnp=/\bdnp\b|(?:ds[-\s]*)?rx[-\s]?1(?:hs)?\b/i.test(combined), other=/epson|selphy|canon|mitsubishi|hiti|fujifilm|kodak|sinfonia|hp\b|brother/i.test(combined);
  if(item.kind==='consumable'&&(dnp||/фотобумаг|photo\s*paper|термобумаг|красящ.*лент/i.test(combined)&&!other))return 17;
  if(item.kind!=='consumable'&&(dnp||/принтер|printer/i.test(combined)&&!other))return /бел(?:ый|ая|ое|ого|ым|ом)|\bwhite\b/i.test(name)?16:18;
  const camera=item.kind!=='consumable'&&(meaningful(body)||/фотокомплект|фотоаппарат|камер/.test(category)||/фотокомплект|фотоаппарат|камера|eos|sony\s*a[0-9]|nikon\s*z[0-9]/i.test(name));
  if(camera){
    if(/\br6\b/.test(text)&&! /\br6\s*(mark\s*ii|mkii|ii|2)\b/.test(text))return 0;
    if(/\br5\b/.test(text)&&! /\br5\s*(mark\s*ii|mkii|ii|2)\b/.test(text))return 1;
    if(/\brp\b/.test(text))return 2;
    if(/\ba\s*7\s*(iii|3|m3)\b/.test(text))return 3;
    if(/\bz\s*6\s*(ii|2)\b/.test(text))return 4;
    if(/\b5d\b/.test(text))return 5;
    if(/\b6d\b/.test(text))return 6;
    return 7;
  }
  const all=category+' '+name;
  if(/объектив|lens|\b\d{2,3}\s*[-–]\s*\d{2,3}\s*(mm|мм)/i.test(all))return 8;
  if(/вспыш|godox|speedlite|speedlight/i.test(all))return /\bv1\b/i.test(all)?9:10;
  if(/ноутбук|macbook|laptop|компьютер/i.test(all))return 11;
  if(/принтер|printer|epson|selphy/i.test(all)&&item.kind!=='consumable')return 12;
  if(/бумаг|paper|фотобумаг|картридж|пленк|плёнк/i.test(all))return 13;
  if(/освещ|свет|led|софтбокс/i.test(all)&&item.kind!=='consumable')return 14;
  return 15;
}
function catalogTile185(item){
  const n=document.createElement('span'), idx=catalog185(item);
  if(item.kind==='consumable'){n.className='r185-catalog';n.style.backgroundImage='url(data:image/webp;base64,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)';n.style.backgroundPosition='center';n.style.backgroundSize='100% 100%';n.setAttribute('role','img');n.setAttribute('aria-label','Расходные материалы');return n;}
  n.className='r185-catalog'+(idx===18?' r1852-dnp-black':idx>=16?' r1851-dnp':'');n.style.backgroundPosition=idx===18?'center':idx>=16?`${(idx-16)*100}% 0%`:`${(idx%4)*100/3}% ${Math.floor(idx/4)*100/3}%`;
  n.setAttribute('role','img');n.setAttribute('aria-label','Иллюстрация по модели или типу товара');return n;
}
function openPhoto185(item,original){
  if(document.querySelector('.r185-photo-overlay'))return;
  const {o,b}=overlay17(item.name);o.classList.add('r185-photo-overlay');b.classList.add('r185-photo-sheet');
  const frame=document.createElement('div');frame.className='r185-photo-frame';frame.append(catalogTile185(item));
  b.append(frame);o.onclick=e=>{if(e.target===o)o.remove()};
  if(original?.complete&&original.naturalWidth&&original.src){const image=new Image();image.alt='Фото экземпляра';image.src=original.src;frame.append(image);}
  else if(item.has_photo){const image=new Image();image.alt='Фото экземпляра';image17(image,itemPath17(item.code,'/photo')).then(()=>{if(o.isConnected){frame.append(image)}}).catch(()=>{});}
}
function attachPhoto185(cover,item){
  const open=e=>{e.stopPropagation();openPhoto185(item,cover.querySelector('img'))};
  cover.tabIndex=0;cover.setAttribute('role','button');cover.setAttribute('aria-label','Увеличить изображение '+item.name);
  cover.addEventListener('pointerdown',e=>e.stopPropagation());cover.addEventListener('contextmenu',e=>{e.preventDefault();e.stopPropagation()});cover.addEventListener('click',open);cover.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open(e)}});
}
function telegramNick185(user){
  const nick=String(user.username||'');const n=document.createElement(/^[A-Za-z0-9_]{1,64}$/.test(nick)?'a':'span');n.className='r185-nick';
  if(n.tagName==='A'){n.textContent='@'+nick;n.href='https://t.me/'+nick;n.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();if(tg.openTelegramLink)tg.openTelegramLink(n.href);else window.open(n.href,'_blank','noopener,noreferrer')})}else n.textContent=user.tg_id<0?'Без Telegram':'Не указан';return n;
}
async function block185(id,blocked,label){
  if(!currentUser?.is_owner)return;
  if(!confirm((blocked?'Заблокировать':'Разблокировать')+' доступ: '+label+' (ID '+id+')? История и выданные товары сохранятся.'))return;
  await api('/api/v185/blocked/'+encodeURIComponent(id),{method:'POST',body:JSON.stringify({blocked})});showToast(blocked?'Доступ заблокирован':'Доступ восстановлен');return true;
}
async function showBlocked185(){
  if(!currentUser?.is_owner)return;
  const {o,b}=overlay17('Блокировка по Telegram ID');b.classList.add('r185-block-sheet');
  const note=document.createElement('p');note.className='meta';note.textContent='Можно заранее запретить вход по числовому ID. Ник может измениться, ID — нет.';b.append(note);
  const id=field17(b,'Telegram ID','','text');id.inputMode='numeric';id.maxLength=16;
  btn17(b,'Заблокировать ID',async()=>{const v=id.value.trim();if(!/^[1-9][0-9]{0,15}$/.test(v))throw Error('Нужен числовой Telegram ID');if(await block185(v,true,'Telegram ID')){o.remove();await loadUsers();showBlocked185()}},'danger');
  const rows=await api('/api/v185/blocked');if(!o.isConnected)return;
  const h=document.createElement('h3');h.textContent='Заблокированы';b.append(h);
  if(!rows.length)b.append(document.createTextNode('Список пуст'));
  for(const u of rows){const c=card17(b,u.full_name||('Telegram ID '+u.tg_id),'ID '+u.tg_id+(u.username?' · @'+u.username:''));btn17(c,'Разблокировать',async()=>{if(await block185(u.tg_id,false,u.full_name||'Telegram ID')){o.remove();await loadUsers();showBlocked185()}},'secondary')}
}
function installRelease185(){
  const footer=[...$('screen-settings').querySelectorAll('.v18-muted')].find(n=>n.textContent.includes('Склад ·'));if(footer)footer.textContent='Склад · v18.5.8';
  installRooms1851();
  const oldApi=api;let revoked=false;
  api=async(...args)=>{try{const result=await oldApi(...args);if(/\/api\/items\/[^/]+(?:\/photo|\/passport)?$/.test(args[0])&&['POST','PUT','PATCH'].includes(args[1]?.method))document.dispatchEvent(new Event('warehouse-photo-changed'));return result}catch(e){if((e.message==='Доступ к приложению заблокирован владельцем.'||e.message==='Войдите на сайт заново'||e.message==='Срок авторизации истёк. Откройте приложение заново.')&&currentUser&&!revoked){revoked=true;clearInterval(autoRefreshInterval);currentUser=null;currentItem=null;allItems=[];document.querySelectorAll('.modal-overlay').forEach(n=>n.remove());document.querySelector('.bottom-nav')?.classList.add('hidden');showScreen('screen-login');$('screen-login').querySelector('.login-card').textContent=e.message;location.reload()}throw e}};
  const oldToast=showToast;showToast=(message,type='success')=>{try{tg.HapticFeedback?.notificationOccurred(type==='error'?'error':'success')}catch(e){}return oldToast(message,type)};
}

/* v18.5.1: room counts come from the current server response, not allItems. */
const r1851IconPaths={workshop:'<path d="M14.7 6.3a5 5 0 0 0-6.6 6.6L3 18l3 3 5.1-5.1a5 5 0 0 0 6.6-6.6l-3.5 3.5-3-3 3.5-3.5z"/>',storage:'<path d="m3 8 9-5 9 5v13H3zM7 21V11h10v10M7 15h10M7 18h10"/>',office:'<path d="M5 21V4h14v17M3 21h18M9 8h1m4 0h1M9 12h1m4 0h1M10 21v-5h4v5"/>',arrow:'<path d="m9 18 6-6-6-6"/>',plus:'<path d="M12 5v14M5 12h14"/>'};
function icon1851(kind){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('class','r1851-symbol');svg.setAttribute('aria-hidden','true');svg.innerHTML=r1851IconPaths[kind]||r1851IconPaths.storage;return svg}
function roomCard1851(room){
  const make=(tag,cls,txt)=>{const n=document.createElement(tag);n.className=cls;if(txt!==undefined)n.textContent=txt;return n};
  const kind=['workshop','storage','office'].includes(room.type)?room.type:/мастер/i.test(room.name)?'workshop':/офис/i.test(room.name)?'office':'storage';
  const card=make('article','card r1851-room-card');card.dataset.kind=kind;card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-label',room.name);
  const header=make('div','r1851-room-head'),symbol=make('span','r1851-room-icon'),arrow=make('span','r1851-room-arrow');symbol.append(icon1851(kind));arrow.append(icon1851('arrow'));header.append(symbol,make('div','r1851-room-title',room.name),arrow);
  const metrics=make('div','r1851-room-metrics');for(const [label,key,unit] of [['Оборудование','equipment_count',''],['Расходники','consumable_count','шт.']]){const metric=make('div','r1851-room-metric'),value=make('div','r1851-room-value');value.append(make('strong','',Number.isFinite(room[key])?room[key].toLocaleString('ru-RU'):'—'));if(unit)value.append(make('span','r1851-room-unit',unit));metric.append(make('div','r1851-room-metric-label',label),value);metrics.append(metric)}
  card.append(header,metrics);card.onclick=()=>openRoom(room.id,room.name);card.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();card.click()}};return card;
}
function installRooms1851(){
  document.querySelectorAll('.sticky-header').forEach(h=>{if(h.querySelector('.v18-header-left')&&h.querySelector('.v18-header-right'))h.classList.add('r1851-balanced')});
  const detail=$('screen-room-view'),select=detail.querySelector('button[onclick="selectAllInRoom()"]');if(select){const row=document.createElement('div');row.className='r1851-room-actions';detail.querySelector('.sticky-header').after(row);row.append(select)}
  const section=$('screen-rooms'),list=$('rooms-list'),add=$('add-item-btn');section.querySelector('.sticky-title').textContent='Склад';add.parentElement.classList.add('r1851-add-wrap');add.replaceChildren(icon1851('plus'),document.createTextNode('Добавить товар'));const label=document.createElement('h2');label.className='r1851-rooms-label';label.textContent='ПОМЕЩЕНИЯ';list.before(label);
  let request=0;showRooms=async()=>{
    if(currentUser?.role!=='admin')return;
    const id=++request;showScreen('screen-rooms');updateNavActive('nav-rooms');$('batch-actions').style.display='none';
    loadLowStock();
    if(!list.querySelector('.r1851-room-card')){const skeleton=document.createElement('div');skeleton.className='card';skeleton.textContent='Загрузка помещений…';list.replaceChildren(skeleton)}
    try{const rooms=await api('/api/locations_view');if(id!==request||currentUser?.role!=='admin')return;list.replaceChildren(...rooms.map(roomCard1851));if(!rooms.length)list.textContent='Нет помещений'}catch(e){if(id!==request)return;if(list.querySelector('.r1851-room-card'))notify(e.message||'Не удалось обновить помещения');else list.textContent=e.message||'Не удалось загрузить помещения'}
  };
}
