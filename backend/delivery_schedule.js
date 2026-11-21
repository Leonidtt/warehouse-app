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
  const panel=el('details','delivery-panel');panel.id='delivery-schedule-panel';
  const heading=el('summary','delivery-heading');
  const count=el('span','delivery-count');
  heading.append(el('strong','','Что привезти'),count);
  const body=el('div','delivery-body'),bar=el('div','delivery-bar');
  const prev=el('button','delivery-control delivery-arrow','‹');
  prev.type='button';prev.title='Предыдущий день';prev.setAttribute('aria-label','Предыдущий день');
  const day=el('input','delivery-date');day.type='date';day.setAttribute('aria-label','Дата доставки');
  const next=el('button','delivery-control delivery-arrow','›');
  next.type='button';next.title='Следующий день';next.setAttribute('aria-label','Следующий день');
  day.value=localDate();
  const source=el('div','delivery-source'),list=el('div','delivery-list');
  const refresh=el('button','delivery-control delivery-refresh','↻');
  refresh.title='Обновить список';refresh.setAttribute('aria-label',refresh.title);
  const upload=el('button','delivery-control delivery-excel','Excel');
  upload.title='Загрузить новый Excel';upload.setAttribute('aria-label',upload.title);
  const file=el('input','hidden');file.type='file';file.accept='.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  refresh.type='button';upload.type='button';
  const datePicker=el('div','delivery-date-picker');
  datePicker.append(prev,day,next);
  bar.append(datePicker,refresh,upload,file);
  body.append(bar,source,list);panel.append(heading,body);
  const activity=main.querySelector('#main-activity');
  if(activity)activity.after(panel);else main.querySelector('#items-list')?.before(panel);
  panel.classList.add('hidden');
  let revision=0,pending=null,rendered=null;
  const permitted=()=>!!currentUser?.is_registered&&currentUser.role==='admin';
  const staff=installStaffSchedule(panel,{el,localDate,offset,permitted});
  const toggleAccess=()=>{
    const show=permitted();panel.classList.toggle('hidden',!show);
    staff.setAccess(show);
    if(!show){panel.open=false;count.textContent='';source.textContent='';list.replaceChildren();rendered=null;}
    return show;
  };
  const names=(people,{showCount=false}={})=>[...people]
    .sort((a,b)=>a.person.localeCompare(b.person,'ru'))
    .map(row=>row.person+(showCount&&row.camera_count>1?' ×'+row.camera_count:'')).join(', ');
  const needsCamera=row=>row.status==='delivery'&&row.camera_count===0;
  const hasCamera=row=>row.status==='delivery'&&row.camera_count>0;
  const needsReview=row=>row.status==='review'||(row.status==='delivery'&&row.camera_count===null);
  const venueLabel=venue=>venue||'Площадку уточнить';
  const infoRow=(label,people,css='',showCount=false)=>{
    const row=el('div',('delivery-line '+css).trim());
    row.append(el('strong','delivery-line-label',label),el('span','delivery-names',names(people,{showCount})));
    return row;
  };
  function showVenuePlan(date,venue,people,notes){
    const {o,b}=overlay17(venueLabel(venue));
    const extras=people.filter(row=>row.status==='no_camera');
    if(extras.length){
      b.append(el('h3','delivery-detail-title','Без отметки «Ф»'),el('p','delivery-names',names(extras)));
    }
    const assignments=people.filter(row=>row.assignment&&row.assignment!==venue);
    if(assignments.length){
      const detail=el('details','delivery-more');
      detail.append(el('summary','','Примечания графика'));
      assignments.forEach(row=>detail.append(el('p','',row.person+' · '+row.assignment)));
      b.append(detail);
    }
    if(!venue)return;
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
  function renderSummary(venues,readyCount){
    const section=el('section','delivery-summary');
    const heading=el('div','delivery-summary-head');
    heading.append(el('h4','','Куда привезти'));
    if(readyCount)heading.append(el('span','','Камер: '+readyCount));
    section.append(heading);
    if(!readyCount){
      section.append(el('p','delivery-muted','Нет подтверждённых доставок'));
      return section;
    }
    for(const {venue,ready} of venues){
      if(ready.length)section.append(infoRow(venue||'Уточнить адрес',ready,venue?'':'delivery-route-pending'));
    }
    return section;
  }
  const draw=data=>{
    list.replaceChildren();
    const entries=data.rows||[];
    const ignored=entries.filter(x=>x.status==='excluded');
    count.textContent='';
    source.textContent='';
    if(!data.meta){
      list.append(el('p','delivery-muted','Загрузите график через кнопку Excel.'));
      return;
    }
    day.title=data.meta.source||'Дата доставки';
    if(data.meta.format_version<2){
      source.textContent='Загрузите Excel заново для полного состава площадок.';
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
    const ordered=[...venues].map(([venue,people])=>({
      venue,people,ready:people.filter(needsCamera)
    })).sort((a,b)=>Number(!a.ready.length)-Number(!b.ready.length)||
      Number(!a.venue)-Number(!b.venue)||a.venue.localeCompare(b.venue,'ru'));
    const readyCount=ordered.reduce((total,group)=>total+group.ready.length,0);
    count.textContent=readyCount?'К доставке: '+readyCount:'';
    for(const {venue,people,ready} of ordered){
      const section=el('section','delivery-group');
      const heading=el('h4','delivery-group-head');
      const hasPlan=venue||people.some(row=>row.status==='no_camera'||row.assignment);
      const title=el(hasPlan?'button':'span','delivery-venue');
      const color=people.find(x=>/^#[0-9a-f]{6}$/i.test(x.venue_color||''))?.venue_color;
      if(color){
        const dot=el('span','delivery-venue-dot');
        dot.style.backgroundColor=color;
        dot.setAttribute('aria-hidden','true');
        title.append(dot);
      }
      title.append(el('span','',venueLabel(venue)));
      if(hasPlan){
        title.type='button';
        title.title='Состав и план · '+venueLabel(venue);
        title.setAttribute('aria-label',title.title);
        title.onclick=()=>showVenuePlan(data.date,venue,people,notesByVenue.get(venue));
      }
      heading.append(title);
      section.append(heading);
      const held=people.filter(hasCamera);
      const review=people.filter(needsReview);
      if(ready.length)section.append(infoRow('Привезти',ready,'delivery-priority'));
      if(held.length)section.append(infoRow('На руках',held,'delivery-held',true));
      if(review.length)section.append(infoRow('Проверить',review,'delivery-review'));
      if(!ready.length&&!held.length&&!review.length){
        section.append(el('div','delivery-muted','Без отметок «Ф»'));
      }
      list.append(section);
    }
    if(ignored.length){
      const skip=el('details','delivery-ignored');
      skip.append(el('summary','','Отсутствуют · '+ignored.length));
      skip.append(el('p','delivery-names',names(ignored)));list.append(skip);
    }
    list.append(renderSummary(ordered,readyCount));
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
  day.onchange=()=>reload();
  refresh.onclick=()=>reload(true);
  upload.onclick=()=>file.click();
  file.onchange=async()=>{
    const selected=file.files?.[0];if(!selected||!permitted())return;
    upload.disabled=true;upload.setAttribute('aria-busy','true');
    try{
      const form=new FormData();form.append('file',selected,selected.name);
      const result=await api('/api/delivery-schedule/upload',{method:'POST',body:form});
      if(typeof showToast==='function')showToast('График обновлён: '+result.rows+' записей');
      await reload(true);
      staff.refresh();
    }catch(error){if(typeof notify==='function')notify(error.message);else alert(error.message);}
    finally{file.value='';upload.disabled=false;upload.removeAttribute('aria-busy');}
  };
  panel.addEventListener('toggle',()=>{if(panel.open&&permitted())reload();});
  const initBefore=init;
  init=async()=>{const result=await initBefore();if(toggleAccess()){panel.open=true;await reload();}return result;};
  const loadBefore=loadItems;
  loadItems=async(...args)=>{const result=await loadBefore(...args);if(toggleAccess()&&panel.open)reload(true);return result;};
}

function installStaffSchedule(anchor,{el,localDate,offset,permitted}){
  const panel=el('details','delivery-panel staff-panel hidden');
  panel.id='staff-schedule-panel';
  const heading=el('summary','delivery-heading');
  heading.append(el('strong','','График сотрудников'),el('span','delivery-count',''));
  const body=el('div','delivery-body');
  const bar=el('div','delivery-bar');
  const datePicker=el('div','delivery-date-picker');
  const previous=el('button','delivery-control delivery-arrow','‹');
  const next=el('button','delivery-control delivery-arrow','›');
  for(const [button,label] of [[previous,'Предыдущая неделя'],[next,'Следующая неделя']]){
    button.type='button';
    button.title=label;
    button.setAttribute('aria-label',label);
  }
  const dateInput=el('input','delivery-date');
  dateInput.type='date';
  dateInput.value=localDate();
  dateInput.setAttribute('aria-label','Дата недели графика');
  datePicker.append(previous,dateInput,next);
  bar.append(datePicker);
  const content=el('div','staff-content');
  body.append(bar,content);
  panel.append(heading,body);
  anchor.before(panel);
  const calendar=['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];
  const formatDate=iso=>iso.slice(8,10)+'.'+iso.slice(5,7);
  const validColor=color=>/^#[0-9a-f]{6}$/i.test(color||'');
  let request=0,loaded='';

  function draw(data,selected){
    content.replaceChildren();
    if(!data.meta){
      content.append(el('p','delivery-muted','Загрузите график через Excel в блоке «Что привезти».'));
      return;
    }
    if(data.meta.format_version<2){
      content.append(el('p','delivery-muted','Загрузите Excel заново для полного состава.'));
    }
    const days=calendar.map((_,i)=>offset(data.start,i));
    const people=new Map(),colors=new Map();
    for(const row of data.rows||[]){
      const key=JSON.stringify([row.person,row.department]);
      if(!people.has(key))people.set(key,{name:row.person,department:row.department,days:new Map()});
      const assignments=people.get(key).days;
      if(!assignments.has(row.work_date))assignments.set(row.work_date,[]);
      assignments.get(row.work_date).push(row);
      if(row.status!=='excluded'&&row.venue&&validColor(row.venue_color)){
        if(!colors.has(row.venue))colors.set(row.venue,new Set());
        colors.get(row.venue).add(row.venue_color);
      }
    }
    const visiblePeople=[...people.values()].filter(person=>[...person.days.values()]
      .some(rows=>rows.some(row=>row.status!=='excluded')));
    if(!visiblePeople.length){
      content.append(el('p','delivery-muted','На эту неделю назначений нет.'));
      return;
    }
    const marker=color=>{
      const item=el('span','staff-color');
      if(color)item.style.backgroundColor=color;
      item.setAttribute('aria-hidden','true');
      return item;
    };
    const colorFor=row=>validColor(row.venue_color)?row.venue_color:colors.get(row.venue)?.values().next().value;
    const legend=el('ul','staff-legend');
    const venues=new Map();
    for(const person of visiblePeople){
      for(const rows of person.days.values()){
        for(const row of rows){
          if(row.status==='excluded')continue;
          const label=row.venue||'Площадка не указана';
          if(!venues.has(label))venues.set(label,new Set());
          venues.get(label).add(colorFor(row)||'');
        }
      }
    }
    for(const [venue,swatches] of [...venues].sort(([a],[b])=>a.localeCompare(b,'ru'))){
      const item=el('li');
      for(const color of swatches)item.append(marker(color));
      item.append(el('span','',venue));
      legend.append(item);
    }
    const detail=el('p','staff-selection');
    detail.setAttribute('aria-live','polite');
    let selectedSlot;
    const table=el('table','staff-grid');
    table.setAttribute('aria-label','График сотрудников на неделю');
    const head=el('thead'),headRow=el('tr');
    const nameHeader=el('th','','Сотрудник');nameHeader.scope='col';headRow.append(nameHeader);
    days.forEach((day,i)=>{
      const th=el('th',day===selected?'staff-today':'');
      th.scope='col';
      th.title=formatDate(day);
      th.append(el('span','',calendar[i]),el('small','',day.slice(8,10)));
      headRow.append(th);
    });
    head.append(headRow);
    const grid=el('tbody');
    visiblePeople.sort((a,b)=>a.name.localeCompare(b.name,'ru')||a.department.localeCompare(b.department,'ru'));
    for(const person of visiblePeople){
      const line=el('tr');
      const name=el('th','',person.name);name.scope='row';name.title=person.department;line.append(name);
      for(const day of days){
        const cell=el('td',day===selected?'staff-today':'');
        const rows=person.days.get(day)||[];
        const shifts=rows.filter(row=>row.status!=='excluded');
        if(shifts.length){
          const slot=el('button','staff-slot');
          slot.type='button';
          const locations=[...new Set(shifts.map(row=>row.venue||'Площадка не указана'))];
          const description=person.name+' · '+formatDate(day)+' · '+locations.join(', ');
          slot.title=description;
          slot.setAttribute('aria-label',description);
          slot.setAttribute('aria-pressed','false');
          const swatches=new Set(shifts.map(colorFor));
          for(const color of swatches)slot.append(marker(color));
          slot.onclick=()=>{
            selectedSlot?.setAttribute('aria-pressed','false');
            selectedSlot=slot;
            slot.setAttribute('aria-pressed','true');
            detail.textContent=description;
          };
          cell.append(slot);
        }else{
          cell.append(el('span','staff-empty',rows.length?'·':'—'));
        }
        line.append(cell);
      }
      grid.append(line);
    }
    table.append(head,grid);
    const scroller=el('div','staff-scroll');
    scroller.append(table);
    content.append(legend,detail,scroller);
  }
  async function load(force=false){
    if(!panel.open||!permitted())return;
    const day=dateInput.value||localDate();
    dateInput.value=day;
    if(!force&&loaded===day)return;
    loaded='';
    const revision=++request;
    content.replaceChildren(el('p','delivery-muted','Загружаем график…'));
    try{
      const result=await api('/api/delivery-schedule/week?date='+encodeURIComponent(day),{cache:'no-store'});
      if(revision!==request||!panel.open||!permitted())return;
      draw(result,day);
      loaded=day;
    }catch(error){
      if(revision!==request||!panel.open||!permitted())return;
      loaded='';
      content.replaceChildren(el('p','delivery-error','Не удалось загрузить график: '+error.message));
    }
  }
  const step=days=>{dateInput.value=offset(dateInput.value||localDate(),days);load();};
  previous.onclick=()=>step(-7);
  next.onclick=()=>step(7);
  dateInput.onchange=()=>load();
  panel.addEventListener('toggle',()=>load());
  return {
    refresh:()=>load(true),
    setAccess(show){
      panel.classList.toggle('hidden',!show);
      if(!show){
        panel.open=false;
        content.replaceChildren();
        loaded='';
        ++request;
      }
    }
  };
}
