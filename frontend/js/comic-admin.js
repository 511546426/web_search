/* 漫剧管理面板 — 交互逻辑 */
const API = '/api/comic';

// ---- 工具函数 ----
function $ (sel, ctx) { return (ctx || document).querySelector(sel); }
function $$ (sel, ctx) { return (ctx || document).querySelectorAll(sel); }
function fmtDate (d) { return new Date(d).toLocaleString('zh-CN'); }
function statusLabel (s) {
  const map = { draft: '草稿', generating_video: '生成视频中', video_done: '视频完成', video_failed: '视频失败', published: '已发布', pending: '排队中', generating: '生成中', completed: '已完成', failed: '失败' };
  return map[s] || s;
}

async function api (url, opts = {}) {
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

// ---- 操作按钮 ----
$('#triggerBtn').addEventListener('click', async () => {
  const topic = $('#topicInput').value.trim();
  const btn = $('#triggerBtn');
  btn.disabled = true; btn.textContent = '触发中...';
  try {
    const res = await api(API + '/trigger', { method: 'POST', body: JSON.stringify({ topic: topic || null, auto_generate_video: true }) });
    alert(res.message);
    loadStats();
  } catch (e) {
    alert('触发生成失败: ' + e.message);
  }
  btn.disabled = false; btn.textContent = '手动触发生成';
});

$('#triggerBatchBtn').addEventListener('click', async () => {
  if (!confirm('确定批量生成 3 个视频？每次约消耗 45 元。')) return;
  const btn = $('#triggerBatchBtn');
  btn.disabled = true; btn.textContent = '生成中...';
  try {
    const res = await api(API + '/trigger-batch', { method: 'POST', body: JSON.stringify({ limit: 3 }) });
    alert(res.message);
    loadStats();
  } catch (e) {
    alert('批量生成失败: ' + e.message);
  }
  btn.disabled = false; btn.textContent = '批量生成 (3个)';
});

$('#fromTextBtn').addEventListener('click', async () => {
  const text = $('#scriptTextInput').value.trim();
  if (!text) { alert('请先输入剧本文字'); return; }
  const visualStyle = $('#visualStyleSelect').value;
  const btn = $('#fromTextBtn');
  btn.disabled = true; btn.textContent = '解析中...';
  try {
    const res = await api(API + '/scripts/from-text', {
      method: 'POST',
      body: JSON.stringify({ text, visual_style: visualStyle })
    });
    let msg = `剧本「${res.title}」已生成 (ID: ${res.id})`;
    if (res.review_score !== null && res.review_score !== undefined) {
      msg += `\n综合评分: ${res.review_score}/10`;
      if (res.review_ready) msg += ' ✅ 建议生成视频';
      else msg += ' ⚠️ 建议修改';
    }
    alert(msg);
    $('#scriptTextInput').value = '';
    loadScripts();
    loadStats();
  } catch (e) {
    alert('解析失败: ' + e.message);
  }
  btn.disabled = false; btn.textContent = '生成剧本';
});

$('#refreshBtn').addEventListener('click', loadCurrentTab);
$('#scrapeTrendingBtn').addEventListener('click', loadTrending);

// ---- Modal ----
$('#modalClose').addEventListener('click', () => $('#detailModal').classList.remove('active'));
$('#adModalClose').addEventListener('click', () => $('#adDetailModal').classList.remove('active'));
$('#novelModalClose').addEventListener('click', () => $('#novelModal').classList.remove('active'));

// ---- 数据加载 ----
async function loadStats () {
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

function loadCurrentTab () {
  if (currentTab === 'scripts') loadScripts();
  else if (currentTab === 'videos') loadVideos();
  else if (currentTab === 'novels') loadNovels();
  else if (currentTab === 'product') { loadProductAds(); }
  else if (currentTab === 'publish') loadPublishLogs();
}

async function loadScripts () {
  try {
    const scripts = await api(API + '/scripts?limit=50');
    const el = $('#scriptList');
    if (!scripts.length) {
      el.innerHTML = '<div class="empty-state"><p>暂无剧本</p><p>点击上方按钮触发生成</p></div>';
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
          <button class="btn btn-sm" style="background:transparent;border:1px solid var(--danger);color:var(--danger);padding:6px 8px;" onclick="deleteScript(${s.id})" title="删除">✕</button>
        </div>
      </div>
    `).join('');
  } catch (e) { $('#scriptList').innerHTML = '<div class="empty-state"><p>加载失败: ' + escHtml(e.message) + '</p></div>'; }
}

async function loadVideos () {
  try {
    const videos = await api(API + '/videos?limit=50');
    const el = $('#videoList');
    if (!videos.length) {
      el.innerHTML = '<div class="empty-state"><p>暂无视频</p><p>先生成剧本后会自动生成视频</p></div>';
      return;
    }
    el.innerHTML = videos.map(v => `
      <div class="card">
        <div class="card-status ${v.status}"></div>
        <div class="card-body">
          <div class="card-title">视频 #${v.id} (剧本 #${v.script_id})</div>
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
          <button class="btn btn-sm" style="background:transparent;border:1px solid var(--danger);color:var(--danger);padding:6px 8px;" onclick="deleteVideo(${v.id})" title="删除">✕</button>
        </div>
      </div>
    `).join('');
  } catch (e) { $('#videoList').innerHTML = '<div class="empty-state"><p>加载失败: ' + escHtml(e.message) + '</p></div>'; }
}

async function loadPublishLogs () {
  try {
    const logs = await api(API + '/publish-logs?limit=50');
    const el = $('#publishList');
    if (!logs.length) {
      el.innerHTML = '<div class="empty-state"><p>暂无发布记录</p><p>视频生成后在视频队列中点击发布</p></div>';
      return;
    }
    el.innerHTML = logs.map(l => `
      <div class="card">
        <div class="card-status ${l.status}"></div>
        <div class="card-body">
          <div class="card-title">视频 #${l.video_id} → ${escHtml(l.platform)}</div>
          <div class="card-meta">
            <span>${statusLabel(l.status)}</span>
            ${l.publish_url ? '<span><a href="' + escHtml(l.publish_url) + '" target="_blank">查看</a></span>' : ''}
            <span>${l.published_at ? fmtDate(l.published_at) : fmtDate(l.created_at)}</span>
          </div>
        </div>
      </div>
    `).join('');
  } catch (e) { $('#publishList').innerHTML = '<div class="empty-state"><p>加载失败: ' + escHtml(e.message) + '</p></div>'; }
}

async function loadTrending () {
  try {
    const res = await fetch('/api/comic/trending?limit=15');
    const topics = await res.json();
    const el = $('#trendingList');
    if (!topics.length) {
      el.innerHTML = '<div class="empty-state"><p>暂无热点数据</p></div>';
    } else {
      el.innerHTML = topics.map((t, i) => `
        <div class="card">
          <div class="card-body">
            <div class="card-title">#${t.rank || i + 1} ${escHtml(t.title)}</div>
            <div class="card-meta">
              <span class="tag">${escHtml(t.platform)}</span>
              ${t.hot_score ? '<span>热度: ' + t.hot_score + '</span>' : ''}
            </div>
          </div>
          <div class="card-actions">
            <button class="btn btn-primary btn-sm" onclick="useTopic('${escHtml(t.title).replace(/'/g, "\\'")}')">用此题材</button>
          </div>
        </div>
      `).join('');
    }
    $('#trendingPanel').classList.add('active');
  } catch (e) {
    alert('获取热点失败: ' + e.message);
  }
}

// ---- 操作函数 ----
function useTopic (title) {
  $('#topicInput').value = title;
  $$('.tab')[0].click();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function viewScript (id) {
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
  } catch (e) { alert('加载剧本详情失败: ' + e.message); }
}

function renderCharacters (chars) {
  return '<h3>角色</h3><ul>' + chars.map(c =>
    '<li><strong>' + escHtml(c.name) + '</strong> (' + escHtml(c.role) + '): ' + escHtml(c.description) + '</li>'
  ).join('') + '</ul>';
}

async function regenerateVideo (id) {
  if (!confirm('确定重新生成该剧本的视频？')) return;
  try {
    const res = await api(API + '/scripts/' + id + '/regenerate-video', { method: 'POST' });
    alert(res.message);
    loadCurrentTab();
  } catch (e) { alert('重新生成失败: ' + e.message); }
}

async function generateWithReview (id, type) {
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
    alert(res.message);
    // 轮询等待完成
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
          if (item.status === 'video_done') alert(`✅ ${label}视频生成完成！`);
          else if (item.status === 'video_failed') alert(`❌ 视频生成失败，请查看详情`);
        }
      } catch {}
    }, 5000);
  } catch (e) {
    alert('触发失败: ' + e.message);
    btn.disabled = false; btn.textContent = origText;
  }
}

async function publishVideo (id) {
  const platform = prompt('发布平台 (bilibili / weibo / douyin / wechat):', 'bilibili');
  if (!platform) return;
  try {
    const res = await api(API + '/videos/' + id + '/publish', {
      method: 'POST',
      body: JSON.stringify({ platform, message: '审核通过，发布' })
    });
    if (res.draft) {
      alert(res.message + '\n\n草稿已保存到B站创作中心，请手动发布。');
    } else {
      alert(res.message);
      if (res.publish_url) alert('发布链接: ' + res.publish_url);
    }
    loadStats();
    loadCurrentTab();
  } catch (e) { alert('发布失败: ' + e.message); }
}

async function bilibiliLogin () {
  try {
    const res = await api(API + '/bilibili/login', { method: 'POST' });
    if (res.qr_image_url) {
      const url = window.location.origin + res.qr_image_url;
      window.open(url, '_blank');
      // 轮询等待扫码完成
      const check = setInterval(async () => {
        try {
          const st = await api(API + '/bilibili/login/check', { method: 'GET' });
          if (st.status === 'done') {
            clearInterval(check);
            alert('B站登录成功！');
            loadCurrentTab();
          } else if (st.status === 'timeout') {
            clearInterval(check);
            alert('二维码已过期，请重新生成');
          }
        } catch (_) {}
      }, 3000);
      setTimeout(() => clearInterval(check), 300000);
    } else {
      alert('生成二维码失败');
    }
  } catch (e) { alert('B站登录失败: ' + e.message); }
}

function previewVideo (path) {
  const videoUrl = window.location.origin + '/' + path.replace(/^.*\/backend\//, '');
  window.open(videoUrl, '_blank');
}

// ---- 删除 ----
async function deleteScript (id) {
  if (!confirm('确定删除剧本 #' + id + '？（关联视频也将删除）')) return;
  try {
    await api(API + '/scripts/' + id, { method: 'DELETE' });
    loadScripts(); loadStats();
  } catch (e) { alert('删除失败: ' + e.message); }
}

async function deleteVideo (id) {
  if (!confirm('确定删除视频 #' + id + '？')) return;
  try {
    await api(API + '/videos/' + id, { method: 'DELETE' });
    loadVideos(); loadStats();
  } catch (e) { alert('删除失败: ' + e.message); }
}

async function deleteProductAd (id) {
  if (!confirm('确定删除带货剧本 #' + id + '？')) return;
  try {
    await api(API + '/product-ad/' + id, { method: 'DELETE' });
    loadProductAds(); loadStats();
  } catch (e) { alert('删除失败: ' + e.message); }
}
// ---- 商品带货 ----

// 选择照片
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
});

// 上传照片
$('#uploadPhotosBtn').addEventListener('click', async () => {
  const input = $('#productPhotoInput');
  const files = input.files;
  if (!files || !files.length) { alert('请先选择照片'); return; }
  const btn = $('#uploadPhotosBtn');
  btn.disabled = true; btn.textContent = '上传中...';
  try {
    const formData = new FormData();
    for (const f of files) formData.append('files', f);
    const res = await fetch(API + '/product-ad/upload-photos', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '上传失败');
    uploadedPhotoIds = data.photo_ids;
    alert(`上传成功 ${data.count} 张图片`);
    // 照片上传后可立即生成剧本，但名称已填写时也可生成
    if ($('#prodName').value.trim()) {
      $('#generateAdScriptBtn').disabled = false;
    }
  } catch (e) {
    alert('上传失败: ' + e.message);
  }
  btn.disabled = false; btn.textContent = '上传';
});

// 选择视频
$('#selectVideoBtn').addEventListener('click', () => $('#productVideoInput').click());
$('#productVideoInput').addEventListener('change', (e) => {
  const files = e.target.files;
  if (!files || !files.length) return;
  $('#videoName').textContent = files[0].name;
  $('#uploadVideoBtn').disabled = false;
});

// 上传视频并抽帧
$('#uploadVideoBtn').addEventListener('click', async () => {
  const input = $('#productVideoInput');
  const file = input.files[0];
  if (!file) { alert('请先选择视频'); return; }
  const btn = $('#uploadVideoBtn');
  btn.disabled = true; btn.textContent = '抽帧中...';
  try {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(API + '/product-ad/upload-video', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '抽帧失败');
    // 合并到已上传的图片列表中
    uploadedPhotoIds = [...uploadedPhotoIds, ...data.photo_ids];
    // 展示抽帧结果缩略图
    const preview = $('#photoPreview');
    for (const pid of data.photo_ids) {
      const img = document.createElement('img');
      img.src = '/uploads/product_photos/' + pid;
      img.className = 'photo-thumb';
      img.title = `视频帧: ${pid}`;
      preview.appendChild(img);
    }
    alert(`视频「${data.source_video}」抽帧完成，获得 ${data.count} 张参考图`);
    if ($('#prodName').value.trim()) {
      $('#generateAdScriptBtn').disabled = false;
    }
  } catch (e) {
    alert('视频处理失败: ' + e.message);
  }
  btn.disabled = false; btn.textContent = '上传并抽帧';
});

// 商品名称输入后自动启用生成按钮
$('#prodName').addEventListener('input', () => {
  if ($('#prodName').value.trim()) {
    $('#generateAdScriptBtn').disabled = false;
  } else {
    $('#generateAdScriptBtn').disabled = true;
  }
});

// 生成带货剧本
$('#generateAdScriptBtn').addEventListener('click', async () => {
  const name = $('#prodName').value.trim();
  if (!name) { alert('请填写商品名称'); return; }
  const btn = $('#generateAdScriptBtn');
  btn.disabled = true; btn.textContent = '生成中...';
  try {
    const res = await api(API + '/product-ad/generate-script', {
      method: 'POST',
      body: JSON.stringify({
        name,
        category: $('#prodCategory').value.trim(),
        description: $('#prodDesc').value.trim(),
        selling_points: $('#prodSellingPoints').value.trim(),
        target_audience: $('#prodAudience').value.trim(),
        visual_style: $('#prodVisualStyle').value,
        showcase_style: $('#prodShowcaseStyle').value,
        photo_ids: uploadedPhotoIds,
      })
    });
    alert(`带货剧本「${res.title}」已生成 (ID: ${res.id})`);
    loadProductAds();
  } catch (e) {
    alert('生成失败: ' + e.message);
  }
  btn.disabled = false; btn.textContent = '③ 生成带货剧本';
});

// ---- 小说 ----

$('#createNovelBtn').addEventListener('click', async () => {
  const title = $('#novelTitle').value.trim();
  const chapters = parseInt($('#novelChapters').value) || 30;
  const btn = $('#createNovelBtn');
  btn.disabled = true; btn.textContent = '创建中...';
  try {
    await api(API + '/novels', {
      method: 'POST',
      body: JSON.stringify({
        title,
        genre: $('#novelGenre').value.trim(),
        theme: $('#novelTheme').value.trim(),
        total_chapters: chapters,
      })
    });
    $('#novelTitle').value = '';
    loadNovels();
  } catch (e) {
    alert('创建失败: ' + e.message);
  }
  btn.disabled = false; btn.textContent = '创建小说';
});

async function loadNovels () {
  try {
    const novels = await api(API + '/novels?limit=50');
    const el = $('#novelList');
    if (!novels.length) {
      el.innerHTML = '<div class="empty-state"><p>暂无小说</p><p>输入标题后点击「创建小说」开始</p></div>';
      return;
    }
    el.innerHTML = novels.map(n => {
      const progress = n.total_chapters > 0 ? Math.round(n.done_chapters / n.total_chapters * 100) : 0;
      return `
      <div class="card">
        <div class="card-status ${n.status === 'completed' ? 'completed' : n.status === 'publishing' ? 'generating' : 'draft'}"></div>
        <div class="card-body">
          <div class="card-title">${escHtml(n.title)}</div>
          <div class="card-meta">
            <span>${statusLabel(n.status)}</span>
            ${n.genre ? '<span class="tag">' + escHtml(n.genre) + '</span>' : ''}
            <span>${n.done_chapters}/${n.total_chapters}章</span>
            <span style="color:var(--text-dim);font-size:0.8rem;">${progress}%</span>
            ${n.has_world ? '<span style="color:var(--success);font-size:0.8rem;">✅世界观</span>' : ''}
            ${n.has_outline ? '<span style="color:var(--success);font-size:0.8rem;">✅大纲</span>' : ''}
            <span>${fmtDate(n.created_at)}</span>
          </div>
          <div style="margin-top:6px;height:4px;background:var(--border);border-radius:2px;overflow:hidden;">
            <div style="height:100%;width:${progress}%;background:var(--primary);border-radius:2px;transition:width 0.3s;"></div>
          </div>
        </div>
        <div class="card-actions" style="flex-wrap:wrap;">
          <button class="btn btn-outline btn-sm" onclick="viewNovel(${n.id})">查看</button>
          ${!n.has_world ? `<button class="btn btn-sm" style="background:var(--primary);color:#fff;padding:6px 10px;" onclick="generateWorld(${n.id})">生成世界观</button>` : ''}
          ${n.has_world && !n.has_outline ? `<button class="btn btn-sm" style="background:var(--primary);color:#fff;padding:6px 10px;" onclick="generateOutline(${n.id})">生成大纲</button>` : ''}
          ${n.has_outline && n.done_chapters < n.total_chapters ? `<button class="btn btn-sm" style="background:var(--success);color:#fff;padding:6px 10px;" onclick="generateAllChapters(${n.id})">生成全部</button>` : ''}
          <button class="btn btn-sm" style="background:transparent;border:1px solid var(--danger);color:var(--danger);padding:6px 8px;" onclick="deleteNovel(${n.id})" title="删除">✕</button>
        </div>
      </div>`;
    }).join('');
  } catch (e) { $('#novelList').innerHTML = '<div class="empty-state"><p>加载失败: ' + escHtml(e.message) + '</p></div>'; }
}

async function generateWorld (id) {
  if (!confirm('确定生成世界观设定？将调用 AI 生成完整世界观和角色设定。')) return;
  try {
    const res = await api(API + '/novels/' + id + '/generate-world', { method: 'POST' });
    alert(res.message);
    setTimeout(loadNovels, 2000);
  } catch (e) { alert('生成失败: ' + e.message); }
}

async function generateOutline (id) {
  if (!confirm('确定生成分章大纲？将基于世界观生成完整章节目录。')) return;
  try {
    const res = await api(API + '/novels/' + id + '/generate-outline', { method: 'POST' });
    alert(res.message);
    setTimeout(loadNovels, 2000);
  } catch (e) { alert('生成失败: ' + e.message); }
}

async function generateAllChapters (id) {
  if (!confirm('确定生成全部章节？将在后台逐章生成+评审，耗时较长。')) return;
  try {
    const res = await api(API + '/novels/' + id + '/generate-all', { method: 'POST' });
    alert(res.message);
  } catch (e) { alert('触发失败: ' + e.message); }
}

async function deleteNovel (id) {
  if (!confirm('确定删除小说 #' + id + '？（所有章节也将删除）')) return;
  try {
    await api(API + '/novels/' + id, { method: 'DELETE' });
    loadNovels();
  } catch (e) { alert('删除失败: ' + e.message); }
}

async function viewNovel (id) {
  try {
    const novel = await api(API + '/novels/' + id);
    const chapters = await api(API + '/novels/' + id + '/chapters');

    let chaptersHtml = '';
    if (chapters.length) {
      chaptersHtml = '<h3>章节目录</h3><div class="chapter-list">' +
        chapters.map(c => `
          <div class="chapter-item ${c.status === 'done' ? '' : 'pending'}" onclick="viewChapter(${id}, ${c.chapter_number})">
            <span class="chapter-num">第${c.chapter_number}章</span>
            <span class="chapter-title">${escHtml(c.title || '')}</span>
            ${c.review_score ? `<span class="chapter-score">${c.review_score}/10</span>` : ''}
            <span class="chapter-status">${c.status === 'done' ? '✅' : '⏳'}</span>
            <span class="chapter-preview">${escHtml(c.preview || '')}...</span>
          </div>
        `).join('') + '</div>';
    }

    let worldHtml = '';
    if (novel.world_setting) {
      const ws = novel.world_setting;
      const world = ws.world || {};
      worldHtml = '<h3>世界观</h3><div class="novel-section">' +
        `<p><strong>${escHtml(world.name || '')}</strong></p>` +
        `<p>${escHtml(world.background || '')}</p>` +
        (world.power_system ? `<p><strong>力量体系:</strong> ${escHtml(world.power_system.name || '')}</p>` : '') +
        '</div>';
    }

    let charHtml = '';
    if (novel.character_profiles && novel.character_profiles.length) {
      charHtml = '<h3>角色设定</h3><div class="novel-section">' +
        novel.character_profiles.map(c =>
          `<div class="char-card">
            <strong>${escHtml(c.name)}</strong>
            <span class="tag">${escHtml(c.role || '')}</span>
            <p>${escHtml(c.personality || '')}</p>
          </div>`
        ).join('') + '</div>';
    }

    let genBtn = '';
    if (novel.has_outline && chapters.length < novel.total_chapters) {
      genBtn = `<button class="btn btn-primary" onclick="generateSingleChapter(${id}, ${chapters.length + 1})" style="margin-bottom:16px;">生成下一章（第${chapters.length + 1}章）</button>`;
    }

    $('#novelModalTitle').textContent = novel.title;
    $('#novelModalBody').innerHTML = `
      <div style="margin-bottom:16px;">
        ${novel.genre ? '<span class="tag">' + escHtml(novel.genre) + '</span>' : ''}
        <span>${novel.done_chapters}/${novel.total_chapters}章</span>
        <span>状态: ${statusLabel(novel.status)}</span>
      </div>
      ${genBtn}
      ${worldHtml}
      ${charHtml}
      ${chaptersHtml}
    `;
    $('#novelModal').classList.add('active');
  } catch (e) { alert('加载失败: ' + e.message); }
}

async function viewChapter (novelId, chapterNum) {
  try {
    const ch = await api(API + '/novels/' + novelId + '/chapters/' + chapterNum);
    if (!ch.content) {
      if (!confirm('本章尚未生成，是否现在生成？')) return;
      const res = await api(API + '/novels/' + novelId + '/generate-chapter/' + chapterNum, { method: 'POST' });
      alert('生成完成，评分: ' + (res.review_score || 'N/A') + '/10');
      viewNovel(novelId);
      return;
    }
    $('#novelModalTitle').textContent = `第${ch.chapter_number}章 ${ch.title || ''}`;
    $('#novelModalBody').innerHTML = `
      <div style="margin-bottom:16px;color:var(--text-dim);font-size:0.85rem;">
        ${ch.word_count > 0 ? Math.round(ch.word_count / 100) / 10 + '千字' : ''}
        ${ch.review_score ? ' | 评分: ' + ch.review_score + '/10' : ''}
      </div>
      <div class="chapter-content">${escHtml(ch.content).replace(/\n/g, '<br>')}</div>
      <div style="margin-top:20px;display:flex;gap:8px;justify-content:center;">
        ${chapterNum > 1 ? `<button class="btn btn-outline btn-sm" onclick="viewChapter(${novelId}, ${chapterNum - 1})">← 上一章</button>` : ''}
        <button class="btn btn-outline btn-sm" onclick="viewNovel(${novelId})">返回目录</button>
        <button class="btn btn-outline btn-sm" onclick="viewChapter(${novelId}, ${chapterNum + 1})">下一章 →</button>
      </div>
    `;
  } catch (e) { alert('加载失败: ' + e.message); }
}

async function generateSingleChapter (novelId, chapterNum) {
  if (!confirm(`确定生成第 ${chapterNum} 章？将自动评审并修改直到达标。`)) return;
  try {
    const res = await api(API + '/novels/' + novelId + '/generate-chapter/' + chapterNum, { method: 'POST' });
    alert(`第${chapterNum}章生成完成，评分: ${res.review_score || 'N/A'}/10`);
    viewNovel(novelId);
  } catch (e) { alert('生成失败: ' + e.message); }
}

// 加载带货剧本列表
async function loadProductAds () {
  try {
    const ads = await api(API + '/product-ad/list?limit=50');
    const el = $('#productAdList');
    if (!ads.length) {
      el.innerHTML = '<div class="empty-state"><p>暂无带货剧本</p><p>上传商品照片并填写信息后生成</p></div>';
      return;
    }
    el.innerHTML = ads.map(a => {
      const scriptContent = a.script_content ? JSON.parse(a.script_content) : {};
      const productName = scriptContent.product || a.title;
      return `
      <div class="card">
        <div class="card-status ${a.status}"></div>
        <div class="card-body">
          <div class="card-title">${escHtml(productName)}</div>
          <div class="card-meta">
            <span>${statusLabel(a.status)}</span>
            ${a.genre ? '<span class="tag">' + escHtml(a.genre) + '</span>' : ''}
            ${a.review_score !== null && a.review_score !== undefined ? '<span class="tag review-score">评分: ' + a.review_score + '/10</span>' : ''}
            <span>${fmtDate(a.created_at)}</span>
            ${a.video_path ? '<span>✅ 有视频</span>' : ''}
          </div>
        </div>
        <div class="card-actions">
          <button class="btn btn-outline btn-sm" onclick="viewProductAd(${a.id})">查看</button>
          <button class="btn btn-secondary btn-sm" onclick="generateWithReview(${a.id}, 'product')" ${a.status === 'generating_video' || a.status === 'video_done' ? 'disabled' : ''}>生成视频</button>
          <button class="btn btn-sm" style="background:transparent;border:1px solid var(--danger);color:var(--danger);padding:6px 8px;" onclick="deleteProductAd(${a.id})" title="删除">✕</button>
        </div>
      </div>`;
    }).join('');
  } catch (e) { $('#productAdList').innerHTML = '<div class="empty-state"><p>加载失败: ' + escHtml(e.message) + '</p></div>'; }
}

// 查看带货剧本详情
async function viewProductAd (id) {
  try {
    const ad = await api(API + '/product-ad/' + id);
    const content = ad.script_content ? JSON.parse(ad.script_content) : {};
    const photos = ad.photo_ids ? JSON.parse(ad.photo_ids) : [];
    const prodInfo = ad.product_info ? JSON.parse(ad.product_info) : {};
    const isVisual = content.showcase_style === 'visual';

    let photoHtml = '';
    if (photos.length) {
      photoHtml = '<h3>参考图片</h3><div style="display:flex;gap:8px;flex-wrap:wrap;">' +
        photos.map(p => `<img src="/uploads/product_photos/${p}" class="photo-thumb" style="width:100px;height:100px;">`).join('') +
        '</div>';
    }

    const scenes = content.scenes || content.script || [];
    let scenesHtml = '';
    if (isVisual) {
      scenesHtml = '<h3>分镜展示</h3>' + scenes.map(s => `
        <div style="background:rgba(0,0,0,0.2);padding:12px;border-radius:8px;margin-bottom:8px;">
          <strong>场景 ${s.scene}</strong>
          <p><strong>镜头:</strong> ${escHtml(s.camera_angle || '')}</p>
          <p><strong>动作:</strong> ${escHtml(s.action || '')}</p>
          <p><strong>产品展示:</strong> ${escHtml(s.product_focus || '')}</p>
        </div>
      `).join('');
    }

    $('#adModalTitle').textContent = ad.title;
    $('#adModalBody').innerHTML = `
      <p><strong>商品:</strong> ${escHtml(prodInfo.name || content.product || '')} | <strong>品类:</strong> ${escHtml(prodInfo.category || '')}</p>
      <p><strong>状态:</strong> ${statusLabel(ad.status)}</p>
      ${content.showcase_style ? '<p><span class="tag">' + (isVisual ? '视觉展示' : '剧情带货') + '</span></p>' : ''}
      ${prodInfo.description ? '<p><strong>描述:</strong> ' + escHtml(prodInfo.description) + '</p>' : ''}
      ${prodInfo.selling_points ? '<p><strong>卖点:</strong> ' + escHtml(prodInfo.selling_points) + '</p>' : ''}
      ${content.characters ? renderCharacters(content.characters) : ''}
      ${content.background_music ? '<p><strong>背景音乐:</strong> ' + escHtml(content.background_music) + '</p>' : ''}
      ${photoHtml}
      ${isVisual ? scenesHtml : '<h3>带货剧本</h3><pre>' + escHtml(JSON.stringify(scenes, null, 2)) + '</pre>'}
      ${content.cta ? '<p><strong>行动号召:</strong> ' + escHtml(content.cta) + '</p>' : ''}
      ${ad.video_path ? '<p><a href="/' + escHtml(ad.video_path.replace(/^.*\/backend\//, '')) + '" target="_blank">🎬 查看生成的视频</a></p>' : ''}
    `;
    $('#adDetailModal').classList.add('active');
  } catch (e) { alert('加载失败: ' + e.message); }
}

// 生成带货视频
async function generateAdVideo (id) {
  if (!confirm('确定生成该带货剧本的视频？将使用上传的商品照片作为参考图。')) return;
  try {
    const res = await api(API + '/product-ad/' + id + '/generate-video', { method: 'POST' });
    alert(res.message);
    loadProductAds();
  } catch (e) { alert('生成失败: ' + e.message); }
}

// ---- 剧本评审 (不再手动调用，评审在生成时自动完成) ----
// 保留 showReviewResult 作为展示评审结果的工具函数
function showReviewResult (r, label) {
  const score = r.overall_score || 0;
  const color = score >= 8 ? 'var(--success)' : score >= 6 ? 'var(--warning)' : 'var(--danger)';
  const readyText = r.ready_for_video ? '✅ 建议生成视频' : '⚠️ 建议修改后再生成';
  const readyColor = r.ready_for_video ? 'var(--success)' : 'var(--danger)';

  let dimsHtml = '';
  if (r.dimensions) {
    dimsHtml = '<h3>维度评分</h3><table style="width:100%;border-collapse:collapse;margin-bottom:12px;">';
    const labels = {
      story_completeness: '故事完整性', character_depth: '角色深度',
      scene_logic: '场景逻辑', visual_feasibility: '视觉可行性',
      dialogue_quality: '对白质量', pacing: '节奏把控',
    };
    for (const [key, val] of Object.entries(r.dimensions)) {
      const s = val.score || 0;
      const c = s >= 8 ? 'var(--success)' : s >= 6 ? 'var(--warning)' : 'var(--danger)';
      dimsHtml += `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:6px 8px;color:var(--text-dim)">${labels[key] || key}</td>
        <td style="padding:6px 8px;font-weight:600;color:${c}">${s}/10</td>
        <td style="padding:6px 8px;color:var(--text-dim);font-size:0.85rem">${escHtml(val.note || '')}</td>
      </tr>`;
    }
    dimsHtml += '</table>';
  }

  const html = `
    <div style="text-align:center;margin-bottom:16px;">
      <div style="font-size:3rem;font-weight:700;color:${color};">${score}</div>
      <div style="font-size:0.9rem;color:var(--text-dim)">/ 10 · ${label}评分</div>
      <div style="margin-top:8px;font-size:1rem;color:${readyColor};font-weight:600">${readyText}</div>
    </div>
    ${dimsHtml}
    <p style="margin-bottom:8px;"><strong>总体评价</strong><br>${escHtml(r.summary || '')}</p>
    ${r.strengths ? '<h3>✅ 优点</h3><ul>' + r.strengths.map(s => '<li>' + escHtml(s) + '</li>').join('') + '</ul>' : ''}
    ${r.weaknesses ? '<h3>⚠️ 不足</h3><ul>' + r.weaknesses.map(s => '<li>' + escHtml(s) + '</li>').join('') + '</ul>' : ''}
    ${r.suggestions ? '<h3>💡 改进建议</h3><ul>' + r.suggestions.map(s => '<li>' + escHtml(s) + '</li>').join('') + '</ul>' : ''}
  `;

  $('#adModalTitle').textContent = `${label}评审结果`;
  $('#adModalBody').innerHTML = html;
  $('#adDetailModal').classList.add('active');
}

// ---- 定时任务开关 ----
async function loadSchedulerStatus () {
  try {
    const res = await api(API + '/scheduler/status');
    const badge = $('#schedulerStatus');
    const btn = $('#schedulerToggleBtn');
    if (res.enabled) {
      badge.textContent = '已开启';
      badge.className = 'scheduler-badge enabled';
      btn.textContent = '关闭';
      btn.className = 'btn btn-sm btn-danger';
    } else {
      badge.textContent = '已关闭';
      badge.className = 'scheduler-badge disabled';
      btn.textContent = '开启';
      btn.className = 'btn btn-sm btn-outline';
    }
  } catch { /* ignore */ }
}

$('#schedulerToggleBtn').addEventListener('click', async () => {
  const btn = $('#schedulerToggleBtn');
  const isEnabled = $('#schedulerStatus').textContent === '已开启';
  btn.disabled = true;
  try {
    if (isEnabled) {
      await api(API + '/scheduler/disable', { method: 'POST' });
    } else {
      await api(API + '/scheduler/enable', { method: 'POST' });
    }
    loadSchedulerStatus();
  } catch (e) {
    alert('操作失败: ' + e.message);
  }
  btn.disabled = false;
});

function escHtml (s) {
  if (typeof s !== 'string') return s;
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ---- 初始化 ----
loadStats();
loadSchedulerStatus();
loadScripts();
