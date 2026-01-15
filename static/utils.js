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
    const configArea = document.getElementById('chapterConfigArea'); 
    if (!configArea) return;
    
    configArea.innerHTML = '';
    let globalTotal = 0;

    if (!parsedStructure || parsedStructure.length === 0) {
        configArea.innerHTML = `
            <div class="text-center text-muted py-5 my-5 border rounded bg-light">
                <i class="bi bi-file-earmark-text display-4 mb-3 d-block"></i>
                <p>请在上方粘贴开题报告或输入大纲进行解析</p>
            </div>`;
        return;
    }

    parsedStructure.forEach((group, gIdx) => {
        // --- 统计本章字数 ---
        let chapterTotalWords = 0;
        group.children.forEach(c => chapterTotalWords += parseInt(c.words || 0));
        globalTotal += chapterTotalWords;

        // --- 渲染章卡片 ---
        const card = document.createElement('div');
        card.className = 'card mb-3 shadow-sm border-0'; // 使用 Bootstrap card 样式
        
        card.innerHTML = `
            <div class="card-header bg-white border-bottom-0 py-2 d-flex align-items-center">
                <i class="bi bi-grip-vertical text-muted me-2" style="cursor: grab;"></i>
                
                <div class="flex-grow-1 me-3">
                    <input type="text" class="form-control fw-bold border-0 px-2 fs-5" 
                           value="${group.title}" 
                           onchange="parsedStructure[${gIdx}].title = this.value"
                           style="background: transparent;">
                </div>
                
                <div class="d-flex align-items-center gap-2">
                    <div class="input-group input-group-sm" style="width: 140px;">
                        <span class="input-group-text bg-light">字数</span>
                        <input type="number" class="form-control text-center" value="${chapterTotalWords}" readonly>
                    </div>
                    
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-secondary" onclick="addLeaf(${gIdx})" title="末尾添加小节">
                            <i class="bi bi-plus-lg"></i>
                        </button>
                        <button class="btn btn-outline-danger" onclick="deleteGroup(${gIdx})" title="删除整章">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
            <div class="card-body p-0">
                <div class="list-group list-group-flush chapter-body"></div>
            </div>
        `;
        
        const body = card.querySelector('.chapter-body');

        // --- 渲染小节列表 ---
        if (group.children && group.children.length > 0) {
            group.children.forEach((child, cIdx) => {
                const row = document.createElement('div');
                row.className = 'list-group-item d-flex align-items-center py-2 px-3 border-start-0 border-end-0';
                
                // 1. 计算缩进
                const currentLevel = child.level || 2; 
                const indent = Math.max(0, (currentLevel - 2) * 24); 

                // 2. 状态样式
                const isDataActive = child.useData;
                const isChartActive = child.chartType && child.chartType !== 'none';
                
                // 图表图标
                let chartIcon = 'bi-graph-up';
                if (child.chartType === 'table') chartIcon = 'bi-table';

                row.innerHTML = `
                    <div class="d-flex align-items-center flex-grow-1 me-3" style="padding-left: ${indent}px; transition: padding 0.2s;">
                        ${currentLevel > 2 ? '<i class="bi bi-arrow-return-right text-muted me-2 opacity-50"></i>' : ''}
                        <input type="text" class="form-control form-control-sm border-0 px-1" 
                               value="${child.text}" 
                               onchange="updateLeaf(${gIdx}, ${cIdx}, 'text', this.value)"
                               style="box-shadow: none; background: transparent; font-weight: 500;">
                    </div>
                    
                    <div class="d-flex align-items-center gap-2 opacity-75 hover-opacity-100">
                        
                        <div class="btn-group btn-group-sm me-1">
                            <button type="button" class="btn btn-light border-0 text-secondary" 
                                    onclick="changeLeafLevel(${gIdx}, ${cIdx}, -1)" title="升级 (向左)">
                                <i class="bi bi-chevron-left"></i>
                            </button>
                            <button type="button" class="btn btn-light border-0 text-secondary" 
                                    onclick="changeLeafLevel(${gIdx}, ${cIdx}, 1)" title="降级 (向右)">
                                <i class="bi bi-chevron-right"></i>
                            </button>
                        </div>

                        <div class="btn-group btn-group-sm me-1">
                            <button type="button" class="btn ${isDataActive ? 'btn-success text-white' : 'btn-outline-secondary text-muted'}" 
                                    onclick="toggleLeafData(${gIdx}, ${cIdx})" 
                                    title="数据开关" style="width: 32px;">
                                <i class="bi bi-database${isDataActive ? '-fill-check' : ''}"></i>
                            </button>
                            <button type="button" class="btn ${isChartActive ? 'btn-primary text-white' : 'btn-outline-secondary text-muted'}" 
                                    onclick="toggleLeafChart(${gIdx}, ${cIdx})" 
                                    title="图表: ${child.chartType === 'table' ? '表格' : (child.chartType === 'plot' ? '统计图' : '无')}" 
                                    style="width: 32px;">
                                <i class="bi ${chartIcon}"></i>
                            </button>
                        </div>

                        <div class="input-group input-group-sm" style="width: 75px;">
                            <input type="number" class="form-control text-center px-1" 
                                   value="${child.words}" step="50" min="0" 
                                   onchange="updateLeaf(${gIdx}, ${cIdx}, 'words', this.value)">
                        </div>

                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-link text-primary p-1" onclick="insertSubLeaf(${gIdx}, ${cIdx})" title="插入子标题">
                                <i class="bi bi-plus-circle-fill"></i>
                            </button>
                            <button class="btn btn-link text-danger p-1" onclick="deleteLeaf(${gIdx}, ${cIdx})" title="删除">
                                <i class="bi bi-x-circle"></i>
                            </button>
                        </div>
                    </div>
                `;
                
                // 鼠标悬停高亮当前行效果 (可选)
                row.addEventListener('mouseenter', () => row.style.backgroundColor = '#f8f9fa');
                row.addEventListener('mouseleave', () => row.style.backgroundColor = 'transparent');
                
                body.appendChild(row);
            });
        } else {
            body.innerHTML = '<div class="text-center py-3 text-muted fst-italic"><small>点击上方 + 添加小节</small></div>';
        }

        configArea.appendChild(card);
    });

    const totalEl = document.getElementById('totalWords');
    if (totalEl) totalEl.innerText = globalTotal;
};

