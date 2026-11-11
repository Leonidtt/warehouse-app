const tg = window.Telegram?.WebApp || {
    ready: () => {}, expand: () => {}, showAlert: (msg) => alert(msg),
    showPopup: (opts, cb) => { if(confirm(opts.message)) cb('open'); },
    initData: "", initDataUnsafe: {}, openLink: (url) => window.open(url, '_blank')
};
tg.ready(); tg.expand();

let currentItem = null, locations = [], allItems = [], spots = [], categories = [], currentUser = null, selectedItems = [], currentRoomId = null;

function notify(msg) { if (tg.showAlert) tg.showAlert(msg); else alert(msg); }

function updateNavActive(id) {
    ["nav-main", "nav-rooms", "nav-history", "nav-settings"].forEach(nav => {
        const el = document.getElementById(nav);
        if (el) el.classList.toggle("active", nav === id);
    });
}

function openDevConsole() {
    if (window.eruda) { window.eruda.init(); window.eruda.show(); }
    else { notify("Консоль не загрузилась. Проверьте интернет."); }
}

async function clearDatabase() {
    if (!confirm("Вы уверены, что хотите УДАЛИТЬ ВСЕ ТОВАРЫ, ИСТОРИЮ И БРОНИ? Комнаты и пользователи останутся.")) return;
    if (!confirm("Это действие необратимо. Точно продолжить?")) return;
    try { await api("/api/clear_database", { method: "POST" }); notify("База товаров очищена."); loadItems(); } catch (e) { notify("Ошибка: " + e.message); }
}

async function api(path, options = {}) {
    const res = await fetch(path, {
        headers: { ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }), "X-Init-Data": tg.initData || "" },
        ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Ошибка сервера");
    return data;
}

async function init() {
    try {
        currentUser = await api("/api/me");
        if (!currentUser.full_name) { showScreen("screen-register"); return; }
        
        const userInfoEl = document.getElementById("user-info");
        if (userInfoEl) {
            userInfoEl.innerHTML = `${currentUser.full_name}<br><span style="color:var(--primary); font-size:10px;">${currentUser.role === 'admin' ? 'Админ' : 'Сотрудник'}</span>`;
        }

        if (currentUser.role === "admin") { 
            const navSettings = document.getElementById("nav-settings");
            if (navSettings) navSettings.classList.remove("hidden"); 
        }
        await loadLocations(); await loadSpots(); await loadCategories(); await loadItems(); await loadStats(); await loadDailyReport(); await loadMyBookings();
        showScreen("screen-main");
    } catch (e) { notify("Ошибка инициализации: " + e.message); }
}

async function doRegister() { const name = document.getElementById("reg-name").value.trim(); if (name.length < 3) { notify("Введите Фамилию и Имя"); return; } try { await api("/api/register", { method: "POST", body: JSON.stringify({ full_name: name }) }); init(); } catch (e) { notify(e.message); } }
async function loadDailyReport() { try { const res = await api("/api/daily_report"); if (res.report) { document.getElementById("daily-report-box").classList.remove("hidden"); document.getElementById("report-text").innerHTML = res.report.replace(/\n/g, '<br>'); } } catch (e) { console.log(e); } }
async function loadMyBookings() { try { const rows = await api("/api/my_bookings"); if (!rows.length) return; document.getElementById("my-bookings-section").classList.remove("hidden"); document.getElementById("my-bookings-list").innerHTML = rows.map(r => `<div class="booking-item"><b>${r.name}</b><div style="font-size:12px; color:var(--text-muted);">${r.date_from} — ${r.date_to}</div></div>`).join(""); } catch (e) { console.log(e); } }

async function loadStats() {
    try {
        const stats = await api("/api/stats");
        if (!stats.length) { document.getElementById("stats-box").classList.add("hidden"); return; }
        const box = document.getElementById("stats-box");
        box.classList.remove("hidden");
        box.innerHTML = `<div class="stats-title">Обзор склада</div>` + stats.map(s => `
            <div class="stat-row">
                <div class="stat-name">${s.name}</div>
                <div class="stat-nums"><span class="stat-total">${s.total}</span> склад ${s.on_stock} · работа ${s.in_work}</div>
            </div>
        `).join("");
    } catch (e) { console.log("Stats error:", e); }
}

async function loadLocations() { 
    locations = await api("/api/locations"); 
    document.getElementById("add-location").innerHTML = locations.map(l => `<option value="${l.id}">${l.name}</option>`).join(""); 
    document.getElementById("filter-location").innerHTML = `<option value="">Все комнаты</option>` + locations.map(l => `<option value="${l.id}">${l.name}</option>`).join("");
    const list = document.getElementById("locations-list"); 
    if (list) { 
        list.innerHTML = locations.map(l => `<div class="card" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; padding:12px;"><div><b>${l.name}</b></div><button class="secondary" style="width:auto; padding:8px 12px; margin:0; font-size:12px;" onclick="renameLocation(${l.id}, '${l.name}')">✏️</button></div>`).join(""); 
    } 
}
async function createLocation() { const name = document.getElementById("new-location-name").value.trim(); if (!name) return; try { await api("/api/locations", { method: "POST", body: JSON.stringify({ name }) }); notify("Добавлено"); document.getElementById("new-location-name").value = ""; loadLocations(); } catch (e) { notify(e.message); } }
async function renameLocation(id, oldName) { const newName = prompt("Новое название комнаты:", oldName); if (!newName || newName === oldName) return; try { await api("/api/locations/update", { method: "POST", body: JSON.stringify({ id, name: newName }) }); notify("Обновлено"); loadLocations(); } catch (e) { notify(e.message); } }

