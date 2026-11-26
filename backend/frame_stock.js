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
  const detail=r=>r.total==null?'Не посчитано':`${fmt(r.boxes)} кор. · ${fmt(r.packs)} уп. · ${fmt(r.loose)} шт.\nВсего: ${fmt(r.total)} шт.`;
  function summary(rows){const known=rows.filter(r=>r.total!=null);return ['РАМКИ · остатки склада · '+date(new Date().toISOString()),...rows.map(r=>label(r)+'\n'+detail(r)),'Итого '+(known.length===rows.length?'':'по посчитанным позициям: ')+fmt(known.reduce((s,r)=>s+r.total,0))+' шт.','Проверено: '+known.length+' из '+rows.length].join('\n\n')}
  async function open(tab='Остатки'){
    const {o,b}=overlay17('Рамки');const tabs=document.createElement('div');tabs.style.cssText='display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin:8px 0';b.append(tabs);
    const content=document.createElement('div');b.append(content);
    let data;let active=tab;
    for(const t of ['Остатки','Движение','Инвентаризация','Статистика'])btn17(tabs,t,()=>render(t));
    async function refresh(){content.textContent='Загрузка…';try{data=await api('/api/frames');render(active)}catch(e){content.textContent=e.message}}
    function render(t){active=t;if(!data)return;for(const el of tabs.children){el.setAttribute('aria-pressed',String(el.textContent===t));el.className=el.textContent===t?'ok':'secondary'}content.replaceChildren();const rows=data.rows;
      if(t==='Остатки'){
        const known=rows.filter(r=>r.total!=null);const last=known.map(r=>r.counted_at).sort().pop();
        card17(content,'Всего: '+fmt(known.reduce((s,r)=>s+r.total,0))+' шт.',`Проверено ${known.length} из ${rows.length}\nПоследняя проверка: ${date(last)}${known.length!==rows.length?'\nИтог только по посчитанным позициям':''}`);
        btn17(content,'Копировать сводку',()=>copyText(summary(rows)),'ok');
        for(const r of rows){const c=card17(content,label(r),detail(r)+(r.minimum==null?'':'\nМинимум: '+fmt(r.minimum)+' шт.'));if(r.low){const p=document.createElement('p');p.style.color='var(--danger)';p.textContent='Заканчивается';c.append(p)}btn17(c,'Мин. остаток',()=>edit(r,'minimum'));}
      }else if(t==='Движение'){
        for(const r of rows){const c=card17(content,label(r),detail(r));if(r.total==null)continue;for(const k of ['receipt','issue','transfer','unpack'])btn17(c,kinds[k],()=>edit(r,k));}
        card17(content,'Последние операции','До 100 записей');for(const e of data.events){const r=rows.find(x=>x.id===e.position);card17(content,kinds[e.kind]+' · '+label(r),`${date(e.created_at)} · ${e.actor}${e.destination?' · '+e.destination:''}\n${e.before_total==null?'Первичный остаток':fmt(e.before_total)+' →'} ${fmt(e.after_total)} шт.${e.comment?'\n'+e.comment:''}`)}
      }else if(t==='Инвентаризация'){
        card17(content,'Фактические остатки','Неучтённые позиции не считаются нулевыми. Расхождения не попадают в расход.');for(const r of rows){const c=card17(content,label(r),detail(r)+'\nПроверка: '+date(r.counted_at));btn17(c,'Пересчитать',()=>edit(r,'inventory'),'ok');}
      }else{
        card17(content,'Расход','Сегодня · с понедельника · с начала месяца (Москва)');for(const r of rows)card17(content,label(r),r.usage.map(fmt).join(' / ')+' шт.');card17(content,'Итого',rows[0].usage.map((_,i)=>fmt(rows.reduce((s,r)=>s+r.usage[i],0))).join(' / ')+' шт.');card17(content,'Передано на площадки за месяц','Расход центрального склада, не продажи.');for(const x of data.shipments)card17(content,x.destination,fmt(x.quantity)+' шт.');
      }
    }
    function edit(r,k){const {o:modal,b:body}=overlay17(kinds[k]+' · '+label(r));const initial=k==='inventory'&&r.total!=null;const fields=[];let destination=null;
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
    const {b}=overlay17(name);
    const host=document.createElement('div');b.append(host);
    const names={vinyl:'Винил',paper46:'4×6',paper68:'6×8'};
    const ops={inventory:'Инвентаризация',receipt:'Поступление',transfer:'На площадку',issue:'Списание',unpack:'Распаковка',cut:'Нарезка',minimum:'Мин. остаток'};
    const units=r=>r.position==='vinyl'?['Цельные коробки','Нарезанные коробки']:['Коробки (2 рулона)','Отдельные рулоны'];
    const amount=r=>r.position==='vinyl'?r.boxes+r.loose:r.boxes*2+r.loose;
    const describe=r=>units(r).map((u,i)=>u+': '+fmt(i?r.loose:r.boxes)).join('\n')+'\nВсего: '+fmt(amount(r))+(r.position==='vinyl'?' кор.':' рул.');
    async function refresh(){
      host.textContent='Загрузка…';
      try{
        const data=await api('/api/materials');host.replaceChildren();
        for(const r of data.rows.filter(r=>positions.includes(r.position))){
          const c=card17(host,names[r.position],r.counted_at?describe(r):'Не посчитано');
          if(r.minimum!=null){const p=document.createElement('p');p.textContent='Минимум: '+fmt(r.minimum)+(r.counted_at&&amount(r)<r.minimum?' · Заканчивается':'');if(r.counted_at&&amount(r)<r.minimum)p.style.color='var(--danger)';c.append(p)}
          for(const k of ['inventory','minimum',...(r.counted_at?['receipt','transfer','issue',r.position==='vinyl'?'cut':'unpack']:[])])btn17(c,ops[k],()=>edit(r,k));
        }
        const events=data.events.filter(e=>positions.includes(e.position));
        card17(host,'Статистика','Выдача со склада, не продажи. По последним 500 операциям.');
        for(const pos of positions){
          const totals=[0,0,0];const now=new Date();const day=new Date(now.toLocaleDateString('en-CA',{timeZone:'Europe/Moscow'})+'T00:00:00+03:00');const week=new Date(day);week.setUTCDate(week.getUTCDate()-((new Date(day.getTime()+10800000).getUTCDay()+6)%7));const month=new Date(day);month.setUTCDate(month.getUTCDate()-(Number(now.toLocaleString('en-GB',{day:'numeric',timeZone:'Europe/Moscow'}))-1));
          for(const e of events.filter(e=>e.position===pos&&['issue','transfer'].includes(e.kind))){[day,week,month].forEach((d,i)=>{if(new Date(e.created_at)>=d)totals[i]+=e.boxes*(pos==='vinyl'?1:2)+e.loose})}
          card17(host,names[pos], 'День / неделя / месяц: '+totals.map(fmt).join(' / '));
        }
        card17(host,'История','Последние операции');
        for(const e of events)card17(host,ops[e.kind]+' · '+names[e.position],date(e.created_at)+' · '+(e.destination||'')+'\n'+e.before_boxes+'/'+e.before_loose+' → '+e.after_boxes+'/'+e.after_loose+(e.comment?'\n'+e.comment:''));
      }catch(e){host.textContent=e.message}
    }
    function edit(r,k){
      const {o,b}=overlay17(ops[k]+' · '+names[r.position]);
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