function updateTotalWordsDisplay() {
    const totalEl = document.getElementById('totalWordsCount');
    if (!totalEl) return;
    let total = 0;
    parsedStructure.forEach(g => {
        if(g.children) g.children.forEach(c => total += parseInt(c.words || 0));
    });
    totalEl.innerText = total;
}

window.toggleLeafChart = function(gIdx, cIdx) {
    const child = parsedStructure[gIdx].children[cIdx];
    if (!child.chartType || child.chartType === 'none') {
        child.chartType = 'table';
    } else if (child.chartType === 'table') {
        child.chartType = 'plot';
    } else {
        child.chartType = 'none';
    }
    // 如果开启了图表，自动开启数据开关
    if (child.chartType !== 'none') child.useData = true;
    renderConfigArea();
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

window.insertSubLeaf = function(gIdx, cIdx) {
    const parentLeaf = parsedStructure[gIdx].children[cIdx];
    const newLevel = (parentLeaf.level || 2) + 1;
    const finalLevel = newLevel > 6 ? 6 : newLevel;

    const newLeaf = {
        text: "", // 留空让用户填
        level: finalLevel,
        words: 300, 
        useData: false,
        chartType: 'none'
    };
    parsedStructure[gIdx].children.splice(cIdx + 1, 0, newLeaf);
    renderConfigArea();
};

window.updateLeaf = function(gIdx, cIdx, field, value) {
    if (field === 'words') value = parseInt(value) || 0;
    parsedStructure[gIdx].children[cIdx][field] = value;
    if (field === 'words') renderConfigArea(); // Update total words
}

window.toggleLeafData = function(gIdx, cIdx) {
    parsedStructure[gIdx].children[cIdx].useData = !parsedStructure[gIdx].children[cIdx].useData;
    renderConfigArea();
}

window.deleteLeaf = function(gIdx, cIdx) { 
    const targetTitle = parsedStructure[gIdx].children[cIdx].text || "该小节";
    if(confirm(`⚠️ 危险操作确认\n\n您确定要永久删除写作点：\n“${targetTitle}” 吗？\n\n删除后无法恢复，请确认。`)) {
        parsedStructure[gIdx].children.splice(cIdx, 1); 
        renderConfigArea(); 
    }
}

window.changeLeafLevel = function(gIdx, cIdx, delta) {
    const child = parsedStructure[gIdx].children[cIdx];
    // 默认层级为 2 (二级标题)，允许范围 2~6
    let currentLevel = child.level || 2;
    let newLevel = currentLevel + delta;
    
    // 边界限制：不能升级成章(1级)，也不能太深(>6级)
    if (newLevel < 2) newLevel = 2;
    if (newLevel > 6) newLevel = 6;
    
    child.level = newLevel;
    renderConfigArea(); // 重绘以显示新缩进
};

window.addLeaf = function(gIdx) {
    const title = prompt("请输入新小节标题\n(提示：输入 '1.1.1 标题' 可自动识别为三级标题)");
    
    if (title && title.trim()) {
        const cleanTitle = title.trim();
        
        // 自动识别层级
        let level = 2; 
        if (/^\d+(\.\d+){1}\s/.test(cleanTitle)) level = 2;      // 1.1
        else if (/^\d+(\.\d+){2}\s/.test(cleanTitle)) level = 3; // 1.1.1
        else if (/^\d+(\.\d+){3}\s/.test(cleanTitle)) level = 4; // 1.1.1.1
        
        const needsData = /结果|分析|实验|数据|验证|测试|调研|统计/.test(cleanTitle);

        if (!parsedStructure[gIdx].children) {
            parsedStructure[gIdx].children = [];
        }

        parsedStructure[gIdx].children.push({ 
            text: cleanTitle, 
            isParent: false, 
            words: 500,  
            level: level, 
            useData: needsData,
            chartType: 'none'
        }); 
        
        renderConfigArea(); 
    }
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