async function loadCategories() {
    categories = await api("/api/categories");
    document.getElementById("add-category").innerHTML = `<option value="">Без категории</option>` + categories.map(c => `<option value="${c.name}">${c.name}</option>`).join("");
    document.getElementById("edit-category").innerHTML = `<option value="">Без категории</option>` + categories.map(c => `<option value="${c.name}">${c.name}</option>`).join("");
    const list = document.getElementById("categories-list");
    if (list) {
        list.innerHTML = categories.map(c => `<div class="card" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; padding:12px;"><div><b>${c.name}</b></div><div style="display:flex; gap:8px;"><button class="secondary" style="width:auto; padding:8px 12px; margin:0; font-size:12px;" onclick="renameCategory(${c.id}, '${c.name}')">✏️</button><button class="danger" style="width:auto; padding:8px 12px; margin:0; font-size:12px;" onclick="deleteCategory(${c.id})">🗑</button></div></div>`).join("");
    }
}
async function createCategory() { const name = document.getElementById("new-category-name").value.trim(); if (!name) return; try { await api("/api/categories", { method: "POST", body: JSON.stringify({ name }) }); notify("Добавлено"); document.getElementById("new-category-name").value = ""; loadCategories(); } catch (e) { notify(e.message); } }
async function renameCategory(id, oldName) { const newName = prompt("Новое название категории:", oldName); if (!newName || newName === oldName) return; try { await api("/api/categories/update", { method: "POST", body: JSON.stringify({ id, name: newName }) }); notify("Обновлено"); loadCategories(); } catch (e) { notify(e.message); } }
async function deleteCategory(id) { if (!confirm("Удалить категорию? У товаров она станет 'Без категории'.")) return; try { await api(`/api/categories/${id}`, { method: "DELETE" }); notify("Удалено"); loadCategories(); } catch (e) { notify(e.message); } }

async function loadSpots() { 
    spots = await api("/api/spots"); 
    document.getElementById("add-spot").innerHTML = `<option value="">Без места</option>` + spots.map(s => `<option value="${s.name}">${s.name}</option>`).join(""); 
    const list = document.getElementById("settings-spots-list"); 
    if (list) { 
        list.innerHTML = spots.map(s => `<div class="card" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; padding:12px;"><div><b>${s.name}</b></div><button class="secondary" style="width:auto; padding:8px 12px; margin:0; font-size:12px;" onclick="renameSpot('${s.name}')">✏️</button></div>`).join(""); 
    } 
}
async function renameSpot(oldName) { const newName = prompt("Новое название полки:", oldName); if (!newName || newName === oldName) return; try { await api("/api/spots/update", { method: "POST", body: JSON.stringify({ old_name: oldName, new_name: newName }) }); notify("Обновлено"); loadSpots(); } catch (e) { notify(e.message); } }

function updateFilterSpots() {
    const locId = parseInt(document.getElementById("filter-location").value);
    const spotSelect = document.getElementById("filter-spot");
    spotSelect.innerHTML = `<option value="">Все полки</option>`;
    if (locId) {
        const locSpots = allItems.filter(i => i.stocks.some(s => s.location_id === locId)).map(i => i.stocks.filter(s => s.location_id === locId).map(s => s.spot)).flat();
        const uniqueSpots = [...new Set(locSpots)].filter(s => s);
        spotSelect.innerHTML += uniqueSpots.map(s => `<option value="${s}">${s}</option>`).join("");
    }
}

function showSettings() { loadLocations(); loadCategories(); loadSpots(); showScreen("screen-settings"); updateNavActive("nav-settings"); }
async function loadUsers() { 
    const list = document.getElementById("users-list"); 
    list.innerHTML = "<p>Загрузка...</p>"; 
    try { 
        const users = await api("/api/users"); 
        list.innerHTML = users.map(u => `
            <div class="card" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; padding:12px;">
                <div>
                    <b>${u.full_name}</b>
                    <div class="meta" style="font-size:12px; color:var(--text-muted);">${u.role === 'admin' ? 'Администратор' : 'Сотрудник'}</div>
                </div>
                <button class="secondary" style="width:auto; padding:8px; font-size:12px; margin:0;" onclick="editUser(${u.tg_id}, '${u.full_name}', '${u.role}')">✏️</button>
            </div>
        `).join(""); 
    } catch (e) { list.innerHTML = `<p style="color:var(--danger)">${e.message}</p>`; } 
}

