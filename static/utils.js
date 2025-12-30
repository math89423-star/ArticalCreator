/**
 * utils.js
 * 包含：通用工具、网络请求、大纲操作、文件处理、UI辅助函数
 */
console.log("Utils.js loaded");

// ============================================================
// 1. 通用工具函数 (Helpers)
// ============================================================

window.generateUUID = function() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => (c === 'x' ? Math.random() * 16 | 0 : (Math.random() * 16 | 0) & 0x3 | 0x8).toString(16));
};

window.escapeRegExp = function(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
};

window.normalizeTitle = function(title) {
    return title.replace(/\s+/g, '').replace(/AI重写|编辑|撤销|删除|精简|重写此节/g, '');
};

window.appendLog = function(msg, type = 'info') {
    const logArea = document.getElementById('logArea');
    if (!logArea) return;
    const time = new Date().toLocaleTimeString();
    let color = '#00ff9d';
    if (type === 'error') color = '#ff4d4d';
    if (type === 'warn') color = '#ffc107';
    const html = `<div style="color:${color}; border-bottom:1px dashed #333; padding:2px 0;">[${time}] ${msg}</div>`;
    logArea.innerHTML += html;
    logArea.scrollTop = logArea.scrollHeight;
};

// 网络请求封装
window.authenticatedFetch = async function(url, options = {}) {
    if (!options.headers) options.headers = {};
    if (!(options.body instanceof FormData)) options.headers['Content-Type'] = 'application/json';
    options.headers['X-User-ID'] = currentUserId; // 依赖全局变量
    return fetch(url, options);
};

// ============================================================
// 2. UI 控制与文件/导出 (UI & IO)
// ============================================================

window.lockUI = function(locked) {
    const btnSubmit = document.getElementById('btnSubmit');
    if(btnSubmit) btnSubmit.disabled = locked;
    
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
    isPaused = !isPaused; // 修改全局状态
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
    fullMarkdownText = ""; // 修改全局状态
    document.getElementById('resultContent').innerHTML = "<div class='text-center text-muted mt-5 pt-5'><p style='font-size: 1.2rem;'>💡 内容已清空</p></div>";
    currentEventIndex = 0; 
    const task = taskList.find(t => t.id === currentTaskId);
    if(task) { task.status = 'draft'; saveTaskListMeta(); renderTaskListUI(); }
    lockUI(false);
    saveCurrentTaskState();
    if(!silent) appendLog("🗑️ 内容已清空", 'warn');
};

// 文件处理
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

// 导出功能
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
// 3. 大纲解析与操作 (Outline Logic)
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

