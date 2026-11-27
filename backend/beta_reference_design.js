/* Beta design implementation based on the approved three-screen reference.
   No API mutations. Old screens, filters, room tools and access rules are preserved. */
function installBetaReferenceDesign(){
  'use strict';
  const byId=id=>document.getElementById(id);
  const make=(tag,cls,text)=>{
    const node=document.createElement(tag);
    if(cls)node.className=cls;
    if(text!==undefined)node.textContent=String(text);
    return node;
  };
  const svg=path=>{
    const node=make('span','r191-line-icon');
    node.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.85" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+path+'</svg>';
    return node;
  };
  const pict={
    camera:'<rect x="2.5" y="6" width="19" height="15" rx="2.5"/><path d="m7 6 2-3h6l2 3"/><circle cx="12" cy="13.5" r="4"/>',
    lens:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 3l3 5M21 12l-6 3M12 21l-3-6M3 12l6-3"/>',
    flash:'<path d="m13 2-8 12h6l-1 8 9-12h-6l1-8z"/>',
    accessory:'<path d="m12 3 9 5-9 5-9-5zM3 12l9 5 9-5M3 16l9 5 9-5"/>',
    consumable:'<path d="m3 8 9-5 9 5v12H3zM3 8l9 5 9-5M12 13v7"/>',
    laptop:'<rect x="4" y="4" width="16" height="12" rx="2"/><path d="M3 19h18"/>',
    printer:'<path d="M6 8V3h12v5M6 17H3V9h18v8h-3M6 14h12v7H6z"/>',
    search:'<circle cx="10.8" cy="10.8" r="6.7"/><path d="m16 16 5 5"/>',
    chevron:'<path d="m9 6 6 6-6 6"/>',
    filter:'<path d="M4 7h16M7 12h10M10 17h4"/><circle cx="9" cy="7" r="2"/><circle cx="15" cy="12" r="2"/>',
    return:'<path d="M5 12h12m-6-6-6 6 6 6"/><path d="M20 6v12"/>',
    checkout:'<path d="M5 19 19 5M9 5h10v10"/>',
    repair:'<path d="m14 6 4 4 3-3a6 6 0 0 1-8 8l-7 7-4-4 7-7a6 6 0 0 1 8-8z"/>',
    history:'<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',
    hand:'<path d="M8 12V5a2 2 0 0 1 4 0v5-6a2 2 0 0 1 4 0v8-5a2 2 0 0 1 4 0v7c0 4-2 7-7 7h-2c-3 0-6-2-7-5L2 11a2 2 0 0 1 4-1l2 2"/>',
    price:'<path d="M3 11V4h7l11 11-7 7L3 11Z"/><circle cx="7" cy="8" r="1"/>',
    wallet:'<rect x="3" y="5" width="18" height="15" rx="2"/><path d="M3 9h18"/><path d="M16 14h2"/>'
  };
  // HOME. Put existing controls into the same visual order as the approved design.
  const home=byId('screen-main');
  const activity=byId('main-activity');
  if(home&&activity){
    home.classList.add('r191-reference-home');
    const title=activity.querySelector('.beta-activity-title');
    if(title)title.setAttribute('aria-hidden','true');
    const quick=home.querySelector('.v18-quick');
    if(quick){
      const take=quick.querySelector('.take-btn'),scan=quick.querySelector('.qr-btn-main');
      if(take)take.classList.add('r191-take-action');
      if(scan)scan.classList.add('r191-scan-action');
    }
    const historyButton=byId('main-history-btn');
    if(historyButton){
      historyButton.classList.add('r191-history-shortcut');
      historyButton.setAttribute('aria-label','Открыть историю действий');
    }
    const mySection=byId('my-items-section');
    if(mySection){
      const details=make('details','r191-my-items-drawer');
      details.append(make('summary','','Моя выданная техника'),mySection);
      activity.append(details);
      const update=()=>details.classList.toggle('hidden',mySection.classList.contains('hidden'));
      update();
      new MutationObserver(update).observe(mySection,{attributes:true,attributeFilter:['class']});
    }
    const actions=make('div','r191-home-actions');
    actions.id='r191-home-actions';
    activity.after(actions);
    for(const id of ['held-list1857','buyout-list1856','boss-equipment-costs1859']){
      const element=byId(id);
      if(element)actions.append(element);
    }
    const icons={held:'hand',buyout:'checkout',prices:'price'};
    for(const [id,k] of [['held-list1857','held'],['buyout-list1856','buyout'],['boss-equipment-costs1859','prices']]){
      const panel=byId(id),summary=panel?.querySelector(':scope > summary');
      if(summary&&!summary.querySelector('.r191-line-icon'))summary.prepend(svg(pict[icons[k]]));
    }
  }

  // STOCK. Actual product catalogue becomes the first view; rooms remain accessible.
  const stock=byId('screen-rooms');
  if(stock&&!byId('r191-stock-catalog')){
    stock.classList.add('r191-reference-stock');
    const header=stock.querySelector('.sticky-header');
    const right=header?.querySelector('.v18-header-right');
    const add=byId('add-item-btn');
    if(add&&right){
      add.classList.add('r191-add-button');
      right.prepend(add);
    }
    const search=make('label','r191-stock-search');
    search.append(svg(pict.search));
    const searchInput=make('input');
    searchInput.type='search';
    searchInput.placeholder='Поиск по складу';
    searchInput.autocomplete='off';
    searchInput.setAttribute('aria-label','Поиск по складу');
    search.append(searchInput);
    const categories=make('div','r191-stock-categories');
    categories.setAttribute('role','group');
    categories.setAttribute('aria-label','Категории склада');
    const options=[
      ['camera','Камеры'],['lens','Объективы'],['flash','Вспышки'],
      ['accessory','Аксессуары'],['consumable','Расходники'],
      ['laptop','Ноутбуки'],['printer','Принтеры']
    ];
    const buttons=new Map();
    let activeCategory='camera',activeStatus='all',sortMode='status';
    const counters=make('div','r191-stock-counters');
    counters.setAttribute('role','group');
    counters.setAttribute('aria-label','Состояние оборудования');
    const counterButtons=new Map();
    for(const [key,label] of [['all','Все'],['free','Свободно'],['held','На руках']]){
      const button=make('button','r191-count');
      button.type='button';
      const name=make('span','',label),num=make('strong','r191-count-value','0');
      button.append(name,num);
      button.onclick=()=>{activeStatus=key;renderStock()};
      counters.append(button);counterButtons.set(key,{button,num});
    }
    const toolbar=make('div','r191-stock-toolbar');
    const sort=make('select','r191-stock-sort');
    sort.setAttribute('aria-label','Сортировка оборудования');
    for(const [value,label] of [['status','По статусу'],['name','По названию А–Я'],['reverse','По названию Я–А']]){
      sort.append(new Option(label,value));
    }
    sort.onchange=()=>{sortMode=sort.value;renderStock()};
    const filterButton=make('button','r191-stock-filter');
    filterButton.type='button';filterButton.append(svg(pict.filter),make('span','','Фильтры'));
    filterButton.setAttribute('aria-expanded','false');
    const filterBox=make('div','r191-stock-filter-box hidden');
    const repairOnly=make('input');
    repairOnly.type='checkbox';
    const filterLabel=make('label');
    filterLabel.append(repairOnly,make('span','','Только требующие ремонта'));
    repairOnly.onchange=renderStock;
    const clear=make('button','r191-clear-filters','Сбросить фильтры');
    clear.type='button';clear.onclick=()=>{
      activeCategory='camera';activeStatus='all';sortMode='status';
      searchInput.value='';repairOnly.checked=false;sort.value='status';renderStock();
    };
    filterBox.append(filterLabel,clear);
    filterButton.onclick=()=>{
      const open=filterBox.classList.toggle('hidden')===false;
      filterButton.setAttribute('aria-expanded',String(open));
    };
    toolbar.append(sort,filterButton);
    const rows=make('div','r191-stock-rows');
    rows.setAttribute('aria-live','polite');
    const rooms=make('details','r191-stock-rooms');
    const roomSummary=make('summary');
    roomSummary.append(svg(pict.consumable),make('span','','Помещения и учёт'),svg(pict.chevron));
    rooms.append(roomSummary);
    const actions=stock.querySelector('.warehouse-room-actions');
    const low=byId('low-stock-banner');
    const roomTitle=stock.querySelector('.r1851-rooms-label');
    const roomList=byId('rooms-list');
    for(const element of [actions,low,roomTitle,roomList])if(element)rooms.append(element);
    const root=make('section','r191-stock-main');
    root.id='r191-stock-catalog';
    const sections=make('div','r191-stock-sections');
    sections.classList.add('r192-room-grid');
    const catalog=make('div','hidden');
    catalog.append(search,categories,counters,toolbar,filterBox,rows);
    rooms.open=true;
    rooms.style.display='';
    const sectionDefs=[['Склад 11','warehouse'],['Офис 7','office'],['Техника','camera'],['Рамки','frame'],['Винил','vinyl'],['Фотобумага','paper']];
    const oldRoomIcon={warehouse:'consumable',office:'accessory',camera:'camera',frame:'accessory',vinyl:'consumable',paper:'printer'};
    for(const [name,kind] of sectionDefs){
      const button=make('button','r191-category');
      button.type='button';button.classList.add('r192-room-tile');button.dataset.roomKind=kind;
      button.append(make('span','r192-room-title',name));
      const art=make('span','r192-room-art');art.setAttribute('aria-hidden','true');
      art.append(svg(pict[oldRoomIcon[kind]]));
      button.append(art);
      button.onclick=async()=>{
        if(currentUser?.role!=='admin')return;
        const special={'Рамки':'frame-stock-button','Винил':'material-vinyl','Фотобумага':'material-paper46'}[name];
        if(special){const target=byId(special);if(target)target.click();else showToast('Раздел ещё загружается');return;}
        try{
          const locations=await api('/api/locations_view');
          const norm=v=>String(v).toLowerCase().replace(/[^а-яё0-9]/g,'');
          const room=locations.find(r=>norm(r.name)===norm(name));
          if(!room){showToast('Помещение не найдено');return;}
          openRoom(room.id,room.name);
        }catch(e){showToast(e.message)}
      };
      sections.append(button);
    }
    if(add){root.append(add);add.classList.add('r192-stock-add');}
    root.append(sections,rooms,catalog);
    header.after(root);
    for(const [key,label]of options){
      const button=make('button','r191-category');
      button.type='button';button.append(svg(pict[key]),make('span','',label));
      button.setAttribute('aria-label',label);
      button.onclick=()=>{
        activeCategory=key;activeStatus='all';repairOnly.checked=false;
        searchInput.value='';renderStock();
      };
      categories.append(button);
      buttons.set(key,button);
    }
    const groupFor=item=>{
      const name=String(item?.name||'').toLowerCase();
      const category=String(item?.category||'').toLowerCase();
      const all=category+' '+name;
      const value=window.warehouseCatalogView?.groupFor?.(item);
      if(value)return value;
      if(item?.kind==='consumable')return 'consumable';
      if(/объектив|линз|lens|оптик/.test(all))return 'lens';
      if(/вспыш|flash|godox|speedlite/.test(all))return 'flash';
      if(/ноутбук|macbook|laptop/.test(all))return 'laptop';
      if(/принтер|dnp|printer|epson/.test(all))return 'printer';
      if(/аксессуар|аккумулятор|заряд|сумк|карт|кабел|ремень|штатив/.test(all))return 'accessory';
      return 'accessory';
    };
    const free=item=>!item.needs_repair&&!(item.holders||[]).length&&Number(item.total||0)>0;
    const held=item=>(item.holders||[]).length>0;
    function renderStock(){
      if(!stock.classList.contains('hidden')&&currentUser?.role!=='admin')return;
      let items=Array.isArray(allItems)?allItems.filter(item=>!item.is_archived):[];
      const term=searchInput.value.trim().toLocaleLowerCase('ru-RU');
      items=items.filter(item=>groupFor(item)===activeCategory);
      if(term)items=items.filter(item=>[item.name,item.code,item.kit_body,item.kit_lens,item.kit_flash,item.category].join(' ').toLocaleLowerCase('ru-RU').includes(term));
      if(repairOnly.checked)items=items.filter(item=>item.needs_repair);
      const total=items.length,stockCount=items.filter(free).length,heldCount=items.filter(held).length;
      for(const [key,value] of [['all',total],['free',stockCount],['held',heldCount]]){
        const control=counterButtons.get(key);
        control.num.textContent=String(value);
        control.button.classList.toggle('active',key===activeStatus);
        control.button.setAttribute('aria-pressed',String(key===activeStatus));
      }
      for(const [key,button]of buttons){
        button.classList.toggle('active',key===activeCategory);
        button.setAttribute('aria-pressed',String(key===activeCategory));
      }
      if(activeStatus==='free')items=items.filter(free);
      if(activeStatus==='held')items=items.filter(held);
      const sorter=(a,b)=>a.name.localeCompare(b.name,'ru');
      items.sort((a,b)=>sortMode==='name'?sorter(a,b):sortMode==='reverse'?-sorter(a,b):
        Number(!free(a))-Number(!free(b))||sorter(a,b));
      const fragment=document.createDocumentFragment();
      const makeCard=window.warehouseCompactItemCard;
      if(typeof makeCard==='function'){
        for(const item of items){
          const card=makeCard(item);
          card.classList.add('r191-stock-item');
          const arrow=make('span','r191-stock-arrow','›');
          arrow.setAttribute('aria-hidden','true');
          card.append(arrow);
          fragment.append(card);
        }
      }
      if(!fragment.childNodes.length)fragment.append(make('p','r191-stock-empty',
        total===0?'Нет товаров в категории':'По выбранным фильтрам ничего не найдено'));
      rows.replaceChildren(fragment);
      // Load real photos lazily; the catalogue placeholder remains visible until loaded.
      rows.querySelectorAll('img[data-code]').forEach(img=>{
        if(!img.getAttribute('src')){
          const code=img.dataset.code;
          if(code&&typeof IntersectionObserver==='undefined'){
            img.loading='lazy';
          }
        }
      });
    }
    searchInput.oninput=renderStock;
    const previousShowRooms=showRooms;
    showRooms=async function(){
      if(currentUser?.role!=='admin')return;
      renderStock();
      return previousShowRooms.apply(this,arguments);
    };
    const previousLoad=loadItems;
    loadItems=async function(){
      const result=await previousLoad.apply(this,arguments);
      if(currentScreen==='screen-rooms')renderStock();
      return result;
    };
    document.addEventListener('warehouse-photo-changed',()=>{
      if(currentScreen==='screen-rooms')renderStock();
    });
    window.betaReferenceStockRefresh=renderStock;
  }
  // HISTORY. Date-grouped timeline and four primary filter tabs (like the mock).
  const history=byId('screen-history');
  if(history&&!byId('r191-history-chips')){
    history.classList.add('r191-reference-history');
    const header=history.querySelector('.sticky-title');
    if(header)header.textContent='История';
    const wrap=history.querySelector(':scope > div:not(.sticky-header)');
    const oldFilters=wrap?.querySelector('.filters');
    const query=byId('history-query'),date=byId('history-date'),type=byId('history-type182'),list=byId('history-list');
    if(oldFilters&&query&&date&&type&&list){
      const search=make('label','r191-history-search');
      search.append(svg(pict.search),query);
      query.placeholder='Поиск по истории';
      query.setAttribute('aria-label','Поиск по истории');
      oldFilters.before(search);
      const chips=make('div','r191-history-chips');
      chips.id='r191-history-chips';
      chips.setAttribute('role','group');
      chips.setAttribute('aria-label','Тип событий');
      const filterTypes=[['','Все'],['checkout','Выдача'],['return','Возврат'],['repair','Ремонт']];
      const chipControls=new Map();
      for(const [value,label]of filterTypes){
        const button=make('button','r191-history-chip');
        button.type='button';
        if(value==='return')button.append(svg(pict.return));
        else if(value==='checkout')button.append(svg(pict.checkout));
        else if(value==='repair')button.append(svg(pict.repair));
        else button.append(svg(pict.history));
        button.append(make('span','',label));
        button.onclick=()=>{type.value=value;renderHistory17()};
        chips.append(button);
        chipControls.set(value,button);
      }
      oldFilters.before(chips);
      const advanced=make('details','r191-history-extra');
      const more=make('summary','','Дата и другие действия');
      advanced.append(more,oldFilters);
      chips.after(advanced);
      type.setAttribute('aria-label','Все типы событий');
      date.setAttribute('aria-label','Дата события');
      const exportButton=byId('export-history-btn');
      if(exportButton)advanced.append(exportButton);
      const oldRender=renderHistory17;
      const dateLabel=key=>{
        const parsed=/^\d{4}-\d{2}-\d{2}$/.test(key)?new Date(key+'T12:00:00'):null;
        if(!parsed||Number.isNaN(parsed.valueOf()))return key||'Дата не указана';
        const today=new Date(),startToday=new Date(today.getFullYear(),today.getMonth(),today.getDate());
        const when=new Date(parsed.getFullYear(),parsed.getMonth(),parsed.getDate());
        const diff=Math.round((startToday-when)/86400000);
        const human=parsed.toLocaleDateString('ru-RU',{day:'numeric',month:'long'});
        return (diff===0?'Сегодня, ':diff===1?'Вчера, ':'')+human;
      };
      renderHistory17=function(){
        const text=query.value.trim().toLocaleLowerCase('ru-RU');
        const day=date.value;
        const action=type.value;
        for(const [key,button]of chipControls){
          button.classList.toggle('active',key===action);
          button.setAttribute('aria-pressed',String(key===action));
        }
        const logs=(Array.isArray(history17)?history17:[]).filter(log=>
          (!action||(action==='repair'?/^repair/i.test(String(log.type||'')):log.type===action))
          &&(!day||String(log.date||'').startsWith(day))
          &&(!text||[log.name,log.item_code,log.user_name,log.taken_for]
            .join(' ').toLocaleLowerCase('ru-RU').includes(text)));
        list.replaceChildren();
        list.classList.remove('beta-history-feed');
        list.classList.add('r191-history-feed');
        if(!logs.length){
          list.append(make('p','r191-history-empty','Нет записей по выбранным условиям'));
          return;
        }
        const buckets=new Map();
        for(const log of logs){
          const key=String(log.date||'').slice(0,10);
          if(!buckets.has(key))buckets.set(key,[]);
          buckets.get(key).push(log);
        }
        for(const [dateKey,records]of buckets){
          const group=make('section','r191-history-day');
          group.append(make('h2','r191-day-title',dateLabel(dateKey)));
          const entries=make('div','r191-day-entries');
          for(const log of records){
            const kind=String(log.type||'');
            const isReturn=kind==='return';
            const isRepair=/repair/.test(kind);
            const isCheckout=kind==='checkout';
            const label=isReturn?'Возврат техники':isRepair?'Отправка в ремонт':
              isCheckout?'Выдача техники':kind==='writeoff'?'Списание':
              kind==='move'?'Перемещение':kind||'Действие';
            const entry=make('article','r191-history-entry');
            const glyph=make('span','r191-history-glyph '+(isReturn?'is-return':isRepair?'is-repair':isCheckout?'is-checkout':'is-other'));
            glyph.append(svg(isReturn?pict.return:isRepair?pict.repair:isCheckout?pict.checkout:pict.history));
            const info=make('div','r191-history-copy');
            const row=make('div','r191-history-heading');
            row.append(make('strong','',label));
            const rawTime=String(log.date||'');
            row.append(make('time','',rawTime.includes(' ')?rawTime.split(' ')[1].slice(0,5):
              rawTime.includes('T')?rawTime.split('T')[1].slice(0,5):''));
            const item=[log.name||log.item_code||'Товар',log.name&&log.item_code?'('+log.item_code+')':''].filter(Boolean).join(' ');
            info.append(row,make('div','r191-history-item',item));
            const actor=log.taken_for?'Кому: '+log.taken_for:String(log.user_name||'');
            if(actor)info.append(make('div','r191-history-person',actor));
            entry.append(glyph,info);
            const known=(Array.isArray(allItems)?allItems:[]).some(i=>i.code===log.item_code);
            if(known){
              entry.classList.add('r191-history-clickable');
              entry.setAttribute('role','button');entry.tabIndex=0;
              entry.onclick=()=>openItem(log.item_code);
              entry.onkeydown=event=>{
                if(event.key==='Enter'||event.key===' '){event.preventDefault();entry.click()}
              };
            }
            entries.append(entry);
          }
          group.append(entries);
          list.append(group);
        }
      };
      // Existing filters and history source are intact; the new renderer handles them.
      if(type.value)renderHistory17();
      window.betaReferenceHistoryReset=()=>{type.value='';date.value='';query.value='';renderHistory17()};
    }
  }
}