function editUser(tg_id, full_name, role) {
    const newName = prompt("Фамилия и Имя пользователя:", full_name);
    if (newName === null) return;
    const newRole = prompt("Роль (admin или employee):", role);
    if (newRole === null || (newRole !== 'admin' && newRole !== 'employee')) { notify("Некорректная роль"); return; }
    api(`/api/users/${tg_id}/update`, { method: "POST", body: JSON.stringify({ full_name: newName, role: newRole }) })
        .then(() => { notify("Сохранено"); loadUsers(); })
        .catch(e => notify(e.message));
}

function showUsers() { loadUsers(); showScreen("screen-users"); }

async function loadItems() { 
    const list = document.getElementById("items-list"); 
    list.innerHTML = "<p>Загрузка...</p>"; 
    try { 
        allItems = await api("/api/items"); 
        filterItems(); 
        loadMyItems(); 
    } catch (e) { list.innerHTML = `<p style="color:var(--danger)">${e.message}</p>`; } 
}

async function loadMyItems() { 
    try { 
        const myItems = await api("/api/my_items"); 
        const section = document.getElementById("my-items-section"); 
        const list = document.getElementById("my-items-list"); 
        if (!myItems.length) { section.classList.add("hidden"); return; } 
        section.classList.remove("hidden"); 
        list.innerHTML = myItems.map(i => `<div class="my-item-card"><div><div style="font-weight:bold;">${i.name}</div><div class="meta" style="font-size:12px; color:var(--text-muted);">${i.item_code} ${i.taken_for ? `(для ${i.taken_for})` : ""}</div></div><button class="my-item-btn" onclick="doReturnFromMain('${i.item_code}')">Вернуть</button></div>`).join(""); 
    } catch (e) { console.log(e); } 
}

async function doReturnFromMain(code) { try { await api(`/api/return?code=${encodeURIComponent(code)}`, { method: "POST" }); notify("Возвращено"); loadItems(); } catch (e) { notify(e.message); } }

function filterItems() { 
    const query = document.getElementById("search-input").value.toLowerCase(); 
    const filterLoc = parseInt(document.getElementById("filter-location").value) || 0;
    const filterSpot = document.getElementById("filter-spot").value;
    const filterKind = document.getElementById("filter-kind").value;

    const list = document.getElementById("items-list"); 
    const filtered = allItems.filter(i => {
        const matchesQuery = i.name.toLowerCase().includes(query) || i.code.toLowerCase().includes(query) || (i.serial_number && i.serial_number.toLowerCase().includes(query));
        const matchesLoc = !filterLoc || i.stocks.some(s => s.location_id === filterLoc);
        const matchesSpot = !filterSpot || i.stocks.some(s => s.spot === filterSpot);
        const matchesKind = !filterKind || i.kind === filterKind;
        return matchesQuery && matchesLoc && matchesSpot && matchesKind;
    });

    if (!filtered.length) { list.innerHTML = "<p style='grid-column: 1/-1; text-align:center; color:var(--text-muted);'>Ничего не найдено</p>"; return; } 
    
    list.innerHTML = filtered.map(i => { 
        let placesHtml = (i.stocks || []).map(s => `<div class="meta">📍 ${s.location_name}${s.spot ? ` · ${s.spot}` : ""}</div>`).join(""); 
        let brokenBadge = i.needs_repair ? `<span class="badge repair">🔧 Ремонт</span>` : ""; 
        let priceBadge = i.price ? `<span class="badge price">${i.price} ₽</span>` : ""; 
        let budgetBadge = i.budget_tag === 'КЦ' ? `<span class="badge budget-kc">КЦ</span>` : (i.budget_tag === 'ТХ' ? `<span class="badge budget-tx">ТХ</span>` : ""); 
        let buyoutBadge = i.buyout_status ? `<span class="badge buyout">💸 ${i.buyout_status}</span>` : ""; 
        let lowBadge = i.is_low ? `<span class="badge low">⚠️ Мало</span>` : ""; 
        let catBadge = i.category ? `<span class="badge category">${i.category}</span>` : "";
        
        return `
        <div class="card item-card" onclick="openItem('${i.code}')">
            ${i.photo ? `<img class="thumb" src="data:image/jpeg;base64,${i.photo}">` : `<div class="thumb" style="display:flex; align-items:center; justify-content:center; font-size:24px; color:var(--text-muted);">📦</div>`}
            <div class="name">${i.name}</div>
            <div class="meta">${i.code} · ${i.total} шт ${i.serial_number ? `· S/N: ${i.serial_number}` : ""}</div>
            ${placesHtml}
            <div style="margin-top:auto; padding-top:8px;">
                <span class="badge ${i.kind === 'equipment' ? 'eq' : 'cons'}">${i.kind === 'equipment' ? 'Оборуд.' : 'Расходник'}</span>
                ${catBadge} ${priceBadge} ${budgetBadge} ${buyoutBadge} ${lowBadge} ${brokenBadge}
            </div>
        </div>
        `; 
    }).join(""); 
}

