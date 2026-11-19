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
  function photoFor(i){const cover=el('div','r184-thumb');cover.append(catalogTile185(i));attachPhoto185(cover,i);if(i.has_photo){const img=el('img');img.alt='Фото товара';img.loading='lazy';img.dataset.code=i.code;cover.append(img);if(observer)observer.observe(img);else loadPhoto(img)}return cover}
  async function loadPhoto(img){const code=img.dataset.code;try{let promise=thumbCache.get(code);if(!promise){promise=blob17('/api/items/'+encodeURIComponent(code)+'/photo').then(blob=>URL.createObjectURL(blob));thumbCache.set(code,promise);if(thumbCache.size>100){const k=thumbCache.keys().next().value;thumbCache.get(k)?.then(URL.revokeObjectURL).catch(()=>{});thumbCache.delete(k)}}const url=await promise;if(img.isConnected){img.onload=()=>{img.parentElement?.classList.add('r185-real-photo')};img.src=url}}catch(e){thumbCache.delete(code);img.remove()}}
  if('IntersectionObserver'in window)observer=new IntersectionObserver(entries=>entries.forEach(x=>{if(x.isIntersecting){observer.unobserve(x.target);loadPhoto(x.target)}}),{rootMargin:'180px'});
  function status(i,body){const line=el('div','r184-status-line');const badge=(text,cls)=>line.append(el('span','r184-status '+cls,text));if(i.holders?.length)for(const h of i.holders)badge('У '+(h.taken_for||h.full_name||'—'),'held');if(i.buyout_status)badge('Выкуп: '+i.buyout_status,'buyout');if(i.needs_repair)badge('Ремонт','repair');if(booked17.has(i.code))badge('Бронь','booked');if(i.kind==='equipment'&&!i.holders?.length&&!i.needs_repair&&!i.buyout_status&&i.total>0)badge('Свободно','free');if(i.kind==='consumable'&&i.is_low)badge('Мало','repair');body.append(line)}
  function longActions(i){const {o,b}=overlay17(i.name);btn17(b,'Информация',()=>{o.remove();openItem(i.code)});btn17(b,'История',async()=>{o.remove();await openItem(i.code);if(currentItem?.code===i.code)showItemHistory()});if(i.kind==='equipment'&&!i.holders.length&&!i.needs_repair&&i.total>0)btn17(b,'Взять технику',async()=>{o.remove();await openItem(i.code);if(currentItem?.code===i.code)doCheckout()});if(i.stocks?.length)btn17(b,'Переместить',async()=>{o.remove();await openItem(i.code);if(currentItem?.code===i.code)showMoveItemScreen()});if(admin())btn17(b,'Редактировать',async()=>{o.remove();await openItem(i.code);if(currentItem?.code===i.code)showEditForm()},'secondary r184-admin-dot');btn17(b,'QR-этикетка',async()=>{o.remove();await openItem(i.code);if(currentItem?.code===i.code)showQr()})}
  function card(i){const c=el('article','card item-card r184-item');c.tabIndex=0;c.setAttribute('role','button');c.setAttribute('aria-label',i.name);const wrap=el('div','r184-item-main'),info=el('div','r184-item-info');wrap.append(photoFor(i),info);info.append(el('div','name',i.name),el('div','meta',i.code+(i.category?' · '+i.category:'' )+(i.serial_number?' · S/N: '+i.serial_number:'')));if(i.kind==='equipment')for(const [k,l]of [['kit_body','Фотоаппарат'],['kit_lens','Объектив'],['kit_flash','Вспышка']])if(i[k])info.append(el('div','r184-part',l+': '+i[k]));for(const s of i.stocks||[])info.append(el('div','meta',s.location_name+(i.kind==='consumable'?' — '+s.quantity+' '+(i.unit||'шт.') :'')));if(i.kind==='consumable')info.append(el('b','r184-qty',String(i.total)+' '+(i.unit||'шт.')));const meta=[];if(i.budget_tag)meta.push(i.budget_tag);if(finance()&&price(i))meta.push(money182(price(i)));if(meta.length)info.append(el('div','meta',meta.join(' · ')));c.append(wrap);status(i,c);let timer=null,startX=0,startY=0,held=false;const clear=()=>{clearTimeout(timer);timer=null};c.onpointerdown=e=>{if(e.target.tagName==='IMG'){}held=false;startX=e.clientX;startY=e.clientY;timer=setTimeout(()=>{held=true;haptic();longActions(i)},550)};c.onpointermove=e=>{if(Math.abs(e.clientX-startX)>10||Math.abs(e.clientY-startY)>10)clear()};c.onpointerup=c.onpointercancel=c.onpointerleave=clear;c.oncontextmenu=e=>{e.preventDefault();clear();if(!held){held=true;longActions(i)}};c.onclick=()=>{if(held){held=false;return}openItem(i.code)};c.onkeydown=e=>{if(e.target===c&&(e.key==='Enter'||e.key===' ')){e.preventDefault();openItem(i.code)}};return c}
  renderItemsGrid=(rows,id)=>{if(id!=='items-list')return oldRender(rows,id);const signature=JSON.stringify([rows,sort,from.value,to.value,fav.checked,fav.checked?cacheGet17('v18_profile'):'',currentUser?.tg_id,currentUser?.role,$('filter-kind').value]);if(signature===lastMainSignature&&root.querySelector('.r183-section')){refreshFilterButtons();return}lastMainSignature=signature;const fragment=document.createDocumentFragment();for(const [kind,title]of [['equipment','Оборудование'],['consumable','Расходники']]){let shown=rows.filter(i=>i.kind===kind);if(finance()){const a=from.value===''?null:Number(from.value),b=to.value===''?null:Number(to.value);shown=shown.filter(i=>(a===null||price(i)>=a)&&(b===null||price(i)<=b))}if(fav.checked){let favorites=[];try{favorites=JSON.parse(cacheGet17('v18_profile')||'{}').favorites||[]}catch(e){}shown=shown.filter(i=>favorites.includes(i.code))}if(!shown.length)continue;const section=el('section','r183-section'),list=el('div','r183-items');section.append(el('h3','',title),list);shown.sort(compare).forEach(i=>list.append(card(i)));fragment.append(section)}if(observer)observer.disconnect();root.replaceChildren(fragment);if(observer)root.querySelectorAll('img[data-code]').forEach(img=>observer.observe(img));if(!root.children.length)root.append(el('p','meta','Ничего не найдено'));refreshFilterButtons()};
  // Default entire stock in selected source room, with integer partial transfer and bounds.
  const oldMove=showMoveItemScreen,source=el('select'),allQty=button('Все',()=>{$('move-qty').value=$('move-qty').max;updateRemain()}),remain=el('div','meta');source.setAttribute('aria-label','Откуда');$('move-item-from').after(source);$('move-qty').after(allQty,remain);$('move-qty').step='1';
  function updateRemain(){const q=Number($('move-qty').value),m=Number($('move-qty').max);remain.textContent='Останется: '+Math.max(0,m-(Number.isFinite(q)?q:0))+' '+(currentItem?.unit||'шт.');$('move-confirm-btn').disabled=!Number.isInteger(q)||q<1||q>m}
  function setSource(id){const s=currentItem.stocks.find(x=>x.location_id===Number(id));if(!s)return;moveFromLocId=s.location_id;selectedMoveRoomId=null;$('move-step-2').classList.add('hidden');$('move-item-from').textContent='Откуда: '+s.location_name;$('move-qty').max=String(s.quantity);$('move-qty').value=currentItem.kind==='consumable'?String(s.quantity):'1';$('move-rooms-list').replaceChildren(...locations.filter(l=>l.id!==moveFromLocId).map(l=>button(l.name,()=>selectMoveRoom(l.id,l.name),'secondary')));updateRemain()}
  source.onchange=()=>setSource(source.value);$('move-qty').oninput=updateRemain;showMoveItemScreen=()=>{oldMove();source.replaceChildren(...currentItem.stocks.filter(s=>s.quantity>0).map(s=>new Option(s.location_name+' · '+s.quantity,s.location_id)));source.classList.toggle('hidden',source.options.length<=1);allQty.classList.toggle('hidden',currentItem.kind!=='consumable');if(source.value)setSource(source.value)};
  const oldExecute=executeMoveItem;let moving=false;executeMoveItem=async()=>{const n=Number($('move-qty').value);if(moving||!Number.isInteger(n)||n<=0||n>Number($('move-qty').max))return notify('Некорректное количество');moving=true;try{await oldExecute()}finally{moving=false}};
  // Real permissions follow the selected role. Account role stays unchanged.
  const setting=$('screen-settings').querySelector('.v18-settings-layout');
  const roleNames1854={admin:'Администратор',boss:'Босс',employee:'Сотрудник'};
  let switching1854=false;
  async function changePreview1854(role){
    if(!currentUser?.can_preview||switching1854)return;
    switching1854=true;
    try{
      await api('/api/v184/preview/role',{method:'POST',body:JSON.stringify({role})});
      clearInterval(autoRefreshInterval);location.reload();
    }catch(e){switching1854=false;throw e}
  }
  function choosePreview1854(){
    if(!currentUser?.can_preview)return;
    const {o,b}=overlay17('Тестирование интерфейса');
    const note=el('p','meta','Действия реальные и сохраняются в рабочей базе. Ваша роль в аккаунте не меняется.');
    b.append(note);
    for(const role of ['admin','boss','employee']){
      const label=roleNames1854[role]+(currentUser.role===role?' · Сейчас':'');
      const btn=btn17(b,label,()=>changePreview1854(role),currentUser.role===role?'secondary':'primary');
      if(currentUser.role===role)btn.disabled=true;
    }
  }
  const preview=button('Тестирование интерфейса',choosePreview1854,'secondary r184-admin-dot hidden');
  setting.prepend(preview);
  const previewBanner=el('div','r184-preview hidden'),previewLabel=el('b');
  const switchRole=button('Сменить',choosePreview1854);
  const stop=button('Выйти',()=>changePreview1854('admin'));
  previewBanner.append(previewLabel,switchRole,stop);document.body.prepend(previewBanner);
  function renderPreview(){
    preview.classList.toggle('hidden',!currentUser?.can_preview);
    const active=!!currentUser?.can_preview&&['employee','boss'].includes(currentUser.preview_role);
    previewBanner.classList.toggle('hidden',!active);
    document.body.classList.toggle('r184-preview-active',active);
    previewLabel.textContent=active?'Тест: '+roleNames1854[currentUser.preview_role]:'';
  }
  // Boss view, with explicit stock-room interpretation and separate holder detail.
  const bossBox=el('section','r184-boss hidden');main.querySelector('.v18-quick').before(bossBox);let bossJob=null;
  function bossPanel(title,key,data){const p=el('div','card r184-boss-panel '+key),heading=el('h3','',title),grid=el('div','r184-boss-grid');p.append(heading,grid);for(const [k,t]of [['cameras','Фотоаппараты'],['flashes','Вспышки']]){const metric=el('div');metric.append(el('span','meta',t),el('strong','',String(data[k]||0)));grid.append(metric)}return p}
