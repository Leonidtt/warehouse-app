/* Beta: compact inventory categories. No stock data is changed. */
(function(){
  function normal(text){return String(text??'').trim().toLowerCase().replace(/ё/g,'е')}
  const hasPart=value=>!['','-','—','нет','none','0','n/a','без','не указан','не указана'].includes(normal(value));
  const view={
    selected:'camera',
    groupFor(item){
      if(item?.kind==='consumable')return 'consumable';
      const category=normal(item?.category),name=normal(item?.name);
      if(/вспыш|строб|спидлайт/.test(category)||/^(?:(?:фото)?вспышк\p{L}*|speedlite|speedlight)(?:\s|$)/u.test(name))return 'flash';
      if(/объектив|оптик|линз/.test(category)||/^(?:объектив\p{L}*|линз\p{L}*|lens)(?:\s|$)/u.test(name))return 'lens';
      if(hasPart(item?.kit_body)||/фотокамер|фотоаппарат|фотокомплект|зеркалк|беззеркалк|тушк|камер/.test(category)||
        /^(комплект|фотоаппарат|камера|тушка|canon eos|sony a[0-9]|nikon d[0-9]|fujifilm x)/iu.test(name))return 'camera';
      return 'accessory';
    },
    refresh(){}
  };
  window.warehouseCatalogView=view;
  window.installCatalogRefinements=function(){
    const main=document.getElementById('screen-main');
    if(!main||document.getElementById('warehouse-category-switcher'))return;
    const toolbar=main.querySelector('.r184-tools');
    if(!toolbar)return;
    const allPanels=main.querySelectorAll('.r184-filter-panel');
    const sortSelect=allPanels[1]?.querySelector('select');
    const filters=toolbar.querySelectorAll('.r184-icon');
    const filterButton=filters[0];
    if(!sortSelect||!filterButton)return;
    const e=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node};
    sortSelect.classList.add('r186-sort-select');
    sortSelect.setAttribute('aria-label','Сортировка товаров');
    filterButton.classList.add('r186-filter');
    filterButton.setAttribute('aria-label','Фильтры товаров');
    filterButton.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="10" cy="18" r="2"/></svg><span>Фильтры</span>';
    toolbar.classList.add('r186-sort-tools');
    toolbar.replaceChildren(sortSelect,filterButton);
    const icons={
      camera:'<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M7 7l2-3h6l2 3"/><circle cx="12" cy="13.5" r="3.5"/>',
      lens:'<rect x="5" y="3" width="14" height="18" rx="4"/><path d="M5 7h14M5 17h14"/><circle cx="12" cy="12" r="3.5"/>',
      flash:'<rect x="5" y="3" width="14" height="18" rx="3"/><path d="m13 6-4 7h4l-2 5 5-8h-4z"/>',
      accessory:'<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 4v16M4 10h16M13 15h4"/>',
      consumable:'<path d="m3 8 9-5 9 5v12H3zM3 8l9 5 9-5M12 13v7M9 3v7"/>'
    };
    const options=[['camera','Фотокамеры'],['lens','Объективы'],['flash','Вспышки'],['accessory','Аксессуары','Аксессуары / допы'],['consumable','Расходники']];
    const bar=e('div','r186-family-bar');bar.id='warehouse-category-switcher';
    bar.setAttribute('role','group');bar.setAttribute('aria-label','Быстрые категории товаров');
    const buttons=new Map();
    for(const [key,label,accessibleLabel=label]of options){
      const b=e('button','r186-family');
      b.type='button';
      b.title=accessibleLabel;
      b.setAttribute('aria-label',accessibleLabel);
      const icon=e('span','r186-family-illustration');
      icon.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true">'+icons[key]+'</svg>';
      b.append(icon,e('span','r186-family-label',label));
      b.onclick=()=>{
        view.selected=view.selected===key?'':key;
        const kind=document.getElementById('filter-kind');
        const category=document.getElementById('filter-category');
        if(kind)kind.value='';
        if(category)category.value='';
        if(typeof filterItems==='function')filterItems();
      };
      bar.append(b);buttons.set(key,b);
    }
    toolbar.after(bar);
    function refresh(){
      for(const [key,b]of buttons){
        const selected=view.selected===key;
        b.classList.toggle('active',selected);
        b.setAttribute('aria-pressed',String(selected));
      }
    }
    view.refresh=refresh;
    window.addEventListener('warehouse-kind-selected',event=>{
      view.selected=event.detail?.kind==='consumable'?'consumable':'';
      refresh();
    });
    const category=document.getElementById('filter-category');
    category?.addEventListener('change',()=>{
      if(category.value){
        view.selected='';
        document.getElementById('filter-kind').value='';
      }
    },true);
    const oldRender=renderItemsGrid;
    renderItemsGrid=(rows,id)=>{
      const result=oldRender(rows,id);
      if(id==='items-list')refresh();
      return result;
    };
    refresh();
  };
})();