async function showRooms() { showScreen("screen-rooms"); updateNavActive("nav-rooms"); const list = document.getElementById("rooms-list"); list.innerHTML = "<p>Загрузка...</p>"; try { const rooms = await api("/api/locations_view"); list.innerHTML = rooms.map(r => `<div class="card room-card" onclick="openRoom(${r.id}, '${r.name}')"><div><div class="room-title">${r.name}</div><div class="room-spots">Полки: ${r.spots.length > 0 ? r.spots.join(", ") : "нет"}</div></div><div class="room-arrow">›</div></div>`).join(""); } catch (e) { list.innerHTML = `<p style="color:var(--danger)">${e.message}</p>`; } }

async function openRoom(id, name) { 
    showScreen("screen-room-view"); currentRoomId = id; document.getElementById("room-title").textContent = name; 
    selectedItems = []; updateBatchUI(); 
    const list = document.getElementById("room-items"); list.innerHTML = "<p>Загрузка...</p>"; 
    try { 
        const data = await api(`/api/room_detail/${id}`); 
        let html = ""; 
        const shelfKeys = Object.keys(data.shelves).sort(); 
        if (shelfKeys.length > 0) { 
            shelfKeys.forEach((shelfName, index) => { 
                const shelfId = `shelf-${index}`; 
                html += `<div class="shelf-header" id="header-${shelfId}" onclick="toggleShelf('${shelfId}')"><span>📦 Полка: ${shelfName}</span><span class="shelf-arrow">▼</span></div><div class="shelf-content hidden" id="${shelfId}">`; 
                data.shelves[shelfName].forEach(item => { 
                    html += `<div class="card" style="display:flex; align-items:center; padding: 12px; margin-bottom:8px;"><input type="checkbox" data-code="${item.code}" style="width:22px; height:22px; margin-right:12px; accent-color:var(--primary);" onchange="toggleSelectItem('${item.code}', this)"><div style="flex:1;" onclick="openItem('${item.code}')"><div class="name" style="font-size:15px; font-weight:600; margin:0;">${item.name}</div><div class="meta">${item.code} · ${item.quantity} шт</div></div></div>`; 
                }); 
                html += `</div>`; 
            }); 
        } 
        if (data.no_shelf.length > 0) { 
            html += `<h2 style="font-size:16px; margin-top: 30px; color: var(--warning);">⚠️ Без полки</h2>`; 
            data.no_shelf.forEach(item => { 
                html += `<div class="card" style="display:flex; align-items:center; padding: 12px; margin-bottom:8px;"><input type="checkbox" data-code="${item.code}" style="width:22px; height:22px; margin-right:12px; accent-color:var(--primary);" onchange="toggleSelectItem('${item.code}', this)"><div style="flex:1;" onclick="openItem('${item.code}')"><div class="name" style="font-size:15px; font-weight:600; margin:0;">${item.name}</div><div class="meta">${item.code} · ${item.quantity} шт</div></div></div>`; 
            }); 
        } 
        list.innerHTML = html || "<p>В этой комнате пусто.</p>"; 
        setTimeout(updateBatchUI, 0);
    } catch (e) { list.innerHTML = `<p style="color:var(--danger)">${e.message}</p>`; } 
}

function updateBatchUI() {
    const total = document.querySelectorAll('#room-items input[type="checkbox"]').length;
    document.getElementById("selected-count").textContent = selectedItems.length;
    const selectAllBtn = document.getElementById("select-all-btn");
    const deselectAllBtn = document.getElementById("deselect-all-btn");
    const moveBtn = document.getElementById("batch-move-btn");
    if (selectedItems.length === 0) {
        selectAllBtn.style.display = total > 0 ? "block" : "none";
        deselectAllBtn.style.display = "none";
        moveBtn.style.display = "none";
    } else {
        selectAllBtn.style.display = "none";
        deselectAllBtn.style.display = "block";
        moveBtn.style.display = "block";
    }
}

function selectAllInRoom() {
    selectedItems = [];
    document.querySelectorAll('#room-items input[type="checkbox"]').forEach(cb => {
        cb.checked = true;
        const code = cb.getAttribute("data-code");
        if (code) selectedItems.push(code);
    });
    updateBatchUI();
}

function deselectAllInRoom() {
    selectedItems = [];
    document.querySelectorAll('#room-items input[type="checkbox"]').forEach(cb => { cb.checked = false; });
    updateBatchUI();
}

function toggleSelectItem(code, checkbox) {
    if (checkbox.checked) { if (!selectedItems.includes(code)) selectedItems.push(code); }
    else { selectedItems = selectedItems.filter(c => c !== code); }
    updateBatchUI();
}

function toggleShelf(shelfId) { const content = document.getElementById(shelfId); const header = document.getElementById(`header-${shelfId}`); if (content.classList.contains("hidden")) { content.classList.remove("hidden"); header.classList.add("open"); } else { content.classList.add("hidden"); header.classList.remove("open"); } }
function showBatchMoveForm() { document.getElementById("batch-to-location").innerHTML = locations.map(l => `<option value="${l.id}">${l.name}</option>`).join(""); document.getElementById("batch-to-spot").innerHTML = `<option value="">Без места</option>` + spots.map(s => `<option value="${s.name}">${s.name}</option>`).join(""); showScreen("screen-batch-move"); }
async function executeBatchMove() { const toLocation = parseInt(document.getElementById("batch-to-location").value); const toSpot = document.getElementById("batch-to-spot").value; if (toLocation === currentRoomId) { notify("Выберите другую комнату"); return; } try { await api("/api/move_batch", { method: "POST", body: JSON.stringify({ codes: selectedItems, from_location: currentRoomId, to_location: toLocation, to_spot: toSpot }) }); notify("Перемещено!"); showRooms(); } catch (e) { notify(e.message); } }

