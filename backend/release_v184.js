/* v18.4 — Beta UI; no credentials or live stock in client code. */
function installRelease184(){
  const el=(tag,cls,txt)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(txt!==undefined)n.textContent=txt;return n};
  const button=(txt,fn,cls='secondary')=>{const n=el('button',cls,txt);n.type='button';n.onclick=async e=>{if(n.disabled)return;try{await fn(e)}catch(err){notify(err.message||String(err))}};return n};
  const admin=()=>currentUser?.role==='admin',finance=()=>['admin','boss'].includes(currentUser?.role);
  const main=$('screen-main'),root=$('items-list'),filterBox=main.querySelector('.filters');
  const inventory=main.querySelector('.v18-inventory');
  const toolbar=el('div','r184-tools'),segments=el('div','r184-segments');
  filterBox.before(toolbar);toolbar.append(segments);
  const panels=el('div','r184-filter-panel hidden'),sortPanel=el('div','r184-filter-panel hidden');toolbar.after(panels,sortPanel);panels.append(filterBox);$('filter-kind').classList.add('hidden');
  const opts=$('filter-status');opts.add(new Option('На выкупе','buyout'));
  const prevMatch=matchesStatus17;matchesStatus17=(i,s)=>s==='buyout'?i.kind==='equipment'&&!!String(i.buyout_status||'').trim():prevMatch(i,s);
  let sort='default',favoriteOnly=false;
  const from=el('input'),to=el('input'),priceWrap=el('div','r184-price-range'),fav=el('input');from.type=to.type='number';from.min=to.min='0';from.placeholder='От';to.placeholder='До';from.setAttribute('aria-label','Цена от');to.setAttribute('aria-label','Цена до');priceWrap.append(el('span','','Стоимость, ₽'),from,to);panels.append(priceWrap);fav.type='checkbox';const favlabel=el('label','r184-favorite-filter');favlabel.append(fav,el('span','','Только избранное'));panels.append(favlabel);
  const sortSelect=el('select');for(const [v,t]of [['default','По статусу'],['name-asc','Название: А–Я'],['name-desc','Название: Я–А'],['price-asc','Цена: от меньшей'],['price-desc','Цена: от большей'],['qty-asc','Количество: от меньшего'],['qty-desc','Количество: от большего'],['date-desc','Сначала новые'],['date-asc','Сначала старые']])sortSelect.add(new Option(t,v));sortPanel.append(sortSelect);
  function refreshFilterButtons(){for(const b of segments.children)b.classList.toggle('active',b.dataset.value===$('filter-kind').value);filterBtn.classList.toggle('active',!!($('filter-location').value||$('filter-category').value||opts.value||fav.checked||(finance()&&(from.value||to.value))));sortBtn.classList.toggle('active',sort!=='default');priceWrap.classList.toggle('hidden',!finance());for(const o of sortSelect.options)if(o.value.startsWith('price'))o.disabled=o.hidden=!finance()}
  for(const [v,t]of [['','Все'],['equipment','Техника'],['consumable','Расходники']]){const b=button(t,()=>{$('filter-kind').value=v;filterItems()},'r184-segment');b.dataset.value=v;segments.append(b)}
  const filterBtn=button('',()=>{panels.classList.toggle('hidden');sortPanel.classList.add('hidden')},'r184-icon'),sortBtn=button('',()=>{sortPanel.classList.toggle('hidden');panels.classList.add('hidden')},'r184-icon');
  filterBtn.innerHTML='<svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="10" cy="18" r="2"/></svg>';sortBtn.innerHTML='<svg viewBox="0 0 24 24"><path d="M7 4v16m-4-4 4 4 4-4M17 20V4m-4 4 4-4 4 4"/></svg>';filterBtn.title=filterBtn.ariaLabel='Фильтры';sortBtn.title=sortBtn.ariaLabel='Сортировка';toolbar.append(filterBtn,sortBtn);
  panels.append(button('Сбросить фильтры',()=>{for(const id of ['filter-location','filter-category','filter-status','filter-kind'])$(id).value='';from.value=to.value='';fav.checked=false;filterItems()}));panels.append(button('Показать товары',()=>panels.classList.add('hidden'),'ok'));
  [from,to].forEach(x=>x.oninput=()=>filterItems());fav.onchange=()=>filterItems();sortSelect.onchange=()=>{sort=sortSelect.value;filterItems();sortPanel.classList.add('hidden')};
  // Keep access to prior profile features without five shortcut buttons.
  const quickActions=main.querySelector('.v18-shortcuts');if(quickActions){const original=[...quickActions.children];const more=button('Ещё',()=>{const {o,b}=overlay17('Товары');for(const a of original){const label=a.textContent.trim();if(!['Недавние','Комплекты','Избранное'].includes(label))continue;btn17(b,label,()=>{o.remove();a.click()})}},'secondary r184-more');inventory.querySelector('.v18-title-row')?.append(more);quickActions.classList.add('hidden')}
  const priority=i=>i.needs_repair?5:i.kind==='equipment'&&String(i.buyout_status||'').trim()?4:!i.holders?.length?1:i.holders.some(h=>h.taken_for?.trim())?3:2;
  const price=i=>{const p=['price_body','price_lens','price_flash','price_acc','price_add'].reduce((a,k)=>a+Number(i[k]||0),0);return p||Number(i.price||0)};
  function compare(a,b){if(sort==='default')return priority(a)-priority(b)||a.name.localeCompare(b.name,'ru');if(a.kind==='equipment'&&!!a.needs_repair!==!!b.needs_repair)return Number(!!a.needs_repair)-Number(!!b.needs_repair);const [key,dir]=sort.split('-'),k=dir==='desc'?-1:1;if(key==='name')return k*a.name.localeCompare(b.name,'ru');if(key==='price')return k*(price(a)-price(b));if(key==='qty')return k*(a.total-b.total);if(key==='date')return k*String(a.created_at||'').localeCompare(String(b.created_at||''));return priority(a)-priority(b)}
  const thumbCache=new Map();let observer,lastMainSignature=null;document.addEventListener('warehouse-photo-changed',()=>{for(const value of thumbCache.values())value.then(URL.revokeObjectURL).catch(()=>{});thumbCache.clear();lastMainSignature=null});const oldRender=renderItemsGrid;
  function photoFor(i){const cover=el('div','r184-thumb');cover.append(catalogTile185(i));const badge=el('small','r185-illustration-mark','Иллюстрация');cover.append(badge);attachPhoto185(cover,i);if(i.has_photo){const img=el('img');img.alt='Фото товара';img.loading='lazy';img.dataset.code=i.code;cover.append(img);if(observer)observer.observe(img);else loadPhoto(img)}return cover}
  async function loadPhoto(img){const code=img.dataset.code;try{let promise=thumbCache.get(code);if(!promise){promise=blob17('/api/items/'+encodeURIComponent(code)+'/photo').then(blob=>URL.createObjectURL(blob));thumbCache.set(code,promise);if(thumbCache.size>100){const k=thumbCache.keys().next().value;thumbCache.get(k)?.then(URL.revokeObjectURL).catch(()=>{});thumbCache.delete(k)}}const url=await promise;if(img.isConnected){img.onload=()=>{img.parentElement?.classList.add('r185-real-photo')};img.src=url}}catch(e){thumbCache.delete(code);img.remove()}}
  if('IntersectionObserver'in window)observer=new IntersectionObserver(entries=>entries.forEach(x=>{if(x.isIntersecting){observer.unobserve(x.target);loadPhoto(x.target)}}),{rootMargin:'180px'});
  function status(i,body){const line=el('div','r184-status-line');const badge=(text,cls)=>line.append(el('span','r184-status '+cls,text));if(i.holders?.length)for(const h of i.holders)badge('У '+(String(h.taken_for||h.full_name||'—').trim().split(/\s+/)[0]),'held');if(i.buyout_status)badge('Выкуп: '+String(i.buyout_status).trim().split(/\s+/)[0],'buyout');if(i.needs_repair)badge('Ремонт','repair');if(booked17.has(i.code))badge('Бронь','booked');if(i.kind==='equipment'&&!i.holders?.length&&!i.needs_repair&&!i.buyout_status&&i.total>0)badge('Свободно','free');if(i.kind==='consumable'&&i.is_low)badge('Мало','repair');body.append(line)}
  function longActions(i){const {o,b}=overlay17(i.name);btn17(b,'Информация',()=>{o.remove();openItem(i.code)});btn17(b,'История',async()=>{o.remove();await openItem(i.code);if(currentItem?.code===i.code)showItemHistory()});if(i.kind==='equipment'&&!i.holders.length&&!i.needs_repair&&i.total>0)btn17(b,'Взять технику',async()=>{o.remove();await openItem(i.code);if(currentItem?.code===i.code)doCheckout()});if(i.stocks?.length)btn17(b,'Переместить',async()=>{o.remove();await openItem(i.code);if(currentItem?.code===i.code)showMoveItemScreen()});if(admin())btn17(b,'Редактировать',async()=>{o.remove();await openItem(i.code);if(currentItem?.code===i.code)showEditForm()},'secondary r184-admin-dot');btn17(b,'QR-этикетка',async()=>{o.remove();await openItem(i.code);if(currentItem?.code===i.code)showQr()})}
  function card(i){const c=el('article','card item-card r184-item');c.tabIndex=0;c.setAttribute('role','button');c.setAttribute('aria-label',i.name);const wrap=el('div','r184-item-main'),info=el('div','r184-item-info');wrap.append(photoFor(i),info);info.append(el('div','name',i.name),el('div','meta',i.code+(i.category?' · '+i.category:'' )+(i.serial_number?' · S/N: '+i.serial_number:'')));if(i.kind==='equipment')for(const [k,l]of [['kit_body','Фотоаппарат'],['kit_lens','Объектив'],['kit_flash','Вспышка']])if(i[k])info.append(el('div','r184-part',l+': '+i[k]));for(const s of i.stocks||[])info.append(el('div','meta',s.location_name+(i.kind==='consumable'?' — '+s.quantity+' '+(i.unit||'шт.') :'')));if(i.kind==='consumable')info.append(el('b','r184-qty',String(i.total)+' '+(i.unit||'шт.')));const meta=[];if(i.budget_tag)meta.push(i.budget_tag);if(finance()&&price(i))meta.push(money182(price(i)));if(meta.length)info.append(el('div','meta',meta.join(' · ')));c.append(wrap);status(i,c);let timer=null,startX=0,startY=0,held=false;const clear=()=>{clearTimeout(timer);timer=null};c.onpointerdown=e=>{if(e.target.tagName==='IMG'){}held=false;startX=e.clientX;startY=e.clientY;timer=setTimeout(()=>{held=true;haptic();longActions(i)},550)};c.onpointermove=e=>{if(Math.abs(e.clientX-startX)>10||Math.abs(e.clientY-startY)>10)clear()};c.onpointerup=c.onpointercancel=c.onpointerleave=clear;c.oncontextmenu=e=>{e.preventDefault();clear();if(!held){held=true;longActions(i)}};c.onclick=()=>{if(held){held=false;return}openItem(i.code)};c.onkeydown=e=>{if(e.target===c&&(e.key==='Enter'||e.key===' ')){e.preventDefault();openItem(i.code)}};return c}
  renderItemsGrid=(rows,id)=>{if(id!=='items-list')return oldRender(rows,id);const signature=JSON.stringify([rows,sort,from.value,to.value,fav.checked,fav.checked?cacheGet17('v18_profile'):'',currentUser?.tg_id,currentUser?.role,$('filter-kind').value]);if(signature===lastMainSignature&&root.querySelector('.r183-section')){refreshFilterButtons();return}lastMainSignature=signature;const fragment=document.createDocumentFragment();for(const [kind,title]of [['equipment','Оборудование'],['consumable','Расходники']]){let shown=rows.filter(i=>i.kind===kind);if(finance()){const a=from.value===''?null:Number(from.value),b=to.value===''?null:Number(to.value);shown=shown.filter(i=>(a===null||price(i)>=a)&&(b===null||price(i)<=b))}if(fav.checked){let favorites=[];try{favorites=JSON.parse(cacheGet17('v18_profile')||'{}').favorites||[]}catch(e){}shown=shown.filter(i=>favorites.includes(i.code))}if(!shown.length)continue;const section=el('section','r183-section'),list=el('div','r183-items');section.append(el('h3','',title),list);shown.sort(compare).forEach(i=>list.append(card(i)));fragment.append(section)}if(observer)observer.disconnect();root.replaceChildren(fragment);if(observer)root.querySelectorAll('img[data-code]').forEach(img=>observer.observe(img));if(!root.children.length)root.append(el('p','meta','Ничего не найдено'));refreshFilterButtons()};
  // Default entire stock in selected source room, with integer partial transfer and bounds.
  const oldMove=showMoveItemScreen,source=el('select'),allQty=button('Все',()=>{$('move-qty').value=$('move-qty').max;updateRemain()}),remain=el('div','meta');source.setAttribute('aria-label','Откуда');$('move-item-from').after(source);$('move-qty').after(allQty,remain);$('move-qty').step='1';
  function updateRemain(){const q=Number($('move-qty').value),m=Number($('move-qty').max);remain.textContent='Останется: '+Math.max(0,m-(Number.isFinite(q)?q:0))+' '+(currentItem?.unit||'шт.');$('move-confirm-btn').disabled=!Number.isInteger(q)||q<1||q>m}
  function setSource(id){const s=currentItem.stocks.find(x=>x.location_id===Number(id));if(!s)return;moveFromLocId=s.location_id;selectedMoveRoomId=null;$('move-step-2').classList.add('hidden');$('move-item-from').textContent='Откуда: '+s.location_name;$('move-qty').max=String(s.quantity);$('move-qty').value=currentItem.kind==='consumable'?String(s.quantity):'1';$('move-rooms-list').replaceChildren(...locations.filter(l=>l.id!==moveFromLocId).map(l=>button(l.name,()=>selectMoveRoom(l.id,l.name),'secondary')));updateRemain()}
  source.onchange=()=>setSource(source.value);$('move-qty').oninput=updateRemain;showMoveItemScreen=()=>{oldMove();source.replaceChildren(...currentItem.stocks.filter(s=>s.quantity>0).map(s=>new Option(s.location_name+' · '+s.quantity,s.location_id)));source.classList.toggle('hidden',source.options.length<=1);allQty.classList.toggle('hidden',currentItem.kind!=='consumable');if(source.value)setSource(source.value)};
  const oldExecute=executeMoveItem;let moving=false;executeMoveItem=async()=>{const n=Number($('move-qty').value);if(moving||!Number.isInteger(n)||n<=0||n>Number($('move-qty').max))return notify('Некорректное количество');moving=true;try{await oldExecute()}finally{moving=false}};
  // Roles and employee preview. Reload drops any previously rendered financial data.
  const setting=$('screen-settings').querySelector('.v18-settings-layout'),preview=button('Стать сотрудником на 3 минуты',async()=>{if(!admin()||!confirm('Временно перейти в интерфейс сотрудника?'))return;preview.disabled=true;try{await api('/api/v184/preview/start',{method:'POST'});location.reload()}finally{preview.disabled=false}},'secondary r184-admin-dot');setting.prepend(preview);
  const previewBanner=el('div','r184-preview hidden'),timer=el('b'),stop=button('Выйти из режима',async()=>{stop.disabled=true;try{await api('/api/v184/preview/stop',{method:'POST'});location.reload()}finally{stop.disabled=false}});previewBanner.append(timer,stop);document.body.prepend(previewBanner);
  let previewTimer;function renderPreview(){clearInterval(previewTimer);if(!currentUser?.preview_until)return;previewBanner.classList.remove('hidden');document.body.classList.add('r184-preview-active');const tick=()=>{let left=Math.max(0,Math.ceil(currentUser.preview_until-Date.now()/1000));timer.textContent='Режим сотрудника · '+Math.floor(left/60)+':'+String(left%60).padStart(2,'0');if(!left){clearInterval(previewTimer);location.reload()}};tick();previewTimer=setInterval(tick,500)}
  // Boss view, with explicit stock-room interpretation and separate holder detail.
  const bossBox=el('section','r184-boss hidden');main.querySelector('.v18-quick').before(bossBox);let bossJob=null;
  function bossPanel(title,key,data){const p=el('div','card r184-boss-panel '+key),heading=el('h3','',title),grid=el('div','r184-boss-grid');p.append(heading,grid);for(const [k,t]of [['cameras','Фотоаппараты'],['flashes','Вспышки']]){const metric=el('div');metric.append(el('span','meta',t),el('strong','',String(data[k]||0)));grid.append(metric)}return p}
