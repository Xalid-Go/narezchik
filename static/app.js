let currentMode = 'batch';
let availableFiles = [];
let pollingInterval = null;
let currentBannerSpeed = 1.0;
let currentBannerWidth = 1260;
let currentBannerHeight = 550;
let currentSplitRatio = 0.5;

document.addEventListener('DOMContentLoaded', async () => {
  await loadFiles();
  await loadClips();
  updateMockSubs();
  startTaskPolling();
});

// ------------------ MOCK SUBTITLES & PREVIEW ------------------
function updateMockSubs() {
  const check = document.getElementById('generateSubtitlesCheck');
  const fontSel = document.getElementById('subFontSelect');
  const colorSel = document.getElementById('subColorSelect');
  const sizeSlider = document.getElementById('subSizeSlider');
  const strokeSlider = document.getElementById('subStrokeSlider');
  const mockSubs = document.getElementById('mockSubs');

  if (!mockSubs) return;

  const isEnabled = check ? check.checked : true;
  mockSubs.style.display = isEnabled ? 'block' : 'none';

  const font = fontSel ? fontSel.value : 'Arial Black';
  const color = colorSel ? colorSel.value : 'yellow';
  const size = sizeSlider ? parseInt(sizeSlider.value) : 56;
  const stroke = strokeSlider ? parseFloat(strokeSlider.value) : 5.0;

  const sizeVal = document.getElementById('subSizeVal');
  if (sizeVal) sizeVal.innerText = `${size}px`;

  const strokeVal = document.getElementById('subStrokeVal');
  if (strokeVal) strokeVal.innerText = `${stroke}px`;

  // Apply font family
  if (font === 'Impact') {
    mockSubs.style.fontFamily = 'Impact, "Arial Black", sans-serif';
  } else if (font === 'Helvetica') {
    mockSubs.style.fontFamily = '"Helvetica Neue", Helvetica, Arial, sans-serif';
  } else if (font === 'Arial') {
    mockSubs.style.fontFamily = 'Arial, sans-serif';
  } else {
    mockSubs.style.fontFamily = '"Arial Black", sans-serif';
  }

  // Apply color
  const colorMap = {
    yellow: '#fff200',
    green: '#00e676',
    cyan: '#00e5ff',
    white: '#ffffff',
    fire: '#ff9100'
  };
  mockSubs.style.color = colorMap[color] || '#fff200';

  // Scale font size proportionally to preview mockup (~250px vs 1080px = ~0.23)
  const previewSize = Math.max(9, Math.round(size * 0.22));
  mockSubs.style.fontSize = `${previewSize}px`;

  // Scale stroke
  const previewStroke = Math.max(1, Math.round(stroke * 0.25));
  mockSubs.style.webkitTextStroke = `${previewStroke}px #000000`;
  mockSubs.style.textShadow = '0 2px 4px rgba(0,0,0,0.85)';
}

// Dynamic 1-word preview animation in phone mockup
let mockWordIndex = 0;
const mockWords = ["СМОТРИ", "КТО", "УКРАЛ", "ЭТИ", "ДЕНЬГИ?", "ХАЙП!"];
setInterval(() => {
  const mockSubs = document.getElementById('mockSubs');
  if (mockSubs && mockSubs.style.display !== 'none') {
    mockWordIndex = (mockWordIndex + 1) % mockWords.length;
    mockSubs.innerText = mockWords[mockWordIndex];
  }
}, 650);

// Helper for safe JSON fetching with Codespaces status detection
async function safeFetchJson(url, options = {}) {
  const res = await fetch(url, options);
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) {
    const data = await res.json();
    return { ok: res.ok, status: res.status, data };
  }
  const text = await res.text();
  const titleMatch = text.match(/<title>(.*?)<\/title>/i);
  const title = titleMatch ? titleMatch[1].trim() : '';

  if (res.status === 502 || res.status === 503 || text.toLowerCase().includes('refused') || text.toLowerCase().includes('bad gateway')) {
    throw new Error('Сервер не запущен в терминале! Запустите: git pull && ./run_codespaces.sh');
  }

  if (title.toLowerCase().includes('codespaces') || text.includes('github.dev')) {
    throw new Error(`Codespaces: "${title || 'Требуется подтверждение'}". Откройте сайт в отдельной вкладке и нажмите Continue!`);
  }

  throw new Error(title || text.replace(/<[^>]*>/g, '').trim().slice(0, 100) || `HTTP ${res.status}`);
}