async function showOnHand() { showScreen("screen-on-hand"); const list = document.getElementById("on-hand-list"); list.innerHTML = "<p>Загрузка...</p>"; try { const rows = await api("/api/on_hand"); if (!rows || !rows.length) { list.innerHTML = "<p style='text-align:center; color:var(--text-muted);'>Все вещи на месте!</p>"; return; } list.innerHTML = rows.map(r => `<div class="card" onclick="openItem('${r.item_code}')"><div class="name">${r.name}</div><div class="meta">${r.item_code}</div><div class="meta" style="color:var(--warning); font-weight:600;">У ${r.full_name || 'Неизвестно'} ${r.taken_for ? `(для ${r.taken_for})` : ""}</div><div class="meta" style="font-size:12px;">Взято: ${new Date(r.taken_at + 'Z').toLocaleString('ru-RU')}</div></div>`).join(""); } catch (e) { list.innerHTML = `<p style="color:var(--danger)">Ошибка: ${e.message}</p>`; } }

function scanQr() { if (!tg.showScanQrPopup) { notify("Сканер QR доступен только с телефона"); return; } tg.showScanQrPopup({ text: "Наведите на QR товара" }, (text) => { if (text) { openItem(text.trim()); return true; } }); }

async function openItem(code) { try { currentItem = await api(`/api/items/${encodeURIComponent(code)}`); document.getElementById("item-title").textContent = currentItem.name; const repairBtn = document.getElementById("repair-btn"); if (currentItem.kind === 'consumable') { repairBtn.style.display = 'none'; } else { repairBtn.style.display = 'block'; } const editBtn = document.getElementById("edit-btn"); if (currentUser.role === 'admin') { editBtn.style.display = 'block'; } else { editBtn.style.display = 'none'; } let photoHtml = currentItem.photo ? `<img src="data:image/jpeg;base64,${currentItem.photo}" style="width:100%; max-height:200px; object-fit:contain; border-radius:12px; margin-bottom:16px; background:#fff;">` : ""; let minStockText = currentItem.kind === 'consumable' ? `<div class="meta">Мин. остаток: ${currentItem.min_stock}</div>` : ""; let priceBadge = currentItem.price ? `<div class="meta" style="color:var(--success); font-weight:bold;">💰 Стоимость: ${currentItem.price} ₽</div>` : ""; let budgetText = currentItem.budget_tag ? `<div class="meta" style="color:${currentItem.budget_tag === 'КЦ' ? 'var(--danger)' : 'var(--success)'}; font-weight:bold;">Бюджет: ${currentItem.budget_tag}</div>` : ""; let snText = currentItem.serial_number ? `<div class="meta">S/N: ${currentItem.serial_number}</div>` : ""; let catText = currentItem.category ? `<div class="meta" style="color:var(--purple); font-weight:bold;">Категория: ${currentItem.category}</div>` : ""; let buyoutText = currentItem.buyout_status ? `<div class="status-badge" style="background:var(--purple); color:white;">💸 На выкупе у: ${currentItem.buyout_status}</div>` : ""; if (currentItem.kit_body || currentItem.kit_lens || currentItem.kit_flash) { document.getElementById("kit-box").classList.remove("hidden"); document.getElementById("kit-body-text").innerHTML = currentItem.kit_body ? `<b>Тушка:</b> ${currentItem.kit_body}` : ""; document.getElementById("kit-lens-text").innerHTML = currentItem.kit_lens ? `<b>Объектив:</b> ${currentItem.kit_lens}` : ""; document.getElementById("kit-flash-text").innerHTML = currentItem.kit_flash ? `<b>Вспышка:</b> ${currentItem.kit_flash}` : ""; } else { document.getElementById("kit-box").classList.add("hidden"); } let statusHtml = ""; if (currentItem.needs_repair) { statusHtml = `<div class="status-badge status-broken">🔧 Требует ремонта</div>`; repairBtn.textContent = "✅ Вернуть в строй"; } else { repairBtn.textContent = "🔧 Отметить как «Требует ремонта»"; if (currentItem.holders.length > 0) { statusHtml = `<div class="status-badge status-taken">На руках у ${currentItem.holders[0].full_name} ${currentItem.holders[0].taken_for ? `(для ${currentItem.holders[0].taken_for})` : ""}</div>`; } else { let totalQty = currentItem.stocks.reduce((sum, s) => sum + s.quantity, 0); let places = currentItem.stocks.map(s => s.location_name + (s.spot ? ` (${s.spot})` : "")).filter((v,i,a)=>a.indexOf(v)===i).join(", "); statusHtml = currentItem.kind === 'equipment' ? `<div class="status-badge status-free">📍 Место хранения: ${places || "Не указано"}</div>` : `<div class="status-badge status-free">В наличии: ${places || "Нет"} (${totalQty} шт)</div>`; } } document.getElementById("item-status-box").innerHTML = `${photoHtml}<div class="meta">Код: ${currentItem.code}</div><div class="meta">Тип: ${currentItem.kind === 'equipment' ? 'оборудование' : 'расходник'}</div>${catText}${priceBadge}${budgetText}${snText}${minStockText}${buyoutText}${statusHtml}`; const bookingSection = document.getElementById("booking-section"); if (currentItem.kind === "consumable") { bookingSection.classList.add("hidden"); } else { bookingSection.classList.remove("hidden"); loadBookings(currentItem.code); } renderActions(); loadComments(currentItem.code); showScreen("screen-item"); } catch (e) { notify(e.message); } }