// 保留原有的 LLM 智能分配逻辑
window.smartDistributeWords = async function() {
    const totalTarget = parseInt(document.getElementById('globalTotalWords').value) || 5000;
    
    // 1. 收集所有需要分配字数的“末级章节” (Leaf Nodes)
    let activeLeaves = [];
    let leafTitles = [];
    
    // 遍历树结构收集叶子节点
    parsedStructure.forEach(group => {
        group.children.forEach(child => {
            if (child.isParent) return; // 跳过父节点
            
            // 排除参考文献和致谢，它们通常不计入正文生成字数，或者固定为0
            if (/参考文献|致谢/.test(child.text)) {
                child.words = 0;
            } else {
                activeLeaves.push(child);
                leafTitles.push(child.text);
            }
        });
    });

    if (leafTitles.length === 0) {
        alert("没有检测到有效的写作章节，无法分配。");
        return;
    }

    // 2. UI 变为加载状态
    const btn = document.querySelector('button[onclick="smartDistributeWords()"]');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 思考中...`;

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 200000);
        // 3. 请求后端 API
        const res = await authenticatedFetch('/api/smart_distribute', {
            method: 'POST',
            body: JSON.stringify({
                total_words: totalTarget,
                leaf_titles: leafTitles
            }),
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        const data = await res.json();
        if (data.status === 'success') {
            const map = data.distribution;
            
            // 4. 应用分配结果
            let assignedTotal = 0;
            activeLeaves.forEach(leaf => {
                // 尝试匹配配置对象
                let config = map[leaf.text];
                
                // 模糊匹配逻辑
                if (!config) {
                    const key = Object.keys(map).find(k => k.includes(leaf.text) || leaf.text.includes(k));
                    if (key) config = map[key];
                }

                if (config) {
                    // [核心修改] 同时应用字数和数据开关
                    leaf.words = parseInt(config.words);
                    // 只有当 LLM 明确说需要数据时，才自动开启；否则保持默认或关闭
                    if (typeof config.needs_data === 'boolean') {
                        leaf.useData = config.needs_data;
                    }
                } else {
                    // 保底逻辑
                    leaf.words = Math.floor(totalTarget / activeLeaves.length);
                }

                assignedTotal += leaf.words;
            });

            appendLog(`✅ 智能规划完成 (字数: ${assignedTotal}, 数据策略已自动应用)`, 'info');
            renderConfigArea(); // 刷新 UI，按钮颜色会变
        }
        else {
            throw new Error(data.msg);
        }

    } catch (e) {
        console.error(e);
        alert("智能分配失败，将回退到平均分配。\n错误: " + e.message);
        // 回退机制：平均分配
        let avg = Math.floor(totalTarget / activeLeaves.length);
        activeLeaves.forEach(leaf => leaf.words = avg);
        renderConfigArea();
    } finally {
        // 5. 恢复按钮
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
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
                        <input type="number" class="form-control text-center" id="chapter-total-${gIdx}" value="${chapterTotalWords}" step="1" min="0">
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
                    <input type="number" class="form-control form-control-sm word-input" value="${child.words}" step="1" min="0" onchange="updateLeaf(${gIdx}, ${cIdx}, 'words', this.value)">
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

// [修改] 章节手动分配：移除取整逻辑，改为精确分配
window.distributeChapterWords = function(gIdx) {
    const targetTotal = parseInt(document.getElementById(`chapter-total-${gIdx}`).value) || 0;
    const group = parsedStructure[gIdx];
    const activeLeaves = group.children.filter(c => !c.isParent);
    if (activeLeaves.length === 0) return alert("该章节下没有可分配的小节");
    
    // 精确除法
    let count = activeLeaves.length;
    let avg = Math.floor(targetTotal / count);
    let remainder = targetTotal % count;
    
    activeLeaves.forEach((leaf, index) => {
        // 余数均匀分配给前几个小节
        leaf.words = avg + (index < remainder ? 1 : 0);
    });
    
    renderConfigArea();
}

window.updateLeaf = function(gIdx, cIdx, field, value) {
    if (field === 'words') value = parseInt(value) || 0;
    parsedStructure[gIdx].children[cIdx][field] = value;
    if (field === 'words') renderConfigArea(); // Update total words
    if (field === 'text') sortLeaves(gIdx);
}

window.toggleLeafData = function(gIdx, cIdx) {
    parsedStructure[gIdx].children[cIdx].useData = !parsedStructure[gIdx].children[cIdx].useData;
    renderConfigArea();
}

window.sortLeaves = function(gIdx) {
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

window.deleteLeaf = function(gIdx, cIdx) { 
    const targetTitle = parsedStructure[gIdx].children[cIdx].text || "该小节";
    if(confirm(`⚠️ 危险操作确认\n\n您确定要永久删除写作点：\n“${targetTitle}” 吗？\n\n删除后无法恢复，请确认。`)) {
        parsedStructure[gIdx].children.splice(cIdx, 1); 
        renderConfigArea(); 
    }
}

window.addLeaf = function(gIdx) {
    const title = prompt("请输入新小节标题");
    if (title) { parsedStructure[gIdx].children.push({ text: title, isParent: false, words: 500 }); sortLeaves(gIdx); }
};
window.deleteGroup = function(gIdx) { if(confirm("确定删除该章节？")) { parsedStructure.splice(gIdx, 1); renderConfigArea(); } };
window.addManualChapter = function() {
    const title = prompt("请输入新章节标题");
    if(title) { parsedStructure.push({ title: title, children: [{ text: title + " 概述", isParent: false, words: 500 }] }); renderConfigArea(); }
};

// 辅助：查找章节配置
window.findChapterConfig = function(title) {
    if (!parsedStructure || parsedStructure.length === 0) return null;
    const cleanTitle = normalizeTitle(title);
    for (let group of parsedStructure) {
        if (normalizeTitle(group.title) === cleanTitle) return group;
        for (let child of group.children) {
            if (normalizeTitle(child.text) === cleanTitle) return child;
        }
    }
    return null;
};

// 辅助：提取段落内容
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

// 模态框辅助
window.openRewriteModal = function(gIdx, cIdx) {
    if (!fullMarkdownText) {
        alert("请先生成论文内容后再使用重写功能！");
        return;
    }
    // 注意：这里可能需要设置全局的 targetRewriteIndices，但主逻辑中重写主要通过 Result 区调用
    // 为了兼容左侧配置区的按钮，我们简单实现：
    const section = parsedStructure[gIdx].children[cIdx];
    document.getElementById('rewriteSectionTitle').value = section.text;
    document.getElementById('rewriteInstruction').value = ""; 
    const modalEl = document.getElementById('rewriteModal');
    const modalInstance = bootstrap.Modal.getOrCreateInstance(modalEl);
    modalInstance.show();
};

window.openRewriteModalFromResult = function(sectionTitle) {
    document.getElementById('rewriteSectionTitle').value = sectionTitle;
    document.getElementById('rewriteInstruction').value = ""; 
    const modalEl = document.getElementById('rewriteModal');
    const modalInstance = bootstrap.Modal.getOrCreateInstance(modalEl);
    modalInstance.show();
};

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