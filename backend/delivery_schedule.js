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
  const permitted=()=>currentUser?.can_view_delivery_schedule===true;
  const entry=el('button','secondary camera-schedule-entry hidden','Фотоаппараты по графику');
  entry.id='camera-schedule-entry';
  entry.type='button';
  entry.onclick=openCameraSchedule;
  const activity=main.querySelector('#main-activity');
  if(activity)activity.after(entry);else main.querySelector('#items-list')?.before(entry);
  const staff=installStaffSchedule(entry,{el,localDate,offset,permitted});
  function updateAccess(){
    entry.classList.toggle('hidden',!permitted());
    staff.setAccess(permitted());
  }
  const initBefore=init;
  init=async()=>{const result=await initBefore();updateAccess();return result;};
  const loadBefore=loadItems;
  loadItems=async(...args)=>{const result=await loadBefore(...args);updateAccess();return result;};

  function cameraScheduleDate(day){
    return new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'})
      .format(new Date(day+'T12:00:00Z'));
  }

  function cameraSchedulePerson(person){
    const camera=person.suggested_camera;
    return camera ? person.name+' · '+camera.code+' ('+camera.model+') на складе' : person.name;
  }

  function renderCameraSchedule(result, report){
    const date=cameraScheduleDate(report.date);
    const summary=el('div','camera-schedule-summary');
    const stats=[
      [report.deliver,'Привезти','delivery'],
      [report.held,'На руках','held'],
      [report.delivery_venues,'Площадок доставки','locations'],
    ];
    for(const [count,label,kind] of stats){
      const stat=el('div','camera-schedule-stat camera-schedule-'+kind);
      stat.append(el('strong','',count),el('span','',label));
      summary.append(stat);
    }
    const title=el('h3','','Москва · '+date);
    const freshness=el('p','meta','Открытые выдачи на момент сверки');
    const venues=el('div','camera-schedule-venues');
    for(const venue of report.venues){
      const card=el('section','camera-schedule-venue');
      const columns=el('div','camera-schedule-columns');
      for(const [label,people,kind] of [['Привезти',venue.deliver,'delivery'],['На руках',venue.held,'held']]){
        const section=el('div','camera-schedule-'+kind);
        section.append(el('h5','',label+' · '+people.length));
        if(people.length){
          const list=el('ul');
          for(const person of people) list.append(el('li','',cameraSchedulePerson(person)));
          section.append(list);
        }
        columns.append(section);
      }
      card.append(el('h4','',venue.name),columns);
      venues.append(card);
    }
    if(!report.venues.length) venues.append(el('p','meta','На эту дату нет подтверждённых назначений.'));
    result.replaceChildren(title,freshness,summary,venues);
    if(report.unmatched.length){
      const details=el('details','camera-schedule-review');
      details.append(el('summary','','Требуют проверки · '+report.unmatched.length));
      const list=el('ul');
      for(const person of report.unmatched) list.append(el('li','',person.name+' — '+person.reason));
      details.append(list);
      result.append(details);
    }
    const copy=el('button','secondary','Скопировать сводку');
    copy.type='button';
    copy.onclick=()=>{
      const lines=['Фотоаппараты · Москва · '+date,
        'Привезти: '+report.deliver+' · На руках: '+report.held+' · Площадок доставки: '+report.delivery_venues];
      for(const venue of report.venues){
        lines.push('',venue.name);
        if(venue.deliver.length) lines.push('Привезти ('+venue.deliver.length+'): '+venue.deliver.map(cameraSchedulePerson).join(', '));
        if(venue.held.length) lines.push('На руках ('+venue.held.length+'): '+venue.held.map(person=>person.name).join(', '));
      }
      if(report.unmatched.length){
        lines.push('','Требуют проверки');
        for(const person of report.unmatched) lines.push(person.name+' — '+person.reason);
      }
      return copyText(lines.join('\n'));
    };
    result.append(copy);
  }

  function openCameraSchedule(){
    if(!permitted()) return;
    const {o,b}=overlay17('Фотоаппараты по графику');
    b.classList.add('camera-schedule-dialog');
    const form=el('form','camera-schedule-form');
    const dayLabel=el('label','','Дата смены');
    const day=el('input');
    day.type='date';day.name='day';day.required=true;
    day.value=offset(localDate(),1);
    dayLabel.append(day);
    const fileLabel=el('label','','График МСК (.xlsx)');
    const file=el('input');
    file.type='file';file.name='file';file.required=true;file.accept='.xlsx';
    fileLabel.append(file);
    const submit=el('button','','Сверить с выдачами');
    submit.type='submit';
    const status=el('p','camera-schedule-status');
    status.setAttribute('role','status');
    const result=el('div','camera-schedule-result');
    form.append(dayLabel,fileLabel,submit);
    b.append(form,status,result);
    form.addEventListener('change',()=>{
      result.replaceChildren();
      status.textContent='';
    });
    form.addEventListener('submit',async event=>{
      event.preventDefault();
      if(submit.disabled) return;
      result.replaceChildren();
      if(file.files[0].size>8_000_000){
        status.textContent='Файл должен быть не больше 8 МБ.';
        return;
      }
      const data=new FormData(form);
      submit.disabled=day.disabled=file.disabled=true;
      status.textContent='Сверяем график с открытыми выдачами…';
      try{
        const report=await api('/api/delivery-schedule/camera-preview',{method:'POST',body:data});
        if(o.isConnected&&permitted()){
          renderCameraSchedule(result,report);
          status.textContent='';
        }
      }catch(error){
        status.textContent=error.networkError?'Нет связи со складом. Повторите сверку.':error.message;
      }finally{
        submit.disabled=day.disabled=file.disabled=false;
      }
    });
  }

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
  const upload=el('button','delivery-control delivery-excel','Загрузить Excel');
  upload.type='button';
  const file=el('input','hidden');
  file.type='file';
  file.accept='.xlsx';
  bar.append(datePicker,upload,file);
  const range=el('span','staff-week-range');
  bar.append(range);
  const content=el('div','staff-content');
  body.append(bar,content);
  panel.append(heading,body);
  anchor.before(panel);
  const calendar=['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];
  const formatDate=iso=>iso.slice(8,10)+'.'+iso.slice(5,7);
  const validColor=color=>/^#[0-9a-f]{6}$/i.test(color||'');
  const notice=el('p','delivery-source');
  notice.setAttribute('role','status');
  content.before(notice);
  let request=0,loaded='',uploaded=null;
  let uploading=false;

  function draw(data,selected){
    content.replaceChildren();
    datePicker.classList.toggle('hidden',!!data.review_date);
    range.textContent=formatDate(data.start)+' – '+formatDate(data.end);
    if(!data.meta){
      content.append(el('p','delivery-muted','Загрузите Excel, чтобы посмотреть неделю.'));
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
    if(!panel.open||!permitted()||uploading)return;
    const day=dateInput.value||localDate();
    dateInput.value=day;
    if(!force&&loaded===day)return;
    if(uploaded){
      const daysFromMonday=(new Date(day+'T12:00:00Z').getUTCDay()+6)%7;
      const start=offset(day,-daysFromMonday);
      const end=offset(start,6);
      draw({start,end,meta:uploaded,rows:uploaded.rows.filter(row=>row.work_date>=start&&row.work_date<=end)},day);
      loaded=day;
      return;
    }
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
  upload.onclick=()=>file.click();
  file.onchange=async()=>{
    const selected=file.files[0];
    if(!selected||!permitted())return;
    if(selected.size>8_000_000){
      notice.textContent='Файл должен быть не больше 8 МБ.';
      file.value='';
      return;
    }
    const revision=++request;
    const data=new FormData();
    data.append('file',selected);
    upload.disabled=uploading=true;
    notice.textContent='Загружаем Excel…';
    try{
      const workbook=await api('/api/delivery-schedule/week-preview',{method:'POST',body:data});
      if(revision!==request||!permitted())return;
      uploaded=workbook;
      const weeks=Object.entries(workbook.weeks).sort(([first],[second])=>first.localeCompare(second));
      const today=localDate();
      dateInput.value=weeks.some(([start,end])=>today>=start&&today<=end)
        ? today : (weeks.filter(([start])=>start<=today).at(-1)||weeks[0])[0];
      notice.textContent='График из загруженного файла';
    }catch(error){
      if(revision===request)notice.textContent=error.networkError?'Нет связи со складом. Повторите загрузку.':error.message;
    }finally{
      upload.disabled=uploading=false;
      file.value='';
      if(revision===request&&permitted())load(true);
    }
  };
  const step=days=>{dateInput.value=offset(dateInput.value||localDate(),days);load();};
  previous.onclick=()=>step(-7);
  next.onclick=()=>step(7);
  dateInput.onchange=()=>load();
  panel.addEventListener('toggle',()=>load());
  return {
    setAccess(show){
      panel.classList.toggle('hidden',!show);
      if(!show){
        panel.open=false;
        content.replaceChildren();
        loaded='';
        uploaded=null;
        notice.textContent='';
        range.textContent='';
        datePicker.classList.add('hidden');
        ++request;
      }
    }
  };
}