function showEditForm() { document.getElementById("edit-name").value = currentItem.name; document.getElementById("edit-kind").value = currentItem.kind; document.getElementById("edit-category").value = currentItem.category || ""; document.getElementById("edit-price").value = currentItem.price || 0; document.getElementById("edit-budget-tag").value = currentItem.budget_tag || ""; document.getElementById("edit-serial-number").value = currentItem.serial_number || ""; document.getElementById("edit-buyout-status").value = currentItem.buyout_status || ""; document.getElementById("edit-kit-body").value = currentItem.kit_body || ""; document.getElementById("edit-kit-lens").value = currentItem.kit_lens || ""; document.getElementById("edit-kit-flash").value = currentItem.kit_flash || ""; document.getElementById("edit-min-stock").value = currentItem.min_stock || 0; if (currentItem.kind === 'consumable') { document.getElementById("edit-consumable-fields").classList.remove("hidden"); } else { document.getElementById("edit-consumable-fields").classList.add("hidden"); } showScreen("screen-edit-item"); }
function toggleEditFields() { if (document.getElementById("edit-kind").value === "consumable") { document.getElementById("edit-consumable-fields").classList.remove("hidden"); } else { document.getElementById("edit-consumable-fields").classList.add("hidden"); } }

async function saveEditItem() { const name = document.getElementById("edit-name").value.trim(); const kind = document.getElementById("edit-kind").value; const category = document.getElementById("edit-category").value; const price = parseFloat(document.getElementById("edit-price").value) || 0; const budget_tag = document.getElementById("edit-budget-tag").value; const serial_number = document.getElementById("edit-serial-number").value.trim(); const buyout_status = document.getElementById("edit-buyout-status").value.trim(); const kit_body = document.getElementById("edit-kit-body").value.trim(); const kit_lens = document.getElementById("edit-kit-lens").value.trim(); const kit_flash = document.getElementById("edit-kit-flash").value.trim(); const minStock = parseInt(document.getElementById("edit-min-stock").value) || 0; try { await api(`/api/items/${currentItem.code}/update`, { method: "POST", body: JSON.stringify({ name, kind, min_stock: minStock, price, kit_body, kit_lens, kit_flash, budget_tag, serial_number, buyout_status, category }) }); notify("Сохранено"); openItem(currentItem.code); } catch (e) { notify(e.message); } }
async function deleteItemFromEdit() { if (!confirm(`Удалить "${currentItem.name}"?`)) return; try { await api(`/api/items/${encodeURIComponent(currentItem.code)}`, { method: "DELETE" }); notify("Удалено"); backToMain(); } catch (e) { notify(e.message); } }

async function showItemHistory() { showScreen("screen-item-history"); const list = document.getElementById("item-history-list"); list.innerHTML = "<p>Загрузка...</p>"; try { const logs = await api(`/api/history`); const filtered = logs.filter(l => l.item_code === currentItem.code); if (!filtered.length) { list.innerHTML = "<p>Нет истории по этому товару</p>"; return; } list.innerHTML = filtered.map(l => `<div class="card" style="display:block;"><div class="meta">${new Date(l.date + 'Z').toLocaleString('ru-RU')}</div><div>${l.type === 'checkout' ? 'Взял' : l.type === 'return' ? 'Вернул' : l.type === 'move' ? 'Переместил' : 'Списал'} — ${l.user_name} (${l.quantity} шт)</div></div>`).join(""); } catch (e) { list.innerHTML = `<p style="color:var(--danger)">${e.message}</p>`; } }