// ------------------ FILE MANAGEMENT ------------------
async function loadFiles() {
  try {
    const { ok, data } = await safeFetchJson('/api/files');
    if (!ok) return;
    availableFiles = data.files || [];

    const mainSelect = document.getElementById('mainVideoSelect');
    const bgSelect = document.getElementById('bgVideoSelect');
    const bannerSelect = document.getElementById('bannerSelect');

    const prevMain = mainSelect.value;
    const prevBg = bgSelect.value;
    const prevBanner = bannerSelect.value;

    mainSelect.innerHTML = '';
    bgSelect.innerHTML = '';
    bannerSelect.innerHTML = '';

    availableFiles.forEach(f => {
      const durMin = Math.floor(f.duration / 60);
      const durSec = Math.floor(f.duration % 60);
      const timeStr = `${durMin}:${durSec < 10 ? '0' : ''}${durSec}`;
      const optText = `${f.filename} (${timeStr}, ${f.width}x${f.height})`;

      const opt1 = new Option(optText, f.filename);
      const opt2 = new Option(optText, f.filename);
      const opt3 = new Option(optText, f.filename);

      mainSelect.add(opt1);
      bgSelect.add(opt2);
      bannerSelect.add(opt3);
    });

    if (prevMain && availableFiles.some(f => f.filename === prevMain)) {
      mainSelect.value = prevMain;
    } else {
      const mainCand = availableFiles.find(f => f.duration > 600 || f.filename.includes('5poSpt'));
      if (mainCand) mainSelect.value = mainCand.filename;
    }

    if (prevBg && availableFiles.some(f => f.filename === prevBg)) {
      bgSelect.value = prevBg;
    } else {
      const bgCand = availableFiles.find(f => f.filename.includes('4qJqau') || f.filename.toLowerCase().includes('subway'));
      if (bgCand) bgSelect.value = bgCand.filename;
    }

    if (prevBanner && availableFiles.some(f => f.filename === prevBanner)) {
      bannerSelect.value = prevBanner;
    } else {
      const bannerCand = availableFiles.find(f => f.filename.includes('реклама') || f.filename.endsWith('.webm'));
      if (bannerCand) bannerSelect.value = bannerCand.filename;
    }

    updateFileLabels();
    updateBatchCalc();

    mainSelect.onchange = () => { updateFileLabels(); updateBatchCalc(); };
    bgSelect.onchange = updateFileLabels;
  } catch (err) {
    console.error('Failed to load files:', err);
  }
}

function updateFileLabels() {
  const mainSelect = document.getElementById('mainVideoSelect');
  const bgSelect = document.getElementById('bgVideoSelect');

  const mainFile = availableFiles.find(f => f.filename === mainSelect.value);
  const bgFile = availableFiles.find(f => f.filename === bgSelect.value);

  if (mainFile) {
    const m = Math.floor(mainFile.duration / 60);
    const s = Math.floor(mainFile.duration % 60);
    document.getElementById('mainVideoInfo').innerText = `Длительность: ${m} мин ${s} сек | ${mainFile.fps} FPS`;
  }
  if (bgFile) {
    const m = Math.floor(bgFile.duration / 60);
    const s = Math.floor(bgFile.duration % 60);
    document.getElementById('bgVideoInfo').innerText = `Длительность: ${m} мин ${s} сек | Фоновый геймплей`;
  }
}

// ------------------ IMPORT & DOWNLOAD ------------------
async function downloadVideoFromUrl() {
  const input = document.getElementById('urlDownloadInput');
  const status = document.getElementById('urlDownloadStatus');
  const btn = document.getElementById('btnDownloadUrl');
  const url = input.value.trim();

  if (!url) {
    alert('Вставьте ссылку на видео (YouTube / Shorts / TikTok)');
    return;
  }

  btn.disabled = true;
  status.style.display = 'block';
  status.style.color = 'var(--accent-blue)';
  status.innerText = '⏳ Скачиваем видео через yt-dlp на максимальной скорости...';

  try {
    const { ok, data } = await safeFetchJson('/api/download-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: url })
    });
    if (ok) {
      status.style.color = 'var(--accent-green)';
      status.innerText = '✅ Видео успешно загружено в проект!';
      input.value = '';
      await loadFiles();
    } else {
      status.style.color = '#ff5252';
      status.innerText = '❌ Ошибка: ' + (data.detail || 'Не удалось скачать');
    }
  } catch (err) {
    status.style.color = '#ff5252';
    status.innerText = '❌ ' + (err.message || err);
  } finally {
    btn.disabled = false;
  }
}

