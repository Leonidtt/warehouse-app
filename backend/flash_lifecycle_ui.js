/* Flash serials, explicit budget, remembered equipment models, and paid archive.
   Installs after the existing v18 modules: no replacement of their business forms. */
function installFlashIdentityUI(){
  'use strict';
  const $=id=>document.getElementById(id);
  const values={};
  let previewRequest=0,previewBusy=false;
  const getCategory=p=>String($(p+'-category')?.value||'').trim().toLowerCase();
  const isFlash=p=>$(p+'-kind')?.value==='equipment'&&
    ['вспышки','вспышка','фотовспышка','фотовспышки'].includes(getCategory(p));
  const budgetGroup=$('add-budget-tag').closest('.input-group');
  const originalBudgetParent=budgetGroup.parentElement;
  const originalBudgetSibling=budgetGroup.nextSibling;
  const editName=$('edit-name'),editCode=$('edit-code');
  const addName=$('add-name'),addCode=$('add-code');
  const originalNamePlaceholder=addName.placeholder;
  let wasFlash=false;
  const originalGenerate=generateCodeForNew;
  async function previewFlash(showQr=false){
    if(!isFlash('add'))return;
    const id=++previewRequest;
    const budget=$('add-budget-tag').value;
    if(!['КЦ','ТХ'].includes(budget)){
      addCode.value='';addName.value='';
      $('qr-preview-box').classList.add('hidden');
      return;
    }
    previewBusy=true;
    try{
      const result=await api('/api/flash/next?budget='+encodeURIComponent(budget));
      if(id!==previewRequest||!isFlash('add')||$('add-budget-tag').value!==budget)return;
      addCode.value=result.code;
      addName.value=result.name;
      $('qr-preview-box').classList.add('hidden');
      if(showQr){
        await showLabelPreview17(result.code,result.name,$('qr-preview-img'));
        if(id!==previewRequest)return;
        $('qr-preview-code').textContent=result.code;
        $('qr-preview-box').classList.remove('hidden');
      }
    }catch(e){
      if(id===previewRequest){addCode.value='';addName.value='';notify('Не удалось получить номер вспышки: '+e.message)}
    }finally{if(id===previewRequest)previewBusy=false}
  }
  function syncAdd(){
    const flash=isFlash('add');
    $('create-item-modal').classList.toggle('r196-flash-mode',flash);
    addName.readOnly=flash;addCode.readOnly=flash;
    $('add-budget-tag').required=flash;
    budgetGroup.querySelector('label').textContent=flash?'Бюджет вспышки *':'Бюджет';
    if(flash){
      const root=$('equipment-fields');
      const info=root.querySelector('.r182-form-section:not(details)');
      if(info&&budgetGroup.parentElement!==info)info.prepend(budgetGroup);
      addName.placeholder='Автоматический номер';
      addCode.placeholder='Выберите бюджет КЦ или ТХ';
      if(!wasFlash&&$('add-name').value&&!/^[1-9]\d*$/.test($('add-name').value)){
        addName.value='';
      }
      if(!wasFlash)previewFlash();
    }else{
      if(budgetGroup.parentElement!==originalBudgetParent){
        if(originalBudgetSibling&&originalBudgetSibling.parentNode===originalBudgetParent)
          originalBudgetParent.insertBefore(budgetGroup,originalBudgetSibling);
        else originalBudgetParent.prepend(budgetGroup);
      }
      if(wasFlash){
        ++previewRequest;
        if(/^[1-9]\d*$/.test(addName.value))addName.value='';
        if(/^(кц|тх)\d+$/i.test(addCode.value))addCode.value='';
      }
      addName.placeholder=originalNamePlaceholder;
      $('add-budget-tag').required=false;
      addCode.placeholder='Код';
    }
    wasFlash=flash;
  }
  const originalToggle=toggleFields;
  toggleFields=function(){const result=originalToggle.apply(this,arguments);syncAdd();return result;};
  $('add-category').addEventListener('change',syncAdd);
  $('add-kind').addEventListener('change',syncAdd);
  $('add-budget-tag').addEventListener('change',()=>previewFlash());
  generateCodeForNew=async function(){
    if(isFlash('add')){
      if(!$('add-budget-tag').value){notify('Обязательно выберите бюджет КЦ или ТХ');$('add-budget-tag').focus();return}
      await previewFlash(true);return;
    }
    return originalGenerate.apply(this,arguments);
  };
  const originalOpen=openAddItemModal;
  openAddItemModal=function(){const result=originalOpen.apply(this,arguments);syncAdd();return result};
  const originalSave=saveNewItem;
  saveNewItem=async function(){
    if(isFlash('add')){
      if(!$('add-budget-tag').value){
        notify('Выберите бюджет КЦ или ТХ — без него вспышку нельзя сохранить');
        $('add-budget-tag').focus();return;
      }
      if(previewBusy||!addName.value||!addCode.value)await previewFlash();
      if(!addName.value||!addCode.value)return;
    }
    return originalSave.apply(this,arguments);
  };
  // The original API returns the real name and code, in case concurrent editors
  // created a flash between preview and save. Keep the success receipt accurate.
  const originalEdit=showEditForm;
  function syncEdit(){
    const flash=isFlash('edit');
    $('screen-edit-item').classList.toggle('r196-flash-mode',flash);
    editName.readOnly=flash;
    editCode.readOnly=flash;
    $('edit-budget-tag').required=flash;
    $('edit-budget-tag').closest('.input-group').querySelector('label').textContent=
      flash?'Бюджет вспышки *':'Бюджет (для админа)';
    if(flash){
      editName.placeholder='Присваивается автоматически';
      editCode.placeholder='Присваивается автоматически';
    }
    const canArchive=currentItem?.kind==='equipment'&&
      currentItem?.buyout&&Number(currentItem.buyout.total)>0&&
      Number(currentItem.buyout.remaining)===0;
    const button=$('r196-buyout-archive-btn');
    if(button){
      button.classList.toggle('hidden',!canArchive);
      button.disabled=!canArchive;
    }
  }
  showEditForm=function(){const result=originalEdit.apply(this,arguments);syncEdit();return result;};
  $('edit-category').addEventListener('change',syncEdit);
  const originalEditSave=saveEditItem;
  saveEditItem=async function(){
    if(isFlash('edit')&&!['КЦ','ТХ'].includes($('edit-budget-tag').value)){
      notify('Для вспышки обязательно выберите бюджет КЦ или ТХ');
      $('edit-budget-tag').focus();return;
    }
    return originalEditSave.apply(this,arguments);
  };
  // Model choices are stored in the existing SQLite equipment fields. New
  // values become suggestions automatically at the next edit/load.
  async function refreshModels(){
    try{
      const response=await api('/api/equipment/models');
      for(const key of ['kit_body','kit_lens','kit_flash'])values[key]=Array.isArray(response[key])?response[key]:[];
    }catch(e){
      for(const [key] of Object.entries({kit_body:1,kit_lens:1,kit_flash:1})){
        const seen=new Map();
        (Array.isArray(allItems)?allItems:[]).forEach(i=>{
          const value=String(i[key]||'').trim();
          if(value&&!seen.has(value.toLocaleLowerCase('ru-RU')))seen.set(value.toLocaleLowerCase('ru-RU'),value);
        });
        values[key]=[...seen.values()];
      }
    }
  }
  function attachSuggestions(input,key){
    if(!input)return;
    input.autocomplete='off';
    input.setAttribute('aria-autocomplete','list');
    const panel=document.createElement('div');
    panel.className='r196-model-suggestions hidden';
    panel.setAttribute('role','listbox');
    input.insertAdjacentElement('afterend',panel);
    let blurHandle;
    function render(){
      const search=input.value.trim().toLocaleLowerCase('ru-RU').replaceAll('ё','е');
      const matches=(values[key]||[]).filter(value=>value.toLocaleLowerCase('ru-RU').replaceAll('ё','е').includes(search)).slice(0,8);
      panel.replaceChildren();
      for(const name of matches){
        const button=document.createElement('button');
        button.className='r196-model-choice';
        button.type='button';button.setAttribute('role','option');
        button.textContent=name;
        button.addEventListener('pointerdown',event=>event.preventDefault());
        button.onclick=()=>{
          input.value=name;panel.classList.add('hidden');
          input.dispatchEvent(new Event('input',{bubbles:true}));
          input.focus();
        };
        panel.append(button);
      }
      panel.classList.toggle('hidden',matches.length===0);
    }
    input.addEventListener('focus',()=>{clearTimeout(blurHandle);refreshModels().then(()=>{if(document.activeElement===input)render()})});
    input.addEventListener('input',render);
    input.addEventListener('blur',()=>{blurHandle=setTimeout(()=>panel.classList.add('hidden'),140)});
    input.addEventListener('keydown',event=>{if(event.key==='Escape')panel.classList.add('hidden')});
  }
  for(const [key]of Object.entries({kit_body:1,kit_lens:1,kit_flash:1})){
    const suffix=key.slice(4).replace('_','-');
    attachSuggestions($('add-kit-'+suffix),key);
    attachSuggestions($('edit-kit-'+suffix),key);
  }
  const archiveButton=document.createElement('button');
  archiveButton.type='button';archiveButton.id='r196-buyout-archive-btn';
  archiveButton.className='secondary r196-buyout-archive hidden';
  archiveButton.textContent='Выкуплено · в архив';
  $('delete-item-btn').insertAdjacentElement('afterend',archiveButton);
  archiveButton.onclick=()=>{
    const item=currentItem;
    if(!item||item.kind!=='equipment')return;
    const buyer=String(item.buyout_status||'').trim();
    const {o,b}=overlay17('Архивировать как выкупленное');
    const explanation=document.createElement('p');
    explanation.className='meta';
    explanation.textContent='Платёж полностью закрыт. Техника будет отмечена как выкупленная, архивирована, а её история сохранится. Номер вспышки освободится.';
    b.append(explanation);
    const field=field17(b,'Кто выкупил (фамилия)',buyer);
    field.required=true;field.maxLength=150;
    btn17(b,'Подтвердить выкуп и архив',async()=>{
      const name=field.value.trim();
      if(!name){notify('Укажите фамилию покупателя');field.focus();return}
      const result=await api('/api/items/'+encodeURIComponent(item.code)+'/archive-buyout',{
        method:'POST',body:JSON.stringify({buyer_name:name,confirmed:true})
      });
      o.remove();
      showToast('Выкуплено: '+result.buyer_name);
      backToMain();
      await loadItems();
      await loadDashboard17();
    },'ok');
  };
  const originalShowExtra=showExtra;
  showExtra=async function(section){
    const result=await originalShowExtra.apply(this,arguments);
    if(section==='archive'){
      const box=$('extra-content');
      if(box){
        const cards=[...box.querySelectorAll('.card')];
        // Original archive rows have a restore action. Bought items are marked
        // explicitly and cannot be restored through the normal archive UI.
        try{
          const rows=await api('/api/archive');
          for(const [index,item]of rows.entries()){
            const card=cards[index];
            if(!card||!item.archive_reason)continue;
            const note=document.createElement('div');note.className='r196-archive-note';
            note.textContent=item.archive_reason==='buyout'
              ?'Выкуплено · '+(item.buyer_name||'—')+' · '+(item.archive_date||'')
              :'Архивировано · прежний код '+item.original_code;
            const restore=card.querySelector('button');
            if(restore){
              restore.before(note);
              if(item.archive_reason==='buyout')restore.remove();
            }else card.append(note);
          }
        }catch(e){console.warn('Archive labels unavailable:',e)}
      }
    }
    return result;
  };
  refreshModels().catch(()=>{});
  syncAdd();
}