function renderActions() { const box = document.getElementById("actions"); const isEq = currentItem.kind === "equipment"; const myId = currentUser.tg_id; const myCheckout = currentItem.holders.find(h => h.user_id === myId); const otherCheckout = currentItem.holders.find(h => h.user_id !== myId); let html = ""; if (currentItem.needs_repair) { html += `<div class="status-badge status-broken">Выдача заблокирована</div>`; } else if (isEq) { if (myCheckout) { html += `<button class="ok" onclick="doReturn()">✅ Вернуть</button>`; } else if (otherCheckout) { html += `<button class="ok" onclick="doReturn()">✅ Вернуть за сотрудника</button>`; } else { if (currentItem.stocks.some(s => s.quantity > 0)) { html += `<button onclick="doCheckout()">📤 Взять себе</button><button class="secondary" onclick="doCheckoutFor()">📝 Взять для...</button>`; } } } else { html += `<h2 style="font-size:16px; margin-top:20px;">Списать</h2><select id="wo-loc">${currentItem.stocks.filter(s => s.quantity > 0).map(s => `<option value="${s.location_id}">${s.location_name} (${s.quantity} шт)</option>`).join("")}</select><input id="wo-qty" type="number" value="1" style="margin-top:10px;"><button class="danger" onclick="doWriteoff()">📉 Списать</button>`; } const stockOpts = currentItem.stocks.filter(s => s.quantity > 0).map(s => `<option value="${s.location_id}">${s.location_name} (${s.quantity} шт)</option>`).join(""); if (stockOpts) { html += `<h2 style="font-size:16px; margin-top:24px;">Переместить</h2><select id="mv-from">${stockOpts}</select><select id="mv-to" style="margin-top:10px;">${locations.map(l => `<option value="${l.id}">${l.name}</option>`).join("")}</select><input id="mv-qty" type="number" value="1" style="margin-top:10px;"><select id="mv-spot" style="margin-top:10px;"><option value="">Без места</option>${spots.map(s => `<option value="${s.name}">${s.name}</option>`).join("")}</select><button class="secondary" onclick="scanSpotQr()">📷 Сканировать полку</button><button class="secondary" onclick="doMove()">📦 Переместить</button>`; } box.innerHTML = html; }

