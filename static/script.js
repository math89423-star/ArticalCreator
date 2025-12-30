console.log("Script.js loaded successfully"); 

// ============================================================
// 0. 全局状态管理
// ============================================================
let currentUserId = null;
let taskList = [];          
let currentTaskId = null;   
let currentRewritingTitle = null; 

// 运行时状态
let parsedStructure = []; 
let fullMarkdownText = "";
let isPaused = false;
let abortController = null; 
let selectedFiles = [];     
let currentEventIndex = 0;
// 章节撤销历史记录 { "章节标题": "旧的内容文本" }
let sectionUndoHistory = {}; 
// [新增] 当前正在进行的精简任务数量
let activeRefineTasks = 0;

marked.setOptions({
    breaks: true, 
    gfm: true
});

// ============================================================
// 1. Initialization & Auth
// ============================================================

window.handleLogin = async function() {
    const inputId = document.getElementById('userIdInput').value.trim();
    const msgSpan = document.getElementById('loginMsg');
    const btn = document.getElementById('loginBtn');
    
    if (!inputId) { 
        msgSpan.innerText = "请输入卡密"; 
        msgSpan.className = "text-danger"; 
        return; 
    }
    btn.disabled = true; 
    btn.innerText = "验证中...";

    await verifyAndLogin(inputId, btn, msgSpan);
};

window.onload = async function() {
    const loginBtn = document.getElementById('loginBtn');
    if (loginBtn) {
        loginBtn.addEventListener('click', handleLogin);
    }

    const storedUser = localStorage.getItem('paper_active_user');
    if (storedUser) {
        await verifyAndLogin(storedUser);
    } else {
        document.getElementById('loginOverlay').style.display = 'flex';
    }
};

async function verifyAndLogin(key, btn = null, msgSpan = null) {
    try {
        const res = await fetch('/verify_login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ key: key })
        });
        const data = await res.json();
        
        if (res.ok) {
            currentUserId = key;
            localStorage.setItem('paper_active_user', key);
            document.getElementById('loginOverlay').style.display = 'none';
            document.getElementById('mainApp').style.filter = 'none';
            document.getElementById('displayUserId').innerText = key;
            if(msgSpan) { msgSpan.innerText = "登录成功！"; msgSpan.className = "text-success"; }
            
            initTaskManager();
        } else {
            if(msgSpan) { 
                msgSpan.innerText = data.msg || "登录失败"; 
                msgSpan.className = "text-danger";
            }
            if(btn) { btn.disabled = false; btn.innerText = "验证并登录"; }
            if(!document.getElementById('userIdInput').value) localStorage.removeItem('paper_active_user');
        }
    } catch(e) { 
        console.error(e); 
        if(btn) { btn.disabled = false; btn.innerText = "验证并登录"; }
        if(msgSpan) { msgSpan.innerText = "网络请求错误"; msgSpan.className = "text-danger"; }
    }
}

window.logout = function() {
    if(confirm("确定退出登录吗？")) {
        localStorage.removeItem('paper_active_user');
        location.reload();
    }
};

// ============================================================
// 2. 任务管理器逻辑
// ============================================================

window.initTaskManager = function() {
    const stored = localStorage.getItem(`tasks_meta_${currentUserId}`);
    taskList = stored ? JSON.parse(stored) : [];
    
    if (taskList.length === 0) {
        createNewTask(); 
    } else {
        const lastActive = localStorage.getItem(`last_active_id_${currentUserId}`);
        const targetId = taskList.find(t => t.id === lastActive) ? lastActive : taskList[0].id;
        switchTask(targetId);
    }
    renderTaskListUI();
};

window.createNewTask = function() {
    if (currentTaskId) saveCurrentTaskState();

    const newTask = {
        id: generateUUID(),
        title: "新论文任务 " + (taskList.length + 1),
        status: 'draft', 
        timestamp: Date.now()
    };
    taskList.unshift(newTask); 
    saveTaskListMeta();
    switchTask(newTask.id);
    
    setTimeout(() => {
        const collapseEl = document.getElementById('taskCollapseArea');
        if(collapseEl && window.bootstrap) {
            try { bootstrap.Collapse.getOrCreateInstance(collapseEl).show(); } catch(e){}
        }
    }, 100);
};

window.createNewPaper = function() {
    createNewTask();
};

window.switchTask = function(targetId) {
    if (currentTaskId === targetId && document.getElementById('paperTitle').value) return; 

    if (currentTaskId) {
        saveCurrentTaskState(); 
        if (abortController) {
            abortController.abort(); 
            abortController = null;
        }
    }

    currentTaskId = targetId;
    localStorage.setItem(`last_active_id_${currentUserId}`, targetId);
    resetWorkspaceVariables(); 
    
    loadTaskState(targetId);
    renderTaskListUI(); 

    const taskMeta = taskList.find(t => t.id === targetId);
    if (taskMeta) {
        if (taskMeta.status === 'running' || taskMeta.status === 'paused') {
            lockUI(true);
            subscribeTask(targetId); 
        } else {
            lockUI(false); 
        }
        isPaused = (taskMeta.status === 'paused');
        updatePauseBtnState();
    }
};

window.deleteTask = function(e, id) {
    e.stopPropagation(); 
    if (!confirm("确定删除该任务及其所有内容吗？此操作不可恢复。")) return;

    localStorage.removeItem(`draft_${currentUserId}_${id}`);
    taskList = taskList.filter(t => t.id !== id);
    saveTaskListMeta();

    if (id === currentTaskId) {
        currentTaskId = null;
        if (abortController) abortController.abort();
        if (taskList.length > 0) switchTask(taskList[0].id);
        else createNewTask();
    } else {
        renderTaskListUI();
    }
};