function r186Brand(value,kind){
 const s=String(value||'').normalize('NFKC').toLowerCase().trim();
 const canon=/(^|[^a-zа-яё])(?:canon|к[еэ]нон|канон|eos)(?=$|[^a-zа-яё])/.test(s);
 const sony=/(^|[^a-zа-яё])(?:sony|сони|с[oо]нька)(?=$|[^a-zа-яё])/.test(s);
 if(canon&&sony)return '?';
 if(canon)return 'К';if(sony)return 'С';
 if(kind==='camera'&&/(^|[^a-z0-9])(?:ilce[-\s]?\d|[aаα]\s*7(?:[rsc]|iii|iv|ii|\d)?)(?=$|[^a-z0-9])/.test(s))return 'С';
 if(kind==='camera'&&/(^|[^a-z0-9])(?:r[35678](?:\s*(?:mark\s*ii|mkii|ii))?|5d|6d|rp)(?=$|[^a-z0-9])/.test(s))return 'К';
 if(kind==='flash'){
  const m=s.match(/(?:^|[^a-z0-9])(?:v1(?:pro)?|v860(?:iii|ii|3|2)?|tt685(?:ii|2)?|tt600|tt350|v350|v480|v100)\s*[-–—]?\s*([cs])(?=$|[^a-z0-9])/);
  if(m)return m[1]==='c'?'К':'С';
  if(/(?:^|[^a-z0-9])(?:speedlite\s*\d|el-[15]|hvl-f\d)/.test(s))return /hvl-f\d/.test(s)?'С':'К';
 }
 return '?';
}
function r186Count(items,type){
 const result={К:0,С:0,'?':0}, field=type==='camera'?'camera':'flash';
 const count=type==='camera'?'camera_count':'flash_count';
 for(const i of items||[]){
  const n=Number(i[count]||0);if(!Number.isFinite(n)||n<=0)continue;
  const raw=String(i[field]||'').trim();
  const explicit=!['','-','—','нет','none','0','n/a','без','не указан'].includes(raw.toLowerCase());
  const b=r186Brand(explicit?raw:i.name,type);result[b]+=n;
 }
 return result;
}
  // Compact boss roster: 'combined', 'icons', 'letters' are kept as alternatives.
  const bossRosterMode='combined';
  function bossSymbol(kind){
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('class','r186-symbol');svg.setAttribute('aria-hidden','true');
    svg.innerHTML=kind==='camera'?'<path d="M4 6h4l2-3h4l2 3h4a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z"/><circle cx="12" cy="13" r="4"/>':'<path d="m13 2-9 12h7l-1 8 10-12h-7z"/>';
    return svg;
  }
  function bossCodes(person,kind){
    const cell=el('span','r186-codes '+kind), counts=r186Count(person.items,kind), prefix=kind==='camera'?'Ф':'В';
    const labels={К:'Canon',С:'Sony','?':'Бренд не указан или не распознан'};
    let accessible=[];
    if(bossRosterMode!=='letters')cell.append(bossSymbol(kind));
    for(const b of ['К','С','?']){
      if(!counts[b])continue;
      const suffix=bossRosterMode==='icons'?({К:'C',С:'S','?':'?'})[b]:prefix+b;
      const chip=el('span','r186-code',suffix+(counts[b]>1?'×'+counts[b]:''));chip.title=labels[b];cell.append(chip);
      accessible.push(labels[b]+': '+counts[b]);
    }
    if(!accessible.length){cell.replaceChildren(el('span','r186-empty','—'));accessible=['нет']}
    cell.setAttribute('aria-label',(kind==='camera'?'Фотоаппараты: ':'Вспышки: ')+accessible.join(', '));return cell;
  }
  function bossRoster(people,expanded){
    const list=el('div','r186-roster');
    for(const p of people){
      const entry=el('details','r186-person');entry.dataset.person=p.key||p.name;entry.open=expanded.has(entry.dataset.person);
      const line=el('summary','r186-row'),name=el('span','r186-name',p.name);
      name.title=p.name;const buyout=(p.items||[]).some(i=>String(i.buyout_status||'').trim());
      const status=el('span','r186-buyout',buyout?'Выкуп':'');const arrow=el('span','r186-arrow','›');arrow.setAttribute('aria-hidden','true');
      line.append(name,bossCodes(p,'camera'),bossCodes(p,'flash'),status,arrow);
      entry.append(line);
      const info=el('div','r186-detail');
      for(const i of p.items||[]){
        const link=button(i.name,()=>openItem(i.code),'secondary r186-item-link');info.append(link);
        const meta=[i.camera_count?('Фотоаппарат: '+(String(i.camera||'').trim()||i.name)):'',i.flash_count?('Вспышка: '+(String(i.flash||'').trim()||i.name)):'',i.buyout_status?'На выкупе: '+i.buyout_status:'',i.taken_at?'Выдано: '+i.taken_at:''].filter(Boolean);
        if(meta.length)info.append(el('div','meta r186-item-meta',meta.join(' · ')));
      }
      entry.append(info);list.append(entry);
    }
    if(!people.length)list.append(el('p','meta','Нет выданной техники'));return list;
  }
  async function refreshBoss(){if(currentUser?.role!=='boss')return;if(bossJob)return bossJob;bossJob=api('/api/v184/boss').then(r=>{if(currentUser?.role!=='boss')return;const office=bossPanel('В офисе','office',r.office),held=bossPanel('На руках','held',r.held);office.append(el('small','meta','Все помещения склада'));const expanded=new Set([...bossBox.querySelectorAll('.r186-person[open]')].map(n=>n.dataset.person));held.append(bossRoster(r.people,expanded));const showFinance=button('Финансы',()=>showExtra('finance'),'secondary');bossBox.replaceChildren(el('h2','','Сводка по технике'),office,held,showFinance);bossBox.classList.remove('hidden')}).catch(e=>{if(!bossBox.children.length)bossBox.append(el('p','meta','Сводка временно недоступна'));bossBox.classList.remove('hidden')}).finally(()=>bossJob=null);return bossJob}

  const oldLoad=loadItems;loadItems=async()=>{await oldLoad();refreshBoss()};
  const oldShowRooms=showRooms;showRooms=async()=>{await oldShowRooms();for(const r of $('rooms-list').querySelectorAll('.room-card')){const title=r.querySelector('.room-title')?.textContent,loc=locations.find(l=>l.name===title);if(!loc)continue;const rows=allItems.flatMap(i=>i.stocks.filter(s=>s.location_id===loc.id).map(s=>({kind:i.kind,qty:s.quantity})));const equipment=rows.filter(i=>i.kind==='equipment').reduce((n,i)=>n+i.qty,0),cons=rows.filter(i=>i.kind==='consumable').reduce((n,i)=>n+i.qty,0);const b=r.querySelector('.room-count-badge');if(b)b.replaceChildren(el('div','','Оборудование: '+equipment),el('div','','Расходники: '+cons+' шт.'))}};
  const mark=()=>{if(!admin())return;for(const q of ['#screen-settings .v18-settings-layout button','#screen-users #users-list button','#nav-settings','#nav-rooms','.v18-admin','#edit-btn','#delete-item-btn','#export-history-btn','#add-item-btn','#actions button[onclick*="replenish"]','#screen-item .owner-only'])document.querySelectorAll(q).forEach(e=>e.classList.add('r184-admin-dot'))};const oldScreen=showScreen;showScreen=id=>{oldScreen(id);mark()};
  const oldInit=init;init=async()=>{await oldInit();if(!currentUser?.is_registered)return;document.body.classList.toggle('r184-admin',admin());document.body.classList.toggle('r184-finance',finance());document.body.classList.toggle('r184-boss-role',currentUser.role==='boss');if(currentUser.role==='boss')$('user-info').append(el('span','r184-role','Босс'));if(!admin())$('export-history-btn').classList.add('hidden');renderPreview();mark();filterItems();refreshBoss()};
}