async function markRepair() { try { const res = await api(`/api/items/${encodeURIComponent(currentItem.code)}/repair`, { method: "POST" }); notify(res.message); openItem(currentItem.code); } catch (e) { notify(e.message); } }
async function markLost() { if (!confirm("Сообщить всем, что вещи нет?")) return; try { const res = await api(`/api/items/${encodeURIComponent(currentItem.code)}/lost`, { method: "POST" }); notify(res.message); } catch (e) { notify(e.message); } }
async function doCheckout() { try { await api(`/api/checkout`, { method: "POST", body: JSON.stringify({ code: currentItem.code, taken_for: "" }) }); notify("Выдано"); openItem(currentItem.code); } catch (e) { notify(e.message); } }
async function doCheckoutFor() { const person = prompt("Для кого?"); if (person === null) return; try { await api(`/api/checkout`, { method: "POST", body: JSON.stringify({ code: currentItem.code, taken_for: person.trim() }) }); notify("Выдано"); openItem(currentItem.code); } catch (e) { notify(e.message); } }
async function doReturn() { try { await api(`/api/return?code=${encodeURIComponent(currentItem.code)}`, { method: "POST" }); notify("Возвращено"); openItem(currentItem.code); } catch (e) { notify(e.message); } }
async function doMove() { const from = parseInt(document.getElementById("mv-from").value); const to = parseInt(document.getElementById("mv-to").value); const qty = parseInt(document.getElementById("mv-qty").value) || 0; const spot = document.getElementById("mv-spot").value; if (from === to) { notify("Локации не должны совпадать"); return; } try { await api("/api/move", { method: "POST", body: JSON.stringify({ code: currentItem.code, from_location: from, to_location: to, quantity: qty, to_spot: spot }) }); notify("Перемещено!"); openItem(currentItem.code); } catch (e) { notify("Ошибка: " + e.message); } }
async function doWriteoff() { const loc = parseInt(document.getElementById("wo-loc").value); const qty = parseInt(document.getElementById("wo-qty").value) || 0; try { await api("/api/writeoff", { method: "POST", body: JSON.stringify({ code: currentItem.code, location_id: loc, quantity: qty }) }); notify("Списано"); openItem(currentItem.code); } catch (e) { notify(e.message); } }
function scanSpotQr() { if (!tg.showScanQrPopup) { notify("Сканер недоступен"); return; } tg.showScanQrPopup({ text: "Наведите на QR полки" }, (text) => { if (text) { document.getElementById("mv-spot").value = text.trim(); return true; } }); }
function showQr() { const url = `/api/qr/${currentItem.code}`; document.getElementById("item-status-box").innerHTML = `<div style="text-align:center; margin-top:10px;"><img src="${url}" style="width:200px; height:200px; border-radius:12px;" onclick="window.open('${url}')" /></div>`; document.getElementById("actions").innerHTML = ""; document.getElementById("booking-section").classList.add("hidden"); }
async function loadBookings(code) { const list = document.getElementById("bookings-list"); try { const rows = await api(`/api/bookings/${code}`); list.innerHTML = rows.length ? rows.map(r => `<div class="booking-item"><b>${r.full_name}</b>: ${r.date_from} — ${r.date_to}</div>`).join("") : ""; } catch (e) { list.innerHTML = ""; } }
async function doBook() { const from = document.getElementById("book-from").value; const to = document.getElementById("book-to").value; if (!from || !to) return; try { await api("/api/bookings", { method: "POST", body: JSON.stringify({ code: currentItem.code, date_from: from, date_to: to }) }); notify("Забронировано"); loadBookings(currentItem.code); } catch (e) { notify(e.message); } }
async function loadComments(code) { const list = document.getElementById("comments-list"); try { const rows = await api(`/api/comments/${code}`); list.innerHTML = rows.map(r => `<div class="comment-box"><b>${r.full_name}</b>: ${r.text}</div>`).join(""); } catch (e) { list.innerHTML = ""; } }
async function doComment() { const text = document.getElementById("comment-text").value.trim(); if (!text) return; try { await api("/api/comments", { method: "POST", body: JSON.stringify({ code: currentItem.code, text }) }); document.getElementById("comment-text").value = ""; loadComments(currentItem.code); } catch (e) { notify(e.message); } }
async function showAddForm() { try { const res = await api("/api/next_code"); document.getElementById("add-code").value = res.code; } catch (e) {} toggleFields(); showScreen("screen-add"); }
function toggleFields() { if (document.getElementById("add-kind").value === "consumable") { document.getElementById("consumable-fields").classList.remove("hidden"); } else { document.getElementById("consumable-fields").classList.add("hidden"); } }
async function saveItem() { const code = document.getElementById("add-code").value.trim(); const name = document.getElementById("add-name").value.trim(); const loc = parseInt(document.getElementById("add-location").value); if (!code || !name || !loc) { notify("Заполните код, название и локацию"); return; } const formData = new FormData(); formData.append("code", code); formData.append("name", name); formData.append("kind", document.getElementById("add-kind").value); formData.append("category", document.getElementById("add-category").value); formData.append("location_id", loc); formData.append("spot", document.getElementById("add-spot").value); formData.append("price", document.getElementById("add-price").value); formData.append("budget_tag", document.getElementById("add-budget-tag").value); formData.append("serial_number", document.getElementById("add-serial-number").value); formData.append("buyout_status", document.getElementById("add-buyout-status").value); formData.append("kit_body", document.getElementById("add-kit-body").value); formData.append("kit_lens", document.getElementById("add-kit-lens").value); formData.append("kit_flash", document.getElementById("add-kit-flash").value); if (document.getElementById("add-kind").value === "consumable") { formData.append("quantity", document.getElementById("add-qty").value); formData.append("min_stock", document.getElementById("add-min-stock").value); } const photoFile = document.getElementById("add-photo").files[0]; if (photoFile) formData.append("photo", photoFile); try { await api("/api/items", { method: "POST", body: formData }); notify("Добавлено"); backToMain(); } catch (e) { notify(e.message); } }
function showImportForm() { showScreen("screen-import"); }
async function submitText() { const text = document.getElementById("csv-text").value; if (!text.trim()) return; try { const res = await api("/api/import_text", { method: "POST", body: JSON.stringify({ text }) }); notify(`Загружено: ${res.added}, обновлено: ${res.updated}`); backToMain(); } catch (e) { notify(e.message); } }
function showSpotQrForm() { document.getElementById("spot-qr-result").innerHTML = ""; showScreen("screen-spot-qr"); }
async function createSpot() { const name = document.getElementById("spot-name").value.trim(); if (!name) return; try { await api("/api/spots", { method: "POST", body: JSON.stringify({ name }) }); notify("Полка создана"); const url = `/api/qr/${encodeURIComponent(name)}`; document.getElementById("spot-qr-result").innerHTML = `<img src="${url}" style="width:200px;" onclick="window.open('${url}')"><br>${name}`; } catch (e) { notify(e.message); } }
async function showHistory() { updateNavActive("nav-history"); const list = document.getElementById("history-list"); showScreen("screen-history"); list.innerHTML = "<p>Загрузка...</p>"; try { const logs = await api("/api/history"); const typeName = t => t === 'checkout' ? '📤 Взял' : t === 'return' ? '📥 Вернул' : t === 'move' ? '📦 Переместил' : t === 'writeoff' ? '📉 Списано' : t; list.innerHTML = logs.length ? logs.map(l => `<div class="card" style="display:block;"><div class="meta">${new Date(l.date + 'Z').toLocaleString('ru-RU')}</div><div>${typeName(l.type)} — ${l.name} (${l.quantity} шт) — ${l.user_name}</div></div>`).join("") : "<p>История пуста</p>"; } catch (e) { list.innerHTML = `<p style="color:var(--danger)">${e.message}</p>`; } }
function downloadHistory() { window.open("/api/export_history", "_blank"); }

function showScreen(id) { 
    ["screen-register", "screen-main", "screen-item", "screen-add", "screen-import", "screen-spot-qr", "screen-history", "screen-on-hand", "screen-rooms", "screen-room-view", "screen-users", "screen-settings", "screen-edit-item", "screen-batch-move", "screen-item-history"].forEach(s => { 
        const el = document.getElementById(s); 
        if (el) el.classList.toggle("hidden", s !== id); 
    }); 
    if (id === "screen-main") updateNavActive("nav-main");
    if (id === "screen-rooms") updateNavActive("nav-rooms");
    if (id === "screen-history") updateNavActive("nav-history");
    if (id === "screen-settings") updateNavActive("nav-settings");
    window.scrollTo(0, 0);
}

function backToMain() { showScreen("screen-main"); loadItems(); }

(async () => { await init(); })();