window.renderTaskListUI = function() {
    const container = document.getElementById('taskListContainer');
    if (!container) return;
    
    container.innerHTML = '';
    const sortedTasks = [...taskList].sort((a, b) => b.timestamp - a.timestamp);

    if (sortedTasks.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-3 small">暂无任务</div>';
        return;
    }

    sortedTasks.forEach(task => {
        const isActive = (task.id === currentTaskId);
        const item = document.createElement('div');
        item.className = `task-item ${isActive ? 'active-task' : ''}`;
        
        let statusBadge = '';
        if (task.status === 'running') statusBadge = '<span class="badge bg-primary bg-opacity-10 text-primary ms-2" style="font-size:0.7rem">生成中</span>';
        else if (task.status === 'paused') statusBadge = '<span class="badge bg-warning bg-opacity-10 text-warning ms-2" style="font-size:0.7rem">暂停</span>';
        else if (task.status === 'completed') statusBadge = '<span class="badge bg-success bg-opacity-10 text-success ms-2" style="font-size:0.7rem">完成</span>';
        
        item.innerHTML = `
            <div class="d-flex justify-content-between align-items-center mb-1">
                <div class="d-flex align-items-center" style="max-width: 75%;">
                    <span class="fw-bold text-truncate text-dark" style="font-size: 0.9rem;">${task.title || '未命名任务'}</span>
                    ${statusBadge}
                </div>
                <button class="btn btn-link text-danger p-0 task-delete-btn" onclick="deleteTask(event, '${task.id}')" title="删除任务">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
            <div class="d-flex justify-content-between align-items-center">
                <small class="text-muted" style="font-size: 0.75rem">
                    <i class="bi bi-clock"></i> ${new Date(task.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                </small>
                <small class="text-muted" style="font-size: 0.75rem">ID: ${task.id.slice(0,4)}</small>
            </div>
        `;
        item.onclick = (e) => {
            if (e.target.closest('.task-delete-btn')) return;
            switchTask(task.id);
        };
        container.appendChild(item);
    });
};

window.showHistory = function() {
    const modalEl = document.getElementById('historyModal');
    const container = document.getElementById('historyList');
    container.innerHTML = '';
    taskList.forEach(t => {
        const d = new Date(t.timestamp);
        container.innerHTML += `
            <div class="p-2 border-bottom history-item" onclick="switchTask('${t.id}'); bootstrap.Modal.getInstance(document.getElementById('historyModal')).hide();">
                <div class="d-flex justify-content-between">
                    <strong>${t.title}</strong>
                    <span class="text-muted small">${d.toLocaleDateString()} ${d.toLocaleTimeString()}</span>
                </div>
                <div class="small text-muted">ID: ${t.id} | 状态: ${t.status}</div>
            </div>
        `;
    });
    new bootstrap.Modal(modalEl).show();
};

function saveTaskListMeta() {
    localStorage.setItem(`tasks_meta_${currentUserId}`, JSON.stringify(taskList));
}

function saveCurrentTaskState() {
    if (!currentUserId || !currentTaskId) return;

    const title = document.getElementById('paperTitle').value;
    const draftData = {
        title: title,
        outline: document.getElementById('outlineRaw').value,
        refs: document.getElementById('references').value,
        customData: document.getElementById('customData').value,
        content: fullMarkdownText,
        structure: parsedStructure,
        eventIndex: currentEventIndex, 
        logsHtml: document.getElementById('logArea').innerHTML, 
        undoHistory: sectionUndoHistory, 
        timestamp: Date.now()
    };

    localStorage.setItem(`draft_${currentUserId}_${currentTaskId}`, JSON.stringify(draftData));

    const taskMeta = taskList.find(t => t.id === currentTaskId);
    if (taskMeta) {
        if (title) taskMeta.title = title;
        taskMeta.timestamp = Date.now();
        saveTaskListMeta();
    }
}

function loadTaskState(id) {
    const json = localStorage.getItem(`draft_${currentUserId}_${id}`);
    if (!json) return; 

    const data = JSON.parse(json);
    
    document.getElementById('paperTitle').value = data.title || "";
    document.getElementById('outlineRaw').value = data.outline || "";
    document.getElementById('references').value = data.refs || "";
    document.getElementById('customData').value = data.customData || "";
    
    parsedStructure = data.structure || [];
    fullMarkdownText = data.content || "";
    currentEventIndex = data.eventIndex || 0;
    sectionUndoHistory = data.undoHistory || {}; 

    if (parsedStructure.length > 0) renderConfigArea();
    if (fullMarkdownText) {
        renderEnrichedResult(fullMarkdownText);
    }
    if (data.logsHtml) document.getElementById('logArea').innerHTML = data.logsHtml;
}

function resetWorkspaceVariables() {
    fullMarkdownText = "";
    parsedStructure = [];
    selectedFiles = []; 
    currentEventIndex = 0;
    isPaused = false;
    currentRewritingTitle = null; 
    sectionUndoHistory = {}; 
    activeRefineTasks = 0; // 重置任务计数
    
    document.getElementById('paperTitle').value = "";
    document.getElementById('outlineRaw').value = "";
    document.getElementById('references').value = "";
    document.getElementById('customData').value = "";
    document.getElementById('fileListDisplay').innerHTML = "";
    document.getElementById('chapterConfigArea').innerHTML = "<div class='text-center text-muted small py-4'>请先解析大纲...</div>";
    document.getElementById('logArea').innerHTML = "准备就绪...";
    document.getElementById('resultContent').innerHTML = "<div class='text-center text-muted mt-5 pt-5'><p style='font-size: 1.2rem;'>💡 登录 -> 解析大纲 -> 智能分配 -> 开始生成</p></div>";
    document.getElementById('totalWords').innerText = "0";
}

// ============================================================
// 4. 提交与生成逻辑
// ============================================================

