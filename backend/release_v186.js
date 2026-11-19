/* Beta: linked physical components and whole-kit transactions. */
function installRelease186(){
  const el=(tag,cls,txt)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(txt!==undefined)n.textContent=txt;return n};
  const labels={body:'Фотоаппарат',lens:'Объектив',flash:'Вспышка'};
  const section=el('section','card r186-kit hidden');$('actions').before(section);
  let seq=0;
  const path=(code,tail='')=>'/api/v186/kits/'+encodeURIComponent(code)+tail;
  const act=async(code,action,taken_for='')=>{
    const res=await api(path(code,'/action'),{method:'POST',body:JSON.stringify({action,taken_for})});
    showToast((action==='take'?'Выдано':'Возвращено')+' · '+res.count+' шт.');
    await loadItems();await openItem(code);
  };
  function status(p){
    if(p.archived)return ['Архив','muted'];
    if(p.holders.length)return ['У '+p.holders.map(h=>h.taken_for||h.full_name||'Не указан').join(', '),'held'];
    if(p.repair)return ['В ремонте','held'];
    if(p.stocks.length)return [p.stocks.map(s=>s.name).join(', '),'free'];
    return ['Нет в наличии','muted'];
  }
  function render(code,data){
    section.replaceChildren();section.classList.add('hidden');
    if(data.candidate&&currentUser?.role==='admin'){
      section.append(el('h3','','Разделение комплекта'),el('p','meta','Камера сохранит старый QR-код. Объектив и вспышка получат свои коды. Старые выдачи останутся в истории камеры.'));
      if(data.split_reason)section.append(el('p','meta',data.split_reason));
      else btn17(section,'Разделить комплект',async()=>{
        if(!confirm('Разделить комплект на самостоятельные единицы? Аксессуары и нераспределённая стоимость останутся у камеры. Отмена разделения пока не предусмотрена.'))return;
        await api(path(code,'/split'),{method:'POST'});showToast('Комплект разделён');
        await loadCategories17();await loadItems();await openItem(code);
      });
      section.classList.remove('hidden');return;
    }
    if(!Array.isArray(data.parts))return;
    section.append(el('h3','',data.kit_name),el('div','meta','Связанный комплект · '+data.parts.length+' ед.'));
    const list=el('div','r186-kit-parts');
    for(const p of data.parts){
      const row=el('button','r186-kit-row');row.type='button';
      const col=el('div','r186-kit-info'),st=status(p);
      col.append(el('b','',labels[p.part]||p.part),el('span','r186-kit-model',p.model||p.name),el('small','meta',p.code));
      row.append(col,el('span','r186-kit-status '+st[1],st[0]));
      row.disabled=p.archived||p.code===code;
      row.onclick=()=>openItem(p.code);list.append(row);
    }
    section.append(list);
    if(['admin','employee'].includes(currentUser?.role)){
      if(data.can_take){
        btn17(section,'Взять комплект целиком',()=>act(code,'take'));
        btn17(section,'Взять комплект для…',async()=>{const name=prompt('Для кого? (Введите фамилию)');if(name?.trim())await act(code,'take',name.trim())});
      }else if(data.can_return){
        btn17(section,'Вернуть комплект целиком',async()=>{if(confirm('Вернуть все компоненты комплекта?'))await act(code,'return')},'ok');
      }else section.append(el('p','meta','Комплект разделён между местами или сотрудниками. Доступны отдельные операции.'));
      const actions=$('actions');
      for(const [selector,text] of [['doCheckout()','Взять только этот компонент'],['doCheckoutFor()','Взять этот компонент для…'],['doReturn()','Вернуть только этот компонент']]){
        const b=actions.querySelector('button[onclick="'+selector+'"]');if(b)b.textContent=text;
      }
    }
    section.classList.remove('hidden');
  }
  const prev=openItem;
  openItem=async code=>{
    const id=++seq;section.classList.add('hidden');section.replaceChildren();
    await prev(code);
    if(id!==seq||currentScreen!=='screen-item'||currentItem?.code!==code||currentItem.kind!=='equipment')return;
    try{const data=await api(path(code));if(id===seq&&currentScreen==='screen-item'&&currentItem?.code===code)render(code,data)}
    catch(e){if(id===seq&&currentScreen==='screen-item'&&currentItem?.code===code){section.replaceChildren(el('p','meta','Связи комплекта временно недоступны'));section.classList.remove('hidden')}}
  };
}
