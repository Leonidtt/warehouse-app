/* Beta: staff rota and camera delivery plan. */
function scheduleWorkbookStorage(owner,file){
  return new Promise((resolve,reject)=>{
    const open=indexedDB.open('warehouse-beta-schedules',1);
    open.onupgradeneeded=()=>open.result.createObjectStore('workbooks');
    open.onerror=()=>reject(open.error);
    open.onsuccess=()=>{
      const db=open.result;
      const write=file!==undefined;
      const transaction=db.transaction('workbooks',write?'readwrite':'readonly');
      const store=transaction.objectStore('workbooks');
      const operation=write?store.put(file,owner):store.get(owner);
      transaction.oncomplete=()=>{db.close();resolve(operation.result);};
      transaction.onabort=()=>{db.close();reject(transaction.error);};
    };
  });
}

function installDeliverySchedule(){
  const main=document.getElementById('screen-main');
  if(!main||document.getElementById('camera-schedule-entry'))return;
  const el=(tag,cls,text)=>{
    const node=document.createElement(tag);
    if(cls)node.className=cls;
    if(text!==undefined)node.textContent=text;
    return node;
  };
  const localDate=()=>{
    const pieces=Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Moscow',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
    const val=key=>pieces.find(piece=>piece.type===key)?.value;
    return [val('year'),val('month'),val('day')].join('-');
  };
  const offset=(iso,n)=>{
    const day=new Date(iso+'T12:00:00Z');
    day.setUTCDate(day.getUTCDate()+n);
    return day.toISOString().slice(0,10);
  };
  const chooseDay=(workbook,preferred)=>{
    const weeks=Object.entries(workbook.weeks).sort(([a],[b])=>a.localeCompare(b));
    const covers=day=>weeks.some(([start,end])=>day>=start&&day<=end);
    const today=localDate();
    if(covers(preferred))return preferred;
    if(covers(today))return today;
    return (weeks.filter(([start])=>start<=today).at(-1)||weeks[0])[0];
  };
  const permitted=()=>currentUser?.can_view_delivery_schedule===true;
  const fileInput=el('input','hidden');
  fileInput.type='file';
  fileInput.accept='.xlsx';
  main.append(fileInput);
  const readWorkbook=file=>{
    const data=new FormData();
    data.append('file',file);
    return api('/api/delivery-schedule/week-preview',{method:'POST',body:data});
  };

  let owner=null,workbookFile=null,uploadTarget=null,uploading=false,accountRequest=0;
  function chooseFile(target){
    if(!permitted()||uploading)return;
    uploadTarget=target;
    fileInput.click();
  }
  function datePreference(section,value){
    const key='warehouse-beta-schedule-day:'+section+':'+owner;
    try{
      if(value)localStorage.setItem(key,value);
      else{
        const saved=localStorage.getItem(key);
        if(/^\d{4}-\d{2}-\d{2}$/.test(saved||''))return saved;
      }
    }catch{}
    return '';
  }
  const options={el,localDate,offset,chooseDay,permitted,chooseFile,readWorkbook,datePreference};
  const camera=installCameraSchedule(options);
  const activity=main.querySelector('#main-activity');
  if(activity)activity.after(camera.panel);else main.querySelector('#items-list')?.before(camera.panel);
  const staff=installStaffSchedule(camera.panel,options);
  const panels=[camera,staff];
  function useWorkbook(file,data){
    workbookFile=file;
    for(const panel of panels)panel.setWorkbook(file,data);
  }
  function updateAccess(){
    const next=permitted()?String(currentUser.tg_id):null;
    for(const panel of panels)panel.setAccess(next!==null);
    if(next===owner)return;
    owner=next;
    const revision=++accountRequest;
    uploading=false;
    for(const panel of panels)panel.setUploading(false);
    useWorkbook(null,null);
    if(next!==null){
      scheduleWorkbookStorage(next).then(saved=>{
        if(saved&&revision===accountRequest&&!workbookFile)useWorkbook(saved,null);
      }).catch(()=>{});
    }
  }
  fileInput.onchange=async()=>{
    const file=fileInput.files[0];
    const target=uploadTarget;
    fileInput.value='';
    if(!file||!target||!permitted())return;
    if(!/\.xlsx$/i.test(file.name)||file.size>8_000_000){
      target.notifyUpload('Выберите файл .xlsx размером до 8 МБ.');
      return;
    }
    const revision=accountRequest;
    const account=owner;
    uploading=true;
    for(const panel of panels)panel.setUploading(true);
    target.notifyUpload('Загружаем Excel…');
    try{
      const data=await readWorkbook(file);
      if(revision!==accountRequest||!permitted())return;
      useWorkbook(file,data);
      target.notifyUpload('');
      try{
        await scheduleWorkbookStorage(account,file);
      }catch{
        if(revision===accountRequest)target.notifyUpload('Файл открыт. Браузер не смог сохранить его для следующего входа.');
      }
    }catch(error){
      if(revision===accountRequest)target.notifyUpload(error.networkError?'Нет связи со складом. Повторите загрузку.':error.message);
    }finally{
      if(revision===accountRequest){
        uploading=false;
        for(const panel of panels)panel.setUploading(false);
      }
    }
  };
  const initBefore=init;
  init=async()=>{const result=await initBefore();updateAccess();return result;};
  const loadBefore=loadItems;
  loadItems=async(...args)=>{const result=await loadBefore(...args);updateAccess();return result;};
}