const paperForm = document.getElementById('paperForm');
if (paperForm) {
    paperForm.onsubmit = async (e) => {
        e.preventDefault();
        
        const btnSubmit = document.getElementById('btnSubmit');
        if(btnSubmit.disabled) return; 
        
        const originalBtnText = btnSubmit.innerText;
        btnSubmit.disabled = true;
        btnSubmit.innerText = "⏳ 正在启动...";

        if (!parsedStructure || parsedStructure.length === 0) {
            const rawOutline = document.getElementById('outlineRaw').value.trim();
            if (rawOutline) {
                parseOutline();
                if (!parsedStructure || parsedStructure.length === 0) {
                    alert("❌ 自动解析失败，请检查大纲格式！");
                    btnSubmit.disabled = false;
                    btnSubmit.innerText = originalBtnText; 
                    return;
                }
            } else {
                alert("⚠️ 请先填写大纲！");
                btnSubmit.disabled = false;
                btnSubmit.innerText = originalBtnText;
                return;
            }
        }

        const taskMeta = taskList.find(t => t.id === currentTaskId);
        if (!taskMeta) { createNewTask(); return; } 

        taskMeta.status = 'running';
        taskMeta.title = document.getElementById('paperTitle').value || "未命名任务";
        saveTaskListMeta();
        renderTaskListUI();

        if (abortController) abortController.abort();
        abortController = new AbortController();
        currentEventIndex = 0; 
        isPaused = false;
        
        const flatTasks = [];
        parsedStructure.forEach(group => {
            flatTasks.push({ title: group.title, is_parent: true, level: 1, words: 0 });
            group.children.forEach(child => {
                flatTasks.push({ 
                    title: child.text, is_parent: false, words: child.words || 0, 
                    use_data: child.useData, level: child.level || 2 
                });
            });
        });

        lockUI(true); 
        saveCurrentTaskState();

        const formData = new FormData();
        formData.append('title', taskMeta.title);
        formData.append('references', document.getElementById('references').value);
        formData.append('custom_data', document.getElementById('customData').value);
        selectedFiles.forEach(file => { formData.append('data_files', file); });
        formData.append('chapter_data', JSON.stringify(flatTasks));
        formData.append('task_id', currentTaskId);
        
        if (fullMarkdownText && fullMarkdownText.length > 50) {
                formData.append('initial_context', fullMarkdownText.slice(-3000));
        }

        try {
            const response = await authenticatedFetch('/generate', { 
                method: 'POST', body: formData 
            });
            
            if (response.ok) {
                appendLog("✅ 任务启动，建立连接...", 'info');
                subscribeTask(currentTaskId);
            } else {
                const errJson = await response.json();
                throw new Error(errJson.msg || "服务器启动任务失败");
            }
        } catch (err) {
            appendLog("❌ 启动异常: " + err.message, 'error');
            taskMeta.status = 'stopped';
            saveTaskListMeta();
            renderTaskListUI();
            
            lockUI(false);
            btnSubmit.disabled = false;
            btnSubmit.innerText = "🚀 3. 开始生成";
        }
    };
}

// ============================================================
// 5. 进度流监听
// ============================================================

async function subscribeTask(taskId) {
    if (taskId !== currentTaskId) return;

    if (abortController) abortController.abort();
    abortController = new AbortController();

    try {
        const response = await authenticatedFetch(`/stream_progress?task_id=${taskId}&last_index=${currentEventIndex}`, {
            method: 'GET',
            signal: abortController.signal
        });

        if (!response.ok) throw new Error("连接流失败");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop(); 

            for (const line of lines) {
                const trimmed = line.trim();
                if (trimmed.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(trimmed.replace('data: ', ''));
                        currentEventIndex++; 

                        if (data.type === 'log') {
                            appendLog(data.msg); 
                        } else if (data.type === 'content') {
                            fullMarkdownText += data.md;
                            renderEnrichedResult(fullMarkdownText);
                            saveCurrentTaskState(); 
                        } else if (data.type === 'done') {
                            finishTask(taskId);
                            return;
                        }
                    } catch (e) { console.error(e); }
                }
            }
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            if (currentTaskId === taskId) {
                appendLog("⚠️ 连接波动，重试中...", 'warn');
                setTimeout(() => subscribeTask(taskId), 3000);
            }
        }
    }
}

function finishTask(taskId) {
    if (taskId !== currentTaskId) return;
    lockUI(false);
    appendLog("🎉 生成完成！", 'info');
    const task = taskList.find(t => t.id === taskId);
    if (task) { task.status = 'completed'; saveTaskListMeta(); renderTaskListUI(); }
    saveCurrentTaskState();
    alert("当前任务生成完成！");
}

// ============================================================
// 6. UI Helpers & 核心重写/编辑逻辑
// ============================================================

function normalizeTitle(title) {
    return title.replace(/\s+/g, '').replace(/AI重写|编辑|撤销|删除|精简|重写此节/g, '');
}

// [辅助] 在parsedStructure中查找某章节的配置信息（为了获取预设字数）
function findChapterConfig(title) {
    if (!parsedStructure || parsedStructure.length === 0) return null;
    const cleanTitle = normalizeTitle(title);
    
    for (let group of parsedStructure) {
        if (normalizeTitle(group.title) === cleanTitle) return group; // 匹配一级章节
        for (let child of group.children) {
            if (normalizeTitle(child.text) === cleanTitle) return child; // 匹配子章节
        }
    }
    return null;
}

