console.log("Script.js loaded successfully"); // Debug check

// ============================================================
// 0. Global State
// ============================================================
let currentUserId = null;
let taskList = [];          
let currentTaskId = null;   

// Runtime State
let parsedStructure = []; 
let fullMarkdownText = "";
let isPaused = false;
let abortController = null; 
let selectedFiles = [];     
let currentEventIndex = 0;  

marked.setOptions({
    breaks: true, // 关键：允许单个回车换行
    gfm: true
});

// ============================================================
// 1. Initialization & Auth
// ============================================================

window.handleLogin = async function() {
    console.log("Login button clicked"); // Debug check
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
    // Attach login listener here to be safe
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
// 2. Task Manager Logic
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

    // Auto expand the task list accordion if Bootstrap is loaded
    const collapseEl = document.getElementById('taskCollapseArea');
    if(collapseEl && window.bootstrap) {
        try {
            const bsCollapse = bootstrap.Collapse.getOrCreateInstance(collapseEl);
            bsCollapse.show();
        } catch(e) { console.log("Bootstrap collapse error", e); }
    }
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

    if (parsedStructure.length > 0) renderConfigArea();
    if (fullMarkdownText) {
        // [修改] 使用增强渲染
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
// 4. Submission & Execution
// ============================================================

const paperForm = document.getElementById('paperForm');
if (paperForm) {
    paperForm.onsubmit = async (e) => {
        e.preventDefault();
        
        if (!parsedStructure || parsedStructure.length === 0) {
            const rawOutline = document.getElementById('outlineRaw').value.trim();
            if (rawOutline) {
                parseOutline();
                if (!parsedStructure || parsedStructure.length === 0) {
                    alert("❌ 自动解析失败，请检查大纲格式！");
                    return;
                }
            } else {
                alert("⚠️ 请先填写大纲！");
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
        }
    };
}

// ============================================================
// 5. Stream Listener
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
                            // [修改] 使用增强渲染，注入重写按钮
                            renderEnrichedResult(fullMarkdownText);
                            saveCurrentTaskState(); // 实时保存
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
// 6. UI Helpers & Rewrite Logic
// ============================================================

// [新增] 增强渲染函数：解析 MD，然后在每个标题后注入“重写”按钮
window.renderEnrichedResult = function(mdText) {
    const container = document.getElementById('resultContent');
    
    // 如果有模态框正在打开（用户正在编辑），暂停刷新 DOM
    if (document.querySelector('.modal.show')) return; 

    // [核心修改] 不再清洗全角空格！完全保留文本原样。
    // 之前是: let displayHtml = mdText.replace(/　　/g, ''); 
    // 现在改为直接使用 mdText
    const rawHtml = marked.parse(mdText);
    container.innerHTML = rawHtml;

    // 查找所有 H1-H4 标签，注入按钮
    const headers = container.querySelectorAll('h1, h2, h3, h4');
    headers.forEach((header, index) => {
        // 提取纯文本标题（防止重复注入）
        let titleText = header.firstChild ? header.firstChild.textContent.trim() : header.innerText.trim();
        
        // 创建按钮容器
        const btnGroup = document.createElement('span');
        btnGroup.className = 'ms-3 opacity-0 hover-show-btns';
        btnGroup.style.transition = 'opacity 0.2s';
        
        // 1. AI 重写按钮
        const btnRewrite = document.createElement('button');
        btnRewrite.className = 'btn btn-sm btn-outline-primary me-1';
        btnRewrite.innerHTML = '<i class="bi bi-magic"></i> AI重写';
        btnRewrite.style.fontSize = '0.75rem';
        btnRewrite.style.padding = '1px 6px';
        btnRewrite.onclick = (e) => {
            e.stopPropagation();
            openRewriteModalFromResult(titleText);
        };

        // 2. 人工编辑按钮
        const btnEdit = document.createElement('button');
        btnEdit.className = 'btn btn-sm btn-outline-success';
        btnEdit.innerHTML = '<i class="bi bi-pencil"></i> 编辑';
        btnEdit.style.fontSize = '0.75rem';
        btnEdit.style.padding = '1px 6px';
        btnEdit.onclick = (e) => {
            e.stopPropagation();
            openManualEditModal(titleText);
        };

        btnGroup.appendChild(btnRewrite);
        btnGroup.appendChild(btnEdit);
        header.appendChild(btnGroup);

        // 绑定悬停事件
        header.onmouseenter = () => btnGroup.style.opacity = '1';
        header.onmouseleave = () => btnGroup.style.opacity = '0';
    });
};


window.openManualEditModal = function(sectionTitle) {
    // 1. 获取当前该章节的文本
    const content = extractSectionContent(sectionTitle);
    
    if (!content) {
        // 如果提取不到，可能是标题格式有误或者内容为空
        if(!confirm(`未找到章节 [${sectionTitle}] 的正文内容，是否创建新内容？`)) return;
    }

    // 2. 填充模态框
    document.getElementById('manualEditSectionTitle').value = sectionTitle;
    document.getElementById('manualEditContent').value = content;

    // 3. 显示
    const modalEl = document.getElementById('manualEditModal');
    const modalInstance = bootstrap.Modal.getOrCreateInstance(modalEl);
    modalInstance.show();
};

window.extractSectionContent = function(title) {
    const escapedTitle = escapeRegExp(title);
    // 匹配: 标题行(Group1) + 正文(Group2) + (下一个标题或结尾)
    const regex = new RegExp(`(#{1,6}\\s*${escapedTitle}\\s*\\n)([\\s\\S]*?)(?=\\n\\s*#{1,6}\\s|$)`, 'i');
    const match = fullMarkdownText.match(regex);
    if (match) {
        return match[2].trim(); // 返回正文内容
    }
    return "";
};

function saveManualEdit() {
    const title = document.getElementById('manualEditSectionTitle').value;
    const newContent = document.getElementById('manualEditContent').value;

    replaceSectionContent(title, newContent);
    
    // 关闭模态框
    const modalEl = document.getElementById('manualEditModal');
    const modalInstance = bootstrap.Modal.getInstance(modalEl);
    modalInstance.hide();

    appendLog(`📝 人工修订章节 [${title}] 已保存`, 'success');
    saveCurrentTaskState();
    
    // 强制刷新一次视图（因为编辑期间视图更新被暂停了）
    renderEnrichedResult(fullMarkdownText);
}

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

    appendLog(`🖊️ AI正在重写章节：[${sectionTitle}]...`, 'warn');
    
    try {
        const formData = {
            title: document.getElementById('paperTitle').value,
            section_title: sectionTitle,
            instruction: instruction,
            context: fullMarkdownText.slice(0, 1500), 
            custom_data: document.getElementById('customData').value
        };

        const res = await authenticatedFetch('/rewrite_section', {
            method: 'POST',
            body: JSON.stringify(formData)
        });
        
        const data = await res.json();
        
        if (data.status === 'success') {
            const newContent = data.content;
            replaceSectionContent(sectionTitle, newContent);
            appendLog(`✅ 章节 [${sectionTitle}] 重写完成！`, 'info');
            saveCurrentTaskState(); 
        } else {
            throw new Error(data.msg);
        }

    } catch (e) {
        alert("重写失败: " + e.message);
        appendLog("❌ 重写失败", 'error');
    }
};

window.renderTaskListUI = function() {
    const container = document.getElementById('taskListContainer');
    if (!container) return;
    container.innerHTML = "";
    
    if (taskList.length === 0) {
        container.innerHTML = "<div class='text-center text-muted py-3 small'>暂无任务</div>";
        return;
    }

    taskList.forEach(task => {
        const isActive = task.id === currentTaskId;
        
        const statusConfig = {
            'draft':     { icon: 'bi-pencil-square', color: 'text-secondary', text: '草稿' },
            'running':   { icon: 'spinner-grow spinner-grow-sm', color: 'text-success', text: '生成中...' },
            'paused':    { icon: 'bi-pause-circle-fill', color: 'text-warning', text: '已暂停' },
            'completed': { icon: 'bi-check-circle-fill', color: 'text-primary', text: '已完成' },
            'stopped':   { icon: 'bi-stop-circle-fill', color: 'text-danger', text: '已停止' }
        };
        
        const st = statusConfig[task.status] || statusConfig['draft'];
        const iconHtml = st.icon.includes('spinner') 
            ? `<span class="${st.icon}" role="status" aria-hidden="true"></span>` 
            : `<i class="bi ${st.icon}"></i>`;

        const itemDiv = document.createElement('div');
        itemDiv.className = `list-group-item task-item d-flex justify-content-between align-items-center ${isActive ? 'active-task' : ''}`;
        itemDiv.onclick = () => switchTask(task.id);
        
        const date = new Date(task.timestamp);
        const timeStr = date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});

        itemDiv.innerHTML = `
            <div class="d-flex flex-column text-truncate" style="width: 85%;">
                <div class="fw-bold text-dark text-truncate mb-1" style="font-size: 0.9rem;">
                    ${task.title || '未命名任务'}
                </div>
                <div class="d-flex align-items-center small">
                    <span class="${st.color} me-2 d-flex align-items-center" style="font-size: 0.75rem;">
                        ${iconHtml} <span class="ms-1">${st.text}</span>
                    </span>
                    <span class="text-muted" style="font-size: 0.75rem;">${timeStr}</span>
                </div>
            </div>
            <button onclick="deleteTask(event, '${task.id}')" class="btn btn-sm btn-link text-danger p-0 task-delete-btn" title="删除">
                <i class="bi bi-trash"></i>
            </button>
        `;
        container.appendChild(itemDiv);
    });
};