async function uploadLocalFile(event) {
  const file = event.target.files[0];
  const status = document.getElementById('fileUploadStatus');
  if (!file) return;

  status.style.display = 'block';
  status.style.color = 'var(--accent-blue)';
  status.innerText = `⏳ Загрузка файла ${file.name}...`;

  const formData = new FormData();
  formData.append('file', file);

  try {
    const { ok, data } = await safeFetchJson('/api/upload', {
      method: 'POST',
      body: formData
    });
    if (ok) {
      status.style.color = 'var(--accent-green)';
      status.innerText = `✅ Файл ${data.filename} загружен и доступен в списке!`;
      await loadFiles();
      if (file.name.includes('баннер') || file.name.includes('реклама') || file.name.endsWith('.webm')) {
        document.getElementById('bannerSelect').value = data.filename;
      } else {
        document.getElementById('mainVideoSelect').value = data.filename;
      }
    } else {
      status.style.color = '#ff5252';
      status.innerText = '❌ Ошибка при загрузке: ' + (data.detail || 'Неизвестная ошибка');
    }
  } catch (err) {
    status.style.color = '#ff5252';
    status.innerText = '❌ ' + (err.message || err);
  } finally {
    event.target.value = '';
  }
}

// ------------------ EDITOR & SPLIT CONTROLS ------------------
function updateSplitRatio(val) {
  const topPct = parseInt(val);
  const botPct = 100 - topPct;
  currentSplitRatio = topPct / 100.0;
  document.getElementById('splitRatioLabel').innerText = `${topPct}% / ${botPct}%`;

  const mockTop = document.getElementById('mockTop');
  const mockBottom = document.getElementById('mockBottom');
  if (mockTop && mockBottom) {
    mockTop.style.flex = `${topPct}`;
    mockBottom.style.flex = `${botPct}`;
  }
}

function switchMode(mode) {
  currentMode = mode;
  document.getElementById('tabBatch').classList.toggle('active', mode === 'batch');
  document.getElementById('tabSingle').classList.toggle('active', mode === 'single');
  document.getElementById('batchControls').style.display = mode === 'batch' ? 'block' : 'none';
  document.getElementById('singleControls').style.display = mode === 'single' ? 'block' : 'none';
}

function setClipDuration(seconds) {
  document.getElementById('batchDurationInput').value = seconds;
  document.querySelectorAll('.preset-pill').forEach(el => el.classList.remove('active'));
  const pill = document.getElementById(`pill${seconds}`);
  if (pill) pill.classList.add('active');
  updateBatchCalc();
}

function updateBatchCalc() {
  const mainSelect = document.getElementById('mainVideoSelect');
  const mainFile = availableFiles.find(f => f.filename === mainSelect.value);
  if (!mainFile) return;

  const clipDur = parseFloat(document.getElementById('batchDurationInput').value) || 60;
  const offset = parseFloat(document.getElementById('batchOffsetInput').value) || 0;
  const maxClips = parseInt(document.getElementById('batchMaxClipsInput')?.value) || null;

  const availableDuration = Math.max(0, mainFile.duration - offset);
  let parts = Math.floor(availableDuration / clipDur);
  if (maxClips && maxClips < parts) {
    parts = maxClips;
  }

  const calcEl = document.getElementById('calcPartsCount');
  if (calcEl) calcEl.innerText = parts;
}

function setBannerPreset(preset) {
  document.querySelectorAll('[id^="pillBanner"]').forEach(el => el.classList.remove('active'));
  const label = document.getElementById('bannerPctLabel');
  const mockBanner = document.getElementById('mockBanner');

  if (preset === 'edge') {
    document.getElementById('pillBannerEdge').classList.add('active');
    currentBannerWidth = 1260;
    currentBannerHeight = 550;
    label.innerText = '✅ Чистая видимая площадь баннера: 25.79% (Гарантированная выплата)';
    label.style.color = 'var(--accent-green)';
    if (mockBanner) {
      mockBanner.style.width = '100%';
      mockBanner.style.transform = 'translate(-50%, -50%) scale(1.10)';
    }
  } else if (preset === 'safe') {
    document.getElementById('pillBannerSafe').classList.add('active');
    currentBannerWidth = 1320;
    currentBannerHeight = 575;
    label.innerText = '🔥 27.46% чистой площади (1320×575) Надежный запас';
    label.style.color = 'var(--accent-green)';
    if (mockBanner) {
      mockBanner.style.width = '105%';
      mockBanner.style.transform = 'translate(-50%, -50%) scale(1.18)';
    }
  } else if (preset === '25') {
    document.getElementById('pillBanner25').classList.add('active');
    currentBannerWidth = 1080;
    currentBannerHeight = 434;
    label.innerText = '⚠️ 18.47% чистой площади (Внимание: риск отклонения модерацией)';
    label.style.color = '#ff5252';
    if (mockBanner) {
      mockBanner.style.width = '90%';
      mockBanner.style.transform = 'translate(-50%, -50%) scale(0.95)';
    }
  }
}