// [核心] 增强渲染函数
window.renderEnrichedResult = function(mdText) {
    const container = document.getElementById('resultContent');
    const manualModal = document.getElementById('manualEditModal');
    if (manualModal && manualModal.classList.contains('show')) return; 

    const rawHtml = marked.parse(mdText);
    container.innerHTML = rawHtml;

    const headers = container.querySelectorAll('h1, h2, h3, h4');
    headers.forEach((header) => {
        let titleText = header.innerText; 
        if (header.childNodes.length > 0 && header.childNodes[0].nodeType === 3) {
            titleText = header.childNodes[0].textContent;
        }
        
        const cleanTitle = normalizeTitle(titleText);
        const targetTitle = normalizeTitle(currentRewritingTitle || "");

        if (currentRewritingTitle && cleanTitle === targetTitle) {
            const loadingSpan = document.createElement('span');
            loadingSpan.className = 'rewrite-loading-badge';
            loadingSpan.innerHTML = `
                <span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true" style="width: 0.7em; height: 0.7em; border-width: 0.1em;"></span>
                AI处理中...
            `;
            header.appendChild(loadingSpan);
        } else {
            const btnGroup = document.createElement('span');
            btnGroup.className = 'ms-3 opacity-0 hover-show-btns';
            btnGroup.style.transition = 'opacity 0.2s';
            
            // 1. AI 重写
            const btnRewrite = document.createElement('button');
            btnRewrite.className = 'btn btn-sm btn-outline-primary me-1';
            btnRewrite.innerHTML = '<i class="bi bi-magic"></i> AI重写';
            btnRewrite.style.fontSize = '0.75rem';
            btnRewrite.style.padding = '1px 6px';
            btnRewrite.onclick = (e) => {
                e.stopPropagation();
                openRewriteModalFromResult(titleText.trim());
            };

            // 2. 编辑
            const btnEdit = document.createElement('button');
            btnEdit.className = 'btn btn-sm btn-outline-success me-1';
            btnEdit.innerHTML = '<i class="bi bi-pencil"></i> 编辑';
            btnEdit.style.fontSize = '0.75rem';
            btnEdit.style.padding = '1px 6px';
            btnEdit.onclick = (e) => {
                e.stopPropagation();
                openManualEditModal(titleText.trim());
            };

            // 3. 撤销
            const btnUndo = document.createElement('button');
            btnUndo.className = 'btn btn-sm btn-outline-secondary me-1';
            btnUndo.innerHTML = '<i class="bi bi-arrow-counterclockwise"></i> 撤销';
            btnUndo.style.fontSize = '0.75rem';
            btnUndo.style.padding = '1px 6px';
            btnUndo.onclick = (e) => {
                e.stopPropagation();
                performUndo(titleText.trim());
            };

            // 4. [新增] 精简按钮
            const btnRefine = document.createElement('button');
            btnRefine.className = 'btn btn-sm btn-outline-warning me-1';
            btnRefine.innerHTML = '<i class="bi bi-scissors"></i> 精简';
            btnRefine.style.fontSize = '0.75rem';
            btnRefine.style.padding = '1px 6px';
            btnRefine.onclick = (e) => {
                e.stopPropagation();
                refineSection(titleText.trim());
            };

            // 5. 删除按钮
            const btnDelete = document.createElement('button');
            btnDelete.className = 'btn btn-sm btn-outline-danger';
            btnDelete.innerHTML = '<i class="bi bi-trash"></i> 删除';
            btnDelete.style.fontSize = '0.75rem';
            btnDelete.style.padding = '1px 6px';
            btnDelete.onclick = (e) => {
                e.stopPropagation();
                deleteSectionContent(titleText.trim());
            };

            btnGroup.appendChild(btnRewrite);
            btnGroup.appendChild(btnEdit);
            btnGroup.appendChild(btnUndo);
            btnGroup.appendChild(btnRefine); // 插入精简按钮
            btnGroup.appendChild(btnDelete);
            header.appendChild(btnGroup);

            header.onmouseenter = () => btnGroup.style.opacity = '1';
            header.onmouseleave = () => btnGroup.style.opacity = '0';
        }
    });
};

window.extractSectionContent = function(title) {
    const escapedTitle = escapeRegExp(title);
    const regex = new RegExp(`(#{1,6}\\s*${escapedTitle}\\s*\\n)([\\s\\S]*?)(?=\\n\\s*#{1,6}\\s|$)`, 'i');
    const match = fullMarkdownText.match(regex);
    
    if (match) {
        let content = match[2];
        content = content.replace(/^\n+/, ''); 
        content = content.replace(/\s+$/, '');
        return content;
    }
    return "";
};

// --- 功能 A: AI 重写 ---
function openRewriteModalFromResult(sectionTitle) {
    document.getElementById('rewriteSectionTitle').value = sectionTitle;
    document.getElementById('rewriteInstruction').value = ""; 
    const modalEl = document.getElementById('rewriteModal');
    const modalInstance = bootstrap.Modal.getOrCreateInstance(modalEl);
    modalInstance.show();
}

window.executeRewrite = async function() {
    const instruction = document.getElementById('rewriteInstruction').value.trim();
    if (!instruction) { alert("请输入修改指令"); return; }

    const sectionTitle = document.getElementById('rewriteSectionTitle').value;
    
    const modalEl = document.getElementById('rewriteModal');
    const modalInstance = bootstrap.Modal.getOrCreateInstance(modalEl);
    modalInstance.hide();

    currentRewritingTitle = sectionTitle;
    renderEnrichedResult(fullMarkdownText);
    
    appendLog(`🖊️ AI正在重写章节：[${sectionTitle}]...`, 'warn');
    const originalContent = extractSectionContent(sectionTitle);
    
    try {
        const formData = {
            title: document.getElementById('paperTitle').value,
            section_title: sectionTitle,
            instruction: instruction,
            context: fullMarkdownText.slice(0, 1500), 
            custom_data: document.getElementById('customData').value,
            original_content: originalContent
        };

        const res = await authenticatedFetch('/rewrite_section', {
            method: 'POST',
            body: JSON.stringify(formData)
        });
        
        const data = await res.json();
        
        if (data.status === 'success') {
            const newContent = data.content;
            currentRewritingTitle = null;
            replaceSectionContent(sectionTitle, newContent);
            appendLog(`✅ 章节 [${sectionTitle}] 重写完成！`, 'info');
            saveCurrentTaskState(); 
        } else {
            throw new Error(data.msg);
        }

    } catch (e) {
        currentRewritingTitle = null;
        renderEnrichedResult(fullMarkdownText); 
        alert("重写失败: " + e.message);
        appendLog("❌ 重写失败", 'error');
    }
};

// --- 功能 B: 人工编辑 ---
window.openManualEditModal = function(sectionTitle) {
    let content = extractSectionContent(sectionTitle);
    
    if (!content) {
        if (!confirm(`未找到章节 [${sectionTitle}] 的正文内容，是否创建新内容？`)) return;
        content = ""; 
    }

    if (content && !content.startsWith('　　') && !content.startsWith('#') && !content.startsWith('```')) {
        content = '　　' + content; 
    }

    document.getElementById('manualEditSectionTitle').value = sectionTitle;
    document.getElementById('manualEditContent').value = content;

    const modalEl = document.getElementById('manualEditModal');
    const modalInstance = bootstrap.Modal.getOrCreateInstance(modalEl);
    modalInstance.show();
};