function installCameraSchedule({el,localDate,offset,chooseDay,permitted,chooseFile,datePreference}){
  const panel=el('details','delivery-panel camera-schedule-panel hidden');
  panel.id='camera-schedule-entry';
  const heading=el('summary','delivery-heading');
  heading.append(el('strong','','Фотоаппараты по графику'));
  const body=el('div','delivery-body');
  const form=el('form','camera-schedule-form');
  const dayLabel=el('label','','Дата смены');
  const day=el('input');
  day.type='date';
  day.required=true;
  dayLabel.append(day);
  const uploadArea=el('div','camera-workbook-control');
  const upload=el('button','delivery-control delivery-excel','Загрузить Excel');
  upload.type='button';
  const filename=el('span','schedule-filename');
  uploadArea.append(upload,filename);
  const submit=el('button','','Сверить с выдачами');
  submit.type='submit';
  submit.disabled=true;
  const uploadStatus=el('p','delivery-source');
  uploadStatus.setAttribute('role','status');
  const status=el('p','camera-schedule-status');
  status.setAttribute('role','status');
  const result=el('div','camera-schedule-result');
  form.append(dayLabel,uploadArea,submit);
  body.append(form,uploadStatus,status,result);
  panel.append(heading,body);
  let workbook=null,uploading=false,comparing=false,revision=0;
  const updateControls=()=>{
    upload.disabled=uploading;
    day.disabled=comparing;
    submit.disabled=!workbook||comparing||uploading;
  };

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
    const card=el('article','camera-schedule-card');
    const hero=el('header','camera-schedule-hero');
    const shiftDate=el('time','camera-schedule-date',
      'Москва / '+new Intl.DateTimeFormat('ru-RU',{weekday:'long',day:'numeric',month:'long',timeZone:'UTC'})
        .format(new Date(report.date+'T12:00:00Z')));
    shiftDate.dateTime=report.date;
    const icon=el('span','camera-schedule-icon');
    icon.setAttribute('aria-hidden','true');
    icon.append(el('span'));
    hero.append(shiftDate,el('h3','','Фотоаппараты'),el('p','','Выдача и доставка по площадкам'),icon);
    const exclusions=report.excluded||[];
    if(exclusions.length)hero.append(el('p','camera-exclusion-pill','Исключения: '+exclusions.map(p=>p.name).join(', ')));

    const body=el('div','camera-schedule-body');
    const summary=el('div','camera-schedule-summary');
    const stats=[
      [report.deliver,'Камер привезти','delivery'],
      [report.held,'Камер на руках','held'],
      [report.delivery_venues,'Площадок доставки','locations'],
    ];
    for(const [count,label,kind] of stats){
      const stat=el('div','camera-schedule-stat camera-schedule-'+kind);
      stat.append(el('strong','',count),el('span','',label));
      summary.append(stat);
    }
    const sectionHeader=el('div','camera-schedule-section-title');
    const count=report.deliver+report.held;
    const peopleLabel=new Intl.PluralRules('ru').select(count)==='few'?'человека':'человек';
    sectionHeader.append(el('h4','','Распределение по площадкам'),el('span','',count+' '+peopleLabel));
    body.append(summary,sectionHeader);

    if(report.venues.length){
      const table=el('table','camera-schedule-table');
      table.setAttribute('aria-label','Распределение по площадкам');
      const head=el('thead'),labels=el('tr');
      for(const [label,kind] of [['Площадка','locations'],['Привезти','delivery'],['Уже на руках','held']]){
        const cell=el('th','camera-schedule-'+kind,label);
        cell.scope='col';
        labels.append(cell);
      }
      head.append(labels);
      const rows=el('tbody');
      for(const venue of report.venues){
        const row=el('tr');
        const name=el('th','',venue.name);
        name.scope='row';
        row.append(name);
        for(const [people,kind] of [[venue.deliver,'delivery'],[venue.held,'held']]){
          const cell=el('td','camera-schedule-'+kind);
          if(people.length){
            const cellContent=el('div','camera-schedule-people');
            cellContent.append(el('span','camera-schedule-badge',people.length),
              el('span','',people.map(person=>person.name+(person.manual?' *':'')).join(', ')));
            cell.append(cellContent);
          }else{
            cell.textContent='—';
          }
          row.append(cell);
        }
        rows.append(row);
      }
      table.append(head,rows);
      const frame=el('div','camera-schedule-table-frame');
      frame.append(table);
      body.append(frame);
    }else{
      body.append(el('p','camera-schedule-empty','На эту дату нет подтверждённых назначений.'));
    }
    for(const venue of report.venues){
      for(const person of venue.deliver){
        const camera=person.suggested_camera;
        if(!camera) continue;
        const note=el('p','camera-schedule-stock');
        note.append(el('strong','',person.name),el('span','',camera.model+' ('+camera.code+') числится на складе'));
        body.append(note);
      }
    }
    body.append(el('p','camera-schedule-freshness','По открытым выдачам Беты на момент сверки'));
    if((report.corrections||[]).length)body.append(el('p','camera-schedule-freshness','* Ручная корректировка отчёта, без изменения выдачи'));
    card.append(hero,body);
    result.replaceChildren(card);
    if(report.unmatched.length){
      const details=el('details','camera-schedule-review');
      details.append(el('summary','','Требуют проверки · '+report.unmatched.length));
      const list=el('ul');
      for(const person of report.unmatched) list.append(el('li','',person.name+' — '+person.reason));
      details.append(list);
      result.append(details);
    }
    const corrections=el('details','camera-correction-box');
    corrections.append(el('summary','','Исключения · '+exclusions.length+' / Корректировки · '+(report.corrections||[]).length));
    const correctionBody=el('div','camera-correction-body');
    for(const person of exclusions)correctionBody.append(el('p','camera-excluded-name',person.name+' — не учитывать'+(person.venue?' · '+person.venue:'')));
    if(currentUser?.role==='admin'&&!currentUser?.preview_role){
      const candidates=new Set([...report.venues.flatMap(v=>[...v.deliver,...v.held]).map(p=>p.name),...report.unmatched.map(p=>p.name),...exclusions.map(p=>p.name)]);
      const name=el('select'),action=el('select'),venue=el('select');
      name.setAttribute('aria-label','Сотрудник');
      action.setAttribute('aria-label','Корректировка');
      venue.setAttribute('aria-label','Новая площадка');
      name.add(new Option('Выберите сотрудника',''));
      [...candidates].sort((a,b)=>a.localeCompare(b,'ru')).forEach(n=>name.add(new Option(n,n)));
      for(const [v,t] of [['exclude','Не учитывать на эту дату'],['held','Камера уже на руках'],['delivery','Нужно привезти камеру'],['venue','Изменить площадку'],['reset','Сбросить ручные изменения']])action.add(new Option(t,v));
      venue.add(new Option('Выберите площадку',''));
      for(const v of report.venues)venue.add(new Option(v.name,v.name));
      for(const p of exclusions)if(p.venue&&!Array.from(venue.options).some(o=>o.value===p.venue))venue.add(new Option(p.venue,p.venue));
      venue.classList.add('hidden');
      const save=el('button','secondary','Применить');
      save.type='button';
      save.disabled=true;
      const update=()=>{venue.classList.toggle('hidden',action.value!=='venue');save.disabled=comparing||!name.value||(action.value==='venue'&&!venue.value);};
      name.onchange=action.onchange=venue.onchange=update;
      save.onclick=async()=>{
        if(comparing||!permitted()||!workbook||day.value!==report.date||!name.value)return;
        const req=++revision;
        const data=new FormData();
        data.append('day',report.date);data.append('file',workbook);
        data.append('name',name.value);data.append('action',action.value);data.append('venue',venue.value);
        comparing=true;updateControls();update();
        status.textContent='Сохраняем корректировку…';
        try{
          const fresh=await api('/api/delivery-schedule/camera-correction',{method:'POST',body:data});
          if(req!==revision||!permitted())return;
          renderCameraSchedule(result,fresh);
          result.querySelector('.camera-correction-box').open=true;
          status.textContent='Корректировка сохранена на выбранную дату.';
        }catch(e){if(req===revision)status.textContent=e.message;}
        finally{if(req===revision){comparing=false;updateControls();update();}}
      };
      correctionBody.append(el('p','delivery-muted','Изменения действуют только на выбранную дату и не изменяют складские выдачи.'),name,action,venue,save);
    }
    corrections.append(correctionBody);
    result.append(corrections);
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
      if(exclusions.length)lines.push('','Исключены: '+exclusions.map(p=>p.name).join(', '));
      if((report.corrections||[]).length)lines.push('','Ручные корректировки: '+report.corrections.map(p=>p.name).join(', '));
      return copyText(lines.join('\n'));
    };
    result.append(copy);
  }

  function resetReport(){
    ++revision;
    comparing=false;
    result.replaceChildren();
    status.textContent='';
    updateControls();
  }
  async function compare(){
    if(!panel.open||!permitted()||!workbook||!day.value||uploading||comparing)return;
    const request=++revision;
    const data=new FormData();
    data.append('day',day.value);
    data.append('file',workbook);
    comparing=true;
    updateControls();
    status.textContent='Сверяем график с открытыми выдачами…';
    try{
      const report=await api('/api/delivery-schedule/camera-preview',{method:'POST',body:data});
      if(request!==revision||!permitted())return;
      renderCameraSchedule(result,report);
      status.textContent='';
    }catch(error){
      if(request===revision){
        result.replaceChildren();
        status.textContent=error.networkError?'Нет связи со складом. Повторите сверку.':error.message;
      }
    }finally{
      if(request===revision){
        comparing=false;
        updateControls();
      }
    }
  }
  form.onsubmit=event=>{event.preventDefault();compare();};
  day.onchange=()=>{
    if(day.value)datePreference('camera',day.value);
    resetReport();
  };
  panel.addEventListener('toggle',()=>{
    if(panel.open&&!result.firstChild)compare();
  });
  const controller={
    panel,
    setAccess(show){
      panel.classList.toggle('hidden',!show);
      if(!show)panel.open=false;
    },
    setWorkbook(file,data){
      workbook=file;
      filename.textContent=file?.name||'';
      filename.title=filename.textContent;
      day.value=datePreference('camera')||offset(localDate(),1);
      if(data)day.value=chooseDay(data,day.value);
      if(file&&day.value)datePreference('camera',day.value);
      uploadStatus.textContent='';
      resetReport();
      if(panel.open)compare();
    },
    setUploading(value){
      uploading=value;
      updateControls();
      if(!uploading&&panel.open&&!result.firstChild)compare();
    },
    notifyUpload(message){uploadStatus.textContent=message;},
  };
  upload.onclick=()=>chooseFile(controller);
  return controller;
}

