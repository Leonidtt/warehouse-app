/* Beta: Excel rota delivery preview for Boss/Admin. */
function installDeliverySchedule(){
  const main=document.getElementById('screen-main');
  if(!main||document.getElementById('delivery-schedule-panel'))return;
  const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;};
  const localDate=()=>{
    const pieces=Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Moscow',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
    const val=k=>pieces.find(x=>x.type===k)?.value;
    return [val('year'),val('month'),val('day')].join('-');
  };
  const offset=(iso,n)=>{const day=new Date(iso+'T12:00:00Z');day.setUTCDate(day.getUTCDate()+n);return day.toISOString().slice(0,10);};
  const display=iso=>new Date(iso+'T12:00:00Z').toLocaleDateString('ru-RU',{day:'numeric',month:'long',weekday:'long',timeZone:'UTC'});
  const panel=el('details','card delivery-panel');panel.id='delivery-schedule-panel';
  const heading=el('summary','delivery-heading');
  const count=el('span','delivery-count');
  heading.append(el('strong','','Что привезти'),count);
  const body=el('div','delivery-body'),bar=el('div','delivery-bar');
  const prev=el('button','secondary compact delivery-arrow','‹');
  prev.type='button';prev.title='Предыдущий день';prev.setAttribute('aria-label','Предыдущий день');
  const day=el('input','delivery-date');day.type='date';day.setAttribute('aria-label','Дата доставки');
  const next=el('button','secondary compact delivery-arrow','›');
  next.type='button';next.title='Следующий день';next.setAttribute('aria-label','Следующий день');
  const today=el('button','secondary compact','Сегодня'),tomorrow=el('button','secondary compact','Завтра');
  today.type='button';tomorrow.type='button';
  day.value=offset(localDate(),1);
  bar.append(prev,day,next,today,tomorrow);
  const source=el('div','delivery-source'),list=el('div','delivery-list'),actions=el('div','delivery-actions');
  const refresh=el('button','secondary compact','Обновить список');
  const upload=el('button','secondary compact hidden','Загрузить новый Excel');
  const file=el('input','hidden');file.type='file';file.accept='.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  refresh.type='button';upload.type='button';
  actions.append(refresh,upload,file);
  body.append(bar,source,list,actions);panel.append(heading,body);
  const activity=main.querySelector('#main-activity');
  if(activity)activity.after(panel);else main.querySelector('#items-list')?.before(panel);
  panel.classList.add('hidden');
  let revision=0;
  const permitted=()=>!!currentUser?.is_registered&&(['admin','boss'].includes(currentUser.role)||currentUser.is_owner);
  const canUpload=()=>!!currentUser?.is_registered&&(currentUser.role==='admin'||currentUser.is_owner);
  const toggleAccess=()=>{
    const show=permitted();panel.classList.toggle('hidden',!show);upload.classList.toggle('hidden',!canUpload());
    if(!show){panel.open=false;count.textContent='';list.replaceChildren();}
    return show;
  };
  const card=row=>{
    const item=el('article','delivery-person');
    const top=el('div','delivery-person-top');
    top.append(el('strong','',row.person),el('span','delivery-department',row.department));
    const type=el('div','delivery-equipment','Фотоаппарат');
    const note=el('p','delivery-note');
    note.textContent=row.venue
      ?'Площадка: '+row.venue+' · По графику: '+row.assignment
      :'Площадка не уточнена · В графике: '+row.assignment;
    item.append(top,type,note);return item;
  };
  const draw=data=>{
    list.replaceChildren();
    const entries=data.rows||[];
    const ready=entries.filter(x=>x.status==='delivery');
    const review=entries.filter(x=>x.status==='review');
    const ignored=entries.filter(x=>x.status==='excluded');
    count.textContent=ready.length?ready.length+' фотоапп.':'';
    if(!data.meta){
      source.textContent='График ещё не загружен.';
      list.append(el('p','delivery-muted','Администратор может загрузить Excel-файл.'));
      return;
    }
    source.textContent=display(data.date)+' · '+data.meta.source;
    if(data.date<data.meta.first_date||data.date>data.meta.last_date){
      list.append(el('p','delivery-muted','Дата вне графика: '+data.meta.first_date+' — '+data.meta.last_date));
      return;
    }
    if(!entries.length){
      list.append(el('p','delivery-muted','На эту дату нет записей с отметкой «Ф».'));
      return;
    }
    const group=(title,items,css)=>{
      if(!items.length)return;
      const section=el('section','delivery-group '+css);
      section.append(el('h4','',title+' · '+items.length));
      items.forEach(x=>section.append(card(x)));
      list.append(section);
    };
    group('Нужно подготовить',ready,'delivery-ready');
    group('Требует уточнения',review,'delivery-review');
    if(ignored.length){
      const skip=el('details','delivery-ignored');
      skip.append(el('summary','','Не в доставке · '+ignored.length));
      ignored.forEach(x=>skip.append(card(x)));list.append(skip);
    }
  };
  const reload=async()=>{
    if(!toggleAccess())return;
    const id=++revision;
    count.textContent='…';list.replaceChildren(el('p','delivery-muted','Загрузка графика…'));
    try{
      const result=await api('/api/delivery-schedule?date='+encodeURIComponent(day.value),{cache:'no-store'});
      if(id===revision&&permitted())draw(result);
    }catch(err){
      if(id===revision){count.textContent='';list.replaceChildren(el('p','delivery-error','Не удалось получить график: '+err.message));}
    }
  };
  const select=iso=>{day.value=iso;reload();};
  prev.onclick=()=>select(offset(day.value,-1));
  next.onclick=()=>select(offset(day.value,1));
  today.onclick=()=>select(localDate());
  tomorrow.onclick=()=>select(offset(localDate(),1));
  day.onchange=reload;
  refresh.onclick=reload;
  upload.onclick=()=>file.click();
  file.onchange=async()=>{
    const selected=file.files?.[0];if(!selected||!canUpload())return;
    upload.disabled=true;upload.textContent='Загружаем…';
    try{
      const form=new FormData();form.append('file',selected,selected.name);
      const result=await api('/api/delivery-schedule/upload',{method:'POST',body:form});
      if(typeof showToast==='function')showToast('График обновлён: '+result.rows+' записей');
      await reload();
    }catch(error){if(typeof notify==='function')notify(error.message);else alert(error.message);}
    finally{file.value='';upload.disabled=false;upload.textContent='Загрузить новый Excel';}
  };
  panel.addEventListener('toggle',()=>{if(panel.open&&permitted())reload();});
  const initBefore=init;
  init=async()=>{const result=await initBefore();if(toggleAccess()){panel.open=true;await reload();}return result;};
  const loadBefore=loadItems;
  loadItems=async(...args)=>{const result=await loadBefore(...args);if(panel.open&&permitted())reload();return result;};
}
