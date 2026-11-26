/* Beta: compact inventory categories. No stock data is changed. */
(function(){
  function normal(text){return String(text??'').trim().toLowerCase().replace(/ё/g,'е')}
  const hasPart=value=>!['','-','—','нет','none','0','n/a','без','не указан','не указана'].includes(normal(value));
  const view={
    selected:'camera',
    takeSelected:'',
    takeSort:'available',
    groupFor(item){
      if(item?.kind==='consumable')return 'consumable';
      const category=normal(item?.category),name=normal(item?.name);
      if(/ноутбук|лэптоп|макбук|macbook|laptop/.test(category)||
        /^(ноутбук|лэптоп|макбук|macbook|apple macbook|thinkpad|lenovo thinkpad|dell latitude)(?:\s|$)/u.test(name))return 'laptop';
      if(/принтер|фотопечать|термосублимац|printer/.test(category)||
        /^(принтер|фотопринтер|dnp|hiti|mitsubishi)(?:\s|$)/u.test(name)||
        /(?:^|\s)(?:ds[- ]?620|ds[- ]?820|rx[- ]?1(?:hs)?|qw[- ]?410)(?:\s|$)/u.test(name))return 'printer';
      if(/вспыш|строб|спидлайт/.test(category)||/^(?:(?:фото)?вспышк\p{L}*|speedlite|speedlight)(?:\s|$)/u.test(name))return 'flash';
      if(/объектив|оптик|линз/.test(category)||/^(?:объектив\p{L}*|линз\p{L}*|lens)(?:\s|$)/u.test(name))return '';
      if(hasPart(item?.kit_body)||/фотокамер|фотоаппарат|фотокомплект|зеркалк|беззеркалк|тушк|камер/.test(category)||
        /^(фотокомплект|комплект|фотоаппарат|камера|тушка|canon eos|sony a[0-9]|nikon d[0-9]|fujifilm x)/iu.test(name))return 'camera';
      return '';
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
    const filterPanel=allPanels[0];
    const sortSelect=allPanels[1]?.querySelector('select');
    const filters=toolbar.querySelectorAll('.r184-icon');
    const filterButton=filters[0];
    if(!filterPanel||!sortSelect||!filterButton)return;
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
      flash:'<path d="m13 2-8 12h6l-1 8 9-12h-6l1-8z"/>',
      laptop:'<rect x="4" y="4" width="16" height="12" rx="2"/><path d="M4 16l-2 3a1 1 0 0 0 1 1h18a1 1 0 0 0 1-1l-2-3M10 17.8h4"/>',
      printer:'<path d="M6 8V3h12v5M6 17H3V9h18v8h-3M6 14h12v7H6zM16 11h2"/>',
      consumable:'<path d="m3 8 9-5 9 5v12H3zM3 8l9 5 9-5M12 13v7M9 3v7"/>'
    };
    const options=[['camera','Фотокомплекты'],['flash','Вспышки'],['laptop','Ноутбуки'],['printer','Принтеры'],['consumable','Расходники']];
    function categoryButton(key,label){
      const button=e('button','r186-family');
      button.type='button';
      button.title=label;
      button.setAttribute('aria-label',label);
      const icon=e('span','r186-family-illustration');
      icon.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true">'+icons[key]+'</svg>';
      button.append(icon);
      return button;
    }
    const bar=e('div','r186-family-bar');bar.id='warehouse-category-switcher';
    bar.setAttribute('role','group');bar.setAttribute('aria-label','Быстрые категории товаров');
    const buttons=new Map();
    for(const [key,label]of options){
      const b=categoryButton(key,label);
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
    filterPanel.after(bar);

    const takeTools=document.getElementById('take-tools');
    if(takeTools){
      takeTools.setAttribute('role','group');
      takeTools.setAttribute('aria-label','Категории и сортировка выдачи');
      const takeButtons=options.slice(0,4).map(([key,label])=>{
        const button=categoryButton(key,label);
        button.onclick=()=>{
          view.takeSelected=view.takeSelected===key?'':key;
          updateTakeTools();
          renderTakeItems();
        };
        takeTools.append(button);
        return [key,button];
      });
      const orders=[
        ['available','По типу · свободные первыми'],
        ['name-asc','Название: А–Я'],
        ['name-desc','Название: Я–А']
      ];
      const sortButton=e('button','r186-family take-sort');
      sortButton.type='button';
      sortButton.setAttribute('aria-haspopup','dialog');
      sortButton.innerHTML='<span class="r186-family-illustration"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4v16m-4-4 4 4 4-4M17 20V4m-4 4 4-4 4 4"/></svg></span>';
      sortButton.onclick=()=>{
        const {o,b}=overlay17('Сортировка');
        b.setAttribute('role','dialog');
        b.setAttribute('aria-label','Сортировка');
        for(const [key,label] of orders){
          const current=view.takeSort===key;
          const option=btn17(b,label,()=>{
            view.takeSort=key;
            o.remove();
            updateTakeTools();
            renderTakeItems();
            sortButton.focus();
          },current?'':'secondary');
          option.setAttribute('aria-pressed',String(current));
        }
        b.querySelector('button[aria-pressed="true"]')?.focus();
      };
      takeTools.append(sortButton);
      function updateTakeTools(){
        for(const [key,button]of takeButtons){
          const active=view.takeSelected===key;
          button.classList.toggle('active',active);
          button.setAttribute('aria-pressed',String(active));
        }
        const label=orders.find(([key])=>key===view.takeSort)[1];
        sortButton.title='Сортировка: '+label;
        sortButton.setAttribute('aria-label',sortButton.title);
        sortButton.classList.toggle('active',view.takeSort!=='available');
      }
      updateTakeTools();
    }
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