function installStaffSchedule(anchor,{el,localDate,offset,chooseDay,permitted,chooseFile,readWorkbook,datePreference}){
  const panel=el('details','delivery-panel staff-panel hidden');
  panel.id='staff-schedule-panel';
  const heading=el('summary','delivery-heading');
  heading.append(el('strong','','График сотрудников'));
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
  dateInput.setAttribute('aria-label','Дата недели графика');
  datePicker.append(previous,dateInput,next);
  const upload=el('button','delivery-control delivery-excel','Загрузить Excel');
  upload.type='button';
  const range=el('span','staff-week-range');
  bar.append(datePicker,upload,range);
  const filename=el('p','delivery-source schedule-filename');
  const notice=el('p','delivery-source');
  notice.setAttribute('role','status');
  const content=el('div','staff-content');
  body.append(bar,filename,notice,content);
  panel.append(heading,body);
  anchor.before(panel);

  const calendar=['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];
  const formatDate=iso=>iso.slice(8,10)+'.'+iso.slice(5,7);
  const colorOf=row=>/^#[0-9a-f]{6}$/i.test(row.venue_color||'')?row.venue_color.toUpperCase():'';
  const venueOf=row=>row.venue||'Площадка не указана';
  let request=0,loaded='',workbook=null,uploaded=null,uploading=false;
  let venueFilter='',colorFilter=null;

  function marker(color){
    const node=el('span','staff-color');
    if(color)node.style.backgroundColor=color;
    node.setAttribute('aria-hidden','true');
    return node;
  }

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
    const shifts=(data.rows||[]).filter(row=>row.status!=='excluded');
    if(!shifts.length){
      content.append(el('p','delivery-muted','На эту неделю назначений нет.'));
      return;
    }
    const venues=[...new Set(shifts.map(venueOf))].sort((a,b)=>a.localeCompare(b,'ru'));
    const colors=new Map();
    for(const shift of shifts){
      const color=colorOf(shift);
      if(!colors.has(color))colors.set(color,new Set());
      colors.get(color).add(venueOf(shift));
    }
    if(!venues.includes(venueFilter))venueFilter='';
    if(!colors.has(colorFilter))colorFilter=null;

    const card=el('section','staff-table-card');
    const filters=el('div','staff-filters');
    const venueLabel=el('label','staff-venue-filter','Площадка');
    const venueSelect=el('select');
    venueSelect.setAttribute('aria-label','Площадка');
    venueSelect.add(new Option('Все площадки',''));
    for(const venue of venues)venueSelect.add(new Option(venue,venue));
    venueSelect.value=venueFilter;
    venueLabel.append(venueSelect);
    const colorField=el('fieldset','staff-color-filter');
    const colorButtons=el('div','staff-color-options');
    colorField.append(el('legend','','Цвет смены'),colorButtons);
    const filterButtons=new Map();
    const choices=[[null,'Все цвета'], ...[...colors].map(([color,names])=>[
      color,color?[...names].sort((a,b)=>a.localeCompare(b,'ru')).join(', ')+' · '+color:'Без цвета'
    ])];
    for(const [color,label] of choices){
      const button=el('button','staff-filter-chip',color===null?'Все':undefined);
      button.type='button';
      button.title=label;
      button.setAttribute('aria-label',label);
      button.setAttribute('aria-pressed',String(color===colorFilter));
      if(color!==null)button.append(marker(color));
      button.onclick=()=>{
        colorFilter=color;
        for(const [value,control] of filterButtons)control.setAttribute('aria-pressed',String(value===colorFilter));
        drawRows();
      };
      filterButtons.set(color,button);
      colorButtons.append(button);
    }
    venueSelect.onchange=()=>{venueFilter=venueSelect.value;drawRows();};
    filters.append(venueLabel,colorField);
    const tableContent=el('div','staff-table-content');
    card.append(filters,tableContent);
    content.append(card);

    function drawRows(){
      const people=new Map();
      for(const shift of shifts){
        if(venueFilter&&venueOf(shift)!==venueFilter)continue;
        if(colorFilter!==null&&colorOf(shift)!==colorFilter)continue;
        const key=JSON.stringify([shift.person,shift.department]);
        if(!people.has(key))people.set(key,{name:shift.person,department:shift.department,days:new Map()});
        const days=people.get(key).days;
        if(!days.has(shift.work_date))days.set(shift.work_date,[]);
        days.get(shift.work_date).push(shift);
      }
      const staff=[...people.values()].sort((a,b)=>a.name.localeCompare(b.name,'ru')||a.department.localeCompare(b.department,'ru'));
      const count=staff.length;
      const noun=new Intl.PluralRules('ru').select(count)==='few'?'человека':'человек';
      const total=el('p','staff-total',count+' '+noun);
      total.setAttribute('role','status');
      tableContent.replaceChildren(total);
      if(!count){
        tableContent.append(el('p','delivery-muted','Нет смен по выбранным фильтрам.'));
        return;
      }

      const scroll=el('div','staff-scroll');
      const table=el('table','staff-grid');
      table.setAttribute('aria-label','График сотрудников на неделю');
      const thead=el('thead'),header=el('tr'),nameHeader=el('th','','Сотрудник');
      nameHeader.scope='col';
      header.append(nameHeader);
      const days=calendar.map((_,i)=>offset(data.start,i));
      days.forEach((day,i)=>{
        const th=el('th',day===selected?'staff-today':'');
        th.scope='col';
        th.title=formatDate(day);
        th.append(el('span','',calendar[i]),el('small','',day.slice(8,10)));
        header.append(th);
      });
      thead.append(header);
      const grid=el('tbody'),detail=el('p','staff-selection');
      detail.setAttribute('aria-live','polite');
      let active;
      for(const person of staff){
        const row=el('tr'),name=el('th','staff-name',person.name);
        name.scope='row';
        name.title=[person.name,person.department].filter(Boolean).join(' · ');
        row.append(name);
        for(const day of days){
          const cell=el('td',day===selected?'staff-today':'');
          const entries=person.days.get(day)||[];
          if(entries.length){
            const slot=el('button','staff-slot');
            slot.type='button';
            slot.setAttribute('aria-pressed','false');
            const marks=new Set(entries.map(colorOf));
            for(const color of marks)slot.append(marker(color));
            if(entries.some(entry=>entry.status==='delivery'))slot.append(el('span','staff-photo-flag','Ф'));
            const descriptions=[...new Set(entries.map(entry=>[
              venueOf(entry),entry.status==='delivery'?'Фотоаппарат':'',entry.assignment
            ].filter(Boolean).join(' · ')))];
            const description=[person.name,formatDate(day),...descriptions].join(' · ');
            slot.title=description;
            slot.setAttribute('aria-label',description);
            slot.onclick=()=>{
              active?.setAttribute('aria-pressed','false');
              active=slot;
              slot.setAttribute('aria-pressed','true');
              detail.textContent=description;
            };
            cell.append(slot);
          }else cell.append(el('span','staff-empty','—'));
          row.append(cell);
        }
        grid.append(row);
      }
      table.append(thead,grid);
      scroll.append(table);
      tableContent.append(scroll,detail);
    }

    drawRows();
  }

  async function load(force=false){
    if(!panel.open||!permitted()||uploading)return;
    let day=dateInput.value||localDate();
    dateInput.value=day;
    if(!force&&loaded===day)return;
    const revision=++request;
    if(!uploaded){
      range.textContent='';
      content.replaceChildren(el('p','delivery-muted','Загружаем график…'));
    }
    try{
      if(workbook){
        if(!uploaded){
          const data=await readWorkbook(workbook);
          if(revision!==request||!panel.open||!permitted())return;
          uploaded=data;
          day=chooseDay(data,day);
          dateInput.value=day;
        }
        const daysFromMonday=(new Date(day+'T12:00:00Z').getUTCDay()+6)%7;
        const start=offset(day,-daysFromMonday),end=offset(start,6);
        draw({start,end,meta:uploaded,rows:uploaded.rows.filter(row=>row.work_date>=start&&row.work_date<=end)},day);
        datePreference('staff',day);
      }else{
        const data=await api('/api/delivery-schedule/week?date='+encodeURIComponent(day),{cache:'no-store'});
        if(revision!==request||!panel.open||!permitted())return;
        draw(data,data.review_date||day);
        if(data.review_date)dateInput.value=data.review_date;
      }
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
  const controller={
    setAccess(show){
      panel.classList.toggle('hidden',!show);
      if(!show)panel.open=false;
    },
    setWorkbook(file,data){
      ++request;
      workbook=file;
      uploaded=data;
      loaded='';
      venueFilter='';
      colorFilter=null;
      datePicker.classList.add('hidden');
      range.textContent='';
      content.replaceChildren();
      filename.textContent=file?.name||'';
      notice.textContent='';
      dateInput.value=datePreference('staff')||localDate();
      if(data)dateInput.value=chooseDay(data,dateInput.value);
      if(panel.open)load();
    },
    setUploading(value){
      uploading=value;
      upload.disabled=value;
      if(!uploading&&panel.open)load();
    },
    notifyUpload(message){notice.textContent=message;},
  };
  upload.onclick=()=>chooseFile(controller);
  return controller;
}
