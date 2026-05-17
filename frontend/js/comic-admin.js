/* 漫剧管理面板 — 交互逻辑 */
const API = '/api/comic';

// ---- 工具函数 ----
function $(sel, ctx) { return (ctx || document).querySelector(sel); }
function $$(sel, ctx) { return (ctx || document).querySelectorAll(sel); }
function fmtDate(d) { return new Date(d).toLocaleString('zh-CN'); }
function statusLabel(s) {
  const map = { draft: '草稿', generating_video: '生成视频中', video_done: '视频完成', video_failed: '视频失败', published: '已发布', pending: '排队中', generating: '生成中', completed: '已完成', failed: '失败' };
  return map[s] || s;
}

// ---- Toast 通知 ----
function showToast(message, type = 'info', duration = 3500) {
  const container = $('#toastContainer');
  const icons = { success: '✓', error: '✕', warning: '△', info: '○' };
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span style="font-weight:600;font-size:1rem;opacity:0.8;">${icons[type] || ''}</span><span>${escHtml(message)}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('toast-out');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

async function api(url, opts = {}) {
  const options = { ...opts };
  if (options.body && !options.headers) {
    options.headers = { 'Content-Type': 'application/json' };
  }
  const res = await fetch(url, options);
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(errText.slice(0, 200));
  }
  return res.json();
}

// ---- 页面状态 ----
let currentTab = 'scripts';
let uploadedPhotoIds = [];
let currentAdId = null;        // 当前步骤流程的 ad_id
let currentStep = 1;           // 1-4
let pollTimer = null;

// ---- 步骤状态常量 ----
const STEPS = { UPLOAD: 1, COMPOSITE: 2, SCRIPT: 3, VIDEO: 4 };

// ---- Tab 切换 ----
$$('.tab').forEach(t => {
  t.addEventListener('click', () => {
    $$('.tab').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    $$('.panel').forEach(x => x.classList.remove('active'));
    currentTab = t.dataset.tab;
    const panelMap = { scripts: 'scriptsPanel', videos: 'videosPanel', novels: 'novelsPanel', product: 'productPanel', publish: 'publishPanel' };
    $(`#${panelMap[currentTab]}`).classList.add('active');
    loadCurrentTab();
  });
});

// ---- 刷新 ----
$('#refreshBtn').addEventListener('click', loadCurrentTab);

// ---- Modal ----
$('#modalClose').addEventListener('click', () => $('#detailModal').classList.remove('active'));
$('#novelModalClose').addEventListener('click', () => $('#novelModal').classList.remove('active'));
document.querySelectorAll('.modal-overlay').forEach(el => {
  el.addEventListener('click', (e) => {
    if (e.target === el) el.classList.remove('active');
  });
});

// ---- 步骤指示器 ----
function updateStepUI(step) {
  currentStep = step;
  $$('.step-indicator .step').forEach((s, i) => {
    const num = i + 1;
    s.classList.remove('step-active', 'step-done');
    s.querySelector('.step-circle').textContent = num;
    if (num < step) {
      s.classList.add('step-done');
      s.querySelector('.step-circle').textContent = '✓';
    } else if (num === step) {
      s.classList.add('step-active');
    }
  });
  $$('.step-content').forEach(c => c.classList.remove('step-content-active'));
  const el = $(`#step${step}Content`);
  if (el) el.classList.add('step-content-active');
}

function goToStep(step) {
  updateStepUI(step);
  window.scrollTo({ top: $('.step-indicator').offsetTop - 20, behavior: 'smooth' });
}