window.lockUI = function(locked) {
    document.getElementById('btnSubmit').disabled = locked;
    const ctrlDiv = document.getElementById('controlButtons');
    ctrlDiv.style.display = 'block'; 

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

// --- Controls ---
window.togglePause = async function() { 
    const action = isPaused ? 'resume' : 'pause';
    await authenticatedFetch('/control', {method: 'POST', body: JSON.stringify({ task_id: currentTaskId, action: action })});
    
    isPaused = !isPaused;
    const task = taskList.find(t => t.id === currentTaskId);
    if(task) { task.status = isPaused ? 'paused' : 'running'; saveTaskListMeta(); renderTaskListUI(); }
    updatePauseBtnState();
    appendLog(isPaused ? "⏸ 任务已暂停" : "▶ 任务继续", 'warn');
};

async function stopTask() { 
    if(!confirm("确定停止当前任务？")) return;
    if(abortController) abortController.abort();
    
    await authenticatedFetch('/control', {method: 'POST', body: JSON.stringify({ task_id: currentTaskId, action: 'stop' })});
    
    const task = taskList.find(t => t.id === currentTaskId);
    if(task) { task.status = 'stopped'; saveTaskListMeta(); renderTaskListUI(); }
    
    lockUI(false);
    appendLog("⏹ 任务已手动停止", 'error');
    saveCurrentTaskState();
}

window.createNewPaper = function() {
    if(confirm("即将创建一个新的论文任务，是否继续？")) {
        createNewTask();
    }
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

// --- Basic Tools ---
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

// --- Files & Export ---
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

// ============================================================
// 7. Outline Parsing Logic
// ============================================================

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
                <button class="btn btn-sm text-secondary ms-2" onclick="deleteLeaf(${gIdx}, ${cIdx})"><i class="bi bi-x"></i></button>
            `;
            body.appendChild(row);
        });
        container.appendChild(card);
    });
    document.getElementById('totalWords').innerText = globalTotal;
}

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

function deleteLeaf(gIdx, cIdx) { parsedStructure[gIdx].children.splice(cIdx, 1); renderConfigArea(); }
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
    // 兼容：如果传入的是 gIdx, cIdx，则为左侧配置区调用
    // 如果没有内容，提示先生成
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

// [核心] 正则替换正文内容
window.replaceSectionContent = function(title, newContent) {
    const escapedTitle = escapeRegExp(title);
    
    // ============================================================
    // 1. 强制格式化 (核心修改)
    // ============================================================
    
    // A. 预处理：统一换行符，去除尾部空白
    let formattedText = newContent.trimEnd().replace(/\r\n/g, '\n');

    // B. 压缩空行：将 \n\n+ (两个及以上换行) 替换为 \n (单换行)
    // 这解决了“两段之间不要有空行”的问题 (在 breaks:true 模式下)
    formattedText = formattedText.replace(/\n\s*\n/g, '\n');

    // C. 强制缩进：处理每一行
    formattedText = formattedText.split('\n').map(line => {
        let l = line.trimEnd(); // 去除行尾空格
        if (!l) return l; // 空行跳过

        // 跳过 Markdown 语法行 (标题、表格、代码块、列表、引用)
        if (/^(\#|\||`|- |\* |> )/.test(l.trimStart())) {
            return l;
        }

        // 如果已经有全角空格，保留
        if (l.startsWith('　　')) return l;

        // 如果是普通空格开头，替换为全角
        // 比如 "  段落" -> "　　段落"
        if (l.startsWith('  ')) {
             return l.replace(/^( +)/, m => '　'.repeat(Math.ceil(m.length/2)));
        }

        // 否则，强制添加全角缩进
        return '　　' + l.trimStart();
    }).join('\n');

    // ============================================================
    // 2. 执行替换
    // ============================================================
    
    const regex = new RegExp(`(#{1,6}\\s*${escapedTitle}\\s*\\n)([\\s\\S]*?)(?=\\n\\s*#{1,6}\\s|$)`, 'i');
    
    const match = fullMarkdownText.match(regex);
    
    if (match) {
        const oldSection = match[0];
        const header = match[1]; 
        
        // 拼接：标题 + 换行 + 格式化后的内容 + 两个换行(与下节隔开)
        const replacement = `${header}${formattedText}\n\n`;
        
        fullMarkdownText = fullMarkdownText.replace(oldSection, replacement);
        
        // 刷新视图
        const container = document.querySelector('.output-area');
        const scrollPos = container ? container.scrollTop : 0;
        
        renderEnrichedResult(fullMarkdownText);
        
        setTimeout(() => {
            if(container) container.scrollTop = scrollPos;
        }, 50);
        
    } else {
        console.warn("未在正文中找到章节，追加到末尾");
        fullMarkdownText += `\n\n### ${title}\n\n${formattedText}\n\n`;
        renderEnrichedResult(fullMarkdownText);
    }
};