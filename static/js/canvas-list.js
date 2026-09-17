// canvas-list.js — Project Workspace.
// Two-pane: LEFT project list, RIGHT Smart Canvas editor for the active project.
// Self-contained; relies only on global fetch / StudioI18n / lucide.

/* ===== Small helpers ===== */
function refreshIcons(){ if(window.lucide) lucide.createIcons(); }
function tr(key){ return window.StudioI18n ? StudioI18n.t(key) : key; }
function langIsEn(){ return window.StudioI18n?.lang?.() === 'en'; }
function escapeHtml(str){ return String(str == null ? '' : str).replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s])); }
function escapeAttr(str){ return escapeHtml(str); }
function L(zh, en){ return langIsEn() ? en : zh; }
function compactLabel(fullZh, compactZh, en){ return window.innerWidth <= 760 ? L(compactZh, en) : L(fullZh, en); }
const CANVAS_LIST_PROJECT_KEY = 'canvasListCurrentProjectId';

function rememberedProjectId(){
    try {
        return new URLSearchParams(window.location.search).get('project') || localStorage.getItem(CANVAS_LIST_PROJECT_KEY) || 'default';
    } catch(e){
        return 'default';
    }
}

function rememberProjectId(pid){
    if(!pid) return;
    try { localStorage.setItem(CANVAS_LIST_PROJECT_KEY, pid); } catch(e){}
}

function formatCanvasTime(value){
    if(!value) return '--';
    const raw = Number(value);
    const time = raw < 10000000000 ? raw * 1000 : raw;
    const date = new Date(time);
    if(Number.isNaN(date.getTime())) return '--';
    return date.toLocaleString(langIsEn() ? 'en-US' : 'zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });
}

function renderCanvasIcon(icon, size = 16){
    if(!icon || icon === '🧩') return `<i data-lucide="layers" style="width:${size}px;height:${size}px"></i>`;
    if(/[^\x00-\x7F]/.test(icon)) return escapeHtml(icon);
    return `<i data-lucide="${escapeHtml(icon)}" style="width:${size}px;height:${size}px"></i>`;
}

/* ===== DOM refs ===== */
const canvasFrame = document.getElementById('canvasFrame');
const projectListEl = document.getElementById('projectList');
const trashEntryBtn = document.getElementById('trashEntry');
const trashBadge = document.getElementById('trashBadge');
const trashPanel = document.getElementById('trashPanel');
const trashListEl = document.getElementById('trashList');
const trashCloseBtn = document.getElementById('trashClose');
const newProjectBtn = document.getElementById('newProjectBtn');
const newProjectRow = document.getElementById('newProjectRow');
const newProjectInput = document.getElementById('newProjectInput');
const newProjectConfirm = document.getElementById('newProjectConfirm');
const newProjectCancel = document.getElementById('newProjectCancel');
const statusEl = document.getElementById('boardStatus');

/* ===== State ===== */
let projects = [];
let canvases = [];          // all canvases across projects
let deletedCanvases = [];
let deletedProjects = [];   // projects in the recycle bin
let currentProjectId = rememberedProjectId();
let currentCanvasId = null;
let pendingDeleteProjectId = null;
let statusTimer = null;

/* ===== Status toast ===== */
function setStatus(text){
    if(!statusEl) return;
    if(!text){ statusEl.classList.remove('show'); return; }
    statusEl.textContent = text;
    statusEl.classList.add('show');
    clearTimeout(statusTimer);
    statusTimer = setTimeout(() => statusEl.classList.remove('show'), 2200);
}

/* ===== Data loading & Project selection ===== */
function currentProject(){ return projects.find(p => p.id === currentProjectId) || projects[0] || null; }
function canvasesInProject(pid){ return canvases.filter(c => (c.project || 'default') === pid); }

function projectCanvasCount(pid){
    const p = projects.find(x => x.id === pid);
    const live = canvasesInProject(pid).length;
    return canvases.length ? live : (p?.canvas_count || 0);
}

async function loadAll(){
    try {
        const [pRes, cRes, tRes] = await Promise.all([
            fetch('/api/projects'),
            fetch('/api/canvases'),
            fetch('/api/projects/trash')
        ]);
        const pData = pRes.ok ? await pRes.json() : { projects: [] };
        const cData = cRes.ok ? await cRes.json() : { canvases: [] };
        const tData = tRes.ok ? await tRes.json() : { projects: [] };
        projects = (pData.projects || []).slice().sort((a, b) => (a.order || 0) - (b.order || 0));
        if(!projects.length) projects = [{ id: 'default', name: L('默认项目','Default'), order: 0, canvas_count: 0 }];
        canvases = cData.canvases || [];
        deletedProjects = tData.projects || [];

        // pick first project (prefer default / order 0)
        if(!projects.find(p => p.id === currentProjectId)){
            const def = projects.find(p => p.id === 'default') || projects.slice().sort((a, b) => (a.order || 0) - (b.order || 0))[0];
            currentProjectId = def ? def.id : 'default';
        }
        rememberProjectId(currentProjectId);
        renderProjects();
        await loadCanvasForProject(currentProjectId);
        updateTrashBadge();
    } catch(e){
        console.error(e);
        setStatus(L('加载失败','Load failed'));
    }
}

/* ===== Smart Canvas Frame embedding ===== */
function setFrameCanvas(cid, pid){
    if(currentCanvasId === cid && canvasFrame.src && !canvasFrame.src.endsWith('about:blank')){
        return;
    }
    currentCanvasId = cid;
    rememberProjectId(pid);
    const enc = encodeURIComponent(cid);
    const project = encodeURIComponent(pid || currentProjectId || 'default');
    canvasFrame.src = `/static/smart-canvas.html?id=${enc}&project=${project}&embedded=1&v=2026.08.30.1789371883`;
}

async function persistMeta(id, patch){
    try {
        const res = await fetch(`/api/canvases/${encodeURIComponent(id)}/meta`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(patch)
        });
        if(!res.ok) throw new Error('meta save failed');
        const data = await res.json();
        if(data.canvas){
            const idx = canvases.findIndex(x => x.id === id);
            if(idx >= 0) canvases[idx] = { ...canvases[idx], ...data.canvas };
        }
    } catch(e){ console.error(e); }
}

