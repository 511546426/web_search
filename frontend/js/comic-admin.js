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
    const panelMap = { scripts: 'scriptsPanel', videos: 'videosPanel', product: 'productPanel', publish: 'publishPanel' };
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
          <button class="btn btn-success btn-sm" onclick="publishVideo(${v.id})" ${v.status !== 'completed' ? 'disabled' : ''}>标记发布</button>
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
  const platform = prompt('发布平台 (weibo / douyin / bilibili / wechat):', 'bilibili');
  if (!platform) return;
  try {
    const res = await api(API + '/videos/' + id + '/publish', {
      method: 'POST',
      body: JSON.stringify({ platform, message: '审核通过，发布' })
    });
    alert(res.message);
    loadStats();
    loadCurrentTab();
  } catch (e) { alert('发布失败: ' + e.message); }
}

function previewVideo (path) {
  const videoUrl = window.location.origin + '/' + path.replace(/^.*\/backend\//, '');
  window.open(videoUrl, '_blank');
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
    $('#generateAdScriptBtn').disabled = false;
  } catch (e) {
    alert('上传失败: ' + e.message);
  }
  btn.disabled = false; btn.textContent = '上传';
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

    let photoHtml = '';
    if (photos.length) {
      photoHtml = '<h3>参考图片</h3><div style="display:flex;gap:8px;flex-wrap:wrap;">' +
        photos.map(p => `<img src="/uploads/product_photos/${p}" class="photo-thumb" style="width:100px;height:100px;">`).join('') +
        '</div>';
    }

    $('#adModalTitle').textContent = ad.title;
    $('#adModalBody').innerHTML = `
      <p><strong>商品:</strong> ${escHtml(prodInfo.name || content.product || '')} | <strong>品类:</strong> ${escHtml(prodInfo.category || '')}</p>
      <p><strong>状态:</strong> ${statusLabel(ad.status)}</p>
      ${prodInfo.description ? '<p><strong>描述:</strong> ' + escHtml(prodInfo.description) + '</p>' : ''}
      ${prodInfo.selling_points ? '<p><strong>卖点:</strong> ' + escHtml(prodInfo.selling_points) + '</p>' : ''}
      ${content.characters ? renderCharacters(content.characters) : ''}
      ${photoHtml}
      <h3>带货剧本</h3>
      <pre>${escHtml(JSON.stringify(content.script || content, null, 2))}</pre>
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