function setBannerSpeed(speed) {
  currentBannerSpeed = speed;
  ['speed10', 'speed11', 'speed12'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
  });
  if (speed === 1.0) document.getElementById('speed10')?.classList.add('active');
  if (speed === 1.1) document.getElementById('speed11')?.classList.add('active');
  if (speed === 1.2) document.getElementById('speed12')?.classList.add('active');
}

// ------------------ RENDERING ACTIONS ------------------
async function startBatchRender() {
  const mainVideo = document.getElementById('mainVideoSelect').value;
  const bgVideo = document.getElementById('bgVideoSelect').value;
  const bannerFile = document.getElementById('bannerSelect').value;
  const clipDur = parseFloat(document.getElementById('batchDurationInput').value) || 60;
  const offset = parseFloat(document.getElementById('batchOffsetInput').value) || 0;
  const maxClips = parseInt(document.getElementById('batchMaxClipsInput')?.value) || null;

  const pauseOnBanner = document.getElementById('pauseOnBannerCheck').checked;
  const generateSubtitles = document.getElementById('generateSubtitlesCheck').checked;
  const removeBlueBg = document.getElementById('removeBlueBgCheck').checked;
  const mirrorTop = document.getElementById('mirrorTopCheck').checked;
  const mirrorBottom = document.getElementById('mirrorBottomCheck').checked;

  const subFont = document.getElementById('subFontSelect').value;
  const subColor = document.getElementById('subColorSelect').value;
  const subSize = parseInt(document.getElementById('subSizeSlider').value) || 56;
  const subStroke = parseFloat(document.getElementById('subStrokeSlider').value) || 5.0;

  if (!mainVideo || !bgVideo || !bannerFile) {
    alert('Пожалуйста, выберите все три файла');
    return;
  }

  try {
    const { ok, data } = await safeFetchJson('/api/render/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        main_video: mainVideo,
        bg_video: bgVideo,
        banner_file: bannerFile,
        clip_duration: clipDur,
        start_offset: offset,
        max_clips: maxClips,
        split_ratio: currentSplitRatio,
        banner_width: currentBannerWidth,
        banner_height: currentBannerHeight,
        pause_on_banner: pauseOnBanner,
        banner_speed: currentBannerSpeed,
        remove_blue_bg: removeBlueBg,
        mirror_top: mirrorTop,
        mirror_bottom: mirrorBottom,
        generate_subtitles: generateSubtitles,
        subtitle_font: subFont,
        subtitle_color: subColor,
        subtitle_size: subSize,
        subtitle_outline: subStroke,
      })
    });
    if (ok) {
      alert(`Запущен пакетный рендеринг (${data.batch_count} клипов)! Следите за шкалой прогресса справа.`);
      pollTasks();
    } else {
      alert('Ошибка при запуске пакета: ' + (data?.detail || 'Неизвестная ошибка'));
    }
  } catch (err) {
    alert('Ошибка: ' + (err.message || err));
  }
}

async function startSingleRender() {
  const mainVideo = document.getElementById('mainVideoSelect').value;
  const bgVideo = document.getElementById('bgVideoSelect').value;
  const bannerFile = document.getElementById('bannerSelect').value;
  const start = parseFloat(document.getElementById('singleStartInput').value) || 0;
  const dur = parseFloat(document.getElementById('singleDurationInput').value) || 60;
  const bgOff = parseFloat(document.getElementById('singleBgOffsetInput').value) || 0;

  const pauseOnBanner = document.getElementById('pauseOnBannerCheck').checked;
  const generateSubtitles = document.getElementById('generateSubtitlesCheck').checked;
  const removeBlueBg = document.getElementById('removeBlueBgCheck').checked;
  const mirrorTop = document.getElementById('mirrorTopCheck').checked;
  const mirrorBottom = document.getElementById('mirrorBottomCheck').checked;

  const subFont = document.getElementById('subFontSelect').value;
  const subColor = document.getElementById('subColorSelect').value;
  const subSize = parseInt(document.getElementById('subSizeSlider').value) || 56;
  const subStroke = parseFloat(document.getElementById('subStrokeSlider').value) || 5.0;

  try {
    const { ok, data } = await safeFetchJson('/api/render/single', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        main_video: mainVideo,
        bg_video: bgVideo,
        banner_file: bannerFile,
        start_time: start,
        duration: dur,
        bg_offset: bgOff,
        split_ratio: currentSplitRatio,
        banner_width: currentBannerWidth,
        banner_height: currentBannerHeight,
        pause_on_banner: pauseOnBanner,
        banner_speed: currentBannerSpeed,
        remove_blue_bg: removeBlueBg,
        mirror_top: mirrorTop,
        mirror_bottom: mirrorBottom,
        generate_subtitles: generateSubtitles,
        subtitle_font: subFont,
        subtitle_color: subColor,
        subtitle_size: subSize,
        subtitle_outline: subStroke,
      })
    });
    if (ok) {
      pollTasks();
    } else {
      alert('Ошибка при запуске: ' + (data?.detail || 'Не удалось создать задачу'));
    }
  } catch (err) {
    alert('Ошибка: ' + (err.message || err));
  }
}

