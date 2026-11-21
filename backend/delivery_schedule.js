/* Beta: Excel rota and camera deliveries for administrators. */
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
  day.value=localDate();
  bar.append(prev,day,next,today,tomorrow);
  const source=el('div','delivery-source'),list=el('div','delivery-list'),actions=el('div','delivery-actions');
  const refresh=el('button','secondary compact','Обновить список');
  const upload=el('button','secondary compact','Загрузить новый Excel');
  const file=el('input','hidden');file.type='file';file.accept='.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  refresh.type='button';upload.type='button';
  actions.append(refresh,upload,file);
  body.append(bar,actions,source,list);panel.append(heading,body);
  const activity=main.querySelector('#main-activity');
  if(activity)activity.after(panel);else main.querySelector('#items-list')?.before(panel);
  panel.classList.add('hidden');
  let revision=0,pending=null,rendered=null;
  const permitted=()=>!!currentUser?.is_registered&&currentUser.role==='admin';
  const toggleAccess=()=>{
    const show=permitted();panel.classList.toggle('hidden',!show);
    if(!show){panel.open=false;count.textContent='';source.textContent='';list.replaceChildren();rendered=null;}
    return show;
  };
  const card=row=>{
    const item=el('article','delivery-person');
    const top=el('div','delivery-person-top');
    top.append(el('strong','',row.person),el('span','delivery-department',row.department));
    item.append(top);
    let label;
    if(row.status==='delivery'){
      if(row.camera_count===null)label='Нужен по графику · уточнить наличие';
      else if(row.camera_count>0){
        label='Камера на руках';
        item.classList.add('delivery-held');
      }else label='Привезти фотоаппарат';
    }else if(row.status==='no_camera')label='Без отметки о фотоаппарате';
    else if(row.status==='review')label='Назначение требует уточнения';
    if(label)item.append(el('div','delivery-equipment',label));
    if(row.assignment&&row.assignment!==row.venue){
      item.append(el('p','delivery-note','По графику: '+row.assignment));
    }
    return item;
  };
  function editVenueNotes(date,venue,notes){
    const {o,b}=overlay17(venue+' · техника и расходники');
    const form=el('form','delivery-notes-form');
    const field=(label,value,placeholder)=>{
      const wrapper=el('label','delivery-note-field',label);
      const input=el('textarea');
      input.value=value||'';
      input.rows=3;
      input.maxLength=3000;
      input.placeholder=placeholder;
      wrapper.append(input);
      form.append(wrapper);
      return input;
    };
    const equipment=field('Задачи по технике',notes?.equipment,'Кому, что и откуда привезти');
    const supplies=field('Расходники',notes?.supplies,'Что привезти и в каком количестве');
    const error=el('p','delivery-error');
    error.setAttribute('role','alert');
    const save=el('button','','Сохранить');
    save.type='submit';
    form.append(save,error);
    b.append(form);
    form.onsubmit=async event=>{
      event.preventDefault();
      save.disabled=true;
      error.textContent='';
      try{
        await api('/api/delivery-schedule/venue-notes?date='+encodeURIComponent(date),{
          method:'PUT',body:JSON.stringify({venue,equipment:equipment.value,supplies:supplies.value})
        });
        o.remove();
        reload(true);
      }catch(err){
        error.textContent=err.message;
      }finally{
        save.disabled=false;
      }
    };
  }
  const draw=data=>{
    list.replaceChildren();
    const entries=data.rows||[];
    const ready=entries.filter(x=>x.status==='delivery'&&x.camera_count===0);
    const ignored=entries.filter(x=>x.status==='excluded');
    count.textContent=ready.length?'Привезти: '+ready.length:'';
    if(!data.meta){
      source.textContent='График ещё не загружен.';
      list.append(el('p','delivery-muted','Администратор может загрузить Excel-файл.'));
      return;
    }
    source.textContent=display(data.date)+' · '+data.meta.source;
    if(data.meta.format_version<2){
      source.append(el('p','delivery-muted','Загрузите Excel заново, чтобы увидеть полный состав площадок.'));
    }
    if(data.date<data.meta.first_date||data.date>data.meta.last_date){
      list.append(el('p','delivery-muted','Дата вне графика: '+data.meta.first_date+' — '+data.meta.last_date));
      return;
    }
    if(!entries.length){
      list.append(el('p','delivery-muted','В графике нет записей на эту дату.'));
      return;
    }
    const venues=new Map();
    const notesByVenue=new Map((data.notes||[]).map(notes=>[notes.venue,notes]));
    for(const row of entries){
      if(row.status==='excluded')continue;
      if(!venues.has(row.venue))venues.set(row.venue,[]);
      venues.get(row.venue).push(row);
    }
    const ordered=[...venues].sort(([a],[b])=>a&&b?a.localeCompare(b,'ru'):Number(!a)-Number(!b));
    for(const [venue,people] of ordered){
      const section=el('section','delivery-group');
      const title=el('h4','delivery-venue');
      const color=people.find(x=>/^#[0-9a-f]{6}$/i.test(x.venue_color||''))?.venue_color;
      if(color){
        const dot=el('span','delivery-venue-dot');
        dot.style.backgroundColor=color;
        dot.setAttribute('aria-hidden','true');
        title.append(dot);
      }
      title.append(el('span','',(venue||'Площадка не определена')+' · '+people.length));
      section.append(title);
      if(venue){
        const notes=notesByVenue.get(venue);
        const equipment=el('div','delivery-venue-notes');
        for(const [label,value] of [['Задачи по технике',notes?.equipment],['Расходники',notes?.supplies]]){
          equipment.append(el('strong','',label),el('p','',value||'Не указаны'));
        }
        const edit=el('button','secondary compact','Уточнить план');
        edit.type='button';
        edit.onclick=()=>editVenueNotes(data.date,venue,notes);
        equipment.append(edit);
        section.append(equipment);
      }
      people.forEach(row=>section.append(card(row)));
      list.append(section);
    }
    if(ignored.length){
      const skip=el('details','delivery-ignored');
      skip.append(el('summary','','Не в доставке · '+ignored.length));
      ignored.forEach(x=>skip.append(card(x)));list.append(skip);
    }
  };
  const reload=(force=false)=>{
    if(!toggleAccess())return;
    const selected=day.value||localDate();
    day.value=selected;
    if(!force&&pending?.date===selected)return pending.promise;
    const id=++revision;
    if(rendered?.date!==selected){
      rendered=null;
      count.textContent='…';source.textContent='';
      list.replaceChildren(el('p','delivery-muted','Загрузка графика…'));
    }
    const promise=api('/api/delivery-schedule?date='+encodeURIComponent(selected),{cache:'no-store'})
      .then(result=>{
        if(id!==revision||!permitted())return;
        const signature=JSON.stringify(result);
        if(signature===rendered?.signature)return;
        const ignoredOpen=list.querySelector('.delivery-ignored')?.open;
        draw(result);
        const ignored=list.querySelector('.delivery-ignored');
        if(ignored&&ignoredOpen)ignored.open=true;
        rendered={date:selected,signature};
      }).catch(err=>{
        if(id!==revision||!permitted())return;
        rendered=null;
        count.textContent='';source.textContent='';
        list.replaceChildren(el('p','delivery-error','Не удалось получить график: '+err.message));
      }).finally(()=>{if(id===revision)pending=null;});
    pending={date:selected,promise};
    return promise;
  };
  const select=iso=>{day.value=iso;reload();};
  prev.onclick=()=>select(offset(day.value||localDate(),-1));
  next.onclick=()=>select(offset(day.value||localDate(),1));
  today.onclick=()=>select(localDate());
  tomorrow.onclick=()=>select(offset(localDate(),1));
  day.onchange=()=>reload();
  refresh.onclick=()=>reload(true);
  upload.onclick=()=>file.click();
  file.onchange=async()=>{
    const selected=file.files?.[0];if(!selected||!permitted())return;
    upload.disabled=true;upload.textContent='Загружаем…';
    try{
      const form=new FormData();form.append('file',selected,selected.name);
      const result=await api('/api/delivery-schedule/upload',{method:'POST',body:form});
      if(typeof showToast==='function')showToast('График обновлён: '+result.rows+' записей');
      await reload(true);
    }catch(error){if(typeof notify==='function')notify(error.message);else alert(error.message);}
    finally{file.value='';upload.disabled=false;upload.textContent='Загрузить новый Excel';}
  };
  panel.addEventListener('toggle',()=>{if(panel.open&&permitted())reload();});
  const initBefore=init;
  init=async()=>{const result=await initBefore();if(toggleAccess()){panel.open=true;await reload();}return result;};
  const loadBefore=loadItems;
  loadItems=async(...args)=>{const result=await loadBefore(...args);if(panel.open&&permitted())reload(true);return result;};
}