function bossBrand1853(value,kind){
  const s=String(value||'').normalize('NFKC').toLowerCase().replace(/[‐‑–—]/g,'-');
  const canon=/(?:^|[^\p{L}\p{N}])(?:canon|к[еэ]нон|канон)(?=$|[^\p{L}\p{N}])/u.test(s);
  const sony=/(?:^|[^\p{L}\p{N}])(?:sony|сони)(?=$|[^\p{L}\p{N}])/u.test(s);
  if(canon||sony)return canon===sony?'?':canon?'К':'С';
  if(kind==='camera'){
    const c=/(?:^|[^\p{L}\p{N}])(?:eos|r[35678](?:\s*(?:mark\s*)?(?:ii|iii))?|rp|r10|r50|r100|[56]d(?:\s*mark\s*(?:ii|iii|iv))?)(?=$|[^\p{L}\p{N}])/u.test(s);
    const a=/(?:^|[^\p{L}\p{N}])(?:[aαа]\s*(?:[179](?:r|s|c)?|6[0134567]00)(?:\s*(?:ii|iii|iv|v|[2345]|m[2345]))?)(?=$|[^\p{L}\p{N}])/u.test(s);
    if(c!==a)return c?'К':'С';
  }else{
    const matches=[...s.matchAll(/(?:^|[^a-z0-9])(?:v1(?:pro)?|v860(?:iii|ii)?|tt685(?:ii)?|tt350|v350|tt600)[\s_-]*([cs])(?=$|[^a-z0-9])/g)].map(m=>m[1]);
    if(matches.length&&new Set(matches).size===1)return matches[0]==='c'?'К':'С';
    if(/(?:^|[^a-z0-9])hvl[-\s]*f\d+/i.test(s))return 'С';
  }
  return '?';
}
function bossCounts1853(items,kind){
  const counts={'К':0,'С':0,'?':0};
  for(const i of items||[]){
    const q=Number(i[kind+'_count'])||0;
    if(q<=0)continue;
    const v=String(i[kind]||'').trim();
    const model=['','-','—','нет','none','0','n/a','без','не указан'].includes(v.toLowerCase())?i.name:v;
    counts[bossBrand1853(model,kind)]+=q;
  }
  return counts;
}
function bossCode1853(kind,brand,count,mode){
  if(!count)return '';
  const letter=mode==='icons'?(brand==='К'?'C':brand==='С'?'S':'?'):(kind==='camera'?'Ф':'В')+brand;
  return letter+(count>1?'×'+count:'');
}
function bossSurname1853(name){
  return String(name||'Не указан').trim().split(/\s+/)[0]||'Не указан';
}

  // Keep all three approved representations. Default: combined.
  const bossMode1853='combined'; // 'icons' | 'letters' | 'combined'
  const bossIcons1853={camera:'<rect x="3" y="6" width="18" height="15" rx="3"/><path d="M8 6l2-3h4l2 3"/><circle cx="12" cy="13" r="3.5"/>',flash:'<path d="m13 2-9 12h7l-1 8 10-12h-7z"/>',arrow:'<path d="m9 5 7 7-7 7"/>'};
  function bossIcon1853(type){const n=document.createElementNS('http://www.w3.org/2000/svg','svg');n.setAttribute('viewBox','0 0 24 24');n.setAttribute('aria-hidden','true');n.setAttribute('class','r1853-icon');n.innerHTML=bossIcons1853[type];return n}
  function bossCell1853(p,kind){
    const n=el('span','r1853-cell '+kind),counts=bossCounts1853(p.items,kind),labels=el('span','r1853-labels'),total=Object.values(counts).reduce((a,b)=>a+b,0);
    const type=kind==='camera'?'Фотоаппараты':'Вспышки';
    if(!total){n.append(el('span','r1853-empty','—'));n.setAttribute('aria-label',type+': нет');return n}
    if(bossMode1853!=='letters')n.append(bossIcon1853(kind));
    const full=[];
    for(const brand of ['К','С','?']){const q=counts[brand];if(!q)continue;labels.append(el('span','',bossCode1853(kind,brand,q,bossMode1853)));full.push((brand==='К'?'Canon':brand==='С'?'Sony':'бренд не указан')+' '+q)}
    n.append(labels);n.title=type+': '+full.join(', ');n.setAttribute('aria-label',n.title);return n
  }
  function bossTotal1853(kind,n){
    const cell=el('span','r1853-total '+kind);cell.append(bossIcon1853(kind),el('strong','',String(n||0)));cell.title=(kind==='camera'?'Фотоаппараты':'Вспышки')+': '+(n||0);cell.setAttribute('aria-label',cell.title);return cell
  }
  function bossPerson1853(p,key,expanded,duplicates){
    const d=el('details','r1853-person');d.dataset.personKey=key;d.open=expanded;
    const head=el('summary','r1853-person-line'),surname=bossSurname1853(p.name);
    const name=el('span','r1853-name',duplicates.has(surname)?p.name:surname);name.title=p.name;
    const buyout=(p.items||[]).filter(i=>String(i.buyout_status||'').trim());
    const flag=el('span','r1853-buyout',buyout.length?'Выкуп':'');if(buyout.length)flag.title='На выкупе: '+buyout.length;
    const arrow=el('span','r1853-arrow');arrow.append(bossIcon1853('arrow'));
    head.append(name,bossCell1853(p,'camera'),bossCell1853(p,'flash'),flag,arrow);d.append(head);
    const content=el('div','r1853-person-details');content.append(el('div','r1853-full-name',p.name));
    for(const i of p.items||[]){
      const item=el('div','r1853-detail-item'),link=button(i.name+' · '+i.code,()=>openItem(i.code),'secondary r1853-item-link');item.append(link);
      for(const [label,k] of [['Фотоаппарат','camera'],['Объектив','lens'],['Вспышка','flash'],['На выкупе у','buyout_status']]){const v=String(i[k]||'').trim();if(v&&!['-','—','нет','none','0','n/a','без','не указан'].includes(v.toLowerCase()))item.append(el('div','meta',label+': '+v))}
      if(i.taken_at){const raw=String(i.taken_at),match=raw.match(/^(\d{4})-(\d{2})-(\d{2})/);item.append(el('div','meta','Выдано: '+(match?[match[3],match[2],match[1]].join('.'):raw)))}
      content.append(item)
    }
    d.append(content);return d
  }
  async function refreshBoss(){
    if(currentUser?.role!=='boss')return;if(bossJob)return bossJob;
    bossJob=api('/api/v184/boss').then(r=>{
      if(currentUser?.role!=='boss')return;
      const expanded=new Set([...bossBox.querySelectorAll('.r1853-person[open]')].map(d=>d.dataset.personKey));
      const office=bossPanel('В офисе','office',r.office);office.append(el('small','meta','Все помещения склада'));
      const held=el('div','card r184-boss-panel held r1853-held'),header=el('div','r1853-held-head');
      header.append(el('h3','','На руках'),bossTotal1853('camera',r.held.cameras),bossTotal1853('flash',r.held.flashes));held.append(header);
      const list=el('div','r1853-people'),seen=new Set(),duplicates=new Set();
      for(const p of r.people){const s=bossSurname1853(p.name);if(seen.has(s))duplicates.add(s);seen.add(s)}
      let unknown=false;
      for(const p of r.people){const key=JSON.stringify([p.person_id??null,p.name]);list.append(bossPerson1853(p,key,expanded.has(key),duplicates));unknown=unknown||!!(bossCounts1853(p.items,'camera')['?']+bossCounts1853(p.items,'flash')['?'])}
      if(!r.people.length)list.append(el('p','meta r1853-no-people','Нет выданной техники'));
      held.append(list);if(unknown)held.append(el('div','r1853-legend','? — бренд не определён'));
      const showFinance=button('Финансы',()=>showExtra('finance'),'secondary');
      bossBox.replaceChildren(el('h2','','Сводка по технике'),office,held,showFinance);bossBox.classList.remove('hidden');
    }).catch(e=>{if(!bossBox.children.length)bossBox.append(el('p','meta','Сводка временно недоступна'));bossBox.classList.remove('hidden')}).finally(()=>bossJob=null);
    return bossJob
  }
  const oldLoad=loadItems;loadItems=async()=>{await oldLoad();refreshBoss()};
  const oldShowRooms=showRooms;showRooms=async()=>{await oldShowRooms();for(const r of $('rooms-list').querySelectorAll('.room-card')){const title=r.querySelector('.room-title')?.textContent,loc=locations.find(l=>l.name===title);if(!loc)continue;const rows=allItems.flatMap(i=>i.stocks.filter(s=>s.location_id===loc.id).map(s=>({kind:i.kind,qty:s.quantity})));const equipment=rows.filter(i=>i.kind==='equipment').reduce((n,i)=>n+i.qty,0),cons=rows.filter(i=>i.kind==='consumable').reduce((n,i)=>n+i.qty,0);const b=r.querySelector('.room-count-badge');if(b)b.replaceChildren(el('div','','Оборудование: '+equipment),el('div','','Расходники: '+cons+' шт.'))}};
  const mark=()=>{if(!admin())return;for(const q of ['#screen-settings .v18-settings-layout button','#screen-users #users-list button','#nav-settings','#nav-rooms','.v18-admin','#edit-btn','#delete-item-btn','#export-history-btn','#add-item-btn','#actions button[onclick*="replenish"]','#screen-item .owner-only'])document.querySelectorAll(q).forEach(e=>e.classList.add('r184-admin-dot'))};const oldScreen=showScreen;showScreen=id=>{oldScreen(id);mark()};
  const oldInit=init;init=async()=>{await oldInit();if(!currentUser?.is_registered)return;document.body.classList.toggle('r184-admin',admin());document.body.classList.toggle('r184-finance',finance());document.body.classList.toggle('r184-boss-role',currentUser.role==='boss');if(currentUser.role==='boss')$('user-info').append(el('span','r184-role','Босс'));if(!admin())$('export-history-btn').classList.add('hidden');renderPreview();mark();filterItems();refreshBoss()};
}
