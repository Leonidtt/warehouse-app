/* Beta: staff rota and camera delivery plan. */
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
  const body=el('div','delivery-body'),bar=el('div','delivery-bar hidden');
  const prev=el('button','delivery-control delivery-arrow','‹');
  prev.type='button';prev.title='Предыдущий день';prev.setAttribute('aria-label','Предыдущий день');
  const day=el('input','delivery-date');day.type='date';day.setAttribute('aria-label','Дата доставки');
  const next=el('button','delivery-control delivery-arrow','›');
  next.type='button';next.title='Следующий день';next.setAttribute('aria-label','Следующий день');
  day.value=localDate();
  const source=el('div','delivery-source'),metrics=el('div','delivery-metrics'),list=el('div','delivery-list');
  metrics.setAttribute('aria-label','Сводка по фотоаппаратам');
  const refresh=el('button','delivery-control delivery-refresh','↻');
  refresh.title='Обновить список';refresh.setAttribute('aria-label',refresh.title);
  const upload=el('button','delivery-control delivery-excel','Excel');
  upload.title='Загрузить новый Excel';upload.setAttribute('aria-label',upload.title);
  const file=el('input','hidden');file.type='file';file.accept='.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  refresh.type='button';upload.type='button';
  const datePicker=el('div','delivery-date-picker');
  datePicker.append(prev,day,next);
  bar.append(datePicker,refresh,upload,file);
  body.append(bar,source,metrics,list);panel.append(heading,body);
  const activity=main.querySelector('#main-activity');
  if(activity)activity.after(panel);else main.querySelector('#items-list')?.before(panel);
  panel.classList.add('hidden');
  let revision=0,pending=null,rendered=null,reviewDate='';
  const permitted=()=>currentUser?.can_view_delivery_schedule===true;
  const staff=installStaffSchedule(panel,{el,localDate,offset,permitted});
  const toggleAccess=()=>{
    const show=permitted();panel.classList.toggle('hidden',!show);
    staff.setAccess(show);
    if(!show){panel.open=false;count.textContent='';source.textContent='';metrics.replaceChildren();list.replaceChildren();rendered=null;reviewDate='';bar.classList.add('hidden');}
    return show;
  };
  const names=(people,{showCount=false}={})=>[...people]
    .sort((a,b)=>a.person.localeCompare(b.person,'ru'))
    .map(row=>row.person+(showCount&&row.camera_count>1?' ×'+row.camera_count:'')).join(', ');
  const hasCamera=row=>row.status==='delivery'&&row.camera_count>0;
  const needsCamera=row=>row.status==='delivery'&&row.camera_count===0&&!!row.venue;
  const needsReview=row=>row.status==='review'||(row.status==='delivery'&&!hasCamera(row)&&!needsCamera(row));
  const venueLabel=venue=>venue||'Площадку уточнить';
  const infoRow=(label,people,css='',showCount=false)=>{
    const row=el('div',('delivery-line '+css).trim());
    row.append(el('strong','delivery-line-label',label),el('span','delivery-names',names(people,{showCount})));
    return row;
  };
  function showVenuePlan(date,venue,people,notes,readOnly){
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
    if(readOnly){
      for(const [label,value] of [['Задачи по технике',notes?.equipment],['Расходники',notes?.supplies]]){
        if(!value)continue;
        const note=el('p','delivery-names',value);
        note.style.whiteSpace='pre-wrap';
        b.append(el('h3','delivery-detail-title',label),note);
      }
      return;
    }
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
  function renderMetrics(groups){
    const totals=[
      ['Привезти','bring','ready'],['На руках','held','held'],['Уточнить','review','review']
    ];
    metrics.replaceChildren();
    for(const [label,style,key] of totals){
      const value=groups.reduce((n,group)=>n+group[key].length,0);
      const cell=el('div','delivery-metric '+style);
      cell.append(el('strong','delivery-metric-value',String(value)),el('span','delivery-metric-label',label));
      metrics.append(cell);
    }
  }
  const draw=data=>{
    list.replaceChildren();
    metrics.replaceChildren();
    const entries=data.rows||[];
    const ignored=entries.filter(x=>x.status==='excluded');
    count.textContent='';
    reviewDate=data.review_date||'';
    bar.classList.toggle('hidden',!!reviewDate);
    if(reviewDate)day.value=reviewDate;
    source.textContent=reviewDate?reviewDate.split('-').reverse().join('.')+' · Шаблон на согласовании':'';
    if(!data.meta){
      list.append(el('p','delivery-muted','Загрузите график через кнопку Excel.'));
      return;
    }
    day.title=data.meta.source||'Дата доставки';
    if(!reviewDate&&data.meta.format_version<2){
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
      venue,people,
      ready:people.filter(needsCamera),held:people.filter(hasCamera),review:people.filter(needsReview)
    })).sort((a,b)=>b.ready.length-a.ready.length||
      Number(!a.venue)-Number(!b.venue)||a.venue.localeCompare(b.venue,'ru'));
    renderMetrics(ordered);
    const bring=ordered.reduce((n,g)=>n+g.ready.length,0);
    count.textContent='Привезти · '+bring;
    const otherVenues=el('details','delivery-ignored');
    const otherCount=ordered.filter(g=>!g.ready.length&&!g.held.length&&!g.review.length).length;
    otherVenues.append(el('summary','',`Другие площадки · ${otherCount}`));
    for(const {venue,people,ready,held,review} of ordered){
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
      title.append(el('span','delivery-venue-name',venueLabel(venue)));
      if(hasPlan){
        title.type='button';
        title.title='Состав и план · '+venueLabel(venue);
        title.setAttribute('aria-label',title.title);
        title.onclick=()=>showVenuePlan(data.date,venue,people,notesByVenue.get(venue),!!reviewDate);
      }
      heading.append(title);
      section.append(heading);
      if(ready.length)section.append(infoRow('Привезти',ready,'delivery-priority'));
      if(held.length)section.append(infoRow('На руках',held,'delivery-held',true));
      if(review.length)section.append(infoRow('Уточнить',review,'delivery-review'));
      (ready.length||held.length||review.length?list:otherVenues).append(section);
    }
    if(otherCount)list.append(otherVenues);
    if(!ordered.length)list.append(el('p','delivery-muted','Нет активных назначений.'));
    if(ignored.length){
      const skip=el('details','delivery-ignored');
      skip.append(el('summary','','Отсутствуют · '+ignored.length));
      skip.append(el('p','delivery-names',names(ignored)));list.append(skip);
    }
  };
  const reload=(force=false)=>{
    if(!toggleAccess())return;
    if(reviewDate&&rendered)return;
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
        const openSections=[...list.querySelectorAll('.delivery-ignored')].map(section=>section.open);
        draw(result);
        list.querySelectorAll('.delivery-ignored').forEach((section,index)=>{section.open=!!openSections[index]});
        rendered={date:reviewDate||selected,signature};
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
  const datePicker=el('div','delivery-date-picker hidden');
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
  const range=el('span','staff-week-range');
  bar.append(range);
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
    datePicker.classList.toggle('hidden',!!data.review_date);
    range.textContent=formatDate(data.start)+' – '+formatDate(data.end);
    if(!data.meta){
      content.append(el('p','delivery-muted','Загрузите график через Excel в блоке «Что привезти».'));
      return;
    }
    if(data.meta.format_version<2){
      content.append(el('p','delivery-muted','Загрузите Excel заново для полного состава.'));
    }
    const days=calendar.map((_,i)=>offset(data.start,i));
    const groups=new Map();
    for(const row of data.rows||[]){
      if(row.status==='excluded')continue;
      const venue=row.venue||'Площадка не указана';
      if(!groups.has(venue))groups.set(venue,new Map());
      const people=groups.get(venue), key=JSON.stringify([row.person,row.department]);
      if(!people.has(key))people.set(key,{name:row.person,department:row.department,days:new Map()});
      const shifts=people.get(key).days;
      if(!shifts.has(row.work_date))shifts.set(row.work_date,[]);
      shifts.get(row.work_date).push(row);
    }
    if(!groups.size){
      content.append(el('p','delivery-muted','На эту неделю назначений нет.'));
      return;
    }
    const colorOf=rows=>rows.find(r=>validColor(r.venue_color))?.venue_color||'';
    const marker=color=>{
      const node=el('span','staff-color');
      if(color)node.style.backgroundColor=color;
      node.setAttribute('aria-hidden','true');
      return node;
    };
    const ordered=[...groups].sort(([a],[b])=>
      Number(a==='Площадка не указана')-Number(b==='Площадка не указана')||a.localeCompare(b,'ru'));
    const fragment=document.createDocumentFragment();
    for(const [index,[venue,people]] of ordered.entries()){
      const section=el('details','staff-venue-group');section.open=index===0;
      const staff=[...people.values()].sort((a,b)=>a.name.localeCompare(b.name,'ru')||a.department.localeCompare(b.department,'ru'));
      const shifts=staff.flatMap(person=>[...person.days.values()].flat());
      const header=el('summary','staff-venue-header');
      header.append(marker(colorOf(shifts)),el('strong','staff-venue-title',venue),el('span','staff-venue-count',staff.length+' чел.'));
      section.append(header);
      const table=el('table','staff-grid');
      table.setAttribute('aria-label','График площадки '+venue);
      const thead=el('thead'),head=el('tr'),first=el('th','','Сотрудник');
      first.scope='col';head.append(first);
      days.forEach((day,i)=>{
        const th=el('th',day===selected?'staff-today':'');
        th.scope='col';th.title=formatDate(day);
        th.append(el('span','',calendar[i]),el('small','',day.slice(8,10)));head.append(th);
      });
      thead.append(head);table.append(thead);
      const grid=el('tbody'),detail=el('p','staff-selection');detail.setAttribute('aria-live','polite');
      let active;
      for(const person of staff){
        const tr=el('tr'),name=el('th','staff-name',person.name);
        name.scope='row';name.title=person.name+' · '+person.department;tr.append(name);
        for(const day of days){
          const td=el('td',day===selected?'staff-today':'');
          const rows=person.days.get(day)||[];
          if(rows.length){
            const slot=el('button','staff-slot');
            slot.type='button';slot.setAttribute('aria-pressed','false');
            const hasPhoto=rows.some(r=>r.status==='delivery');
            slot.append(marker(colorOf(rows)));
            if(hasPhoto)slot.append(el('span','staff-photo-flag','Ф'));
            const notes=[...new Set(rows.map(r=>r.assignment).filter(Boolean))];
            const description=person.name+' · '+formatDate(day)+' · '+venue+
              (hasPhoto?' · фотоаппарат':'')+(notes.length?' · '+notes.join(', '):'');
            slot.title=description;slot.setAttribute('aria-label',description);
            slot.onclick=()=>{
              active?.setAttribute('aria-pressed','false');
              active=slot;slot.setAttribute('aria-pressed','true');
              detail.textContent=description;
            };
            td.append(slot);
          }else td.append(el('span','staff-empty','—'));
          tr.append(td);
        }
        grid.append(tr);
      }
      table.append(grid);
      const scroll=el('div','staff-scroll');scroll.append(table);
      section.append(scroll,detail);fragment.append(section);
    }
    content.append(fragment);
  }
  async function load(force=false){
    if(!panel.open||!permitted())return;
    const day=dateInput.value||localDate();
    dateInput.value=day;
    if(!force&&loaded===day)return;
    loaded='';
    range.textContent='';
    const revision=++request;
    content.replaceChildren(el('p','delivery-muted','Загружаем график…'));
    try{
      const result=await api('/api/delivery-schedule/week?date='+encodeURIComponent(day),{cache:'no-store'});
      if(revision!==request||!panel.open||!permitted())return;
      draw(result,day);
      if(result.review_date)dateInput.value=result.review_date;
      loaded=dateInput.value;
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
        range.textContent='';
        datePicker.classList.add('hidden');
        ++request;
      }
    }
  };
}
