/**
 * main.js
 * 包含：全局状态、鉴权、任务管理、生成逻辑、结果渲染
 * 依赖：必须先加载 utils.js
 */
console.log("Main.js loaded");

// ============================================================
// 0. 全局状态管理
// ============================================================
window.currentUserId = null;
window.taskList = [];          
window.currentTaskId = null;   
window.currentRewritingTitle = null; 

// 运行时状态
window.parsedStructure = []; 
window.fullMarkdownText = "";
window.isPaused = false;
window.abortController = null; 
window.selectedFiles = [];     
window.currentEventIndex = 0;
window.sectionUndoHistory = {}; 
window.activeRefineTasks = 0;

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

window.verifyAndLogin = async function(key, btn = null, msgSpan = null) {
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

window.createNewPaper = function() { createNewTask(); };

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

window.saveTaskListMeta = function() {
    localStorage.setItem(`tasks_meta_${currentUserId}`, JSON.stringify(taskList));
};

window.saveCurrentTaskState = function() {
    if (!currentUserId || !currentTaskId) return;

    const title = document.getElementById('paperTitle').value;
    const draftData = {
        title: title,
        outline: document.getElementById('outlineRaw').value,
        // --- 修改开始 ---
        refDomestic: document.getElementById('refDomestic').value, // 新增
        refForeign: document.getElementById('refForeign').value,   // 新增
        // refs: document.getElementById('references').value,      // 删除旧的
        // --- 修改结束 ---
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
};

window.loadTaskState = function(id) {
    const json = localStorage.getItem(`draft_${currentUserId}_${id}`);
    if (!json) return; 

    const data = JSON.parse(json);
    
    document.getElementById('paperTitle').value = data.title || "";
    document.getElementById('outlineRaw').value = data.outline || "";
    document.getElementById('refDomestic').value = data.refDomestic || data.refs || ""; // 兼容旧数据
    document.getElementById('refForeign').value = data.refForeign || "";
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
};

window.resetWorkspaceVariables = function() {
    fullMarkdownText = "";
    parsedStructure = [];
    selectedFiles = []; 
    currentEventIndex = 0;
    isPaused = false;
    currentRewritingTitle = null; 
    sectionUndoHistory = {}; 
    activeRefineTasks = 0; 
    
    document.getElementById('paperTitle').value = "";
    document.getElementById('outlineRaw').value = "";
    document.getElementById('refDomestic').value = "";
    document.getElementById('refForeign').value = "";
    document.getElementById('customData').value = "";
    document.getElementById('fileListDisplay').innerHTML = "";
    document.getElementById('chapterConfigArea').innerHTML = "<div class='text-center text-muted small py-4'>请先解析大纲...</div>";
    document.getElementById('logArea').innerHTML = "准备就绪...";
    document.getElementById('resultContent').innerHTML = "<div class='text-center text-muted mt-5 pt-5'><p style='font-size: 1.2rem;'>💡 登录 -> 解析大纲 -> 智能分配 -> 开始生成</p></div>";
    document.getElementById('totalWords').innerText = "0";
};

// ============================================================
// 4. 提交与生成逻辑 (Core Logic)
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
                parseOutline(); // Call utils
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
        formData.append('ref_domestic', document.getElementById('refDomestic').value);
        formData.append('ref_foreign', document.getElementById('refForeign').value);
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

window.subscribeTask = async function(taskId) {
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
};

window.finishTask = function(taskId) {
    if (taskId !== currentTaskId) return;
    lockUI(false);
    appendLog("🎉 生成完成！", 'info');
    const task = taskList.find(t => t.id === taskId);
    if (task) { task.status = 'completed'; saveTaskListMeta(); renderTaskListUI(); }
    saveCurrentTaskState();
    alert("当前任务生成完成！");
};

// ============================================================
// 6. 结果渲染与操作逻辑 (Action Logic)
// ============================================================

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
            
            // 按钮定义...
            const btnRewrite = document.createElement('button');
            btnRewrite.className = 'btn btn-sm btn-outline-primary me-1';
            btnRewrite.innerHTML = '<i class="bi bi-magic"></i> AI重写';
            btnRewrite.style.fontSize = '0.75rem';
            btnRewrite.style.padding = '1px 6px';
            btnRewrite.onclick = (e) => { e.stopPropagation(); openRewriteModalFromResult(titleText.trim()); };

            const btnEdit = document.createElement('button');
            btnEdit.className = 'btn btn-sm btn-outline-success me-1';
            btnEdit.innerHTML = '<i class="bi bi-pencil"></i> 编辑';
            btnEdit.style.fontSize = '0.75rem';
            btnEdit.style.padding = '1px 6px';
            btnEdit.onclick = (e) => { e.stopPropagation(); openManualEditModal(titleText.trim()); };

            const btnUndo = document.createElement('button');
            btnUndo.className = 'btn btn-sm btn-outline-secondary me-1';
            btnUndo.innerHTML = '<i class="bi bi-arrow-counterclockwise"></i> 撤销';
            btnUndo.style.fontSize = '0.75rem';
            btnUndo.style.padding = '1px 6px';
            btnUndo.onclick = (e) => { e.stopPropagation(); performUndo(titleText.trim()); };

            const btnRefine = document.createElement('button');
            btnRefine.className = 'btn btn-sm btn-outline-warning me-1';
            btnRefine.innerHTML = '<i class="bi bi-scissors"></i> 精简';
            btnRefine.style.fontSize = '0.75rem';
            btnRefine.style.padding = '1px 6px';
            btnRefine.onclick = (e) => { e.stopPropagation(); refineSection(titleText.trim()); };

            const btnDelete = document.createElement('button');
            btnDelete.className = 'btn btn-sm btn-outline-danger';
            btnDelete.innerHTML = '<i class="bi bi-trash"></i> 删除';
            btnDelete.style.fontSize = '0.75rem';
            btnDelete.style.padding = '1px 6px';
            btnDelete.onclick = (e) => { e.stopPropagation(); deleteSectionContent(titleText.trim()); };

            btnGroup.appendChild(btnRewrite);
            btnGroup.appendChild(btnEdit);
            btnGroup.appendChild(btnUndo);
            btnGroup.appendChild(btnRefine);
            btnGroup.appendChild(btnDelete);
            header.appendChild(btnGroup);

            header.onmouseenter = () => btnGroup.style.opacity = '1';
            header.onmouseleave = () => btnGroup.style.opacity = '0';
        }
    });
};

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

