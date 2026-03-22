/**
 * 情侣记录站 · 前端
 * API 基地址：同源则用相对路径 /api
 */
const API = '/api';

function get(url) {
  return fetch(API + url).then((r) => {
    if (!r.ok) throw new Error(r.statusText);
    return r.json();
  });
}

function post(url, body) {
  return fetch(API + url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((r) => {
    if (!r.ok) throw new Error(r.statusText);
    return r.json();
  });
}

function postForm(url, formData) {
  return fetch(API + url, {
    method: 'POST',
    body: formData,
  }).then((r) => {
    if (!r.ok) throw new Error(r.statusText);
    return r.json();
  });
}

// ---------- 我们在一起第 N 天 ----------
function renderHero() {
  const daysEl = document.getElementById('daysNum');
  const msgEl = document.getElementById('heroMessage');
  get('/stats')
    .then((data) => {
      if (data.days_together != null) {
        daysEl.textContent = data.days_together;
        msgEl.textContent = data.name ? `从 ${data.first_date} 开始 · 每一天都值得纪念` : '';
      } else {
        daysEl.textContent = '…';
        msgEl.textContent = data.message || '添加「在一起的日子」纪念日即可显示';
      }
    })
    .catch(() => {
      daysEl.textContent = '--';
      msgEl.textContent = '连接失败，稍后再试';
    });
}

// ---------- 纪念日 ----------
function formatDate(d) {
  const date = new Date(d);
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
}

function daysUntil(nextDate) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const next = new Date(nextDate);
  next.setHours(0, 0, 0, 0);
  const diff = Math.ceil((next - today) / (1000 * 60 * 60 * 24));
  return diff;
}

function renderAnniversaries() {
  const el = document.getElementById('anniversariesList');
  el.innerHTML = '<div class="loading">加载中…</div>';
  get('/anniversaries')
    .then((list) => {
      if (!list || list.length === 0) {
        el.innerHTML = '<div class="empty"><span class="icon">📅</span><p>还没有纪念日</p><button type="button" class="btn-add empty-cta" data-open="modalAnniversary">＋ 添加第一个纪念日</button></div>';
        return;
      }
      el.innerHTML = list
        .map((a) => {
          const d = daysUntil(a.date);
          const text = d === 0 ? '就是今天！' : d > 0 ? `还有 ${d} 天` : `已经 ${-d} 天`;
          return `
            <div class="card anniversary-card">
              <div>
                <span class="name">${escapeHtml(a.name)}</span>
                <div class="date">${formatDate(a.date)}</div>
              </div>
              <div class="countdown">${text}</div>
            </div>`;
        })
        .join('');
    })
    .catch(() => {
      el.innerHTML = '<div class="empty">加载失败，请稍后再试</div>';
    });
}

// ---------- 时光轴 ----------
function renderMemories() {
  const el = document.getElementById('memoriesList');
  el.innerHTML = '<div class="loading">加载中…</div>';
  get('/memories')
    .then((list) => {
      if (!list || list.length === 0) {
        el.innerHTML = '<div class="empty"><span class="icon">📖</span><p>还没有记录</p><button type="button" class="btn-add empty-cta" data-open="modalMemory">＋ 添加第一条回忆</button></div>';
        return;
      }
      el.innerHTML = list
        .map((m) => {
          const time = new Date(m.happened_at).toLocaleString('zh-CN', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          });
          const mood = m.mood ? `<span class="mood">${escapeHtml(m.mood)}</span>` : '';
          const img = m.image_url
            ? `<img src="${escapeAttr(m.image_url)}" alt="" style="max-width:100%; border-radius:8px; margin-top:0.5rem;" />`
            : '';
          return `
            <div class="card">
              <div class="meta">${time} ${mood}</div>
              ${m.title ? `<div class="title">${escapeHtml(m.title)}</div>` : ''}
              <div class="content">${escapeHtml(m.content).replace(/\n/g, '<br>')}</div>
              ${img}
            </div>`;
        })
        .join('');
    })
    .catch(() => {
      el.innerHTML = '<div class="empty">加载失败，请稍后再试</div>';
    });
}

// ---------- 相册（含照片故事展示 + 点击放大） ----------
function photoUrl(filename) {
  if (!filename) return '';
  if (filename.startsWith('http')) return filename;
  return `/uploads/${filename}`;
}