function goToStepInteractive(step) {
  goToStep(step);
  if (!_lastFetchedAd || !currentAdId) return;
  const ad = _lastFetchedAd;

  if (step === STEPS.SCRIPT) {
    const hasScript = ad.script_content && ad.script_content !== '{}';
    if (hasScript) {
      $('#scriptPlaceholder').style.display = 'none';
      $('#scriptLoading').style.display = 'none';
      renderScriptPreview(ad);
    } else {
      $('#scriptPlaceholder').style.display = 'block';
      $('#scriptLoading').style.display = 'none';
      $('#scriptPreviewArea').style.display = 'none';
      $('#scriptActions').style.display = 'none';
    }
  } else if (step === STEPS.VIDEO) {
    if (ad.video_path) {
      $('#videoGenResult').style.display = 'block';
      $('#videoGenPlaceholder').style.display = 'none';
      $('#videoGenLoading').style.display = 'none';
      const src = window.location.origin + '/' + ad.video_path.replace(/^.*\/backend\//, '');
      $('#generatedVideoSrc').src = src;
      $('#generatedVideo').load();
      $('#generateVideoBtn').disabled = false;
    } else if (ad.script_confirmed) {
      $('#videoGenPlaceholder').style.display = 'block';
      $('#videoGenResult').style.display = 'none';
      $('#videoGenLoading').style.display = 'none';
      $('#generateVideoBtn').disabled = false;
    } else {
      $('#videoGenPlaceholder').style.display = 'block';
      $('#videoGenResult').style.display = 'none';
      $('#videoGenLoading').style.display = 'none';
      $('#generateVideoBtn').disabled = true;
    }
  } else if (step === STEPS.COMPOSITE) {
    if (!uploadedPhotoIds || !uploadedPhotoIds.length) {
      showToast('无商品照片，跳过合成步骤', 'info');
      goToStep(STEPS.SCRIPT);
      return;
    }
    runCompositePreview();
  }
}

// 步骤指示器点击导航
(function bindStepIndicator() {
  const indicator = document.querySelector('#stepIndicator');
  if (!indicator) return;
  indicator.addEventListener('click', (e) => {
    const stepEl = e.target.closest('.step');
    if (!stepEl) return;
    const targetStep = parseInt(stepEl.dataset.step);
    if (!targetStep || targetStep === currentStep) return;
    goToStepInteractive(targetStep);
  });
})();

// ---- 数据加载 ----
async function loadStats() {
  try {
    const stats = await api(API + '/stats');
    $('#statsBar').innerHTML = `
      <span class="stat">剧本: <strong>${stats.total_scripts}</strong></span>
      <span class="stat">视频: <strong>${stats.total_videos}</strong></span>
      <span class="stat">已完成: <strong>${stats.videos_completed}</strong></span>
      <span class="stat">已发布: <strong>${stats.total_published}</strong></span>
    `;
  } catch { $('#statsBar').innerHTML = '<span class="stat">无法加载统计</span>'; }
}

function loadCurrentTab() {
  if (currentTab === 'scripts') loadScripts();
  else if (currentTab === 'videos') loadVideos();
  else if (currentTab === 'novels') loadNovels();
  else if (currentTab === 'product') {
    if (_inProductStepFlow) {
      showProductStepFlow();
    } else {
      showProductListView();
    }
  }
  else if (currentTab === 'publish') loadPublishLogs();
}

// ---- 剧本列表 ----
async function loadScripts() {
  try {
    const scripts = await api(API + '/scripts?limit=50');
    const el = $('#scriptList');
    if (!scripts.length) {
      el.innerHTML = '<div class="empty-state"><p>暂无剧本</p><p class="sub">点击上方按钮触发生成</p></div>';
      return;
    }
    el.innerHTML = scripts.map(s => `
      <div class="card">
        <div class="card-status ${s.status}"></div>
        <div class="card-body">
          <div class="card-title">${escHtml(s.title)}</div>
          <div class="card-meta">
            <span>${statusLabel(s.status)}</span>
            ${s.genre ? '<span class="tag">' + escHtml(s.genre) + '</span>' : ''}
            ${s.review_score !== null && s.review_score !== undefined ? '<span class="tag review-score">评分: ' + s.review_score + '/10</span>' : ''}
            <span>${fmtDate(s.created_at)}</span>
          </div>
        </div>
        <div class="card-actions">
          <button class="btn btn-outline btn-sm" onclick="viewScript(${s.id})">查看</button>
          <button class="btn btn-secondary btn-sm" onclick="generateWithReview(${s.id}, 'script')" ${s.status === 'generating_video' ? 'disabled' : ''}>生成视频</button>
          <button class="btn btn-ghost-danger btn-sm" onclick="deleteScript(${s.id})" title="删除">✕</button>
        </div>
      </div>
    `).join('');
  } catch (e) { $('#scriptList').innerHTML = '<div class="empty-state"><p>加载失败</p><p class="sub">' + escHtml(e.message) + '</p></div>'; }
}

async function viewScript(id) {
  try {
    const script = await api(API + '/scripts/' + id);
    const storyboard = script.storyboard_json ? JSON.parse(script.storyboard_json) : [];
    const content = script.script_content ? JSON.parse(script.script_content) : {};
    $('#modalTitle').textContent = script.title;
    $('#modalBody').innerHTML = `
      <p><strong>类型:</strong> ${escHtml(script.genre || '未分类')} | <strong>状态:</strong> ${statusLabel(script.status)}</p>
      <p><strong>来源话题:</strong> ${escHtml(script.source_topic || '手动')}</p>
      ${content.characters ? renderCharacters(content.characters) : ''}
      <h3>剧本内容</h3>
      <pre>${escHtml(JSON.stringify(content.script || content, null, 2))}</pre>
      <h3>分镜描述 (${storyboard.length} 个场景)</h3>
      <pre>${escHtml(JSON.stringify(storyboard, null, 2))}</pre>
    `;
    $('#detailModal').classList.add('active');
  } catch (e) { showToast('加载失败: ' + e.message, 'error'); }
}

function renderCharacters(chars) {
  return '<h3>角色</h3><ul style="margin-bottom:12px;">' + chars.map(c =>
    '<li style="margin-bottom:4px;"><strong>' + escHtml(c.name) + '</strong> (' + escHtml(c.role) + '): ' + escHtml(c.description) + '</li>'
  ).join('') + '</ul>';
}

// ---- 视频列表 ----
async function loadVideos() {
  try {
    const videos = await api(API + '/videos?limit=50');
    const el = $('#videoList');
    if (!videos.length) {
      el.innerHTML = '<div class="empty-state"><p>暂无视频</p><p class="sub">先生成剧本后会自动生成视频</p></div>';
      return;
    }
    el.innerHTML = videos.map(v => `
      <div class="card">
        <div class="card-status ${v.status}"></div>
        <div class="card-body">
          <div class="card-title">视频 #${v.id}（剧本 #${v.script_id}）</div>
          <div class="card-meta">
            <span>${statusLabel(v.status)}</span>
            <span>${v.resolution}</span>
            <span>${v.duration_seconds}s</span>
            ${v.seedance_task_id ? '<span>任务: ' + escHtml(v.seedance_task_id.slice(0, 12)) + '...</span>' : ''}
            <span>${fmtDate(v.created_at)}</span>
          </div>
        </div>
        <div class="card-actions">
          ${v.file_path ? '<button class="btn btn-outline btn-sm" onclick="previewVideo(\'' + escHtml(v.file_path) + '\')">预览</button>' : ''}
          <button class="btn btn-info btn-sm" onclick="bilibiliLogin()">B站登录</button>
          <button class="btn btn-success btn-sm" onclick="publishVideo(${v.id})" ${v.status !== 'completed' ? 'disabled' : ''}>发布</button>
          <button class="btn btn-ghost-danger btn-sm" onclick="deleteVideo(${v.id})" title="删除">✕</button>
        </div>
      </div>
    `).join('');
  } catch (e) { $('#videoList').innerHTML = '<div class="empty-state"><p>加载失败</p><p class="sub">' + escHtml(e.message) + '</p></div>'; }
}

// ---- 发布管理 ----
async function loadPublishLogs() {
  try {
    const logs = await api(API + '/publish-logs?limit=50');
    const el = $('#publishList');
    if (!logs.length) {
      el.innerHTML = '<div class="empty-state"><p>暂无发布记录</p><p class="sub">视频生成后在视频队列中点击发布</p></div>';
      return;
    }
    el.innerHTML = logs.map(l => `
      <div class="card">
        <div class="card-status ${l.status}"></div>
        <div class="card-body">
          <div class="card-title">视频 #${l.video_id} → ${escHtml(l.platform)}</div>
          <div class="card-meta">
            <span>${statusLabel(l.status)}</span>
            ${l.publish_url ? '<span><a href="' + escHtml(l.publish_url) + '" target="_blank" style="color:var(--gold-light);text-decoration:none;">查看链接</a></span>' : ''}
            <span>${l.published_at ? fmtDate(l.published_at) : fmtDate(l.created_at)}</span>
          </div>
        </div>
      </div>
    `).join('');
  } catch (e) { $('#publishList').innerHTML = '<div class="empty-state"><p>加载失败</p><p class="sub">' + escHtml(e.message) + '</p></div>'; }
}

// ---- 视频发布/预览/B站登录 ----
async function publishVideo(id) {
  const platform = prompt('发布平台 (bilibili / weibo / douyin / wechat):', 'bilibili');
  if (!platform) return;
  try {
    const res = await api(API + '/videos/' + id + '/publish', {
      method: 'POST',
      body: JSON.stringify({ platform, message: '审核通过，发布' })
    });
    if (res.draft) {
      showToast(res.message + ' 草稿已保存到B站创作中心', 'success', 5000);
    } else {
      showToast(res.message, 'success');
      if (res.publish_url) showToast('发布链接: ' + res.publish_url, 'info', 5000);
    }
    loadStats();
    loadCurrentTab();
  } catch (e) { showToast('发布失败: ' + e.message, 'error'); }
}

async function bilibiliLogin() {
  try {
    const res = await api(API + '/bilibili/login', { method: 'POST' });
    if (res.qr_image_url) {
      const url = window.location.origin + res.qr_image_url;
      window.open(url, '_blank');
      const check = setInterval(async () => {
        try {
          const st = await api(API + '/bilibili/login/check');
          if (st.status === 'done') {
            clearInterval(check); showToast('B站登录成功！', 'success'); loadCurrentTab();
          } else if (st.status === 'timeout') {
            clearInterval(check); showToast('二维码已过期', 'warning');
          }
        } catch (_) {}
      }, 3000);
      setTimeout(() => clearInterval(check), 300000);
    } else { showToast('生成二维码失败', 'error'); }
  } catch (e) { showToast('B站登录失败: ' + e.message, 'error'); }
}

function previewVideo(path) {
  const videoUrl = window.location.origin + '/' + path.replace(/^.*\/backend\//, '');
  window.open(videoUrl, '_blank');
}

// ---- 删除（剧本/视频） ----
async function deleteScript(id) {
  if (!confirm('确定删除剧本 #' + id + '？（关联视频也将删除）')) return;
  try {
    await api(API + '/scripts/' + id, { method: 'DELETE' });
    showToast('剧本已删除', 'success'); loadScripts(); loadStats();
  } catch (e) { showToast('删除失败: ' + e.message, 'error'); }
}
async function deleteVideo(id) {
  if (!confirm('确定删除视频 #' + id + '？')) return;
  try {
    await api(API + '/videos/' + id, { method: 'DELETE' });
    showToast('视频已删除', 'success'); loadVideos(); loadStats();
  } catch (e) { showToast('删除失败: ' + e.message, 'error'); }
}

// ---- 小说 ----
$('#createNovelBtn').addEventListener('click', async () => {
  const title = $('#novelTitle').value.trim();
  const chapters = parseInt($('#novelChapters').value) || 30;
  const btn = $('#createNovelBtn');
  btn.disabled = true; btn.textContent = '创建中...';
  try {
    await api(API + '/novels', { method: 'POST', body: JSON.stringify({ title, genre: $('#novelGenre').value.trim(), theme: $('#novelTheme').value.trim(), total_chapters: chapters }) });
    $('#novelTitle').value = '';
    showToast('小说创建成功', 'success');
    loadNovels();
  } catch (e) { showToast('创建失败: ' + e.message, 'error'); }
  btn.disabled = false; btn.textContent = '创建小说';
});

async function loadNovels() {
  try {
    const novels = await api(API + '/novels?limit=50');
    const el = $('#novelList');
    if (!novels.length) { el.innerHTML = '<div class="empty-state"><p>暂无小说</p><p class="sub">输入标题后点击「创建小说」开始</p></div>'; return; }
    el.innerHTML = novels.map(n => {
      const progress = n.total_chapters > 0 ? Math.round(n.done_chapters / n.total_chapters * 100) : 0;
      return `
      <div class="card">
        <div class="card-status ${n.status === 'completed' ? 'completed' : n.status === 'publishing' ? 'generating' : 'draft'}"></div>
        <div class="card-body">
          <div class="card-title">${escHtml(n.title)}</div>
          <div class="card-meta">
            <span>${statusLabel(n.status)}</span>
            ${n.genre ? '<span class="tag genre-tag">' + escHtml(n.genre) + '</span>' : ''}
            <span>${n.done_chapters}/${n.total_chapters}章</span>
            <span style="color:var(--text-tertiary);font-size:0.78rem;">${progress}%</span>
            ${n.has_world ? '<span style="color:var(--green);font-size:0.78rem;">✅世界观</span>' : ''}
            ${n.has_outline ? '<span style="color:var(--green);font-size:0.78rem;">✅大纲</span>' : ''}
            <span>${fmtDate(n.created_at)}</span>
          </div>
          <div class="progress-track"><div class="progress-fill" style="width:${progress}%"></div></div>
        </div>
        <div class="card-actions" style="flex-wrap:wrap;">
          <button class="btn btn-outline btn-sm" onclick="viewNovel(${n.id})">查看</button>
          ${n.done_chapters > 0 ? `<button class="btn btn-outline btn-sm" onclick="downloadNovel(${n.id})">下载</button>` : ''}
          ${!n.has_world ? `<button class="btn btn-primary btn-sm" onclick="generateWorld(${n.id})">世界观</button>` : `<button class="btn btn-outline btn-sm" onclick="showNovelFeedback('world', ${n.id})">重设世界观</button>`}
          ${n.has_world && !n.has_outline ? `<button class="btn btn-primary btn-sm" onclick="generateOutline(${n.id})">大纲</button>` : ''}
	          ${n.has_world && n.has_outline ? `<button class="btn btn-outline btn-sm" onclick="showNovelFeedback('outline', ${n.id})">重设大纲</button>` : ''}
          ${n.has_outline && n.done_chapters < n.total_chapters ? `<button class="btn btn-success btn-sm" onclick="generateAllChapters(${n.id})">生成全部</button>` : ''}
          <button class="btn btn-ghost-danger btn-sm" onclick="deleteNovel(${n.id})" title="删除">✕</button>
        </div>
      </div>`;
    }).join('');
  } catch (e) { $('#novelList').innerHTML = '<div class="empty-state"><p>加载失败</p><p class="sub">' + escHtml(e.message) + '</p></div>'; }
}

async function viewNovel(id) {
  try {
    const novel = await api(API + '/novels/' + id);
    const chapters = await api(API + '/novels/' + id + '/chapters');
    let chaptersHtml = '';
    if (chapters.length) {
      chaptersHtml = '<h3>章节目录</h3><div class="chapter-list">' + chapters.map(c => `
        <div class="chapter-item ${c.status === 'done' ? '' : 'pending'}" onclick="viewChapter(${id}, ${c.chapter_number})">
          <span class="chapter-num">第${c.chapter_number}章</span>
          <span class="chapter-title">${escHtml(c.title || '')}</span>
          ${c.review_score ? '<span class="chapter-score">' + c.review_score + '/10</span>' : ''}
          <span class="chapter-status">${c.status === 'done' ? '✓' : '○'}</span>
          <span class="chapter-preview">${escHtml(c.preview || '')}...</span>
        </div>`).join('') + '</div>';
    }
    let worldHtml = '';
    if (novel.world_setting) {
      const ws = novel.world_setting;
      const world = ws.world || {};
      worldHtml = '<div style="display:flex;align-items:center;gap:8px;"><h3>世界观</h3><button class="btn btn-outline btn-sm" onclick="showNovelFeedback(\'world\', ' + id + ')">重新生成</button></div><div class="novel-section"><p><strong>' + escHtml(world.name || '') + '</strong></p><p>' + escHtml(world.background || '') + '</p>' + (world.power_system ? '<p><strong>力量体系:</strong> ' + escHtml(world.power_system.name || '') + '</p>' : '') + '</div>';
    }
    let charHtml = '';
    if (novel.character_profiles && novel.character_profiles.length) {
      charHtml = '<div style="display:flex;align-items:center;gap:8px;margin-top:12px;"><h3 style="margin:0;">角色设定</h3><button class="btn btn-outline btn-sm" onclick="showNovelFeedback(\'world\', ' + id + ')">重新生成</button></div><div class="novel-section">' + novel.character_profiles.map(c => '<div class="char-card"><strong>' + escHtml(c.name) + '</strong><span class="tag">' + escHtml(c.role || '') + '</span><p>' + escHtml(c.personality || '') + '</p></div>').join('') + '</div>';
    }
    let genBtn = '';
    if (novel.has_outline && chapters.length < novel.total_chapters) {
      genBtn = '<button class="btn btn-primary" onclick="generateSingleChapter(' + id + ', ' + (chapters.length + 1) + ')" style="margin-bottom:16px;">生成下一章（第' + (chapters.length + 1) + '章）</button>';
    }
    $('#novelModalTitle').textContent = novel.title;
    $('#novelModalBody').innerHTML = `
      <div style="margin-bottom:16px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
        ${novel.genre ? '<span class="tag genre-tag">' + escHtml(novel.genre) + '</span>' : ''}
        <span>${novel.done_chapters}/${novel.total_chapters}章</span>
        <span>状态: ${statusLabel(novel.status)}</span>
        ${novel.done_chapters > 0 ? '<button class="btn btn-outline btn-sm" onclick="downloadNovel(' + id + ')" style="margin-left:auto;">下载 TXT</button>' : ''}
      </div>
      ${genBtn}
      ${worldHtml}
      ${charHtml}
      ${chaptersHtml}
    `;
    $('#novelModal').classList.add('active');
  } catch (e) { showToast('加载失败: ' + e.message, 'error'); }
}

async function viewChapter(novelId, chapterNum) {
  try {
    const ch = await api(API + '/novels/' + novelId + '/chapters/' + chapterNum);
    if (!ch.content) {
      if (!confirm('本章尚未生成，是否现在生成？')) return;
      const res = await api(API + '/novels/' + novelId + '/generate-chapter/' + chapterNum, { method: 'POST' });
      showToast('生成完成，评分: ' + (res.review_score || 'N/A') + '/10', 'success');
      viewNovel(novelId); return;
    }
    $('#novelModalTitle').textContent = '第' + ch.chapter_number + '章 ' + (ch.title || '');
    $('#novelModalBody').innerHTML = `
      <div style="margin-bottom:16px;color:var(--text-tertiary);font-size:0.82rem;">${ch.word_count > 0 ? Math.round(ch.word_count / 100) / 10 + '千字' : ''}${ch.review_score ? ' | 评分: ' + ch.review_score + '/10' : ''}</div>
      <div class="chapter-content">${escHtml(ch.content).replace(/\n/g, '<br>')}</div>
      <div style="margin-top:20px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap;">
        ${chapterNum > 1 ? '<button class="btn btn-outline btn-sm" onclick="viewChapter(' + novelId + ', ' + (chapterNum - 1) + ')">← 上一章</button>' : ''}
        <button class="btn btn-outline btn-sm" onclick="viewNovel(' + novelId + ')">返回目录</button>
        <button class="btn btn-outline btn-sm" onclick="showNovelFeedback('chapter', ' + novelId + ', ' + chapterNum + ')">重新生成</button>
        <button class="btn btn-outline btn-sm" onclick="viewChapter(' + novelId + ', ' + (chapterNum + 1) + ')">下一章 →</button>
      </div>`;
  } catch (e) { showToast('加载失败: ' + e.message, 'error'); }
}

async function downloadNovel(id) { window.open(API + '/novels/' + id + '/download', '_blank'); }
async function generateWorld(id) {
  if (!confirm('确定生成世界观设定？')) return;
  try { const res = await api(API + '/novels/' + id + '/generate-world', { method: 'POST' }); showToast(res.message, 'info'); setTimeout(loadNovels, 2000); } catch (e) { showToast('生成失败: ' + e.message, 'error'); }
}
async function generateOutline(id) {
  if (!confirm('确定生成分章大纲？')) return;
  try { const res = await api(API + '/novels/' + id + '/generate-outline', { method: 'POST' }); showToast(res.message, 'info'); setTimeout(loadNovels, 2000); } catch (e) { showToast('生成失败: ' + e.message, 'error'); }
}
async function generateAllChapters(id) {
  if (!confirm('确定生成全部章节？耗时较长。')) return;
  try { const res = await api(API + '/novels/' + id + '/generate-all', { method: 'POST' }); showToast(res.message, 'info'); } catch (e) { showToast('触发失败: ' + e.message, 'error'); }
}
async function deleteNovel(id) {
  if (!confirm('确定删除小说 #' + id + '？')) return;
  try { await api(API + '/novels/' + id, { method: 'DELETE' }); showToast('小说已删除', 'success'); loadNovels(); } catch (e) { showToast('删除失败: ' + e.message, 'error'); }
}
async function generateSingleChapter(novelId, chapterNum) {
  if (!confirm('确定生成第' + chapterNum + '章？')) return;
  try { const res = await api(API + '/novels/' + novelId + '/generate-chapter/' + chapterNum, { method: 'POST' }); showToast('第' + chapterNum + '章生成完成，评分: ' + (res.review_score || 'N/A') + '/10', 'success'); viewNovel(novelId); } catch (e) { showToast('生成失败: ' + e.message, 'error'); }
}

// ---- 小说反馈重试 ----
let _feedbackState = { type: '', id: 0, chapterNum: null };

function showNovelFeedback(type, id, chapterNum) {
  _feedbackState = { type, id, chapterNum: chapterNum || null };
  const labels = { world: '世界观', outline: '大纲', chapter: '章节' };
  $('#novelFeedbackTitle').textContent = '重新生成' + (labels[type] || '');
  $('#novelFeedbackInput').value = '';
  $('#novelFeedbackModal').classList.add('active');
}

function closeNovelFeedback() {
  $('#novelFeedbackModal').classList.remove('active');
  $('#novelFeedbackInput').value = '';
}

$('#doNovelFeedbackBtn').addEventListener('click', async () => {
  const { type, id, chapterNum } = _feedbackState;
  const feedback = $('#novelFeedbackInput').value.trim();
  if (!feedback) { showToast('请填写修改意见', 'warning'); return; }
  closeNovelFeedback();

  const btn = $('#doNovelFeedbackBtn');
  btn.disabled = true; btn.textContent = '生成中...';

  try {
    let endpoint, method = 'POST';
    if (type === 'world') {
      endpoint = API + '/novels/' + id + '/retry-world';
    } else if (type === 'outline') {
      endpoint = API + '/novels/' + id + '/retry-outline';
    } else if (type === 'chapter') {
      endpoint = API + '/novels/' + id + '/retry-chapter/' + chapterNum;
    } else {
      showToast('未知操作类型', 'error'); return;
    }
    const res = await api(endpoint, { method, body: JSON.stringify({ feedback }) });
    showToast(res.message || '重新生成成功', 'success');
    if (type === 'chapter') {
      viewChapter(id, chapterNum);
    } else {
      viewNovel(id);
      loadNovels();
    }
  } catch (e) {
    showToast('重新生成失败: ' + e.message, 'error');
  } finally {
    btn.disabled = false; btn.textContent = '重新生成';
  }
});

// =========================================================
// 商品带货步骤流程
// =========================================================

// ---- 商品带货列表 ----
let _inProductStepFlow = false;
let _lastFetchedAd = null;

function showProductListView() {
  _inProductStepFlow = false;
  $('#productListView').style.display = 'block';
  $('#productStepFlow').style.display = 'none';
  loadProductAds();
  // 重置步骤状态
  currentStep = 1;
  currentAdId = null;
  _lastFetchedAd = null;
  uploadedPhotoIds = [];
  updateStepUI(1);
  $('#photoPreview').innerHTML = '';
  $('#photoCount').textContent = '未选择';
  $('#videoName').textContent = '未选择视频';
  $('#productPhotoInput').value = '';
  $('#productVideoInput').value = '';
  $('#createDraftBtn').disabled = true;
}

function showProductStepFlow() {
  _inProductStepFlow = true;
  $('#productListView').style.display = 'none';
  $('#productStepFlow').style.display = 'block';
}

async function loadProductAds() {
  try {
    const list = await api(API + '/product-ad/list?limit=50');
    const el = $('#productAdList');
    if (!list.length) {
      el.innerHTML = '<div class="empty-state"><p>暂无带货剧本</p><p class="sub">点击「新建带货」创建</p></div>';
      return;
    }
    el.innerHTML = list.map(ad => `
      <div class="card">
        <div class="card-status ${ad.status === 'video_done' ? 'completed' : ad.status === 'video_failed' ? 'failed' : 'draft'}"></div>
        <div class="card-body">
          <div class="card-title">${escHtml(ad.title)}</div>
          <div class="card-meta">
            <span>${statusLabel(ad.status)}</span>
            ${ad.genre ? '<span class="tag">' + escHtml(ad.genre) + '</span>' : ''}
            ${ad.review_score !== null && ad.review_score !== undefined ? '<span class="tag review-score">评分: ' + ad.review_score + '/10</span>' : ''}
            <span>${fmtDate(ad.created_at)}</span>
          </div>
        </div>
        <div class="card-actions">
          <button class="btn btn-outline btn-sm" onclick="continueProductAd(${ad.id})">继续制作</button>
          <button class="btn btn-outline btn-sm" onclick="viewProductAdScript(${ad.id})">查看剧本</button>
          ${ad.video_path ? '<button class="btn btn-secondary btn-sm" onclick="previewVideo(\'' + escHtml(ad.video_path) + '\')">预览视频</button>' : ''}
          <button class="btn btn-ghost-danger btn-sm" onclick="deleteProductAd(${ad.id})" title="删除">✕</button>
        </div>
      </div>
    `).join('');
  } catch (e) { $('#productAdList').innerHTML = '<div class="empty-state"><p>加载失败</p><p class="sub">' + escHtml(e.message) + '</p></div>'; }
}

async function continueProductAd(id) {
  try {
    const ad = await api(API + '/product-ad/' + id);
    _lastFetchedAd = ad;
    currentAdId = id;
    uploadedPhotoIds = JSON.parse(ad.photo_ids || '[]');
    // 填充表单
    if (ad.product_info) {
      const info = typeof ad.product_info === 'string' ? JSON.parse(ad.product_info) : ad.product_info;
      $('#prodName').value = info.name || '';
      $('#prodCategory').value = info.category || '';
      $('#prodDesc').value = info.description || '';
      $('#prodSellingPoints').value = info.selling_points || '';
      $('#prodAudience').value = info.target_audience || '';
      if (info.visual_style) $('#prodVisualStyle').value = info.visual_style;
      if (info.showcase_style) $('#prodShowcaseStyle').value = info.showcase_style;
      if (info.style_preference) $('#prodStylePreference').value = info.style_preference;
    }
    showProductStepFlow();
    // 根据状态跳转到对应步骤
    if (ad.composite_confirmed && ad.script_confirmed && (ad.status === 'video_done' || ad.status === 'video_failed')) {
      goToStep(STEPS.VIDEO);
      if (ad.video_path) {
        $('#videoGenResult').style.display = 'block';
        $('#videoGenPlaceholder').style.display = 'none';
        $('#videoGenLoading').style.display = 'none';
        const src = window.location.origin + '/' + ad.video_path.replace(/^.*\/backend\//, '');
        $('#generatedVideoSrc').src = src;
        $('#generatedVideo').load();
      }
      $('#generateVideoBtn').disabled = false;
    } else if (ad.composite_confirmed && ad.script_confirmed) {
      goToStep(STEPS.VIDEO);
      $('#generateVideoBtn').disabled = false;
    } else if (ad.composite_confirmed) {
      goToStep(STEPS.SCRIPT);
      // 已有剧本内容则直接展示，否则触发生成
      const hasScript = ad.script_content && ad.script_content !== '{}';
      if (hasScript) {
        renderScriptPreview(ad);
      } else {
        runScriptGeneration();
      }
    } else {
      const hasPhotos = uploadedPhotoIds && uploadedPhotoIds.length > 0;
      if (hasPhotos) {
        goToStep(STEPS.COMPOSITE);
        runCompositePreview();
      } else if (ad.composite_confirmed) {
        // 无照片但已确认合成 → 直接进入剧本步骤
        goToStep(STEPS.SCRIPT);
        if (ad.script_content && ad.script_content !== '{}') {
          renderScriptPreview(ad);
        } else {
          runScriptGeneration();
        }
      } else {
        goToStep(STEPS.UPLOAD);
      }
    }
    showToast('已加载: ' + ad.title, 'info');
  } catch (e) { showToast('加载失败: ' + e.message, 'error'); }
}

async function deleteProductAd(id) {
  if (!confirm('确定删除带货剧本 #' + id + '？')) return;
  try {
    await api(API + '/product-ad/' + id, { method: 'DELETE' });
    showToast('已删除', 'success');
    loadProductAds();
  } catch (e) { showToast('删除失败: ' + e.message, 'error'); }
}

async function viewProductAdScript(id) {
  try {
    const ad = await api(API + '/product-ad/' + id);
    _lastFetchedAd = ad;
    const script = typeof ad.script_content === 'string' ? JSON.parse(ad.script_content || '{}') : (ad.script_content || {});
    const scenes = script.scenes || script.script || [];
    const tags = script.tags || [];
    const showcaseMap = { visual: '视觉展示', story: '剧情带货' };

    $('#modalTitle').textContent = ad.title || '带货剧本';
    $('#modalBody').innerHTML = `
      <p><strong>商品:</strong> ${escHtml(script.product || ad.title || '—')} | <strong>风格:</strong> ${escHtml(showcaseMap[script.showcase_style] || script.showcase_style || '—')}</p>
      <p><strong>状态:</strong> ${statusLabel(ad.status)} | <strong>评分:</strong> ${ad.review_score !== null && ad.review_score !== undefined ? ad.review_score + '/10' : '—'}</p>
      ${script.setting ? '<p><strong>场景设定:</strong> ' + escHtml(script.setting) + '</p>' : ''}
      ${script.background_music ? '<p><strong>背景音乐:</strong> ' + escHtml(script.background_music) + '</p>' : ''}
      ${tags.length ? '<p>' + tags.map(t => '<span class="tag">' + escHtml(t) + '</span>').join(' ') + '</p>' : ''}
      <h3>场景列表 (${scenes.length} 个)</h3>
      ${scenes.map(s => `
        <div style="background:rgba(255,255,255,0.03);border-radius:8px;padding:10px;margin-bottom:8px;">
          <strong>场景 ${s.scene || '?'}</strong> <span style="color:var(--text-tertiary);">${s.duration_seconds || '—'}s</span>
          ${s.camera_angle ? '<div style="font-size:0.85rem;margin-top:4px;"><span style="color:var(--gold-light);">镜头:</span> ' + escHtml(s.camera_angle) + '</div>' : ''}
          ${s.action ? '<div style="font-size:0.85rem;margin-top:2px;"><span style="color:var(--gold-light);">动作:</span> ' + escHtml(s.action) + '</div>' : ''}
          ${s.product_focus ? '<div style="font-size:0.85rem;margin-top:2px;"><span style="color:var(--gold-light);">展示:</span> ' + escHtml(s.product_focus) + '</div>' : ''}
        </div>
      `).join('')}
      <h3 style="cursor:pointer;color:var(--gold-light);" onclick="
        const raw=document.getElementById('rawScriptBlock_${id}');
        const showing=raw.style.display!=='none';
        raw.style.display=showing?'none':'block';
        this.querySelector('span').textContent=showing?'▶ 原始 JSON':'▼ 原始 JSON';
      "><span>▶ 原始 JSON</span></h3>
      <pre id="rawScriptBlock_${id}" style="display:none;max-height:300px;overflow-y:auto;">${escHtml(JSON.stringify(script, null, 2))}</pre>
    `;
    $('#detailModal').classList.add('active');
  } catch (e) {
    showToast('加载剧本失败: ' + e.message, 'error');
  }
}

$('#refreshProductBtn').addEventListener('click', loadProductAds);
$('#newProductBtn').addEventListener('click', () => {
  // 重置表单
  $('#prodName').value = '';
  $('#prodCategory').value = '';
  $('#prodDesc').value = '';
  $('#prodSellingPoints').value = '';
  $('#prodAudience').value = '';
  $('#prodVisualStyle').value = 'realistic';
  $('#prodShowcaseStyle').value = 'story';
  $('#prodStylePreference').value = '';
  currentAdId = null;
  uploadedPhotoIds = [];
  goToStep(STEPS.UPLOAD);
  showProductStepFlow();
});
$('#backToProductListBtn').addEventListener('click', showProductListView);

// ---- Step 1: 上传素材 ----
$('#selectPhotosBtn').addEventListener('click', () => $('#productPhotoInput').click());
$('#productPhotoInput').addEventListener('change', (e) => {
  const files = e.target.files;
  if (!files || !files.length) return;
  const preview = $('#photoPreview');
  preview.innerHTML = '';
  for (const f of files) {
    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = document.createElement('img');
      img.src = ev.target.result;
      img.className = 'photo-thumb';
      img.title = f.name;
      preview.appendChild(img);
    };
    reader.readAsDataURL(f);
  }
  $('#photoCount').textContent = `${files.length} 张已选择`;
  $('#uploadPhotosBtn').disabled = false;
  checkCanCreateDraft();
});

$('#uploadPhotosBtn').addEventListener('click', async () => {
  const input = $('#productPhotoInput');
  const files = input.files;
  if (!files || !files.length) { showToast('请先选择照片', 'warning'); return; }
  const btn = $('#uploadPhotosBtn');
  btn.disabled = true; btn.textContent = '上传中...';
  try {
    const formData = new FormData();
    for (const f of files) formData.append('files', f);
    const res = await fetch(API + '/product-ad/upload-photos', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '上传失败');
    uploadedPhotoIds = data.photo_ids;
    showToast(`上传成功 ${data.count} 张图片`, 'success');
    checkCanCreateDraft();
  } catch (e) { showToast('上传失败: ' + e.message, 'error'); }
  btn.disabled = false; btn.textContent = '上传照片';
});

$('#selectVideoBtn').addEventListener('click', () => $('#productVideoInput').click());
$('#productVideoInput').addEventListener('change', (e) => {
  const files = e.target.files;
  if (!files || !files.length) return;
  $('#videoName').textContent = files[0].name;
  $('#uploadVideoBtn').disabled = false;
});

$('#uploadVideoBtn').addEventListener('click', async () => {
  const input = $('#productVideoInput');
  const file = input.files[0];
  if (!file) { showToast('请先选择视频', 'warning'); return; }
  const btn = $('#uploadVideoBtn');
  btn.disabled = true; btn.textContent = '抽帧中...';
  try {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(API + '/product-ad/upload-video', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '抽帧失败');
    uploadedPhotoIds = [...uploadedPhotoIds, ...data.photo_ids];
    for (const pid of data.photo_ids) {
      const img = document.createElement('img');
      img.src = '/uploads/product_photos/' + pid;
      img.className = 'photo-thumb';
      img.title = `帧: ${pid}`;
      $('#photoPreview').appendChild(img);
    }
    showToast(`视频「${data.source_video}」抽帧完成，获得 ${data.count} 张参考图`, 'success');
    checkCanCreateDraft();
  } catch (e) { showToast('视频处理失败: ' + e.message, 'error'); }
  btn.disabled = false; btn.textContent = '上传并抽帧';
});

function checkCanCreateDraft() {
  const hasName = $('#prodName').value.trim().length > 0;
  $('#createDraftBtn').disabled = !hasName;
}

$('#prodName').addEventListener('input', checkCanCreateDraft);

// ---- 开始制作（创建草稿 + 进入 Step 2） ----
$('#createDraftBtn').addEventListener('click', async () => {
  const name = $('#prodName').value.trim();
  if (!name) { showToast('请填写商品名称', 'warning'); return; }
  const hasPhotos = uploadedPhotoIds.length > 0;

  const btn = $('#createDraftBtn');
  btn.disabled = true; btn.textContent = '创建中...';
  try {
    // 如果是继续已有草稿（currentAdId 已存在）
    if (currentAdId) {
      if (hasPhotos) {
        showToast('继续合成检测...', 'success');
        goToStep(STEPS.COMPOSITE);
        runCompositePreview();
      } else {
        showToast('直接生成剧本...', 'success');
        goToStep(STEPS.SCRIPT);
        runScriptGeneration();
      }
      btn.disabled = false; btn.textContent = '开始制作 →';
      return;
    }
    const res = await api(API + '/product-ad/create-draft', {
      method: 'POST',
      body: JSON.stringify({
        name,
        category: $('#prodCategory').value.trim(),
        description: $('#prodDesc').value.trim(),
        selling_points: $('#prodSellingPoints').value.trim(),
        target_audience: $('#prodAudience').value.trim(),
        style_preference: $('#prodStylePreference').value,
        photo_ids: uploadedPhotoIds,
        visual_style: $('#prodVisualStyle').value,
        showcase_style: $('#prodShowcaseStyle').value,
      })
    });
    currentAdId = res.ad_id;
    if (hasPhotos) {
      showToast('草稿已创建，开始合成检测...', 'success');
      goToStep(STEPS.COMPOSITE);
      runCompositePreview();
    } else {
      showToast('草稿已创建，开始生成剧本...', 'success');
      goToStep(STEPS.SCRIPT);
      runScriptGeneration();
    }
  } catch (e) { showToast('创建失败: ' + e.message, 'error'); }
  btn.disabled = false; btn.textContent = '开始制作 →';
});

// ---- Step 2: 商标合成预览 ----
async function runCompositePreview() {
  if (!currentAdId) { showToast('请先创建草稿', 'warning'); return; }
  showCompositeLoading(true);

  try {
    const res = await api(API + '/product-ad/' + currentAdId + '/preview-composite', { method: 'POST' });
    showCompositeLoading(false);
    renderCompositePreview(res);
  } catch (e) {
    showCompositeLoading(false);
    showToast('合成预览失败: ' + e.message, 'error');
    // 出错时允许跳过合成
    $('#compositeActions').style.display = 'flex';
    $('#confirmCompositeBtn').textContent = '跳过合成 →';
    $('#confirmCompositeBtn').onclick = () => goToStep(STEPS.SCRIPT);
  }
}

function showCompositeLoading(show) {
  $('#compositeLoading').style.display = show ? 'block' : 'none';
  $('#compositePreviewArea').style.display = show ? 'none' : 'flex';
  $('#compositeActions').style.display = show ? 'none' : 'flex';
  $('#noCompositeMsg').style.display = 'none';
  $('#noCompositeBadge').style.display = 'none';
}

function renderCompositePreview(data) {
  const area = $('#compositePreviewArea');
  const items = data.items || [];

  const proceedToScript = async () => {
    // 先确认合成（无需合成也要标记确认），再跳到剧本生成
    try {
      await api(API + '/product-ad/' + currentAdId + '/confirm-composite', {
        method: 'POST',
        body: JSON.stringify({ ad_id: currentAdId, photo_ids: uploadedPhotoIds })
      });
    } catch {}
    goToStep(STEPS.SCRIPT);
    runScriptGeneration();
  };

  if (items.length === 0) {
    $('#noCompositeMsg').style.display = 'block';
    $('#compositeActions').style.display = 'none';
    setTimeout(proceedToScript, 1500);
    return;
  }

  // 检查是否有实际合成（是否有 logo_visible=true 的项）
  const hasComposite = items.some(i => i.logo_visible);
  if (!hasComposite) {
    $('#noCompositeBadge').style.display = 'inline-block';
    $('#noCompositeMsg').style.display = 'block';
    $('#compositeActions').style.display = 'flex';
    $('#confirmCompositeBtn').textContent = '直接下一步 →';
    $('#confirmCompositeBtn').onclick = proceedToScript;
    area.innerHTML = items.map(i => `
      <div class="composite-item">
        <img src="${i.photo_url}" class="composite-thumb" alt="${i.photo_id}">
        <div class="composite-info">
          <span class="composite-type">${i.garment_type || '服装'}</span>
          ${i.position ? '<span class="tag">位置: ' + i.position + '</span>' : ''}
          <span class="composite-status">无需合成</span>
        </div>
      </div>
    `).join('');
    return;
  }

  area.innerHTML = items.map(i => `
    <div class="composite-item ${i.confirmed ? 'confirmed' : ''}">
      <img src="${i.photo_url}" class="composite-thumb" alt="${i.photo_id}">
      <div class="composite-info">
        <span class="composite-type">${i.garment_type || '服装'}</span>
        <span class="tag">位置: ${i.position || '左胸前'}</span>
        <span class="composite-status status-${i.logo_visible ? 'ok' : 'na'}">
          ${i.logo_visible ? '✓ 已合成' : ''}
        </span>
      </div>
    </div>
  `).join('');

  $('#compositeActions').style.display = 'flex';
  $('#confirmCompositeBtn').textContent = '确认合成 ✓';
  $('#confirmCompositeBtn').onclick = confirmComposite;
}

async function confirmComposite() {
  if (!currentAdId) return;
  const items = $('#compositePreviewArea').querySelectorAll('.composite-item');
  const photoIds = Array.from(items).map(item => {
    const img = item.querySelector('img');
    return img ? img.alt : '';
  }).filter(Boolean);

  // 同时也包含原始服装照片（无商标的衣服照也要给Seedance参考）
  const allIds = [...new Set([...photoIds, ...uploadedPhotoIds])];

  try {
    await api(API + '/product-ad/' + currentAdId + '/confirm-composite', {
      method: 'POST',
      body: JSON.stringify({ ad_id: currentAdId, photo_ids: allIds })
    });
    showToast('合成已确认', 'success');
    goToStep(STEPS.SCRIPT);
    runScriptGeneration();
  } catch (e) { showToast('确认失败: ' + e.message, 'error'); }
}

// ---- 合成重试弹窗 ----
$('#retryCompositeBtn').addEventListener('click', () => {
  // 动态生成位置选择
  const items = $('#compositePreviewArea').querySelectorAll('.composite-item');
  let html = '<p style="margin-bottom:12px;">为每件服装选择新的落标位置：</p>';
  const positions = ['左胸前', '右胸前', '领口', '左袖口', '右袖口', '背部中央', '下摆', '后领口'];

  items.forEach((item, idx) => {
    const img = item.querySelector('img');
    const photoId = img ? img.alt : '';
    const typeEl = item.querySelector('.composite-type');
    const type = typeEl ? typeEl.textContent : '服装 ' + (idx + 1);
    html += `<div style="margin-bottom:12px;display:flex;align-items:center;gap:12px;">
      <span style="min-width:80px;font-size:0.85rem;">${escHtml(type)}</span>
      <select id="retryPos_${photoId}" style="padding:6px 10px;border-radius:8px;border:1px solid var(--border-default);background:rgba(0,0,0,0.3);color:var(--text-primary);">
        ${positions.map(p => `<option value="${p}">${p}</option>`).join('')}
      </select>
    </div>`;
  });
  $('#retryCompositeModalBody').innerHTML = html;
  $('#retryCompositeModal').classList.add('active');
});

$('#doRetryCompositeBtn').addEventListener('click', async () => {
  if (!currentAdId) return;
  const selects = $('#retryCompositeModalBody').querySelectorAll('select');
  const positions = {};
  selects.forEach(sel => {
    const photoId = sel.id.replace('retryPos_', '');
    positions[photoId] = sel.value;
  });

  $('#retryCompositeModal').classList.remove('active');
  showCompositeLoading(true);

  try {
    const res = await api(API + '/product-ad/' + currentAdId + '/retry-composite', {
      method: 'POST',
      body: JSON.stringify({ ad_id: currentAdId, positions })
    });
    showCompositeLoading(false);
    renderCompositePreview(res);
    showToast('重新合成完成', 'success');
  } catch (e) {
    showCompositeLoading(false);
    showToast('重新合成失败: ' + e.message, 'error');
  }
});

// ---- Step 3: 剧本生成 + 预览 ----
async function runScriptGeneration() {
  if (!currentAdId) return;

  $('#scriptPlaceholder').style.display = 'none';
  $('#scriptLoading').style.display = 'block';
  $('#scriptPreviewArea').style.display = 'none';
  $('#scriptActions').style.display = 'none';
  $('#scriptStatusBadge').textContent = '生成中...';

  try {
    // 获取已有草稿的信息
    const draft = await api(API + '/product-ad/' + currentAdId);
    const info = JSON.parse(draft.product_info || '{}');

    const res = await api(API + '/product-ad/generate-script', {
      method: 'POST',
      body: JSON.stringify({
        name: info.name || '',
        category: info.category || '',
        description: info.description || '',
        selling_points: info.selling_points || '',
        target_audience: info.target_audience || '',
        style_preference: info.style_preference || $('#prodStylePreference').value || '',
        photo_ids: uploadedPhotoIds,
        visual_style: info.visual_style || 'realistic',
        showcase_style: info.showcase_style || 'story',
        ad_id: currentAdId,  // 复用已有草稿
      })
    });
    renderScriptPreview(res);
    _lastFetchedAd = res;
  } catch (e) {
    $('#scriptLoading').style.display = 'none';
    showToast('剧本生成失败: ' + e.message, 'error');
  }
}

function renderScriptPreview(data) {
  $('#scriptLoading').style.display = 'none';
  $('#scriptPreviewArea').style.display = 'block';
  $('#scriptActions').style.display = 'flex';

  let scriptData;
  try {
    scriptData = typeof data.script_content === 'string' ? JSON.parse(data.script_content) : data.script_content;
  } catch { scriptData = {}; }

  const scenes = scriptData.scenes || scriptData.script || [];
  const score = data.review_score !== null && data.review_score !== undefined ? data.review_score : (scriptData.review_score || '—');
  const showcaseLabel = scriptData.showcase_style === 'visual' ? '视觉展示' : '剧情带货';

  // Meta info
  $('#scriptMeta').innerHTML = `
    <div class="script-meta-row">
      <span><strong>${escHtml(data.title || scriptData.title || '')}</strong></span>
      <span class="tag">${showcaseLabel}</span>
      ${score !== '—' ? `<span class="tag review-score">评分: ${score}/10</span>` : ''}
      <span style="color:var(--text-tertiary);font-size:0.82rem;">${scenes.length} 个场景</span>
    </div>
    ${scriptData.setting ? '<div style="margin-top:8px;font-size:0.85rem;color:var(--text-secondary);"><strong>场景设定：</strong>' + escHtml(scriptData.setting) + '</div>' : ''}
    ${scriptData.cta ? '<div style="margin-top:4px;font-size:0.85rem;color:var(--gold-light);"><strong>CTA：</strong>' + escHtml(scriptData.cta) + '</div>' : ''}
  `;

  // Review detail (dimensions, strengths, weaknesses)
  renderReviewDetail(data);

  // Reference photos
  let photosForScript = uploadedPhotoIds && uploadedPhotoIds.length ? uploadedPhotoIds : [];
  if (!photosForScript.length && data.photo_ids) {
    try { photosForScript = typeof data.photo_ids === 'string' ? JSON.parse(data.photo_ids) : data.photo_ids; } catch {}
  }
  if (photosForScript.length) {
    $('#scriptRefPhotos').innerHTML = '<h4 style="margin:16px 0 8px;font-size:0.9rem;">📷 参考商品照片</h4>' +
      '<div class="ref-photos-grid">' +
      photosForScript.map(pid => `<img src="/uploads/product_photos/${escHtml(pid)}" class="ref-photo-thumb" alt="${escHtml(pid)}" loading="lazy">`).join('') +
      '</div>';
    $('#scriptRefPhotos').style.display = 'block';
  } else {
    $('#scriptRefPhotos').style.display = 'none';
  }

  // Scenes
  if (scenes.length) {
    $('#scriptScenesList').innerHTML = '<h4 style="margin:16px 0 10px;font-size:0.9rem;">场景列表</h4>' +
      scenes.map(s => `
        <div class="scene-card">
          <div class="scene-header">
            <span class="scene-num">场景 ${s.scene || '?'}</span>
            <span class="scene-duration">${s.duration_seconds || '—'}s</span>
            ${s.shot_type ? '<span class="tag">' + escHtml(s.shot_type) + '</span>' : ''}
          </div>
          ${s.camera_angle ? '<div class="scene-detail"><span class="scene-label">镜头</span>' + escHtml(s.camera_angle) + '</div>' : ''}
          ${s.action ? '<div class="scene-detail"><span class="scene-label">动作</span>' + escHtml(s.action) + '</div>' : ''}
          ${s.product_focus ? '<div class="scene-detail"><span class="scene-label">展示</span>' + escHtml(s.product_focus) + '</div>' : ''}
          ${s.narration ? '<div class="scene-detail"><span class="scene-label">旁白</span>' + escHtml(s.narration) + '</div>' : ''}
          ${s.dialogues && s.dialogues.length ? '<div class="scene-detail"><span class="scene-label">对白</span>' + s.dialogues.map(d => escHtml(d.character) + '：' + escHtml(d.line)).join('<br>') + '</div>' : ''}
        </div>
      `).join('');
  }

  // Raw JSON
  $('#scriptRawContent').textContent = JSON.stringify(scriptData, null, 2);

  $('#scriptStatusBadge').textContent = '已生成 ✓';
  showToast('带货剧本已生成', 'success');
}

function renderReviewDetail(data) {
  const el = $('#scriptReviewDetail');
  let review;
  try {
    review = typeof data.review_detail === 'string' ? JSON.parse(data.review_detail) : data.review_detail;
  } catch { review = null; }
  if (!review || !review.dimensions) { el.style.display = 'none'; return; }

  const dims = review.dimensions;
  const dimNames = {
    story_completeness: '故事完整性', character_depth: '角色深度', scene_logic: '场景逻辑',
    visual_feasibility: '视觉可行性', dialogue_quality: '对白质量', pacing: '节奏把控',
    hook_strength: '开场钩子', info_density: '信息密度', product_persuasion: '产品说服力',
    visual_diversity: '视觉多样性', scene_flow: '场景衔接', ai_executability: 'AI可执行性'
  };

  function scoreClass(s) { return s >= 8 ? 'high' : s >= 6 ? 'mid' : 'low'; }

  const dimsHtml = Object.entries(dims).map(([k, v]) => {
    const name = dimNames[k] || k;
    const s = v.score || 0;
    const pct = Math.round((s / 10) * 100);
    return `
      <div class="dim-item">
        <div class="dim-header">
          <span class="dim-name">${name}</span>
          <span class="dim-score ${scoreClass(s)}">${s}</span>
        </div>
        <div class="dim-bar-track"><div class="dim-bar-fill ${scoreClass(s)}" style="width:${pct}%"></div></div>
      </div>`;
  }).join('');

  const strengthsHtml = review.strengths && review.strengths.length
    ? `<div class="review-strengths"><h5>✓ 优点</h5><ul>${review.strengths.map(t => '<li>' + escHtml(t) + '</li>').join('')}</ul></div>` : '';
  const weaknessesHtml = review.weaknesses && review.weaknesses.length
    ? `<div class="review-weaknesses"><h5>△ 待改进</h5><ul>${review.weaknesses.map(t => '<li>' + escHtml(t) + '</li>').join('')}</ul></div>` : '';

  el.innerHTML = `
    <div class="review-header" onclick="toggleReviewDetail()">
      <span class="toggle-icon" id="reviewToggleIcon">▼</span>
      <span class="review-summary">${escHtml(review.summary || '')}</span>
      <span class="tag review-score">${review.overall_score != null ? review.overall_score + '/10' : ''}</span>
    </div>
    <div class="review-body" id="reviewBody">
      <div class="dimensions-grid">${dimsHtml}</div>
      ${strengthsHtml}
      ${weaknessesHtml}
    </div>`;
  el.style.display = 'block';
}

function toggleReviewDetail() {
  const body = document.getElementById('reviewBody');
  const icon = document.getElementById('reviewToggleIcon');
  if (!body || !icon) return;
  const collapsed = body.classList.toggle('collapsed');
  icon.textContent = collapsed ? '▶' : '▼';
}

// Raw JSON toggle
function toggleRawScript() {
  const content = $('#scriptRawContent');
  const icon = $('#rawToggleIcon');
  const isHidden = content.style.display === 'none' || !content.style.display;
  content.style.display = isHidden ? 'block' : 'none';
  icon.textContent = isHidden ? '▼' : '▶';
}

// Confirm script
$('#confirmScriptBtn').addEventListener('click', async () => {
  if (!currentAdId) return;
  try {
    await api(API + '/product-ad/' + currentAdId + '/confirm-script', { method: 'POST' });
    showToast('剧本已确认', 'success');
    goToStep(STEPS.VIDEO);
    $('#generateVideoBtn').disabled = false;
  } catch (e) { showToast('确认失败: ' + e.message, 'error'); }
});

// ---- Step 3 retry modal ----
function showRetryScriptModal() {
  $('#retryScriptModal').classList.add('active');
}

$('#doRetryScriptBtn').addEventListener('click', async () => {
  if (!currentAdId) return;
  const feedback = $('#scriptFeedbackInput').value.trim();
  $('#retryScriptModal').classList.remove('active');

  $('#scriptPlaceholder').style.display = 'none';
  $('#scriptLoading').style.display = 'block';
  $('#scriptPreviewArea').style.display = 'none';
  $('#scriptActions').style.display = 'none';

  try {
    const res = await api(API + '/product-ad/' + currentAdId + '/retry-script', {
      method: 'POST',
      body: JSON.stringify({ ad_id: currentAdId, feedback })
    });
    renderScriptPreview(res);
    _lastFetchedAd = res;
    showToast('剧本已重新生成', 'success');
  } catch (e) {
    $('#scriptLoading').style.display = 'none';
    showToast('重新生成失败: ' + e.message, 'error');
  }
});

// ---- Step 4: 视频生成 ----
$('#generateVideoBtn').addEventListener('click', async () => {
  if (!currentAdId) return;
  const btn = $('#generateVideoBtn');
  btn.disabled = true;

  $('#videoGenPlaceholder').style.display = 'none';
  $('#videoGenLoading').style.display = 'block';
  $('#videoGenResult').style.display = 'none';
  $('#videoGenStatus').textContent = '排队等待中...';

  try {
    const res = await api(API + '/product-ad/' + currentAdId + '/generate-video', { method: 'POST' });
    showToast(res.message, 'info');

    // 轮询直到完成
    let waited = 0;
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      waited += 5;
      $('#videoGenStatus').textContent = `AI 正在生成视频... ${waited}s`;
      try {
        const ad = await api(API + '/product-ad/' + currentAdId);
        _lastFetchedAd = ad;
        if (ad.status === 'video_done') {
          clearInterval(pollTimer);
          $('#videoGenLoading').style.display = 'none';
          $('#videoGenResult').style.display = 'block';
          const videoSrc = ad.video_path
            ? window.location.origin + '/' + ad.video_path.replace(/^.*\/backend\//, '')
            : '';
          if (videoSrc) {
            $('#generatedVideoSrc').src = videoSrc;
            $('#generatedVideo').load();
          }
          showToast('视频生成完成！', 'success');
        } else if (ad.status === 'video_failed') {
          clearInterval(pollTimer);
          $('#videoGenLoading').style.display = 'none';
          showToast('视频生成失败: ' + (ad.error_message || '未知错误'), 'error');
          btn.disabled = false;
        }
      } catch {}
    }, 5000);

    // 超时保护
    setTimeout(() => {
      if (pollTimer) {
        clearInterval(pollTimer);
        $('#videoGenLoading').style.display = 'none';
        showToast('视频生成超时，请稍后刷新查看', 'warning');
        btn.disabled = false;
      }
    }, 600000);

  } catch (e) {
    $('#videoGenLoading').style.display = 'none';
    showToast('触发失败: ' + e.message, 'error');
    btn.disabled = false;
  }
});

async function retryVideo() {
  if (!currentAdId) return;
  $('#videoGenResult').style.display = 'none';
  $('#generateVideoBtn').disabled = false;
  $('#generateVideoBtn').click();
}

// ---- 剧本/视频生成（旧版保留，用于剧本列表） ----
async function generateWithReview(id, type) {
  const label = type === 'product' ? '带货剧本' : '剧本';
  if (!confirm(`自动评审 → 修改达标 → 生成视频？\n\n系统将自动评审该${label}，不足8分会自动修改直到达标，然后生成视频。`)) return;
  const btn = event.target;
  const origText = btn.textContent;
  btn.disabled = true; btn.textContent = '评审修改中...';
  const endpoint = type === 'product'
    ? API + '/product-ad/' + id + '/generate-video'
    : API + '/scripts/' + id + '/generate-video';
  try {
    const res = await api(endpoint, { method: 'POST' });
    showToast(res.message, 'info');
    let waited = 0;
    const pollInterval = setInterval(async () => {
      waited += 5;
      btn.textContent = `处理中 ${waited}s...`;
      try {
        const list = await api(API + (type === 'product' ? '/product-ad/list?limit=10' : '/scripts?limit=10'));
        const item = list.find(x => x.id === id);
        if (item && (item.status === 'video_done' || item.status === 'video_failed' || item.status === 'draft')) {
          clearInterval(pollInterval);
          btn.textContent = '生成视频';
          btn.disabled = false;
          loadCurrentTab();
          if (item.status === 'video_done') showToast(`✅ ${label}视频生成完成！`, 'success');
          else if (item.status === 'video_failed') showToast(`❌ 视频生成失败`, 'error');
        }
      } catch {}
    }, 5000);
  } catch (e) {
    showToast('触发失败: ' + e.message, 'error');
    btn.disabled = false; btn.textContent = origText;
  }
}

// ---- HTML 转义 ----
function escHtml(s) {
  if (typeof s !== 'string') return s;
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ---- 初始化 ----
loadStats();
loadScripts();
