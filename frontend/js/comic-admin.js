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

// ---- Tab 切换 ----
$$('.tab').forEach(t => {
  t.addEventListener('click', () => {
    $$('.tab').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    $$('.panel').forEach(x => x.classList.remove('active'));
    currentTab = t.dataset.tab;
    const panelId = currentTab === 'publish' ? 'publishPanel' : currentTab === 'videos' ? 'videosPanel' : 'scriptsPanel';
    $(`#${panelId}`).classList.add('active');
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

$('#refreshBtn').addEventListener('click', loadCurrentTab);
$('#scrapeTrendingBtn').addEventListener('click', loadTrending);

// ---- Modal ----
$('#modalClose').addEventListener('click', () => $('#detailModal').classList.remove('active'));

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
            <span>${fmtDate(s.created_at)}</span>
          </div>
        </div>
        <div class="card-actions">
          <button class="btn btn-outline btn-sm" onclick="viewScript(${s.id})">查看</button>
          <button class="btn btn-secondary btn-sm" onclick="regenerateVideo(${s.id})" ${s.status === 'generating_video' ? 'disabled' : ''}>重新生成视频</button>
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

function escHtml (s) {
  if (typeof s !== 'string') return s;
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ---- 初始化 ----
loadStats();
loadScripts();