window.saveManualEdit = function() {
    const title = document.getElementById('manualEditSectionTitle').value;
    const newContent = document.getElementById('manualEditContent').value;

    const modalEl = document.getElementById('manualEditModal');
    const modalInstance = bootstrap.Modal.getInstance(modalEl);
    if (modalInstance) {
        modalInstance.hide();
    }
    
    modalEl.classList.remove('show');
    const backdrop = document.querySelector('.modal-backdrop');
    if(backdrop) backdrop.remove();
    document.body.classList.remove('modal-open');
    document.body.style.overflow = '';
    document.body.style.paddingRight = '';

    replaceSectionContent(title, newContent);
    appendLog(`📝 人工修订章节 [${title}] 已保存`, 'info');
    saveCurrentTaskState();
};

// --- 功能 C: 撤销/回退 ---
window.performUndo = function(title) {
    if (!sectionUndoHistory[title]) {
        alert("此段落未进行过重写或修改，无历史版本可回退。");
        return;
    }
    
    if(!confirm(`确定要回退章节 [${title}] 到上一个版本吗？\n(注意：这将把当前内容和历史记录进行互换)`)) return;
    
    const prevContent = sectionUndoHistory[title];
    replaceSectionContent(title, prevContent);
    saveCurrentTaskState();
    appendLog(`↺ 已回退章节：[${title}]`, 'info');
};

// --- 功能 D: 删除/清空 ---
window.deleteSectionContent = function(title) {
    if(!confirm(`⚠️ 确定要清空章节 [${title}] 的正文内容吗？\n\n(提示：标题将保留。删除前的内容会自动存入历史记录，您可以通过“撤销”按钮恢复。)`)) return;
    replaceSectionContent(title, "");
    appendLog(`🗑️ 已清空章节内容：[${title}]`, 'warn');
};

// --- 功能 E: 自动精简 (核心新增) ---
window.refineSection = async function(title) {
    // 1. 并发限制
    if (activeRefineTasks >= 3) {
        alert("⚠️ 当前已有 3 个精简任务在运行，请稍候再试。");
        return;
    }

    // 2. 获取预设字数
    const chapterConfig = findChapterConfig(title);
    if (!chapterConfig) {
        alert("❌ 无法在大纲中找到该章节的配置，无法获取目标字数。");
        return;
    }
    const targetWords = parseInt(chapterConfig.words) || 500;

    // 3. 获取当前内容及字数检测
    const currentContent = extractSectionContent(title);
    if (!currentContent) {
        alert("该章节暂无内容，无需精简。");
        return;
    }
    const currentLen = currentContent.replace(/\s/g, '').length;
    
    if (currentLen <= targetWords) {
        alert(`ℹ️ 当前字数 (${currentLen}) 未超过目标字数 (${targetWords})，无需精简。`);
        return;
    }

    if (!confirm(`即将对章节 [${title}] 进行精简。\n\n当前字数：${currentLen}\n目标字数：${targetWords}\n\n确定执行吗？`)) return;

    // 4. 执行任务
    activeRefineTasks++;
    currentRewritingTitle = title; // 显示 Loading 状态
    renderEnrichedResult(fullMarkdownText);
    
    appendLog(`✂️ 正在精简章节 [${title}] (${currentLen} -> ${targetWords}字)...`, 'warn');

    try {
        const formData = {
            title: document.getElementById('paperTitle').value,
            section_title: title,
            // 构造精简专用的 prompt
            instruction: `请将上述内容精简到 ${targetWords} 字左右。要求：保留核心论点和数据，删除冗余修饰，确保语句通顺。`,
            context: fullMarkdownText.slice(0, 1500), 
            custom_data: document.getElementById('customData').value,
            original_content: currentContent
        };

        // 复用 rewrite_section 接口
        const res = await authenticatedFetch('/rewrite_section', {
            method: 'POST',
            body: JSON.stringify(formData)
        });
        
        const data = await res.json();
        
        if (data.status === 'success') {
            const newContent = data.content;
            currentRewritingTitle = null;
            replaceSectionContent(title, newContent);
            
            const newLen = newContent.replace(/\s/g, '').length;
            appendLog(`✅ 章节 [${title}] 精简完成！(当前: ${newLen}字)`, 'info');
            saveCurrentTaskState(); 
        } else {
            throw new Error(data.msg);
        }

    } catch (e) {
        currentRewritingTitle = null;
        renderEnrichedResult(fullMarkdownText); 
        alert("精简失败: " + e.message);
        appendLog("❌ 精简失败", 'error');
    } finally {
        activeRefineTasks--; // 释放并发名额
    }
};