// ------------------ TASK MONITORING ------------------
function startTaskPolling() {
  if (pollingInterval) clearInterval(pollingInterval);
  pollTasks();
  pollingInterval = setInterval(pollTasks, 1500);
}

async function pollTasks() {
  try {
    const { ok, data } = await safeFetchJson('/api/tasks');
    if (!ok) return;
    const tasks = data?.tasks || [];

    const badge = document.getElementById('taskCountBadge');
    if (badge) badge.innerText = `${tasks.length} задач`;

    const list = document.getElementById('taskList');
    if (!list) return;

    if (tasks.length === 0) {
      list.innerHTML = `<div style="font-size: 13px; color: var(--text-muted); text-align: center; padding: 20px;">Нет активных задач.</div>`;
      return;
    }

    list.innerHTML = tasks.slice().reverse().map(t => {
      const statusColor = t.status === 'completed' ? 'var(--accent-green)' : (t.status === 'failed' ? '#ff5252' : '#00b0ff');
      return `
        <div class="task-item">
          <div class="task-header">
            <span>${t.name}</span>
            <span style="color: ${statusColor}; font-weight: 700;">${t.status === 'completed' ? 'Готово ✅' : (t.status === 'failed' ? 'Ошибка ❌' : `${t.progress}%`)}</span>
          </div>
          <div class="progress-bar-bg">
            <div class="progress-bar-fill" style="width: ${t.progress}%;"></div>
          </div>
          <div style="font-size: 11px; color: var(--text-muted);">${t.message || ''}</div>
        </div>
      `;
    }).join('');

    const completedCount = tasks.filter(t => t.status === 'completed').length;
    if (window._lastCompletedCount !== completedCount) {
      window._lastCompletedCount = completedCount;
      loadClips();
    }
  } catch (err) {
    console.warn('Task poll waiting for server or public port...');
  }
}

// ------------------ FINISHED CLIPS GALLERY ------------------
async function loadClips() {
  try {
    const { ok, data } = await safeFetchJson('/api/clips');
    if (!ok) return;
    const clips = data?.clips || [];

    const grid = document.getElementById('clipsGrid');
    if (!grid) return;

    if (clips.length === 0) {
      grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 30px;">Здесь появятся готовые ролики.</div>`;
      return;
    }

    grid.innerHTML = clips.map(c => `
      <div class="clip-card">
        <video class="clip-video-preview" controls preload="metadata" src="${c.url}"></video>
        <div class="clip-body">
          <div class="clip-title" title="${c.filename}">${c.filename}</div>
          <div class="clip-meta">
            <span>⏱️ ${Math.round(c.duration)}с</span>
            <span>💾 ${c.size_mb} MB</span>
            <span>#бубавпн ✅</span>
          </div>
          <div class="clip-actions">
            <a href="${c.url}" download="${c.filename}" class="btn-primary" style="padding: 6px 10px; font-size: 11px; text-decoration: none;">
              ⬇️ Скачать
            </a>
            <button class="btn-secondary" onclick="copyCaption('${c.filename}')" style="padding: 6px 8px; font-size: 11px;">
              📋 Текст и #теги
            </button>
          </div>
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error('Failed to load clips:', err);
  }
}

function copyCaption(filename) {
  const caption = `Смотри до конца! Ссылка на бота в шапке профиля 👆\n\n#бубавпн #рек #fyp #врек #shorts #нарезка`;
  navigator.clipboard.writeText(caption).then(() => {
    alert(`Текст скопирован в буфер обмена!\n\n${caption}\n\nВставляйте в TikTok или YouTube Shorts при публикации.`);
  });
}