async function loadCanvasForProject(pid){
    const p = projects.find(x => x.id === pid);
    const projName = p ? p.name : L('默认项目','Default');
    const items = canvasesInProject(pid);
    let targetCanvas = items.find(c => (c.kind || 'classic') === 'smart') || items[0];
    if(!targetCanvas){
        try {
            const res = await fetch('/api/canvases', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: projName,
                    icon: 'sparkles',
                    kind: 'smart',
                    project: pid,
                    board_x: 40,
                    board_y: 40
                })
            });
            if(res.ok){
                const data = await res.json();
                if(data.canvas){
                    targetCanvas = data.canvas;
                    canvases.push(targetCanvas);
                    renderProjects();
                }
            }
        } catch(e){
            console.error('Failed to auto-create canvas for project', e);
        }
    } else if(projName && targetCanvas.title !== projName){
        targetCanvas.title = projName;
        persistMeta(targetCanvas.id, { title: projName });
    }
    if(targetCanvas){
        setFrameCanvas(targetCanvas.id, pid);
    }
}

/* ===== Project sidebar rendering ===== */
function renderProjects(){
    projectListEl.innerHTML = '';
    projects.forEach(p => {
        if(pendingDeleteProjectId === p.id){
            const box = document.createElement('div');
            box.className = 'ws-project-confirm';
            box.innerHTML = `
                <div class="ws-project-confirm-title">${L('删除项目','Delete project')}「${escapeHtml(p.name)}」？${L('其下画布将一并移入回收站，30 天后自动清除。','Its canvases move to Trash and are cleared after 30 days.')}</div>
                <div class="ws-project-confirm-actions">
                    <button class="ws-confirm-btn" type="button">${L('删除','Delete')}</button>
                    <button class="ws-cancel-btn" type="button">${L('取消','Cancel')}</button>
                </div>`;
            box.querySelector('.ws-confirm-btn').onclick = () => deleteProject(p.id);
            box.querySelector('.ws-cancel-btn').onclick = () => { pendingDeleteProjectId = null; renderProjects(); };
            projectListEl.appendChild(box);
            return;
        }
        const row = document.createElement('div');
        row.className = 'ws-project-row' + (p.id === currentProjectId ? ' active' : '');
        row.dataset.projectId = p.id;
        const count = projectCanvasCount(p.id);
        const isDefault = p.id === 'default';
        row.innerHTML = `
            <span class="ws-project-icon"><i data-lucide="${isDefault ? 'folder' : 'folder-open'}" class="w-4 h-4"></i></span>
            <span class="ws-project-name">${escapeHtml(p.name)}</span>
            <span class="ws-project-count">${count}</span>
            <span class="ws-project-actions">
                <button class="ws-proj-act rename" type="button" title="${L('重命名','Rename')}" aria-label="${L('重命名','Rename')}"><i data-lucide="pencil" class="w-3.5 h-3.5"></i></button>
                ${isDefault ? '' : `<button class="ws-proj-act del" type="button" title="${L('删除','Delete')}" aria-label="${L('删除','Delete')}"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i></button>`}
            </span>`;
        row.onclick = e => {
            if(e.target.closest('.ws-proj-act')) return;
            selectProject(p.id);
        };
        const renameBtn = row.querySelector('.ws-proj-act.rename');
        if(renameBtn) renameBtn.onclick = e => { e.stopPropagation(); startProjectRename(p.id, row); };
        const delBtn = row.querySelector('.ws-proj-act.del');
        if(delBtn) delBtn.onclick = e => { e.stopPropagation(); pendingDeleteProjectId = p.id; renderProjects(); };
        projectListEl.appendChild(row);
    });
    refreshIcons();
    updateCapsuleLabel();
}