function renderGallery() {
  const el = document.getElementById('galleryList');
  el.innerHTML = '<div class="loading">加载中…</div>';
  get('/photos')
    .then((list) => {
      if (!list || list.length === 0) {
        el.innerHTML = '<div class="empty"><span class="icon">📷</span><p>还没有照片</p><button type="button" class="btn-add empty-cta" data-open="modalPhoto">＋ 上传第一张照片</button></div>';
        return;
      }
      el.innerHTML = list
        .map((p) => {
          const time = new Date(p.taken_at).toLocaleDateString('zh-CN');
          const hasStory = p.description && String(p.description).trim();
          const descText = hasStory ? String(p.description).trim() : time;
          const label = hasStory ? '照片故事' : '上传于';
          const src = photoUrl(p.filename);
          return `
            <div class="gallery-item" role="button" tabindex="0" data-src="${escapeAttr(src)}" data-label="${escapeAttr(label)}" data-desc="${escapeAttr(descText)}" title="点击放大">
              <img src="${escapeAttr(src)}" alt="${escapeAttr(descText)}" loading="lazy" />
              <div class="gallery-item-desc">
                <span class="gallery-item-label">${escapeHtml(label)}</span>
                <span class="gallery-item-text">${escapeHtml(descText)}</span>
              </div>
            </div>`;
        })
        .join('');
    })
    .catch(() => {
      el.innerHTML = '<div class="empty">加载失败，请稍后再试</div>';
    });
}

// ---------- 照片大图查看：点击相册照片放大并显示故事 ----------
function openPhotoLightbox(src, label, desc) {
  const lb = document.getElementById('photoLightbox');
  const img = document.getElementById('lightboxImg');
  const labelEl = document.getElementById('lightboxLabel');
  const descEl = document.getElementById('lightboxDesc');
  if (!lb || !img) return;
  img.src = src;
  img.alt = desc;
  if (labelEl) labelEl.textContent = label;
  if (descEl) descEl.textContent = desc;
  lb.classList.add('is-open');
  lb.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
}

function closePhotoLightbox() {
  const lb = document.getElementById('photoLightbox');
  if (!lb) return;
  lb.classList.remove('is-open');
  lb.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
}

function initPhotoLightbox() {
  const list = document.getElementById('galleryList');
  if (list) {
    list.addEventListener('click', (e) => {
      const item = e.target.closest('.gallery-item[data-src]');
      if (!item) return;
      const src = item.getAttribute('data-src');
      const label = item.getAttribute('data-label') || '照片故事';
      const desc = item.getAttribute('data-desc') || '';
      if (src) openPhotoLightbox(src, label, desc);
    });
    list.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const item = e.target.closest('.gallery-item[data-src]');
      if (!item) return;
      e.preventDefault();
      const src = item.getAttribute('data-src');
      const label = item.getAttribute('data-label') || '照片故事';
      const desc = item.getAttribute('data-desc') || '';
      if (src) openPhotoLightbox(src, label, desc);
    });
  }
  const overlay = document.querySelector('#photoLightbox .lightbox-overlay');
  const closeBtn = document.querySelector('#photoLightbox .lightbox-close');
  if (overlay) overlay.addEventListener('click', closePhotoLightbox);
  if (closeBtn) closeBtn.addEventListener('click', closePhotoLightbox);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closePhotoLightbox();
  });
}

// ---------- 悄悄话 ----------
function renderNotes() {
  const el = document.getElementById('notesList');
  el.innerHTML = '<div class="loading">加载中…</div>';
  get('/notes')
    .then((list) => {
      if (!list || list.length === 0) {
        el.innerHTML = '<div class="empty"><span class="icon">💌</span><p>还没有悄悄话</p><button type="button" class="btn-add empty-cta" data-open="modalNote">＋ 写一句悄悄话</button></div>';
        return;
      }
      el.innerHTML = list
        .map((n) => {
          const time = new Date(n.created_at).toLocaleString('zh-CN');
          return `
            <div class="card note-card">
              <div class="meta">${time}</div>
              <div class="content">「${escapeHtml(n.content)}」</div>
            </div>`;
        })
        .join('');
    })
    .catch(() => {
      el.innerHTML = '<div class="empty">加载失败，请稍后再试</div>';
    });
}

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

function escapeAttr(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ---------- 弹窗 ----------
function showModal(id) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.add('is-open');
    el.setAttribute('aria-hidden', 'false');
  }
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.remove('is-open');
    el.setAttribute('aria-hidden', 'true');
  }
}