// [核心] 正则替换 + 强制格式化 + 自动备份历史
window.replaceSectionContent = function(title, newContent) {
    const escapedTitle = escapeRegExp(title);
    
    // 1. 预处理：按行分割
    let lines = newContent.trimEnd().replace(/\r\n/g, '\n').split('\n');
    let formattedLines = [];
    
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trimEnd();
        
        // 跳过纯空行（稍后重建时由 join 决定间距，或者根据逻辑插入）
        if (!line) continue; 

        // --- 缩进处理 ---
        let processedLine = line;
        // 只有非标题、非表格、非代码块、非引用的普通段落，才加缩进
        if (!/^(\#|\||`|- |\* |> )/.test(line.trimStart())) {
            if (line.startsWith('　　')) processedLine = line;
            else if (line.startsWith('  ')) processedLine = line.replace(/^( +)/, m => '　'.repeat(Math.ceil(m.length/2)));
            else processedLine = '　　' + line.trimStart();
        } else {
            // 如果是表格行，确保去掉可能存在的全角缩进，防止解析错误
            if (line.trimStart().startsWith('|')) {
                processedLine = line.trim();
            }
        }

        // --- [关键修复] 表格分离检测 ---
        // 如果上一行是表格(以|结尾或开头)，且当前行不是表格 -> 强制插入空行断开
        if (formattedLines.length > 0) {
            let lastLine = formattedLines[formattedLines.length - 1];
            let isLastLineTable = lastLine.trim().startsWith('|');
            let isCurrentLineTable = processedLine.trim().startsWith('|');
            
            if (isLastLineTable && !isCurrentLineTable) {
                formattedLines.push(''); // 插入一个空字符串，join时会变成空行
            }
        }
        
        formattedLines.push(processedLine);
    }
    
    // 使用单换行连接，因为我们在需要的地方已经插入了空字符串（即双换行）
    let formattedText = formattedLines.join('\n');

    const regex = new RegExp(`(#{1,6}\\s*${escapedTitle}\\s*\\n)([\\s\\S]*?)(?=\\n\\s*#{1,6}\\s|$)`, 'i');
    const match = fullMarkdownText.match(regex);
    
    if (match) {
        const currentContent = match[2].trim(); 
        sectionUndoHistory[title] = currentContent;

        const oldSection = match[0];
        const header = match[1]; 
        // 确保 header 和 content 之间也有空行
        const replacement = `${header}\n${formattedText}\n\n`;
        
        fullMarkdownText = fullMarkdownText.replace(oldSection, replacement);
        
        const container = document.querySelector('.output-area');
        const scrollPos = container ? container.scrollTop : 0;
        
        renderEnrichedResult(fullMarkdownText);
        setTimeout(() => { if(container) container.scrollTop = scrollPos; }, 50);
        
    } else {
        console.warn("未在正文中找到章节，追加到末尾");
        fullMarkdownText += `\n\n### ${title}\n\n${formattedText}\n\n`;
        renderEnrichedResult(fullMarkdownText);
    }
};

// ... (其他辅助函数) ...
window.lockUI = function(locked) {
    document.getElementById('btnSubmit').disabled = locked;
    const ctrlDiv = document.getElementById('controlButtons');
    if(ctrlDiv) ctrlDiv.style.display = 'block'; 

    const inputs = ['paperTitle', 'outlineRaw', 'references', 'customData', 'globalTotalWords', 'fileInput'];
    inputs.forEach(id => { const el = document.getElementById(id); if(el) el.disabled = locked; });
    document.querySelectorAll('.chapter-card input, .chapter-card button').forEach(el => el.disabled = locked);

    if (locked) {
        document.getElementById('btnPause').style.display = 'inline-block';
        document.getElementById('btnStop').style.display = 'inline-block';
    } else {
        document.getElementById('btnPause').style.display = 'none';
        document.getElementById('btnStop').style.display = 'none';
    }
};

window.updatePauseBtnState = function() {
    const btn = document.getElementById('btnPause');
    btn.innerText = isPaused ? "▶ 继续" : "⏸ 暂停";
    btn.className = isPaused ? "btn btn-info btn-sm me-2" : "btn btn-warning btn-sm me-2";
};

window.togglePause = async function() { 
    const action = isPaused ? 'resume' : 'pause';
    await authenticatedFetch('/control', {method: 'POST', body: JSON.stringify({ task_id: currentTaskId, action: action })});
    isPaused = !isPaused;
    const task = taskList.find(t => t.id === currentTaskId);
    if(task) { task.status = isPaused ? 'paused' : 'running'; saveTaskListMeta(); renderTaskListUI(); }
    updatePauseBtnState();
    appendLog(isPaused ? "⏸ 任务已暂停" : "▶ 任务继续", 'warn');
};

window.stopTask = async function() { 
    if(!confirm("确定停止当前任务？")) return;
    if(abortController) abortController.abort();
    await authenticatedFetch('/control', {method: 'POST', body: JSON.stringify({ task_id: currentTaskId, action: 'stop' })});
    const task = taskList.find(t => t.id === currentTaskId);
    if(task) { task.status = 'stopped'; saveTaskListMeta(); renderTaskListUI(); }
    lockUI(false);
    appendLog("⏹ 任务已手动停止", 'error');
    saveCurrentTaskState();
};

window.clearResults = function(silent = false) {
    if (!silent && !confirm("确定清空正文内容吗？(配置保留)")) return;
    fullMarkdownText = "";
    document.getElementById('resultContent').innerHTML = "<div class='text-center text-muted mt-5 pt-5'><p style='font-size: 1.2rem;'>💡 内容已清空</p></div>";
    currentEventIndex = 0; 
    const task = taskList.find(t => t.id === currentTaskId);
    if(task) { task.status = 'draft'; saveTaskListMeta(); renderTaskListUI(); }
    lockUI(false);
    saveCurrentTaskState();
    if(!silent) appendLog("🗑️ 内容已清空", 'warn');
};

window.authenticatedFetch = async function(url, options = {}) {
    if (!options.headers) options.headers = {};
    if (!(options.body instanceof FormData)) options.headers['Content-Type'] = 'application/json';
    options.headers['X-User-ID'] = currentUserId;
    return fetch(url, options);
};

window.appendLog = function(msg, type = 'info') {
    const logArea = document.getElementById('logArea');
    const time = new Date().toLocaleTimeString();
    let color = '#00ff9d';
    if (type === 'error') color = '#ff4d4d';
    if (type === 'warn') color = '#ffc107';
    const html = `<div style="color:${color}; border-bottom:1px dashed #333; padding:2px 0;">[${time}] ${msg}</div>`;
    logArea.innerHTML += html;
    logArea.scrollTop = logArea.scrollHeight;
};

window.generateUUID = function() { return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => (c === 'x' ? Math.random() * 16 | 0 : (Math.random() * 16 | 0) & 0x3 | 0x8).toString(16)); };
window.escapeRegExp = function(string) { return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); };

window.handleFileSelect = function() {
    const input = document.getElementById('fileInput');
    selectedFiles = selectedFiles.concat(Array.from(input.files));
    renderFileList();
    input.value = ''; 
};
window.renderFileList = function() {
    const list = document.getElementById('fileListDisplay');
    list.innerHTML = selectedFiles.map((f, i) => `
        <div class='d-flex justify-content-between border-bottom py-1'>
            <span class='text-truncate small'>📄 ${f.name}</span>
            <button class='btn btn-link text-danger p-0' onclick='removeFile(${i})'>×</button>
        </div>`).join('');
};
window.removeFile = function(i) { selectedFiles.splice(i, 1); renderFileList(); };

