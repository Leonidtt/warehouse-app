/* v18.2: presentation layer. Existing operations and permissions remain server-side. */
const money182 = n => new Intl.NumberFormat('ru-RU', {maximumFractionDigits:2}).format(Number(n)||0)+' ₽';
async function sendOwnerBackup182(){
  if(!currentUser?.is_owner)throw Error('Доступ только владельцу');
  if(!confirm('Создать резервную копию базы?'))return;
  if(tg.initData){await api('/api/owner/backup',{method:'POST'},0);showToast('Копия отправлена в личный чат с ботом')}
  else await downloadFile('/api/backup','warehouse_backup.db');
}
function installRelease182(){
  const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=String(text);return e};
  const button=(text,fn,cls='secondary')=>{const e=el('button',cls,text);e.type='button';e.onclick=fn;return e};
  const icons={pin:'<path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',music:'<path d="M9 18V5l12-2v13M9 9l12-2"/><ellipse cx="6" cy="18" rx="3" ry="3"/><ellipse cx="18" cy="16" rx="3" ry="3"/>',ship:'<path d="M3 13 12 9l9 4-3 6H6zM7 11V5h10v6M12 5V2M2 22q2-3 5 0 3-3 5 0 3-3 5 0 3-3 5 0"/>',check:'<path d="m5 12 4 4L19 6"/>',alert:'<circle cx="12" cy="12" r="9"/><path d="M12 7v6m0 3h.01"/>',box:'<path d="m3 7 9-4 9 4v13H3zM3 7l9 5 9-5M12 12v8"/>',camera:'<rect x="2" y="6" width="20" height="15" rx="3"/><path d="M7 6l2-3h6l2 3"/><circle cx="12" cy="13" r="4"/>',right:'<path d="m9 18 6-6-6-6"/>',refresh:'<path d="M20 10a8 8 0 1 0-2 8m2-14v6h-6"/>',user:'<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>'};
  const icon=k=>{const e=el('span','r182-icon');e.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+(icons[k]||icons.box)+'</svg>';return e};
  document.querySelectorAll('.search-icon').forEach(e=>e.replaceChildren(icon('search')));
  const main=$('screen-main'),quick=main.querySelector('.v18-quick'),overview=main.querySelector('.v18-overview');
  quick.prepend(quick.querySelector('.take-btn'));quick.before($('dashboard-v17'));quick.querySelector('.qr-btn-main').lastChild.textContent=' Сканировать QR';overview.prepend($('low-stock-banner'));
  overview.querySelector('.v18-overview-details')?.remove();
  const addNoCategory=()=>{if(![...$('filter-category').options].some(o=>o.value==='__without_category__'))$('filter-category').add(new Option('Без категории','__without_category__'))};const oldCategories=loadCategories17;loadCategories17=async()=>{await oldCategories();addNoCategory()};addNoCategory();
  const filter=$('filter-status');filter.add(new Option('На складе','stock182'));filter.add(new Option('В работе','work182'));
  const prevMatches=matchesStatus17;matchesStatus17=(i,s)=>s==='stock182'?i.kind==='equipment'&&!i.needs_repair&&i.total>0:s==='work182'?i.kind==='equipment'&&!i.needs_repair&&i.holders.length>0:prevMatches(i,s);
  function filterTo(status='',category='',equipment=true){
    $('filter-status').value=status;$('filter-kind').value=equipment?'equipment':'';$('filter-category').value=category==='Без категории'?'__without_category__':category;$('filter-location').value='';$('search-input').value='';filterItems();
    $('items-list').scrollIntoView({block:'start',behavior:'smooth'});
  }
  const historyType=el('select');historyType.id='history-type182';[['','Все действия'],['checkout','Выдача'],['return','Возврат'],['writeoff','Списание'],['move','Перемещение']].forEach(([v,t])=>historyType.add(new Option(t,v)));$('history-date').after(historyType);historyType.onchange=()=>renderHistory17();
  async function openDailyHistory(date,key){$('history-query').value='';$('history-date').value=date;historyType.value={taken:'checkout',returned:'return',written_off:'writeoff'}[key]||'';await showHistory()}
  const dashboard=$('dashboard-v17'),daily=$('daily-report-box'),low=$('low-stock-banner');
  const countNum=v=>new Intl.NumberFormat('ru-RU').format(Number(v)||0);
  function renderOverview(data){
    const {counts:c,categories,booked,daily:d,low:short}=data;booked17=new Set(booked);
    const expanded=dashboard.querySelector('details')?.open??false;
    dashboard.className='r182-overview card';
    dashboard.replaceChildren();
    const summary=el('div','r182-summary');
    const left=el('div','r182-summary-main');
    const right=el('div','r182-summary-cats');
    dashboard.append(summary);
    summary.append(left,right);

    const hasRepairs=Number(c.repair)>0;
    const states=[['stock','На складе','stock182'],['working','В работе','work182']];
    if(hasRepairs)states.push(['repair','В ремонте','repair']);
    dashboard.classList.toggle('r182-no-repair',!hasRepairs);

    const total=button('',()=>filterTo(),'r182-total');
    const totalCopy=el('span','r182-total-copy');
    totalCopy.append(el('span','r182-muted','Всего фототехники'),el('strong','',countNum(c.total)));
    const ring=el('span','r182-ring');
    ring.setAttribute('aria-hidden','true');
    ring.append(el('span','r182-overview-photo'));
    if(c.total>0){
      const segments=[];
      let shown=0;
      for(const [key] of states){
        const count=Number(c[key]);
        if(count<=0)continue;
        const start=shown/c.total*100;
        shown+=count;
        segments.push('var(--overview-'+key+') '+start+'% '+(shown/c.total*100)+'%');
      }
      if(segments.length)ring.style.setProperty('--overview-ring-fill','conic-gradient('+segments.join(',')+')');
    }
    total.append(totalCopy,ring);
    left.append(total);

    const numbers=el('div','r182-numbers');
    for(const [key,label,status] of states){
      const tile=button('',()=>filterTo(status),'r182-stat');
      const dot=el('span','r182-overview-dot '+key);
      dot.setAttribute('aria-hidden','true');
      tile.append(dot,el('strong','r182-color-'+key,countNum(c[key])),el('span','',label));
      numbers.append(tile);
    }
    left.append(numbers);
    const reservations=button('',()=>filterTo('booked_today'),'r182-booked');
    reservations.append(el('span','r182-booked-label','Забронировано сегодня'),el('b','',countNum(booked.length)),icon('right'));
    left.append(reservations);

    const detail=el('details','r182-categories');
    detail.open=expanded;
    const detailTitle=el('summary');
    detailTitle.append(el('span','','По категориям'),icon('right'));
    detail.append(detailTitle);
    right.append(detail);
    const table=el('div','r182-category-table'), row=el('div','r182-cat-row r182-cat-head');
    const headings=['Категория','Всего','Склад','Работа'];
    if(hasRepairs)headings.push('Рем.');
    row.append(...headings.map(title=>el('span','',title)));
    table.append(row);
    const categoryStates=[['total','Всего',''],...states];
    for(const cat of categories.filter(x=>x.total>0)){
      const line=el('div','r182-cat-row');
      line.append(button(cat.name,()=>openCategoryStats(cat.name),'r182-cat-name'));
      for(const [key,label,status] of categoryStates){
        const count=button(countNum(cat[key]),()=>filterTo(status,cat.name),'r182-cat-num r182-color-'+key);
        count.setAttribute('aria-label',cat.name+': '+label+' '+countNum(cat[key]));
        line.append(count);
      }
      table.append(line);
    }
    if(!categories.some(x=>x.total>0))table.append(el('p','r182-muted','Нет оборудования'));detail.append(table);
    if(d){daily.className='card r182-daily';daily.replaceChildren(el('div','r182-overview-heading','Сводка за '+d.date.split('-').reverse().join('.')));const metrics=el('div','r182-numbers');for(const [key,label,color]of [['taken','Выдано','working'],['returned','Возвращено','stock'],['written_off','Списано','repair']]){const b=button('',()=>openDailyHistory(d.date,key),'r182-stat');b.append(el('strong','r182-color-'+color,countNum(d[key])),el('span','',label));metrics.append(b)}daily.append(metrics);}else{daily.replaceChildren();daily.className="hidden";}
    low.className='card r182-low'+(short.length?'':' hidden');low.removeAttribute('style');low.replaceChildren();if(short.length){const h=el('div','r182-overview-heading');h.append(icon('alert'),el('span','','Заканчиваются расходники'));low.append(h);for(const item of short){const b=button('',()=>openItem(item.code),'r182-low-row');b.append(el('span','',item.name),el('b','',countNum(item.stock)+' / '+countNum(item.minimum)+' '+item.unit),icon('right'));low.append(b)}}
    filterItems();
  }
  let pendingOverview=null,lastOverview=0;
  const loadOverview=()=>{if(pendingOverview)return pendingOverview;if(Date.now()-lastOverview<700)return Promise.resolve();pendingOverview=api('/api/v18/overview').then(data=>{renderOverview(data);lastOverview=Date.now()}).catch(e=>console.warn('Обзор:',e.message)).finally(()=>pendingOverview=null);return pendingOverview};
  loadDashboard17=loadOverview;loadStats=loadOverview;loadDailyReport=loadOverview;loadLowStock=loadOverview;
  // Correct status classification, including negative phrases like «не хватает».
  const classify=value=>{const s=String(value??'').toLowerCase().trim().replace(/ё/g,'е');if(!s)return 'unknown';if(/не\s*хватает|недостат|не\s*доста|нет\s+|нужн|требу|не\s*ок/.test(s))return 'issue';if(/^(?:[✓✅\s]*)(?:всего\s+хватает|все\s+хватает|хватает|все\s+есть|ок|все\s+в\s+наличии)[.!\s]*$/.test(s))return 'ok';return 'issue'};
  const dateKey=s=>{const v=String(s||'');const m=v.match(/^(\d{1,2})\.(\d{1,2})\.(\d{2,4})/);if(m)return Date.UTC(Number(m[3])+(m[3].length===2?2000:0),Number(m[2])-1,Number(m[1]));return /^\d{4}-\d{2}-\d{2}/.test(v)?Date.parse(v)||0:0};
  const sections={site:{id:'screen-platforms',search:'platform-search',list:'platforms-list',sync:'sync-btn-plat',sheet:'кц',cache:'platforms',accent:'site',kind:'music'},vessel:{id:'screen-th',search:'th-search',list:'th-list',sync:'sync-btn-th',sheet:'тх мск',cache:'ships',accent:'vessel',kind:'ship'}};
  const statusLabels={all:'Все',issue:'Не хватает',ok:'Всё есть',unknown:'Нет данных'};
  for(const config of Object.values(sections)){
    config.filter='all';const root=$(config.id);root.classList.add('r182-event-screen','r182-'+config.accent);
    config.tabs=el('div','r182-event-tabs');$(config.list).before(config.tabs);
    config.stamp=el('div','r182-sync-time');$(config.sync).after(config.stamp);
    const sync=$(config.sync);sync.replaceChildren(icon('refresh'),el('span','','Обновить данные'));sync.classList.add('r182-sync');
  }
  function eventRows(key){let raw=key==='site'?cachedPlatforms:cachedTH;return raw.filter(r=>r&&typeof r==='object').map(row=>{
    if(key==='site')return {name:String(row['Площадка']||'—'),date:String(row['дата']||row['Дата']||''),status:String(row['чего не хватает']||''),fields:[['Администратор',row['админ']],['Счётчик',row['счетчик']],['Запас',row['запас']]].filter(x=>x[1]!==undefined&&x[1]!==''&&x[1]!==null)};
    const askKey=Object.keys(row).find(k=>/просят|нужно|статус|не хватает/i.test(k));const fallback=Object.entries(row).find(([k,v])=>/хватает|недостат/i.test(String(v)))?.[0];const statusKey=askKey||fallback;
    return {name:String(row['Название']||Object.values(row)[0]||'—'),date:String(row['Дата']||row['дата']||''),status:String(statusKey?row[statusKey]||'':''),fields:Object.entries(row).filter(([k,v])=>!['Название','Дата','дата',statusKey].includes(k)&&v!==''&&v!=null)};
  }).map(r=>({...r,state:classify(r.status)})).sort((a,b)=>({issue:0,unknown:1,ok:2}[a.state]-{issue:0,unknown:1,ok:2}[b.state])||dateKey(b.date)-dateKey(a.date));}
  function eventValue(key,label,value){
    const node=el('b','r182-event-value',value);
    if(key!=='vessel')return node;
    const match=String(value).trim().match(/^(-?(?:\d{1,3}(?:\s\d{3})+|\d+)(?:[.,]\d+)?)(?:\s*(?:шт\.?|м\.?|метр(?:а|ов)?|рул\.?|рулон(?:а|ов)?|компл\.?|комплект(?:а|ов)?))?$/i);
    if(!match)return node;
    const minimum=/винил/i.test(label)?50:2;
    const low=Number(match[1].replace(/\s/g,'').replace(',','.'))<minimum;
    node.classList.add(low?'r182-value-low':'r182-value-ok');
    node.title=low?'Ниже нормы: минимум '+minimum:'В норме: минимум '+minimum;
    return node;
  }
  function statusNode(r){const e=el('div','r182-event-status r182-status-'+r.state);e.append(icon(r.state==='ok'?'check':'alert'),el('span','',r.state==='ok'?'Всего хватает':r.status||'Статус не указан'));return e}
  function eventLink(key,r){const b=button('',()=>showLinked17(key,r.name),'r182-event-link');b.append(icon('box'),el('span','',key==='site'?'Оборудование площадки':'Оборудование теплохода'),icon('right'));return b}
  function renderEvent(key){const cfg=sections[key],all=eventRows(key),query=$(cfg.search).value.trim().toLowerCase();const filtered=all.filter(r=>(cfg.filter==='all'||r.state===cfg.filter)&&r.name.toLowerCase().includes(query));
    cfg.tabs.replaceChildren(...Object.entries(statusLabels).map(([status,label])=>{
      const bring=key==='site'&&status==='issue';
      const count=all.filter(r=>status==='all'||r.state===status).length;
      const title=(bring?'Нужно привезти':label)+' · '+count;
      const tab=button(title,()=>{cfg.filter=status;renderEvent(key)},'r182-event-tab');
      tab.classList.toggle('r182-bring-tab',bring);
      tab.classList.toggle('active',cfg.filter===status);
      tab.setAttribute('aria-pressed',String(cfg.filter===status));
      return tab;
    }));
    const stamp=cacheGet17('sync182_'+cfg.cache);cfg.stamp.textContent=stamp?'Последняя синхронизация: '+new Date(Number(stamp)).toLocaleString('ru-RU'):'Данные не обновлялись в этом браузере';
    const list=$(cfg.list);list.replaceChildren();if(!filtered.length){list.append(el('p','r182-muted',all.length?'Ничего не найдено':'Нет сохранённых данных. Ожидаем обновления.'));return}
    if(document.body.classList.contains('web-mode')&&innerWidth>=900){
      const wrap=el('div','v18-table-wrap r182-event-table'), table=el('table','v18-table');
      const head=el('thead'), headings=el('tr'), body=el('tbody');
      for(const title of ['Название','Дата','Сведения','Статус','Оборудование'])headings.append(el('th','',title));
      head.append(headings);
      for(const r of filtered){
        const row=el('tr'), fields=el('td'), status=el('td'), link=el('td');
        for(const [label,value] of r.fields){
          const field=el('div');
          field.append(document.createTextNode(label+': '),eventValue(key,label,value));
          fields.append(field);
        }
        status.append(statusNode(r));
        link.append(eventLink(key,r));
        row.append(el('td','',r.name),el('td','',r.date||'—'),fields,status,link);
        body.append(row);
      }
      table.append(head,body);
      wrap.append(table);
      list.append(wrap);
      return;
    }
    for(const r of filtered){
      const card=el('article','card platform-card'), header=el('div','platform-title');
      header.append(el('span','',r.name),el('span','platform-date',r.date));
      const fields=el('div','platform-info');
      for(const [label,value] of r.fields){
        const field=el('div','platform-info-row');
        field.append(el('span','',label+':'),eventValue(key,label,value));
        fields.append(field);
      }
      const statusClass={ok:'status-ok',issue:'status-bad',unknown:'r183-event-unknown'}[r.state];
      const status=el('div','platform-status '+statusClass,r.state==='ok'?'ВСЕГО ХВАТАЕТ':r.status||'Нет данных');
      const link=button(key==='site'?'Оборудование площадки':'Оборудование теплохода',()=>showLinked17(key,r.name));
      card.append(header,fields,status,link);
      list.append(card);
    }
  }
  renderPlatformsList=()=>renderEvent('site');renderTHList=()=>renderEvent('vessel');
  const syncJobs=new Map();syncGoogle=sheet=>{const key=sheet==='кц'?'site':'vessel',cfg=sections[key];if(syncJobs.has(key))return syncJobs.get(key);const b=$(cfg.sync);setLoading(b,true,'Обновляем…');const job=api('/api/sync_google?sheet_name='+encodeURIComponent(cfg.sheet)+'&t='+Date.now(),{cache:'no-store'},0).then(r=>{if(r.status==='error'||!Array.isArray(r.data))throw Error(r.message||'Не удалось обновить данные');if(key==='site')cachedPlatforms=r.data;else cachedTH=r.data;cacheSet17(cfg.cache,JSON.stringify(r.data));cacheSet17('sync182_'+cfg.cache,String(Date.now()));renderEvent(key);if(currentScreen===cfg.id)showToast('Данные обновлены')}).catch(e=>{if(currentScreen===cfg.id)notify('Не удалось обновить. Сохранены прежние данные: '+e.message)}).finally(()=>{setLoading(b,false);syncJobs.delete(key)});syncJobs.set(key,job);return job};
  const maybeSync=key=>{const cfg=sections[key],last=Number(cacheGet17('sync182_'+cfg.cache)||0);if(Date.now()-last>300000&&!syncJobs.has(key))syncGoogle(cfg.sheet)};
  showPlatforms=()=>{updateNavActive('nav-platforms');renderEvent('site');showScreen('screen-platforms');syncGoogle(sections.site.sheet)};showTH=()=>{updateNavActive('nav-th');renderEvent('vessel');showScreen('screen-th');syncGoogle(sections.vessel.sheet)};setInterval(()=>{if(document.visibilityState==='visible'&&currentUser){if(currentScreen==='screen-platforms')maybeSync('site');if(currentScreen==='screen-th')maybeSync('vessel')}},60000);
  // Selection panel: keep clear of the floating navigation and format badges.
  const formatPrices=root=>root.querySelectorAll('.badge.price').forEach(b=>{const m=b.textContent.trim().match(/^([+-]?[\d.,\s]+)\s*₽$/);if(m){const n=Number(m[1].replace(/\s/g,'').replace(',','.'));if(Number.isFinite(n))b.textContent=money182(n)}});
  const cleanCards=root=>{formatPrices(root);root.querySelectorAll('.meta').forEach(e=>{if(e.textContent.startsWith('📍')){const t=e.textContent.replace(/^📍\s*/u,'');e.replaceChildren(icon('pin'),document.createTextNode(t));e.classList.add('r182-place-meta')}});root.querySelectorAll('.badge.repair,.badge.low,.badge.buyout').forEach(e=>e.textContent=e.textContent.replace(/^(?:🔧|⚠️?|💸)\s*/u,''))};
  const oldRender=renderItemsGrid;renderItemsGrid=(rows,id)=>{oldRender(rows,id);const root=$(id);if(root)cleanCards(root)};
  const oldTake=renderTakeItems;renderTakeItems=()=>{oldTake();cleanCards($('take-items-list'))};
  // Reuse existing form fields and names, so drafts, templates and backend writes stay compatible.
  const modal=$('create-item-modal'),body=modal.querySelector('.modal-content'),field=id=>$(id).closest('.input-group'),pair=(...children)=>{const w=el('div','r182-form-grid');w.append(...children);return w},section=(title,...children)=>{const w=el('section','r182-form-section');w.append(el('h3','',title),...children);return w};
  const type=field('add-kind'),selector=el('div','r182-types');const tabs=[['equipment','Оборудование','camera'],['consumable','Расходники','box']].map(([value,label,k])=>{const b=button('',()=>{$('add-kind').value=value;toggleFields();$('add-kind').dispatchEvent(new Event('input',{bubbles:true}))},'r182-type');b.append(icon(k),el('span','',label));selector.append(b);return [value,b]});type.before(selector);type.classList.add('r182-type-source');
  const header=body.firstElementChild;header.classList.add('r182-form-header');header.after(selector,type);
  const name=field('add-name'),photo=field('add-photo'),code=$('add-code'),codeRow=code.parentElement,gen=codeRow.querySelector('button');codeRow.classList.add('r182-code-row');codeRow.replaceChildren(code,gen);gen.textContent='Сгенерировать';code.removeAttribute('style');gen.removeAttribute('style');
  const codeSection=section('Код товара',codeRow,$('qr-preview-box'));codeSection.classList.add('r182-code-section');
  const basics=section('Основное',name,pair(field('add-category'),field('add-location')),codeSection);type.after(basics);
  const eq=$('equipment-fields'),cons=$('consumable-fields'),parts=['body','lens','flash','acc','add'];
  const eqInfo=section('Оборудование',field('add-serial-number'),field('add-price-eq'));
  const eqParts=section('Комплектация и стоимость',...parts.map(k=>pair(field('add-kit-'+k),field('add-price-'+k))));
  const eqTotal=el('div','r182-form-total');eqParts.append(eqTotal);
  const extras=el('details','r182-form-section');extras.append(el('summary','','Дополнительные сведения'),field('add-budget-tag'),field('add-buyout-status'));eq.replaceChildren(eqInfo,eqParts,extras);
  const cTotal=el('div','r182-form-total');const cMain=section('Остатки и стоимость',pair(field('add-qty'),field('add-min-stock')),pair(field('add-price'),field('add-unit')),cTotal);const cExtra=el('details','r182-form-section');cExtra.append(el('summary','','Дополнительные сведения'),field('add-supplier'),field('add-location-desc'));cons.replaceChildren(cMain,cExtra);
  const footer=el('div','r182-form-footer');footer.append($('save-item-btn'));body.append(footer);$('save-item-btn').removeAttribute('style');
  function formTotals(){const n=id=>Math.max(0,Number($(id).value)||0),equipment=$('add-kind').value==='equipment';const target=equipment?extras:cExtra;if(photo.parentElement!==target)target.append(photo);const sum=parts.reduce((a,k)=>a+n('add-price-'+k),0);eqTotal.replaceChildren(el('span','','Стоимость комплекта'),el('b','',money182(sum||n('add-price-eq'))));cTotal.replaceChildren(el('span','','Стоимость партии'),el('b','',money182(n('add-qty')*n('add-price'))));for(const [value,b]of tabs){b.classList.toggle('active',$('add-kind').value===value);b.setAttribute('aria-pressed',String($('add-kind').value===value))}if(!$('save-item-btn').disabled)$('save-item-btn').textContent=equipment?'Создать оборудование':'Создать расходник';$('save-item-btn').classList.toggle('r182-main-action',equipment)}
  const oldToggle=toggleFields;toggleFields=()=>{oldToggle();formTotals()};body.addEventListener('input',formTotals);formTotals();
  // On save, reserve a code automatically if the user hasn't typed one.
  const oldSave=saveNewItem;let saving=false;saveNewItem=async()=>{if(saving)return;saving=true;try{if(!$('add-name').value.trim())return notify('Введите название');if(!$('add-code').value.trim())await generateCodeForNew();if(!$('add-code').value.trim())return;await oldSave()}finally{saving=false}};
  const edit=$('screen-edit-item');edit.classList.add('r182-edit');const editBody=$('edit-name').closest('.input-group').parentElement;const oldHeading=editBody.querySelector('h2');oldHeading.classList.add('r182-form-title');for(const k of parts){const a=field('edit-kit-'+k),b=field('edit-price-'+k);const marker=document.createComment('pair');a.before(marker);marker.replaceWith(pair(a,b))}
  const editFooter=el('div','r182-edit-footer');const save=edit.querySelector('button[onclick="saveEditItem()"]');save.before(editFooter);editFooter.append(save);
}
function showCreated182(code,name){
  const {o,b}=overlay17('Товар создан');const title=document.createElement('h3');title.textContent=name+' · '+code;b.append(title);const image=document.createElement('img');image.className='label-img r182-created-label';image.alt='QR-этикетка';b.append(image);showLabelPreview17(code,name,image).catch(()=>notify('Не удалось загрузить этикетку'));
  btn17(b,'Скачать PNG',()=>downloadCreatedLabel182(code,'png'),'ok');btn17(b,'Скачать PDF',()=>downloadCreatedLabel182(code,'pdf'));btn17(b,'Готово',()=>{if(image.dataset.objecturl)URL.revokeObjectURL(image.dataset.objecturl);o.remove()});
}
async function downloadCreatedLabel182(code,format){
  let d={width:50,height:80};try{d={...d,...JSON.parse(cacheGet17('label_dimensions')||'{}')}}catch(e){}
  await downloadFile('/api/label/'+encodeURIComponent(code)+'?format='+format+'&width_mm='+encodeURIComponent(d.width)+'&height_mm='+encodeURIComponent(d.height),code+'.'+format);
}