// 点击任意 [data-open] 按钮打开对应弹窗（含动态插入的空状态按钮）
document.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-open]');
  if (btn) showModal(btn.getAttribute('data-open'));
});

function bindModal(modalId, openBtnId, onClose) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  if (openBtnId) {
    const openBtn = document.getElementById(openBtnId);
    if (openBtn) openBtn.addEventListener('click', () => showModal(modalId));
  }
  const overlay = modal.querySelector('.modal-overlay');
  if (overlay) overlay.addEventListener('click', () => { closeModal(modalId); if (onClose) onClose(); });
  modal.querySelectorAll('.btn-cancel').forEach((btn) => {
    btn.addEventListener('click', () => { closeModal(modalId); if (onClose) onClose(); });
  });
}

// ---------- 添加纪念日 ----------
function initAddAnniversary() {
  bindModal('modalAnniversary', 'btnAddAnniversary', null);
  const form = document.getElementById('formAnniversary');
  if (!form) return;
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const dateStr = fd.get('date');
    const body = {
      name: (fd.get('name') || '').trim(),
      date: dateStr,
      repeat_yearly: fd.get('repeat_yearly') === 'on',
    };
    const submitBtn = form.querySelector('.btn-submit');
    submitBtn.disabled = true;
    post('/anniversaries', body)
      .then(() => {
        closeModal('modalAnniversary');
        form.reset();
        form.querySelector('[name="repeat_yearly"]').checked = true;
        renderAnniversaries();
        renderHero();
      })
      .catch((err) => alert('添加失败：' + (err.message || '请稍后再试')))
      .finally(() => { submitBtn.disabled = false; });
  });
}

// ---------- 添加回忆 ----------
function initAddMemory() {
  bindModal('modalMemory', 'btnAddMemory');
  const form = document.getElementById('formMemory');
  if (!form) return;
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const body = {
      content: (fd.get('content') || '').trim(),
      title: (fd.get('title') || '').trim() || undefined,
      mood: (fd.get('mood') || '').trim() || undefined,
    };
    const submitBtn = form.querySelector('.btn-submit');
    submitBtn.disabled = true;
    post('/memories', body)
      .then(() => {
        closeModal('modalMemory');
        form.reset();
        renderMemories();
      })
      .catch((err) => alert('添加失败：' + (err.message || '请稍后再试')))
      .finally(() => { submitBtn.disabled = false; });
  });
}

// ---------- 写悄悄话 ----------
function initAddNote() {
  bindModal('modalNote', 'btnAddNote');
  const form = document.getElementById('formNote');
  if (!form) return;
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const body = { content: (fd.get('content') || '').trim(), is_public: true };
    const submitBtn = form.querySelector('.btn-submit');
    submitBtn.disabled = true;
    post('/notes', body)
      .then(() => {
        closeModal('modalNote');
        form.reset();
        renderNotes();
      })
      .catch((err) => alert('添加失败：' + (err.message || '请稍后再试')))
      .finally(() => { submitBtn.disabled = false; });
  });
}

// ---------- 上传照片 ----------
function initAddPhoto() {
  bindModal('modalPhoto', 'btnAddPhoto');
  const form = document.getElementById('formPhoto');
  if (!form) return;
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const file = fd.get('file');
    if (!file || !file.size) {
      alert('请选择一张图片');
      return;
    }
    const formData = new FormData();
    formData.append('file', file);
    const desc = (fd.get('description') || '').trim();
    if (desc) formData.append('description', desc);
    const submitBtn = form.querySelector('.btn-submit');
    submitBtn.disabled = true;
    postForm('/photos', formData)
      .then(() => {
        closeModal('modalPhoto');
        form.reset();
        renderGallery();
      })
      .catch((err) => alert('上传失败：' + (err.message || '请稍后再试')))
      .finally(() => { submitBtn.disabled = false; });
  });
}

// ---------- 标签切换 ----------
function initTabs() {
  document.querySelectorAll('.tabs button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll('.tabs button').forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.section').forEach((s) => s.classList.remove('active'));
      btn.classList.add('active');
      const section = document.getElementById('section-' + tab);
      if (section) section.classList.add('active');
    });
  });
}

// ---------- 入口 ----------
function init() {
  initTabs();
  initAddAnniversary();
  initAddMemory();
  initAddNote();
  initAddPhoto();
  initPhotoLightbox();
  renderHero();
  renderAnniversaries();
  renderMemories();
  renderGallery();
  renderNotes();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

// PWA：注册 Service Worker
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}