window.exportToMarkdown = function() {
    if(!fullMarkdownText) return;
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([fullMarkdownText], {type: 'text/markdown'}));
    a.download = `${document.getElementById('paperTitle').value || 'thesis'}.md`; a.click();
};
window.exportToDocx = async function() {
    if(!fullMarkdownText) return alert("无内容");
    try {
        const res = await authenticatedFetch('/export_docx', { method: 'POST', body: JSON.stringify({ content: fullMarkdownText }) });
        if (res.ok) {
            const url = window.URL.createObjectURL(await res.blob());
            const a = document.createElement('a'); a.href = url; a.download = `${document.getElementById('paperTitle').value || 'thesis'}.docx`; a.click();
        }
    } catch(e) { alert("导出失败"); }
};

window.loadDemoOutline = function() {
    document.getElementById('outlineRaw').value = `摘要\n第一章 绪论\n1.1 研究背景\n1.2 研究意义\n第二章 核心理论\n2.1 理论基础\n第三章 总结\n参考文献`;
    parseOutline();
};

window.analyzeLineStructure = function(text) {
    text = text.trim();
    if (!text) return null;
    if (/^(摘要|Abstract|参考文献|致谢|总结|结论)/i.test(text)) return { level: 1, type: 'keyword' };
    if (/^第[一二三四五六七八九十0-9]+[章|部分]/.test(text)) return { level: 1, type: 'chapter' };
    const decimalMatch = text.match(/^(\d+(\.\d+)+)/);
    if (decimalMatch) return { level: decimalMatch[1].split('.').length, type: 'decimal' };
    if (/^[一二三四五六七八九十]+、/.test(text)) return { level: 2, type: 'cn_num' };
    if (/^[\(（][一二三四五六七八九十0-9]+[\)）]/.test(text)) return { level: 3, type: 'paren' };
    if (/^\d+([\.\s、]|$)/.test(text)) return { level: 1, type: 'simple_num' };
    return { level: 2, type: 'text' }; 
};

window.parseOutline = function() {
    const text = document.getElementById('outlineRaw').value;
    const lines = text.split('\n');
    let processedItems = [];
    let lastLevel1Type = null; 

    lines.forEach(line => {
        const trimmed = line.trim();
        if(!trimmed) return;
        let info = analyzeLineStructure(trimmed);
        if (info.type === 'simple_num' && lastLevel1Type === 'chapter') info.level = 2;
        if (info.level === 1) lastLevel1Type = info.type;

        processedItems.push({
            text: trimmed, level: info.level, isParent: false, words: 0,
            useData: /结果|分析|实验|数据|验证|测试/.test(trimmed)
        });
    });

    for (let i = 0; i < processedItems.length - 1; i++) {
        if (processedItems[i+1].level > processedItems[i].level) processedItems[i].isParent = true;
    }

    parsedStructure = [];
    let currentMainGroup = null;
    processedItems.forEach(item => {
        if (item.level === 1) {
            currentMainGroup = { title: item.text, children: [] };
            parsedStructure.push(currentMainGroup);
            if (!item.isParent) currentMainGroup.children.push(item);
        } else {
            if (!currentMainGroup) {
                currentMainGroup = { title: "前言/导论", children: [] };
                parsedStructure.push(currentMainGroup);
            }
            currentMainGroup.children.push(item);
        }
    });
    smartDistributeWords();
};

window.smartDistributeWords = function() {
    const totalTarget = parseInt(document.getElementById('globalTotalWords').value) || 5000;
    let reserved = 0, activeLeaves = [];
    parsedStructure.forEach(group => {
        group.children.forEach(child => {
            if (child.isParent) return; 
            if (/摘要|Abstract/.test(child.text)) { child.words = 400; reserved += 400; }
            else if (/参考文献|致谢/.test(child.text)) child.words = 0;
            else activeLeaves.push(child);
        });
    });
    let avgWords = Math.max(200, Math.round(Math.floor(Math.max(0, totalTarget - reserved) / (activeLeaves.length || 1)) / 50) * 50);
    activeLeaves.forEach(leaf => leaf.words = avgWords);
    renderConfigArea();
};