function selectProject(pid){
    closeProjectMenu();
    if(pid === currentProjectId && !trashPanel.classList.contains('active')) return;
    currentProjectId = pid;
    rememberProjectId(pid);
    closeTrashView();
    renderProjects();
    loadCanvasForProject(pid);
}

function startProjectRename(pid, row){
    const p = projects.find(x => x.id === pid);
    if(!p) return;
    const nameEl = row.querySelector('.ws-project-name');
    if(!nameEl || nameEl.querySelector('input')) return;
    const input = document.createElement('input');
    input.type = 'text'; input.maxLength = 60; input.value = p.name;
    input.className = 'ws-project-name-input';
    nameEl.replaceWith(input);
    input.focus(); input.select();
    input.onclick = e => e.stopPropagation();
    let done = false;
    const finish = commit => {
        if(done) return; done = true;
        const v = input.value.trim();
        if(commit && v && v !== p.name) renameProject(pid, v);
        else renderProjects();
    };
    input.onblur = () => finish(true);
    input.onkeydown = e => {
        e.stopPropagation();
        if(e.key === 'Enter'){ e.preventDefault(); finish(true); }
        if(e.key === 'Escape'){ e.preventDefault(); finish(false); }
    };
}

/* ===== Project CRUD ===== */
function openNewProject(){
    newProjectRow.classList.add('active');
    newProjectInput.value = '';
    newProjectInput.focus();
}
function closeNewProject(){
    newProjectRow.classList.remove('active');
    newProjectInput.value = '';
}
async function createProject(){
    const name = newProjectInput.value.trim() || L('新项目','New project');
    closeNewProject();
    try {
        const res = await fetch('/api/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if(!res.ok) throw new Error('create project failed');
        const data = await res.json();
        const proj = data.project;
        if(proj){
            let newCanvas = null;
            try {
                const cRes = await fetch('/api/canvases', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title: proj.name,
                        icon: 'sparkles',
                        kind: 'smart',
                        project: proj.id,
                        board_x: 40,
                        board_y: 40
                    })
                });
                if(cRes.ok){
                    const cData = await cRes.json();
                    if(cData.canvas){
                        newCanvas = cData.canvas;
                        canvases.push(newCanvas);
                    }
                }
            } catch(ce){
                console.error(ce);
            }
            projects.push(proj);
            projects.sort((a, b) => (a.order || 0) - (b.order || 0));
            currentProjectId = proj.id;
            rememberProjectId(currentProjectId);
            closeProjectMenu();
            renderProjects();
            if(newCanvas){
                setFrameCanvas(newCanvas.id, proj.id);
            } else {
                loadCanvasForProject(proj.id);
            }
        }
    } catch(e){
        console.error(e);
        setStatus(L('创建项目失败','Create project failed'));
    }
}
async function renameProject(pid, name){
    const p = projects.find(x => x.id === pid);
    if(p) p.name = name;
    renderProjects();
    const items = canvasesInProject(pid);
    items.forEach(c => {
        c.title = name;
        persistMeta(c.id, { title: name });
    });
    if(pid === currentProjectId && canvasFrame?.contentWindow){
        try {
            const doc = canvasFrame.contentDocument || canvasFrame.contentWindow.document;
            const titleEl = doc.getElementById('smartTitle');
            if(titleEl) titleEl.textContent = name;
        } catch(e){}
    }
    try {
        const res = await fetch(`/api/projects/${encodeURIComponent(pid)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if(!res.ok) throw new Error('rename project failed');
    } catch(e){ console.error(e); setStatus(L('重命名失败','Rename failed')); loadAll(); }
}
async function deleteProject(pid){
    pendingDeleteProjectId = null;
    try {
        const res = await fetch(`/api/projects/${encodeURIComponent(pid)}`, { method: 'DELETE' });
        if(!res.ok) throw new Error('delete project failed');
        const data = await res.json();
        // 从主列表移除，移入回收站
        const del = projects.find(p => p.id === pid);
        projects = projects.filter(p => p.id !== pid);
        if(del) deletedProjects.unshift(data.project || del);
        // 该项目下画布已随项目一并软删除，从本地画布列表移除
        canvases = canvases.filter(c => (c.project || 'default') !== pid);
        if(currentProjectId === pid) currentProjectId = 'default';
        rememberProjectId(currentProjectId);
        closeProjectMenu();
        renderProjects();
        updateTrashBadge();
        loadCanvasForProject(currentProjectId);
        setStatus(L('已移入回收站','Moved to Trash'));
    } catch(e){ console.error(e); setStatus(L('删除项目失败','Delete project failed')); loadAll(); }
}

/* ===== Trash / recycle bin ===== */
function updateTrashBadge(){
    const n = (deletedCanvases?.length || 0) + (deletedProjects?.length || 0);
    trashBadge.textContent = String(n);
    trashBadge.classList.toggle('visible', n > 0);
}
async function refreshTrashCount(){
    try {
        const [cRes, pRes] = await Promise.all([
            fetch('/api/canvases/trash'),
            fetch('/api/projects/trash')
        ]);
        if(cRes.ok){ const d = await cRes.json(); deletedCanvases = d.canvases || []; }
        if(pRes.ok){ const d = await pRes.json(); deletedProjects = d.projects || []; }
        updateTrashBadge();
    } catch(e){}
}
async function openTrashView(){
    closeProjectMenu();
    document.body.classList.add('trash-open');
    trashEntryBtn.classList.add('active');
    trashPanel.classList.add('active');
    await loadTrash();
}
function closeTrashView(){
    document.body.classList.remove('trash-open');
    trashEntryBtn.classList.remove('active');
    trashPanel.classList.remove('active');
}
async function reloadCanvases(){
    try {
        const res = await fetch('/api/canvases');
        if(res.ok){
            const data = await res.json();
            canvases = data.canvases || [];
        }
    } catch(e){ console.error(e); }
}
async function loadTrash(){
    try {
        const [cRes, pRes] = await Promise.all([
            fetch('/api/canvases/trash'),
            fetch('/api/projects/trash')
        ]);
        if(!cRes.ok && !pRes.ok) throw new Error('trash load failed');
        if(cRes.ok){ const d = await cRes.json(); deletedCanvases = d.canvases || []; }
        if(pRes.ok){ const d = await pRes.json(); deletedProjects = d.projects || []; }
        renderTrash();
        updateTrashBadge();
    } catch(e){ console.error(e); setStatus(L('加载回收站失败','Load trash failed')); }
}
function renderTrash(){
    trashListEl.innerHTML = '';
    // 同一份画布不要重复展示：项目卡片上已经标了「N 个画布」，
    // 它下面的画布就不再单独列出来了——避免「同一个画布在项目/画布两块各出一张卡」。
    const trashedProjectIds = new Set(deletedProjects.map(p => p.id));
    const standaloneCanvases = deletedCanvases.filter(c => !(c.project && trashedProjectIds.has(c.project)));
    const hasItems = deletedProjects.length > 0 || standaloneCanvases.length > 0;
    if(!hasItems){
        const empty = document.createElement('div');
        empty.className = 'ws-trash-empty';
        empty.textContent = L('回收站为空','Trash is empty');
        trashListEl.appendChild(empty);
        return;
    }
    deletedProjects.forEach(p => {
        const card = buildProjectTrashCard(p);
        if(card) trashListEl.appendChild(card);
    });
    standaloneCanvases.forEach(c => {
        const card = buildCanvasTrashCard(c);
        if(card) trashListEl.appendChild(card);
    });
    refreshIcons();
}
function buildProjectTrashCard(p){
    const cnt = p.canvas_count || 0;
    const card = document.createElement('div');
    card.className = 'ws-trash-card';
    card.dataset.projectId = p.id;
    card.innerHTML = `
        <div class="ws-card-top">
            <span class="ws-card-icon"><i data-lucide="folder-open" class="w-4 h-4"></i></span>
            <span class="ws-card-kind classic">${L('项目','Project')}</span>
        </div>
        <div class="ws-card-title">${escapeHtml(p.name)}</div>
        <div class="ws-card-meta"><span class="ws-card-nodes">${cnt > 0 ? cnt + L(' 个画布',' canvases') : L('无画布','No canvases')}</span><span class="ws-card-meta-dot"></span><span class="ws-card-time">${formatCanvasTime(p.deleted_at)}</span></div>
        <div class="ws-card-actions">
            <button class="ws-trash-act restore" type="button"><i data-lucide="rotate-ccw" class="w-3.5 h-3.5"></i><span>${L('恢复','Restore')}</span></button>
            <button class="ws-trash-act purge" type="button"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i><span>${L('彻底删除','Delete')}</span></button>
        </div>
        <div class="ws-trash-confirm">
            <div class="ws-trash-confirm-title">${L('彻底删除项目？其下画布一并清除，不可恢复','Delete project permanently? Its canvases are also removed.')}</div>
            <div class="ws-trash-confirm-actions">
                <button class="ws-trash-confirm-yes" type="button">${L('删除','Delete')}</button>
                <button class="ws-trash-confirm-no" type="button">${L('取消','Cancel')}</button>
            </div>
        </div>`;
    card.querySelector('.ws-trash-act.restore').onclick = () => restoreProject(p.id);
    card.querySelector('.ws-trash-act.purge').onclick = () => card.classList.add('confirming');
    card.querySelector('.ws-trash-confirm-yes').onclick = () => purgeProject(p.id);
    card.querySelector('.ws-trash-confirm-no').onclick = () => card.classList.remove('confirming');
    return card;
}
function buildCanvasTrashCard(c){
    const isSmart = (c.kind || 'classic') === 'smart';
    const projName = (projects.find(p => p.id === (c.project || 'default')) || {}).name || L('默认项目','Default');
    const card = document.createElement('div');
    card.className = 'ws-trash-card';
    card.dataset.canvasId = c.id;
    card.innerHTML = `
        <div class="ws-card-top">
            <span class="ws-card-icon">${renderCanvasIcon(isSmart && /[^\x00-\x7F]/.test(c.icon || '') ? 'sparkles' : c.icon, 17)}</span>
            <span class="ws-card-kind ${isSmart ? 'smart' : 'classic'}">${isSmart ? L('智能','Smart') : L('普通','Classic')}</span>
        </div>
        <div class="ws-card-title">${escapeHtml(c.title)}</div>
        <div class="ws-card-meta"><span class="ws-card-nodes">${escapeHtml(projName)}</span><span class="ws-card-meta-dot"></span><span class="ws-card-time">${formatCanvasTime(c.deleted_at)}</span></div>
        <div class="ws-card-actions">
            <button class="ws-trash-act restore" type="button"><i data-lucide="rotate-ccw" class="w-3.5 h-3.5"></i><span>${L('恢复','Restore')}</span></button>
            <button class="ws-trash-act purge" type="button"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i><span>${L('彻底删除','Delete')}</span></button>
        </div>
        <div class="ws-trash-confirm">
            <div class="ws-trash-confirm-title">${L('彻底删除？不可恢复','Delete permanently?')}</div>
            <div class="ws-trash-confirm-actions">
                <button class="ws-trash-confirm-yes" type="button">${L('删除','Delete')}</button>
                <button class="ws-trash-confirm-no" type="button">${L('取消','Cancel')}</button>
            </div>
        </div>`;
    card.querySelector('.ws-trash-act.restore').onclick = () => restoreCanvas(c.id);
    card.querySelector('.ws-trash-act.purge').onclick = () => card.classList.add('confirming');
    card.querySelector('.ws-trash-confirm-yes').onclick = () => purgeCanvas(c.id);
    card.querySelector('.ws-trash-confirm-no').onclick = () => card.classList.remove('confirming');
    return card;
}
async function restoreCanvas(id){
    try {
        const res = await fetch(`/api/canvases/${encodeURIComponent(id)}/restore`, { method: 'POST' });
        if(!res.ok) throw new Error('restore failed');
        deletedCanvases = deletedCanvases.filter(c => c.id !== id);
        await loadAll();
        renderTrash();
        setStatus(L('已恢复','Restored'));
    } catch(e){ console.error(e); setStatus(L('恢复失败','Restore failed')); }
}
async function purgeCanvas(id){
    try {
        const res = await fetch(`/api/canvases/${encodeURIComponent(id)}/purge`, { method: 'DELETE' });
        if(!res.ok) throw new Error('purge failed');
        deletedCanvases = deletedCanvases.filter(c => c.id !== id);
        renderTrash();
        updateTrashBadge();
        setStatus(L('已彻底删除','Deleted'));
    } catch(e){ console.error(e); setStatus(L('删除失败','Delete failed')); }
}
async function restoreProject(id){
    try {
        const res = await fetch(`/api/projects/${encodeURIComponent(id)}/restore`, { method: 'POST' });
        if(!res.ok) throw new Error('restore project failed');
        const data = await res.json();
        const proj = data.project;
        deletedProjects = deletedProjects.filter(p => p.id !== id);
        if(proj){
            projects.push(proj);
            projects.sort((a, b) => (a.order || 0) - (b.order || 0));
            currentProjectId = proj.id;
            rememberProjectId(currentProjectId);
        }
        await reloadCanvases();
        renderProjects();
        renderTrash();
        updateTrashBadge();
        loadCanvasForProject(currentProjectId);
        setStatus(L('已恢复项目','Project restored'));
    } catch(e){ console.error(e); setStatus(L('恢复失败','Restore failed')); }
}
async function purgeProject(id){
    try {
        const res = await fetch(`/api/projects/${encodeURIComponent(id)}/purge`, { method: 'DELETE' });
        if(!res.ok) throw new Error('purge project failed');
        deletedProjects = deletedProjects.filter(p => p.id !== id);
        // 该项目下画布也一并被永久删除，从回收站画布列表里移除
        deletedCanvases = deletedCanvases.filter(c => (c.project || 'default') !== id);
        renderTrash();
        updateTrashBadge();
        setStatus(L('已彻底删除','Deleted'));
    } catch(e){ console.error(e); setStatus(L('删除失败','Delete failed')); }
}

/* ===== Event bindings ===== */
newProjectBtn.addEventListener('click', openNewProject);
newProjectConfirm.addEventListener('click', createProject);
newProjectCancel.addEventListener('click', closeNewProject);
newProjectInput.addEventListener('keydown', e => {
    if(e.key === 'Enter'){ e.preventDefault(); createProject(); }
    if(e.key === 'Escape'){ e.preventDefault(); closeNewProject(); }
});

trashEntryBtn.addEventListener('click', () => {
    if(trashPanel.classList.contains('active')) closeTrashView();
    else openTrashView();
});
trashCloseBtn.addEventListener('click', closeTrashView);

document.addEventListener('keydown', e => {
    if(e.key !== 'Escape') return;
    if(capsuleIsOpen()){ closeProjectMenu(); return; }
    if(trashPanel.classList.contains('active')) closeTrashView();
});

// language switch from parent (index.html) via postMessage
window.addEventListener('message', event => {
    if(event.origin && event.origin !== location.origin) return;
    if(event.data?.type === 'studio-lang'){
        if(event.data.lang && window.StudioI18n) StudioI18n.set(event.data.lang);
        window.StudioI18n?.apply?.();
        renderProjects();
        refreshCapsuleTexts();
        if(trashPanel.classList.contains('active')) renderTrash();
        refreshIcons();
    }
});

/* ===== 项目胶囊（接管原左侧项目栏） =====
   项目数据与新建/重命名/删除/切换逻辑都在本页，画布只是 iframe，所以胶囊由本页渲染。
   胶囊挂在 body 下（不在 .workspace 里），因此用的是真实视觉像素；
   位置与尺度由 syncProjectCapsule() 实测 iframe 内 .smart-title 的布局盒得到 ——
   父页面用 zoom 缩放、画布页内部用另一套 scale，两者系数不同（实测 0.805 vs 0.951），
   硬编码 22px 一定会错位。 */
const projectCapsule = document.getElementById('projectCapsule');
const projectCapsuleBtn = document.getElementById('projectCapsuleBtn');
const projectCapsuleName = document.getElementById('projectCapsuleName');
const projectMenuTitle = document.getElementById('projectMenuTitle');
const newProjectLabel = document.getElementById('newProjectLabel');
const trashLabelEl = trashEntryBtn ? trashEntryBtn.querySelector('.ws-trash-label') : null;

function currentProjectName(){
    const p = currentProject();
    return p ? p.name : L('默认项目','Default');
}

function updateCapsuleLabel(){
    if(projectCapsuleName) projectCapsuleName.textContent = currentProjectName();
}

function refreshCapsuleTexts(){
    if(projectMenuTitle) projectMenuTitle.textContent = L('项目','Projects');
    if(newProjectLabel) newProjectLabel.textContent = L('新建项目','New project');
    if(trashLabelEl) trashLabelEl.textContent = L('回收站','Trash');
    if(newProjectInput) newProjectInput.placeholder = L('项目名称','Project name');
    updateCapsuleLabel();
}

function syncProjectCapsule(){
    if(!projectCapsule) return;
    let x = 22, y = 22, h = 40, fs = 13, padx = 14;
    try {
        const idoc = canvasFrame && canvasFrame.contentDocument;
        const pill = idoc && idoc.getElementById ? idoc.getElementById('smartTitle') : null;
        const r = pill && pill.getBoundingClientRect ? pill.getBoundingClientRect() : null;
        if(r && r.width > 0 && r.height > 0){
            const view = idoc.defaultView || window;
            const ps = view.getComputedStyle(pill);
            const cssH = parseFloat(ps.height) || 40;
            const k = cssH > 0 ? (r.height / cssH) : 1;   // 画布内视觉缩放系数
            x = r.left; y = r.top; h = r.height;
            fs = (parseFloat(ps.fontSize) || 13) * k;
            padx = (parseFloat(ps.paddingLeft) || 14) * k;
        }
    } catch(e){}
    projectCapsule.style.setProperty('--pc-x', x + 'px');
    projectCapsule.style.setProperty('--pc-y', y + 'px');
    projectCapsule.style.setProperty('--pc-h', h + 'px');
    projectCapsule.style.setProperty('--pc-fs', fs + 'px');
    projectCapsule.style.setProperty('--pc-padx', padx + 'px');
    projectCapsule.hidden = false;
    updateCapsuleLabel();
}

// 画布是 iframe，点在画布上的事件不会冒泡到本页，得直接挂到它的 document 上才能收起浮窗。
function bindFrameOutsideClick(){
    try {
        const idoc = canvasFrame && canvasFrame.contentDocument;
        if(!idoc || idoc.__capsuleOutsideBound) return;
        idoc.__capsuleOutsideBound = true;
        idoc.addEventListener('mousedown', () => { if(capsuleIsOpen()) closeProjectMenu(); }, true);
    } catch(e){}
}

function capsuleIsOpen(){
    return !!projectCapsule && projectCapsule.classList.contains('open');
}
function openProjectMenu(){
    if(!projectCapsule || capsuleIsOpen()) return;
    closeNewProject();
    pendingDeleteProjectId = null;
    renderProjects();
    projectCapsule.classList.add('open');
    projectCapsuleBtn.setAttribute('aria-expanded','true');
    refreshIcons();
}
function closeProjectMenu(){
    if(!capsuleIsOpen()) return;
    projectCapsule.classList.remove('open');
    projectCapsuleBtn.setAttribute('aria-expanded','false');
    pendingDeleteProjectId = null;
    closeNewProject();
    renderProjects();
}
function toggleProjectMenu(){ capsuleIsOpen() ? closeProjectMenu() : openProjectMenu(); }

if(projectCapsuleBtn){
    projectCapsuleBtn.addEventListener('click', e => { e.stopPropagation(); toggleProjectMenu(); });
}
document.addEventListener('click', e => {
    if(!capsuleIsOpen()) return;
    if(projectCapsule && projectCapsule.contains(e.target)) return;
    closeProjectMenu();
});
window.addEventListener('resize', syncProjectCapsule);
window.addEventListener('studio-ui-scale-change', () => setTimeout(syncProjectCapsule, 160));

/* ===== Boot ===== */
window.StudioI18n?.apply?.();
refreshCapsuleTexts();
// 先立即显示一次：不等 iframe 的 load 事件。否则画布页加载慢、或 load 因任何原因
// 未触发时，胶囊会一直停在 HTML 上的 hidden 状态，表现为「项目功能整个不见了」。
syncProjectCapsule();
if(canvasFrame){
    canvasFrame.addEventListener('load', () => {
        // 画布页加载后还会再套一层自身 scale，晚一点补测两次把位置钉准
        syncProjectCapsule();
        bindFrameOutsideClick();
        setTimeout(() => { syncProjectCapsule(); bindFrameOutsideClick(); }, 260);
        setTimeout(syncProjectCapsule, 900);
    });
    // 兜底：load 事件没来时也补测一次
    setTimeout(syncProjectCapsule, 1500);
}
loadAll();
refreshIcons();