window.deleteSectionContent = function(title) {
    if(!confirm(`⚠️ 确定要清空章节 [${title}] 的正文内容吗？\n\n(提示：标题将保留。删除前的内容会自动存入历史记录，您可以通过“撤销”按钮恢复。)`)) return;
    replaceSectionContent(title, "");
    appendLog(`🗑️ 已清空章节内容：[${title}]`, 'warn');
};

window.refineSection = async function(title) {
    if (activeRefineTasks >= 3) {
        alert("⚠️ 当前已有 3 个精简任务在运行，请稍候再试。");
        return;
    }

    const chapterConfig = findChapterConfig(title);
    if (!chapterConfig) {
        alert("❌ 无法在大纲中找到该章节的配置，无法获取目标字数。");
        return;
    }
    const targetWords = parseInt(chapterConfig.words) || 500;

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

    activeRefineTasks++;
    currentRewritingTitle = title;
    renderEnrichedResult(fullMarkdownText);
    
    appendLog(`✂️ 正在精简章节 [${title}] (${currentLen} -> ${targetWords}字)...`, 'warn');

    try {
        const formData = {
            title: document.getElementById('paperTitle').value,
            section_title: title,
            instruction: `请将上述内容精简到 ${targetWords} 字左右。要求：保留核心论点和数据，删除冗余修饰，确保语句通顺。`,
            context: fullMarkdownText.slice(0, 1500), 
            custom_data: document.getElementById('customData').value,
            original_content: currentContent
        };

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
        activeRefineTasks--; 
    }
};

window.replaceSectionContent = function(title, newContent) {
    const escapedTitle = escapeRegExp(title);
    let lines = newContent.trimEnd().replace(/\r\n/g, '\n').split('\n');
    let formattedLines = [];
    
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trimEnd();
        if (!line) continue; 

        let processedLine = line;
        if (!/^(\#|\||`|- |\* |> )/.test(line.trimStart())) {
            if (line.startsWith('　　')) processedLine = line;
            else if (line.startsWith('  ')) processedLine = line.replace(/^( +)/, m => '　'.repeat(Math.ceil(m.length/2)));
            else processedLine = '　　' + line.trimStart();
        } else {
            if (line.trimStart().startsWith('|')) {
                processedLine = line.trim();
            }
        }

        if (formattedLines.length > 0) {
            let lastLine = formattedLines[formattedLines.length - 1];
            let isLastLineTable = lastLine.trim().startsWith('|');
            let isCurrentLineTable = processedLine.trim().startsWith('|');
            if (isLastLineTable && !isCurrentLineTable) {
                formattedLines.push(''); 
            }
        }
        
        formattedLines.push(processedLine);
    }
    
    let formattedText = formattedLines.join('\n');
    const regex = new RegExp(`(#{1,6}\\s*${escapedTitle}\\s*\\n)([\\s\\S]*?)(?=\\n\\s*#{1,6}\\s|$)`, 'i');
    const match = fullMarkdownText.match(regex);
    
    if (match) {
        const currentContent = match[2].trim(); 
        sectionUndoHistory[title] = currentContent;

        const oldSection = match[0];
        const header = match[1]; 
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