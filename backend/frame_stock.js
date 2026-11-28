(function(){
  function install(){
    const host=document.querySelector('#screen-rooms .warehouse-room-actions');
    if(!host||document.getElementById('frame-stock-button'))return;
    const launch=document.createElement('button');launch.id='frame-stock-button';launch.className='secondary';launch.textContent='Рамки';host.after(launch);launch.style.cssText='width:calc(100% - 32px);margin:8px 16px';
    launch.onclick=()=>{if(currentUser?.role==='admin')open()};
    for(const [name,positions] of [['Винил',['vinyl']],['Фотобумага',['paper46','paper68']]]){
      const button=launch.cloneNode(false);button.id='material-'+positions[0];button.textContent=name;launch.parentNode.insertBefore(button,launch.nextSibling);button.onclick=()=>{if(currentUser?.role==='admin')openMaterials(name,positions)};
    }
  }
  const fmt=n=>n==null?'Не посчитано':Number(n).toLocaleString('ru-RU');
  const date=s=>s?new Date(s).toLocaleString('ru-RU',{timeZone:'Europe/Moscow'}):'—';
  const kinds={inventory:'Инвентаризация',receipt:'Поступление',issue:'Выдача',transfer:'На площадку',unpack:'Распаковка',minimum:'Мин. остаток'};
  const label=r=>r.group+' · '+r.orientation;
  const el=(tag,cls,text)=>{
    const node=document.createElement(tag);
    if(cls)node.className=cls;
    if(text!==undefined)node.textContent=text;
    return node;
  };
  const icons={
    inventory:'<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4m8-4v4M4 10h16m-12 5 2 2 5-5"/>',
    minimum:'<path d="M4 19h16M7 15v-3m5 3V5m5 10V8"/>',
    receipt:'<path d="M12 3v13m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    issue:'<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',
    transfer:'<path d="M3 12h17m-6-6 6 6-6 6"/>',
    unpack:'<path d="m4 8 8-4 8 4v11H4zm0 0 8 4 8-4m-8 4v7"/>',
    cut:'<circle cx="6" cy="7" r="3"/><circle cx="6" cy="17" r="3"/><path d="m8.5 8.5 10.5 9m-10.5-2L19 6"/>',
    copy:'<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    close:'<path d="m6 6 12 12m0-12L6 18"/>'
  };
  function icon(kind){
    const node=el('span','r191-line-icon');
    node.setAttribute('aria-hidden','true');
    node.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">'+icons[kind]+'</svg>';
    return node;
  }
  function sheet(title,form=false){
    const dialog=overlay17(title);
    dialog.b.classList.add('beta-supply-sheet');
    if(form)dialog.b.classList.add('beta-supply-form');
    const close=dialog.b.firstElementChild.querySelector('button');
    close.classList.add('beta-supply-close');
    close.setAttribute('aria-label','Закрыть');
    close.replaceChildren(icon('close'));
    return dialog;
  }
  function section(parent,title){
    const section=el('section','beta-supply-section');
    const group=el('div','beta-supply-group');
    section.append(el('h3','',title),group);
    parent.append(section);
    return group;
  }
  function valueRow(parent,name,value,state=''){
    const row=el('div','beta-supply-value');
    const amount=el('strong',state,value);
    row.append(el('span','',name),amount);
    parent.append(row);
  }
  function action(parent,name,kind,run){
    const button=btn17(parent,name,run,'secondary beta-supply-action');
    button.type='button';
    button.dataset.supplyAction=kind;
    button.prepend(icon(kind));
  }
  function metrics(parent,values,unit){
    const list=el('dl','beta-supply-metrics');
    ['День','Неделя','Месяц'].forEach((label,index)=>{
      const cell=el('div');
      cell.append(el('dt','',label),el('dd','',fmt(values[index])+' '+unit));
      list.append(cell);
    });
    parent.append(list);
  }
  function empty(parent,text){
    parent.append(el('p','beta-supply-empty',text));
  }
  function history(parent,events,format){
    const group=section(parent,'История');
    if(!events.length){
      empty(group,'Операций пока нет');
      return;
    }
    const details=el('details','beta-supply-disclosure');
    const title=el('summary');
    title.append(el('span','','Последние операции'),el('span','beta-supply-meta',fmt(events.length)));
    const list=el('ul','beta-supply-history');
    for(const event of events){
      const {title,note}=format(event);
      const row=el('li');
      row.append(el('strong','',title),el('span','beta-supply-meta',note));
      list.append(row);
    }
    details.append(title,list);
    group.append(details);
  }
  const detail=r=>r.total==null?'Не посчитано':`${fmt(r.boxes)} кор. · ${fmt(r.packs)} уп. · ${fmt(r.loose)} шт.\nВсего: ${fmt(r.total)} шт.`;
  function summary(rows){const known=rows.filter(r=>r.total!=null);return ['РАМКИ · остатки склада · '+date(new Date().toISOString()),...rows.map(r=>label(r)+'\n'+detail(r)),'Итого '+(known.length===rows.length?'':'по посчитанным позициям: ')+fmt(known.reduce((s,r)=>s+r.total,0))+' шт.','Проверено: '+known.length+' из '+rows.length].join('\n\n')}
  async function open(tab='Остатки'){
    const {b}=sheet('Рамки');
    const tabs=el('div','beta-material-tabs');
    tabs.setAttribute('role','group');
    tabs.setAttribute('aria-label','Разделы учёта рамок');
    const content=el('div','beta-supply-content');
    b.append(tabs,content);
    let data;let active=tab;
    const controls=new Map();
    for(const t of ['Остатки','Движение','Инвентаризация','Статистика']){
      const button=btn17(tabs,t==='Инвентаризация'?'Проверка':t,()=>render(t));
      button.setAttribute('aria-label',t);
      button.setAttribute('aria-pressed',String(t===active));
      controls.set(t,button);
    }
    async function refresh(){content.textContent='Загрузка…';try{data=await api('/api/frames');render(active)}catch(e){content.textContent=e.message}}
    function positions(parent,rows){
      for(const r of rows){
        const details=el('details','beta-supply-disclosure');
        const summary=el('summary');
        const value=r.total==null?'Не посчитано':fmt(r.total)+' шт.';
        summary.append(el('span','',label(r)),el('strong',r.low?'beta-supply-warning':'beta-supply-meta',value));
        details.append(summary);
        if(r.total!=null){
          valueRow(details,'Коробки',fmt(r.boxes));
          valueRow(details,'Упаковки',fmt(r.packs));
          valueRow(details,'Отдельные рамки',fmt(r.loose));
        }
        if(r.minimum!=null)valueRow(details,'Минимальный остаток',fmt(r.minimum)+' шт.');
        if(r.low)empty(details,'Заканчивается');
        if(active==='Инвентаризация')valueRow(details,'Последняя проверка',date(r.counted_at));
        if(active==='Остатки')action(details,kinds.minimum,'minimum',()=>edit(r,'minimum'));
        if(active==='Инвентаризация')action(details,'Пересчитать','inventory',()=>edit(r,'inventory'));
        if(active==='Движение'&&r.total!=null){
          for(const kind of ['receipt','issue','transfer','unpack'])action(details,kinds[kind],kind,()=>edit(r,kind));
        }
        parent.append(details);
      }
    }
    function render(t){
      active=t;
      for(const [view,button] of controls)button.setAttribute('aria-pressed',String(view===t));
      if(!data)return;
      content.replaceChildren();
      const rows=data.rows;
      if(t==='Остатки'){
        const known=rows.filter(r=>r.total!=null);const last=known.map(r=>r.counted_at).sort().pop();
        const overview=section(content,'Сводка');
        valueRow(overview,known.length===rows.length?'Всего':'По посчитанным позициям',known.length?fmt(known.reduce((s,r)=>s+r.total,0))+' шт.':'Не посчитано');
        valueRow(overview,'Проверено',known.length+' из '+rows.length);
        valueRow(overview,'Последняя проверка',date(last));
        action(overview,'Копировать сводку','copy',()=>copyText(summary(rows)));
        positions(section(content,'Позиции'),rows);
      }else if(t==='Движение'){
        positions(section(content,'Позиции'),rows);
        history(content,data.events,e=>{
          const row=rows.find(x=>x.id===e.position);
          return {
            title:kinds[e.kind]+' · '+(row?label(row):e.position),
            note:[ [date(e.created_at),e.actor,e.destination].filter(Boolean).join(' · '),
              (e.before_total==null?'Первичный остаток · ':fmt(e.before_total)+' → ')+fmt(e.after_total)+' шт.',
              e.comment ].filter(Boolean).join('\n')
          };
        });
      }else if(t==='Инвентаризация'){
        positions(section(content,'Фактические остатки'),rows);
      }else{
        const totals=[0,1,2].map(i=>rows.reduce((sum,r)=>sum+r.usage[i],0));
        metrics(section(content,'Расход со склада'),totals,'шт.');
        for(const r of rows)metrics(section(content,label(r)),r.usage,'шт.');
        const shipments=section(content,'Передачи на площадки за месяц');
        for(const x of data.shipments)valueRow(shipments,x.destination,fmt(x.quantity)+' шт.');
        if(!data.shipments.length)empty(shipments,'Передач пока нет');
      }
    }
    function edit(r,k){const {o:modal,b:body}=sheet(kinds[k]+' · '+label(r),true);const initial=k==='inventory'&&r.total!=null;const fields=[];let destination=null;
      if(k==='transfer'){destination=field17(body,'Площадка','','text');destination.required=true;destination.maxLength=200;const list=document.createElement('datalist');list.id='frame-dest-'+Date.now();destination.setAttribute('list',list.id);body.append(list);const fill=rows=>{for(const name of [...new Set(rows.map(x=>String(x['Площадка']||'').trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ru')))list.append(new Option(name,name))};if(typeof cachedPlatforms!=='undefined'&&cachedPlatforms.length)fill(cachedPlatforms);else api('/api/sync_google?sheet_name=кц').then(r=>{if(r.status==='ok')fill(r.data||[])}).catch(()=>{});card17(body,'Выдача на площадку','Уменьшает остаток склада. Продажи и остаток площадки не учитываются.');}
      if(k==='minimum'){fields.push(field17(body,'Минимум, шт. (пусто — отключить)',r.minimum??'','number'));}
      else{for(const [i,name]of ['Коробки (500 шт.)','Упаковки (50 шт.)','Отдельные рамки'].entries()){if(k==='unpack'&&i===2)break;const f=field17(body,name,initial?[r.boxes,r.packs,r.loose][i]:'0','number');f.min=0;f.step=1;fields.push(f);if(k==='receipt'||k==='issue'||k==='transfer')btn17(body,['+500 шт.','+50 шт.','+1 шт.'][i],()=>{f.value=String(Number(f.value||0)+1);update()});}
        if(k==='unpack')card17(body,'Распаковка','Коробка превращается в 10 упаковок, упаковка — в 50 отдельных рамок. Общий остаток не меняется.');}
      const hint=document.createElement('p');hint.className='meta';body.append(hint);const comment=k==='minimum'?null:field17(body,'Комментарий (необязательно)','','textarea');if(comment)comment.maxLength=500;
      function numbers(){return fields.map(f=>{const v=f.value;if(v===''&&k==='minimum')return null;if(v===''||!Number.isInteger(Number(v))||Number(v)<0||Number(v)>1000000)throw Error('Введите целое неотрицательное количество');return Number(v)})}
      function update(){try{if(k==='minimum'||k==='unpack')return;const [a,c,d]=numbers();const n=a*500+c*50+d;hint.textContent='Всего: '+fmt(n)+' шт.'+(k==='inventory'&&r.total!=null?' · Расхождение: '+(n-r.total>0?'+':'')+fmt(n-r.total)+' шт.':'')}catch(e){hint.textContent=e.message}}
      for(const f of fields){f.min=0;f.step=1;f.addEventListener('input',update)}update();
      btn17(body,'Сохранить',async()=>{const n=numbers();const payload={position:r.id,kind:k,revision:r.revision,comment:comment?.value||'',destination:destination?.value.trim()||''};if(k==='transfer'&&!payload.destination)throw Error('Укажите площадку');if(k==='minimum')payload.minimum=n[0];else [payload.boxes,payload.packs,payload.loose]=[n[0],n[1],n[2]??0];if(k==='inventory'&&!confirm('Сохранить фактический остаток?'))return;try{await api('/api/frames',{method:'POST',body:JSON.stringify(payload)})}catch(e){if(e.status===409){modal.remove();await refresh()}throw e}modal.remove();showToast('Сохранено');await refresh()},'ok');
    }
    await refresh();
  }
  async function openMaterials(name,positions){
    const {b}=sheet(name);
    const host=el('div','beta-supply-content');
    b.append(host);
    const names={vinyl:'Винил',paper46:'4×6',paper68:'6×8'};
    const ops={inventory:'Инвентаризация',receipt:'Поступление',transfer:'На площадку',issue:'Списание',unpack:'Распаковка',cut:'Нарезка',minimum:'Мин. остаток'};
    const units=r=>r.position==='vinyl'?['Цельные коробки','Нарезанные коробки']:['Коробки (2 рулона)','Отдельные рулоны'];
    const amount=r=>r.position==='vinyl'?r.boxes+r.loose:r.boxes*2+r.loose;
    const unit=pos=>pos==='vinyl'?'кор.':'рул.';
    const hasSizes=positions.length>1;
    function usagePeriods(){
      const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Moscow',year:'numeric',month:'2-digit',day:'2-digit'})
        .formatToParts(new Date());
      const day=kind=>parts.find(part=>part.type===kind).value;
      const today=new Date(`${day('year')}-${day('month')}-${day('day')}T00:00:00+03:00`);
      const week=new Date(today);
      const weekday=new Date(today.getTime()+10800000).getUTCDay();
      week.setUTCDate(week.getUTCDate()-(weekday+6)%7);
      const month=new Date(today);
      month.setUTCDate(month.getUTCDate()-Number(day('day'))+1);
      return [today,week,month];
    }
    async function refresh(){
      host.textContent='Загрузка…';
      try{
        const data=await api('/api/materials');
        host.replaceChildren();
        for(const r of data.rows.filter(r=>positions.includes(r.position))){
          const group=section(host,hasSizes?'Остаток '+names[r.position]:'Остаток');
          const counted=Boolean(r.counted_at);
          const low=counted&&r.minimum!=null&&amount(r)<r.minimum;
          valueRow(group,'На складе',counted?fmt(amount(r))+' '+unit(r.position):'Не посчитано',
            low?'beta-supply-warning':counted?'':'beta-supply-meta');
          if(counted){
            const [boxes,loose]=units(r);
            valueRow(group,boxes,fmt(r.boxes));
            valueRow(group,loose,fmt(r.loose));
          }
          if(r.minimum!=null){
            valueRow(group,'Минимальный остаток',fmt(r.minimum)+' '+unit(r.position));
          }
          if(low)empty(group,'Заканчивается');
          const actions=['inventory','minimum'];
          if(counted)actions.push('receipt','transfer','issue',r.position==='vinyl'?'cut':'unpack');
          for(const kind of actions)action(group,ops[kind],kind,()=>edit(r,kind));
        }
        const events=data.events.filter(e=>positions.includes(e.position));
        const periods=usagePeriods();
        const stats=section(host,'Расход со склада');
        for(const pos of positions){
          const totals=[0,0,0];
          for(const e of events.filter(e=>e.position===pos&&['issue','transfer'].includes(e.kind))){
            const stamp=new Date(e.created_at);
            const quantity=e.boxes*(pos==='vinyl'?1:2)+e.loose;
            periods.forEach((start,i)=>{if(stamp>=start)totals[i]+=quantity});
          }
          if(hasSizes)stats.append(el('h4','beta-supply-size',names[pos]));
          metrics(stats,totals,unit(pos));
        }
        if(data.events.length>=500)empty(stats,'По последним 500 операциям');
        history(host,events,e=>({
          title:ops[e.kind]+(hasSizes?' · '+names[e.position]:''),
          note:[[date(e.created_at),e.destination].filter(Boolean).join(' · '),
            e.before_boxes+'/'+e.before_loose+' → '+e.after_boxes+'/'+e.after_loose,e.comment].filter(Boolean).join('\n')
        }));
      }catch(e){host.textContent=e.message}
    }
    function edit(r,k){
      const {o,b}=sheet(ops[k]+' · '+names[r.position],true);
      const fields=[];
      if(k==='minimum')fields.push(field17(b,'Минимум (пусто — отключить)',r.minimum??'','number'));
      else for(const [i,u] of units(r).entries()){if(k==='unpack'&&i===1)break;fields.push(field17(b,k==='cut'?(i?'Получено нарезанных коробок':'Израсходовано цельных коробок'):u,k==='inventory'?(i?r.loose:r.boxes):0,'number'))}
      const dest=k==='transfer'?field17(b,'Площадка','','text'):null;
      const comment=field17(b,'Комментарий','','text');
      for(const f of fields){f.min=0;f.step=1}
      btn17(b,'Сохранить',async()=>{
        const n=fields.map(f=>{if(k==='minimum'&&f.value==='')return null;const v=Number(f.value);if(f.value===''||!Number.isInteger(v)||v<0||v>1000000)throw Error('Введите целое неотрицательное число');return v});
        const payload={position:r.position,kind:k,revision:r.revision,destination:dest?.value||'',comment:comment.value};
        if(k==='minimum')payload.minimum=n[0];else {payload.boxes=n[0];payload.loose=n[1]||0}
        if(k==='inventory'&&!confirm('Сохранить фактический остаток?'))return;
        await api('/api/materials',{method:'POST',body:JSON.stringify(payload)});o.remove();showToast('Сохранено');await refresh();
      },'ok');
    }
    await refresh();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install);else install();
})();