window.renderConfigArea = function() {
    const container = document.getElementById('chapterConfigArea');
    container.innerHTML = '';
    let globalTotal = 0;

    parsedStructure.forEach((group, gIdx) => {
        let chapterTotalWords = 0;
        group.children.forEach(c => chapterTotalWords += (c.words || 0));
        globalTotal += chapterTotalWords;

        const card = document.createElement('div');
        card.className = 'chapter-card';
        card.innerHTML = `
            <div class="chapter-header py-2">
                <div class="d-flex align-items-center" style="width: 35%;">
                    <i class="bi bi-folder2-open me-2 text-primary"></i> 
                    <span class="text-truncate fw-bold" title="${group.title}">${group.title}</span>
                </div>
                <div class="d-flex align-items-center justify-content-center" style="width: 40%;">
                    <div class="input-group input-group-sm">
                        <span class="input-group-text bg-white text-muted">本章</span>
                        <input type="number" class="form-control text-center" id="chapter-total-${gIdx}" value="${chapterTotalWords}" step="100" min="0">
                        <button class="btn btn-outline-secondary" type="button" onclick="distributeChapterWords(${gIdx})"><i class="bi bi-arrow-down-up"></i> 分配</button>
                    </div>
                </div>
                <div class="d-flex align-items-center justify-content-end" style="width: 25%;">
                    <button class="btn btn-sm btn-link text-primary p-0 me-2" onclick="sortLeaves(${gIdx})"><i class="bi bi-sort-numeric-down"></i></button>
                    <button class="btn btn-sm btn-link text-success p-0 me-2" onclick="addLeaf(${gIdx})"><i class="bi bi-plus-circle"></i></button>
                    <button class="btn btn-sm btn-link text-danger p-0" onclick="deleteGroup(${gIdx})"><i class="bi bi-trash"></i></button>
                </div>
            </div>
            <div class="chapter-body"></div>
        `;
        
        const body = card.querySelector('.chapter-body');
        group.children.forEach((child, cIdx) => {
            const row = document.createElement('div');
            row.className = 'leaf-row';
            const indent = Math.max(0, (child.level - 2) * 20); 
            const dataBtnColor = child.useData ? 'btn-outline-success active' : 'btn-outline-secondary';
            
            row.innerHTML = `
                <div class="d-flex align-items-center flex-grow-1" style="padding-left: ${indent}px;">
                    ${child.level > 2 ? '<i class="bi bi-arrow-return-right text-muted me-2 small"></i>' : ''}
                    <input type="text" class="leaf-title-input" value="${child.text}" onchange="updateLeaf(${gIdx}, ${cIdx}, 'text', this.value)">
                </div>
                <div class="me-2">
                    <button type="button" class="btn btn-sm ${dataBtnColor}" onclick="toggleLeafData(${gIdx}, ${cIdx})" title="数据挂载开关" style="font-size: 0.75rem; padding: 2px 6px;">
                        <i class="bi bi-database${child.useData ? '-fill-check' : ''}"></i> 数据
                    </button>
                </div>
                <div class="me-2">
                    <button type="button" class="btn btn-sm text-secondary btn-rewrite" 
                            onclick="openRewriteModal(${gIdx}, ${cIdx})" 
                            title="AI 重写本节" style="font-size: 0.75rem; padding: 2px 6px; border: 1px solid #dee2e6;">
                        <i class="bi bi-magic"></i> 重写
                    </button>
                </div>
                <div class="word-input-group">
                    <input type="number" class="form-control form-control-sm word-input" value="${child.words}" step="50" min="0" onchange="updateLeaf(${gIdx}, ${cIdx}, 'words', this.value)">
                    <span class="ms-1 small text-muted">字</span>
                </div>
                <button class="btn btn-sm text-danger ms-2" onclick="deleteLeaf(${gIdx}, ${cIdx})" title="删除此写作点">
                    <i class="bi bi-trash3"></i>
                </button>
            `;
            body.appendChild(row);
        });
        container.appendChild(card);
    });
    document.getElementById('totalWords').innerText = globalTotal;
};

function distributeChapterWords(gIdx) {
    const targetTotal = parseInt(document.getElementById(`chapter-total-${gIdx}`).value) || 0;
    const group = parsedStructure[gIdx];
    const activeLeaves = group.children.filter(c => !c.isParent);
    if (activeLeaves.length === 0) return alert("该章节下没有可分配的小节");
    
    let avg = Math.floor(targetTotal / activeLeaves.length);
    if (targetTotal > 0) avg = Math.max(50, Math.round(avg / 50) * 50);
    else avg = 0;
    
    activeLeaves.forEach(leaf => leaf.words = avg);
    renderConfigArea();
}

function updateLeaf(gIdx, cIdx, field, value) {
    if (field === 'words') value = parseInt(value) || 0;
    parsedStructure[gIdx].children[cIdx][field] = value;
    if (field === 'words') renderConfigArea(); // Update total words
    if (field === 'text') sortLeaves(gIdx);
}

function toggleLeafData(gIdx, cIdx) {
    parsedStructure[gIdx].children[cIdx].useData = !parsedStructure[gIdx].children[cIdx].useData;
    renderConfigArea();
}

function sortLeaves(gIdx) {
    const group = parsedStructure[gIdx];
    const leaves = group.children.filter(c => !c.isParent);
    const parents = group.children.filter(c => c.isParent);
    leaves.sort((a, b) => {
        const getVer = s => (s.match(/^(\d+(\.\d+)*)/) || ['999'])[0].split('.').map(Number);
        const vA = getVer(a.text), vB = getVer(b.text);
        for(let i=0; i<Math.max(vA.length, vB.length); i++) {
            if ((vA[i]||0) !== (vB[i]||0)) return (vA[i]||0) - (vB[i]||0);
        }
        return 0;
    });
    group.children = [...parents, ...leaves];
    renderConfigArea();
}

function deleteLeaf(gIdx, cIdx) { 
    const targetTitle = parsedStructure[gIdx].children[cIdx].text || "该小节";
    if(confirm(`⚠️ 危险操作确认\n\n您确定要永久删除写作点：\n“${targetTitle}” 吗？\n\n删除后无法恢复，请确认。`)) {
        parsedStructure[gIdx].children.splice(cIdx, 1); 
        renderConfigArea(); 
    }
}

function addLeaf(gIdx) {
    const title = prompt("请输入新小节标题");
    if (title) { parsedStructure[gIdx].children.push({ text: title, isParent: false, words: 500 }); sortLeaves(gIdx); }
}
function deleteGroup(gIdx) { if(confirm("确定删除该章节？")) { parsedStructure.splice(gIdx, 1); renderConfigArea(); } }
function addManualChapter() {
    const title = prompt("请输入新章节标题");
    if(title) { parsedStructure.push({ title: title, children: [{ text: title + " 概述", isParent: false, words: 500 }] }); renderConfigArea(); }
}

// --- [新增] 重写功能模块 ---
let targetRewriteIndices = { g: -1, c: -1 };

// 修改 openRewriteModal 支持从右侧结果区调用
function openRewriteModal(gIdx, cIdx) {
    if (!fullMarkdownText) {
        alert("请先生成论文内容后再使用重写功能！");
        return;
    }
    targetRewriteIndices = { g: gIdx, c: cIdx };
    const section = parsedStructure[gIdx].children[cIdx];
    
    document.getElementById('rewriteSectionTitle').value = section.text;
    document.getElementById('rewriteInstruction').value = ""; 
    
    const modalEl = document.getElementById('rewriteModal');
    const modalInstance = bootstrap.Modal.getOrCreateInstance(modalEl);
    modalInstance.show();
}