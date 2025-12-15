(() => {
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));
  const apiBase = () => $('#apiBase').value.trim().replace(/\/$/, '');
  const escapeHtml = (str = '') =>
    String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');

  const state = {
    es: null,
    profile: null,
    jd: null,
    job: null,
    lastMatch: null,
    roleRecommendations: [],
    deliveredHashes: new Set(),
    lastSearchPayload: null,
  };

  const sampleProfile = {
    name: 'Alice Wang',
    contact: 'alice@example.com · +61 4 1234 5678',
    location: 'Melbourne, VIC',
    skills: ['Python', 'C++', 'FastAPI', 'REST API', 'AWS', 'ROS'],
    education: [
      {
        school: 'University of New South Wales',
        degree: "Master of Information Technology",
        major: 'Artificial Intelligence',
        start: '2019',
        end: '2021',
      },
      {
        school: 'Tongji University',
        degree: "Bachelor of Software Engineering",
        start: '2015',
        end: '2019',
      },
    ],
    experience: [
      {
        company: 'Uni Capstone Project',
        role: 'Software Engineer',
        start: '2020-07',
        end: '2021-06',
        bullets: [
          '使用 FastAPI 构建多模块 REST 服务，服务 1.2k+ 每日请求',
          '设计基于 AWS S3 + Lambda 的简历处理流水线，平均延迟降低 35%',
          '编写 C++/ROS 模块用于机器人路径规划的仿真验证',
        ],
      },
      {
        company: 'TechCamp',
        role: 'Backend Intern',
        start: '2019-06',
        end: '2019-09',
        bullets: [
          '实现基于 Celery 的异步任务队列，支持批量 PDF 导出',
          '补充单元测试并提升后端代码覆盖率至 82%',
        ],
      },
    ],
    courses: [
      {
        code: 'COMP9444',
        name: 'Neural Networks & Deep Learning',
        topics: ['CNN', 'RNN'],
        skills: ['PyTorch', 'TensorFlow'],
      },
      {
        code: 'COMP9321',
        name: 'Data Services Engineering',
        topics: ['API Design', 'ETL'],
        skills: ['FastAPI', 'PostgreSQL'],
      },
    ],
    languages: ['English', 'Mandarin'],
    target_roles: ['Software Engineer', 'Backend Engineer'],
    target_locations: ['Melbourne', 'Sydney'],
  };

  const sampleFreeText = `我叫 Alice Wang，目前在墨尔本，拥有 UNSW 信息技术硕士学位。擅长 Python、C++、FastAPI、REST API 和 AWS。

最近在毕业设计中担任后端工程师，实现了一个基于 FastAPI 的多模块 REST 服务，日均处理 1200+ 请求；还搭建了 AWS S3 + Lambda 的简历处理流水线，使得 PDF 导出平均延迟降低 35%。同时，使用 C++/ROS 进行机器人路径规划仿真。

本科就读同济大学软件工程，期间在 TechCamp 担任后台实习生，实现 Celery 异步任务队列、批量 PDF 导出，并补充单元测试将覆盖率提升到 82%。

课程方面，修读了 COMP9444（Neural Networks & Deep Learning）和 COMP9321（Data Services Engineering），熟悉 PyTorch/TensorFlow、FastAPI、PostgreSQL 等工具。

期待寻找在墨尔本或悉尼的后端/软件工程相关职位。`;

  const defaultPreviewMessage =
    '尚未匹配，请在职位卡片中依次点击“解析 JD → 匹配 → 预览”。';
  const defaultRoleMessage =
    '点击“智能岗位推荐”后将展示适合的岗位方向与命中关键词。';

  function showToast(message, type = 'info', timeout = 2600) {
    const el = $('#toast');
    if (!el) return;
    el.textContent = message;
    el.className = `toast ${type === 'success' ? 'success' : type === 'error' ? 'error' : ''} visible`;
    clearTimeout(el._timer);
    el._timer = setTimeout(() => {
      el.classList.remove('visible');
    }, timeout);
  }

  function setText(selector, text) {
    const el = $(selector);
    if (el) el.textContent = text;
  }

  function resetMatchResult() {
    const matchEl = $('#matchResult');
    if (matchEl) {
      matchEl.classList.add('muted');
      matchEl.innerHTML = defaultPreviewMessage;
    }
  }

  function renderRoleRecommendations(list) {
    const container = $('#roleRecommendations');
    const statusEl = $('#roleRecommendStatus');
    state.roleRecommendations = Array.isArray(list) ? list : [];
    if (!container) return;
    if (!list || !list.length) {
      container.classList.add('empty');
      container.innerHTML = `<p>${defaultRoleMessage}</p>`;
      if (statusEl) {
        statusEl.textContent = Array.isArray(list)
          ? '暂无推荐岗位，可完善技能或点击按钮重新尝试'
          : '';
      }
    } else {
      container.classList.remove('empty');
      container.innerHTML = list
        .map(
          (item) => `
        <div class="role-card">
          <div class="role-card-title">${item.title || '推荐岗位'}</div>
          ${item.reason ? `<div class="role-card-reason">${item.reason}</div>` : ''}
          ${
            item.matched_keywords && item.matched_keywords.length
              ? `<div class="role-card-tags">关键词：${item.matched_keywords
                  .slice(0, 8)
                  .join(', ')}</div>`
              : ''
          }
        </div>`
        )
        .join('');
      if (statusEl) statusEl.textContent = `共推荐 ${list.length} 个岗位`;
    }
  }

  function renderProfile(profile, meta = {}) {
    const summary = $('#profileSummary');
    const jsonEl = $('#profileJson');
    if (!summary || !jsonEl) return;

    if (!profile) {
      summary.classList.add('empty');
      summary.innerHTML = '<p>画像结果会展示在这里。</p>';
      jsonEl.textContent = '';
      renderRoleRecommendations([]);
      return;
    }

    summary.classList.remove('empty');

    const skills = profile.skills || [];
    const education = profile.education || [];
    const experience = profile.experience || [];
    const courses = profile.courses || [];
    const summaryBlock = profile.summary
      ? `<div>
            <h3>个人简介</h3>
            <p>${escapeHtml(profile.summary)}</p>
          </div>`
      : '';

    const skillHtml = skills.length
      ? `<div class="chips">${skills.map((s) => `<span class="chip">${s}</span>`).join('')}</div>`
      : '<div class="muted">暂无技能</div>';

    const eduHtml = education.length
      ? education
          .slice(0, 3)
          .map((edu) => {
            const detail = [edu.degree, edu.major].filter(Boolean).join(' · ');
            const period = [edu.start, edu.end].filter(Boolean).join(' - ');
            return `<div><strong>${edu.school || '未填写学校'}</strong>${detail ? ` · ${detail}` : ''}${
              period ? ` <span class="muted">${period}</span>` : ''
            }</div>`;
          })
          .join('')
      : '<div class="muted">暂无教育记录</div>';

    const expHtml = experience.length
      ? experience
          .slice(0, 3)
          .map((exp) => {
            const period = [exp.start, exp.end].filter(Boolean).join(' - ');
            const bullets = (exp.bullets || []).slice(0, 3).map((b) => `<li>${b}</li>`).join('');
            return `<div>
                <strong>${exp.role || '岗位'} @ ${exp.company || '公司'}</strong>${
              period ? ` · <span class="muted">${period}</span>` : ''
            }
                ${bullets ? `<ul>${bullets}</ul>` : ''}
              </div>`;
          })
          .join('')
      : '<div class="muted">暂无工作经历</div>';

    const courseHtml = courses.length
      ? courses
          .slice(0, 4)
          .map((course) => {
            const info = [course.code, course.name].filter(Boolean).join(' · ');
            const tags = (course.skills || course.topics || []).slice(0, 3).join(', ');
            return `<div>${info}${tags ? ` <span class="muted">(${tags})</span>` : ''}</div>`;
          })
          .join('')
      : '';

    summary.innerHTML = `
      <div>
        <h3>基础信息</h3>
        <div class="definition-list">
          <div><strong>姓名：</strong>${profile.name || '—'}</div>
          <div><strong>联系方式：</strong>${profile.contact || '—'}</div>
          <div><strong>地点：</strong>${profile.location || '—'}</div>
        </div>
      </div>
      ${summaryBlock}
      <div>
        <h3>技能 (${skills.length})</h3>
        ${skillHtml}
      </div>
      <div>
        <h3>教育 (${education.length})</h3>
        <div class="definition-list">${eduHtml}</div>
      </div>
      <div>
        <h3>经历 (${experience.length})</h3>
        <div class="definition-list">${expHtml}</div>
      </div>
      ${
        courseHtml
          ? `<div>
              <h3>课程 (${courses.length})</h3>
              <div class="definition-list">${courseHtml}</div>
            </div>`
          : ''
      }
    `;

    jsonEl.textContent = JSON.stringify(profile, null, 2);
    renderRoleRecommendations(meta.role_recommendations || []);
  }

  async function analyzeProfile() {
    const statusEl = $('#analyzeStatus');
    const button = $('#analyzeProfile');
    const fileInput = $('#resumeFile');
    const freeText = $('#freeText');

    if (!statusEl || !button) return;

    const text = freeText?.value?.trim() || '';
    const file = fileInput?.files?.[0];

    if (!text && !file) {
      showToast('请填写自由文本或上传简历文件', 'error');
      return;
    }

    try {
      statusEl.textContent = '分析中...';
      button.disabled = true;

      let response;
      if (file) {
        if (file.size > 10 * 1024 * 1024) {
          showToast('文件过大，请小于 10MB', 'error');
          return;
        }
        const formData = new FormData();
        formData.append('file', file);
        if (text) formData.append('free_text', text);
        response = await fetch(`${apiBase()}/profile/analyze-upload`, {
          method: 'POST',
          body: formData,
        });
      } else {
        response = await fetch(`${apiBase()}/profile/analyze`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ free_text: text }),
        });
      }

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(errText || `HTTP ${response.status}`);
      }

      const data = await response.json();
      state.profile = data.profile;
      renderProfile(state.profile, data);
      renderRoleRecommendations(data.role_recommendations || []);
      statusEl.textContent = '画像解析完成';
      showToast('画像解析完成', 'success');
    } catch (err) {
      console.error(err);
      statusEl.textContent = '解析失败';
      showToast(`画像解析失败：${err.message || '未知错误'}`, 'error');
    } finally {
      button.disabled = false;
    }
  }

  function loadSampleProfile() {
    const freeText = $('#freeText');
    if (freeText) {
      freeText.value = sampleFreeText;
    }
    state.profile = JSON.parse(JSON.stringify(sampleProfile));
    renderProfile(state.profile, { course_enrichment_notes: ['已填充示例数据（未调用后端）'] });
    renderRoleRecommendations([]);
    setText('#analyzeStatus', '已填充示例画像');
    showToast('已填充示例画像，可直接用于匹配', 'success');
  }

  function clearProfile() {
    const freeText = $('#freeText');
    const fileInput = $('#resumeFile');
    if (freeText) freeText.value = '';
    if (fileInput) fileInput.value = '';
    state.profile = null;
    renderProfile(null);
    resetMatchResult();
    renderRoleRecommendations(null);
    setText('#analyzeStatus', '尚未调用');
    const preview = $('#preview');
    if (preview) preview.src = 'about:blank';
    showToast('已清空画像表单');
    state.deliveredHashes = new Set();
    state.lastSearchPayload = null;
  }

  function ensureProfile() {
    if (state.profile) return state.profile;
    showToast('请先完成画像解析或使用“填充示例”', 'error');
    return null;
  }

  function ensureJD(card) {
    if (card?.jdData) return card.jdData;
    if (state.jd) return state.jd;
    showToast('请先解析 JD', 'error');
    return null;
  }

  async function fetchJD(card) {
    const job = card.jobData;
    const jdUrl = job?.jd_url;
    if (!jdUrl) {
      showToast('该职位没有提供 JD 链接', 'error');
      return;
    }
    const fetchBtn = card.querySelector('[data-action="fetch"]');
    if (!fetchBtn) return;

    const renderToggle = $('#renderToggle');
    const render = !!renderToggle?.checked;
    const jdBlock = card.querySelector('.jd-block');

    try {
      fetchBtn.disabled = true;
      fetchBtn.textContent = '解析中...';
      const response = await fetch(`${apiBase()}/jd/fetch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jd_url: jdUrl, render, debug: false }),
      });
      if (!response.ok) {
        const err = await response.text();
        throw new Error(err || `HTTP ${response.status}`);
      }
      const data = await response.json();
      card.jdData = data.jd;
      state.jd = data.jd;
      state.job = job;
      if (jdBlock) {
        jdBlock.textContent = JSON.stringify(data.jd, null, 2);
        jdBlock.classList.add('visible');
      }
      showToast('JD 解析成功', 'success');
    } catch (err) {
      console.error(err);
      showToast(`JD 解析失败：${err.message || '未知错误'}`, 'error');
    } finally {
      fetchBtn.disabled = false;
      fetchBtn.textContent = '解析 JD';
    }
  }

  async function matchJob(card) {
    const profile = ensureProfile();
    if (!profile) return;
    const jd = ensureJD(card);
    if (!jd) return;

    const matchBtn = card.querySelector('[data-action="match"]');
    if (!matchBtn) return;

    try {
      matchBtn.disabled = true;
      matchBtn.textContent = '匹配中...';
      const response = await fetch(`${apiBase()}/matching/match`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile, jd }),
      });
      if (!response.ok) {
        const err = await response.text();
        throw new Error(err || `HTTP ${response.status}`);
      }
      const data = await response.json();
      state.lastMatch = { data, job: card.jobData };
      renderMatchResult(data, card.jobData);
      showToast('匹配完成', 'success');
    } catch (err) {
      console.error(err);
      showToast(`匹配失败：${err.message || '未知错误'}`, 'error');
    } finally {
      matchBtn.disabled = false;
      matchBtn.textContent = '匹配';
    }
  }

  function renderMatchResult(result, job) {
    const matchEl = $('#matchResult');
    if (!matchEl) return;

    const score = typeof result.score === 'number' ? Math.round(result.score) : '—';
    const reasons = (result.reasons || []).map((r) => `<li>${r}</li>`).join('');
    const gaps = (result.gaps || []).map((g) => `<li>${g}</li>`).join('');
    const recommendations = (result.recommendations || [])
      .map((r) => `<li>${r}</li>`)
      .join('');

    matchEl.classList.remove('muted');
    matchEl.innerHTML = `
      <div><strong>匹配得分 ${score}</strong> · ${job?.title || '职位'}</div>
      ${job?.company ? `<div class="muted">${job.company}</div>` : ''}
      ${
        reasons
          ? `<div><strong>亮点</strong><ul>${reasons}</ul></div>`
          : '<div class="muted">暂无亮点说明</div>'
      }
      ${
        gaps
          ? `<div><strong>差距</strong><ul>${gaps}</ul></div>`
          : '<div class="muted">暂未识别出差距</div>'
      }
      ${
        recommendations
          ? `<div><strong>建议</strong><ul>${recommendations}</ul></div>`
          : ''
      }
    `;
  }

  async function previewResume(card) {
    const profile = ensureProfile();
    if (!profile) return;
    const jd = ensureJD(card);
    if (!jd) return;

    const previewBtn = card.querySelector('[data-action="preview"]');
    const iframe = $('#preview');
    if (!previewBtn || !iframe) return;

    try {
      previewBtn.disabled = true;
      previewBtn.textContent = '生成中...';
      const response = await fetch(`${apiBase()}/resume/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile,
          jd,
          template_id: 'resume-ats-en',
          language: 'en',
          polish: true,
        }),
      });
      if (!response.ok) {
        const err = await response.text();
        throw new Error(err || `HTTP ${response.status}`);
      }
      const data = await response.json();
      const blob = new Blob([data.html], { type: 'text/html' });
      iframe.src = URL.createObjectURL(blob);
      showToast('预览已生成', 'success');
    } catch (err) {
      console.error(err);
      showToast(`预览生成失败：${err.message || '未知错误'}`, 'error');
    } finally {
      previewBtn.disabled = false;
      previewBtn.textContent = '预览';
    }
  }

  function toggleJD(card) {
    const block = card.querySelector('.jd-block');
    if (!block || !block.textContent) {
      showToast('请先解析 JD', 'error');
      return;
    }
    block.classList.toggle('visible');
  }

  function createJobCard(job) {
    const card = document.createElement('article');
    card.className = 'job-card';
    card.jobData = job;
    card.jdData = null;
    card.innerHTML = `
      <h3>${job.title || '未知职位'}<span>${job.company || ''}</span></h3>
      <div class="job-meta">
        ${job.source ? `<span>来源：${job.source}</span>` : ''}
        ${job.location ? `<span>地区：${job.location}</span>` : ''}
      </div>
      <div class="job-actions">
        <a href="${job.jd_url || '#'}" target="_blank" rel="noopener">打开 JD</a>
        <button class="btn outline small" data-action="fetch">解析 JD</button>
        <button class="btn outline small" data-action="match">匹配</button>
        <button class="btn outline small" data-action="preview">预览</button>
        <button class="btn ghost small" data-action="toggle">展开原文</button>
      </div>
      <pre class="jd-block"></pre>
    `;

    card.querySelector('[data-action="fetch"]')?.addEventListener('click', () => fetchJD(card));
    card.querySelector('[data-action="match"]')?.addEventListener('click', () => matchJob(card));
    card.querySelector('[data-action="preview"]')?.addEventListener('click', () => previewResume(card));
    card.querySelector('[data-action="toggle"]')?.addEventListener('click', () => toggleJD(card));

    return card;
  }

  function buildSearchPayload() {
    const parseList = (value) =>
      value
        .split(',')
        .map((v) => v.trim())
        .filter(Boolean);
    const sessionId = $('#sessionId').value || '';
    const limit = Number($('#limit').value || 10);
    const seekCount = Number($('#seekCount').value || 0);
    const linkedinCount = Number($('#linkedinCount').value || 0);
    return {
      session_id: sessionId,
      query: {
        titles: parseList($('#titles').value || ''),
        keywords: parseList($('#keywords').value || ''),
        locations: parseList($('#locations').value || 'AU'),
      },
      allocation: {
        seek: seekCount,
        linkedin: linkedinCount,
      },
      limit,
    };
  }

  function startStream() {
    stopStream();
    resetMatchResult();
    const jobsEl = $('#jobs');
    if (jobsEl) {
      jobsEl.classList.add('empty');
      jobsEl.innerHTML = '<p>正在等待职位流...</p>';
    }
    setText('#progress', '等待返回职位...');

    const payload = buildSearchPayload();
    state.lastSearchPayload = payload;
    state.deliveredHashes = new Set();

    const query = new URLSearchParams({
      session_id: payload.session_id || '',
      titles: (payload.query.titles || []).join(','),
      keywords: (payload.query.keywords || []).join(','),
      locations: (payload.query.locations || []).join(',') || 'AU',
      seek: String(payload.allocation.seek ?? 0),
      linkedin: String(payload.allocation.linkedin ?? 0),
      limit: String(payload.limit ?? 10),
    });

    const es = new EventSource(`${apiBase()}/jobs/stream?${query.toString()}`);
    state.es = es;

    es.addEventListener('job', (event) => {
      try {
        const job = JSON.parse(event.data);
        const list = $('#jobs');
        if (!list) return;
        if (list.classList.contains('empty')) {
          list.classList.remove('empty');
          list.innerHTML = '';
        }
        if (job.hash) {
          state.deliveredHashes.add(job.hash);
        }
        list.appendChild(createJobCard(job));
      } catch (err) {
        console.error(err);
      }
    });

    es.addEventListener('progress', (event) => {
      try {
        const progress = JSON.parse(event.data);
        setText(
          '#progress',
          `进度：${progress.delivered ?? 0} / ${progress.requested ?? ''}`
        );
      } catch (err) {
        console.error(err);
      }
    });

    es.addEventListener('end', () => {
      setText('#progress', '进度：已完成');
      stopStream();
    });

    es.onerror = () => {
      showToast('职位流连接中断，如有需要请重试', 'error');
      stopStream();
    };

    setTimeout(() => {
      const list = $('#jobs');
      if (list?.classList.contains('empty')) {
        setText(
          '#progress',
          '暂无职位返回，可尝试减少来源数量、降低总限制或仅使用 Seek。'
        );
      }
    }, 5000);
  }

  function stopStream() {
    if (state.es) {
      state.es.close();
      state.es = null;
      showToast('已停止职位流', 'info');
    }
  }

  async function fetchNextBatch() {
    const btn = $('#nextBatch');
    if (btn) btn.disabled = true;
    try {
      const payload = buildSearchPayload();
      payload.exclude_hashes = Array.from(state.deliveredHashes || []);
      state.lastSearchPayload = payload;
      const response = await fetch(`${apiBase()}/jobs/next-batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const err = await response.text();
        throw new Error(err || `HTTP ${response.status}`);
      }
      const data = await response.json();
      const jobs = data.jobs || [];
      if (!jobs.length) {
        showToast('没有更多新的岗位，试试调整关键词或地区', 'info');
        return;
      }
      const list = $('#jobs');
      if (list && list.classList.contains('empty')) {
        list.classList.remove('empty');
        list.innerHTML = '';
      }
      jobs.forEach((job) => {
        if (job.hash) {
          state.deliveredHashes.add(job.hash);
        }
        $('#jobs')?.appendChild(createJobCard(job));
      });
      const progress = $('#progress');
      if (progress) {
        progress.textContent = `已追加 ${jobs.length} 个新岗位（累计 ${state.deliveredHashes.size} 个）`;
      }
      showToast(`已获取 ${jobs.length} 个新岗位`, 'success');
    } catch (err) {
      console.error(err);
      showToast(`继续查找失败：${err.message || '未知错误'}`, 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function download(kind) {
    const profile = ensureProfile();
    if (!profile) return;
    const jd = state.jd;
    if (!jd) {
      showToast('请先解析 JD 并生成预览', 'error');
      return;
    }

    try {
      const endpoint = kind === 'docx' ? '/resume/file/docx' : '/resume/file/pdf';
      const response = await fetch(`${apiBase()}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile,
          jd,
          template_id: 'resume-ats-en',
          language: 'en',
          polish: true,
        }),
      });
      if (!response.ok) {
        const err = await response.text();
        throw new Error(err || `HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = kind === 'docx' ? 'resume.docx' : 'resume.pdf';
      document.body.appendChild(link);
      link.click();
      link.remove();
      showToast(kind === 'docx' ? '已导出 DOCX' : '已导出 PDF', 'success');
    } catch (err) {
      console.error(err);
      showToast(`导出失败：${err.message || '未知错误'}`, 'error');
    }
  }

  async function pingApi() {
    const status = $('#pingStatus');
    if (!status) return;
    try {
      status.textContent = '检测中...';
      const response = await fetch(`${apiBase()}/profile/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      status.textContent = response.ok ? 'API 可用' : `API 异常：${response.status}`;
      showToast(status.textContent, response.ok ? 'success' : 'error');
    } catch (err) {
      status.textContent = '无法连接 API';
      showToast('无法连接 API，请检查服务或跨域设置', 'error');
    }
  }

  async function fetchRoleRecommendations(triggeredByAnalyze = false) {
    const profile = ensureProfile();
    if (!profile) return;
    const statusEl = $('#roleRecommendStatus');
    const btn = $('#roleRecommendBtn');
    try {
      if (statusEl) statusEl.textContent = '智能匹配中...';
      if (btn && !triggeredByAnalyze) btn.disabled = true;
      const response = await fetch(`${apiBase()}/profile/recommend-roles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile, limit: 5 }),
      });
      if (!response.ok) {
        const err = await response.text();
        throw new Error(err || `HTTP ${response.status}`);
      }
      const data = await response.json();
      renderRoleRecommendations(data.role_recommendations || []);
      if (!triggeredByAnalyze) {
        showToast('岗位推荐已更新', 'success');
      }
      if (statusEl) {
        statusEl.textContent =
          (data.role_recommendations || []).length > 0
            ? `共推荐 ${(data.role_recommendations || []).length} 个岗位`
            : '暂无推荐岗位，可补充技能后重试';
      }
    } catch (err) {
      console.error(err);
      if (statusEl) statusEl.textContent = '推荐失败';
      showToast(`岗位推荐失败：${err.message || '未知错误'}`, 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function bindEvents() {
    $('#analyzeProfile')?.addEventListener('click', analyzeProfile);
    $('#loadSample')?.addEventListener('click', loadSampleProfile);
    $('#clearProfile')?.addEventListener('click', clearProfile);
    $('#startStream')?.addEventListener('click', startStream);
    $('#stopStream')?.addEventListener('click', stopStream);
    $('#nextBatch')?.addEventListener('click', fetchNextBatch);
    $('#downloadDocx')?.addEventListener('click', () => download('docx'));
    $('#downloadPdf')?.addEventListener('click', () => download('pdf'));
    $('#pingApi')?.addEventListener('click', pingApi);
    $('#roleRecommendBtn')?.addEventListener('click', () => fetchRoleRecommendations(false));
    $('#toggleAdvanced')?.addEventListener('click', toggleAdvancedPanel);

    const dropzone = $('#dropzone');
    const fileInput = $('#resumeFile');
    if (dropzone && fileInput) {
      ['dragenter', 'dragover'].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
          event.preventDefault();
          dropzone.classList.add('hover');
        });
      });
      ['dragleave', 'drop'].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
          event.preventDefault();
          dropzone.classList.remove('hover');
        });
      });
      dropzone.addEventListener('drop', (event) => {
        const files = event.dataTransfer?.files;
        if (files && files.length) {
          fileInput.files = files;
          showToast(`已选择文件：${files[0].name}`);
        }
      });
    }
  }

  function init() {
    bindEvents();
    pingApi();
    renderProfile(null);
    resetMatchResult();
    renderRoleRecommendations(null);
    state.deliveredHashes = new Set();
    state.lastSearchPayload = null;
    const status = $('#pingStatus');
    if (status && !status.textContent) {
      status.textContent = '前端已就绪';
    }
    const panel = $('#advancedSettings');
    if (panel && !panel.classList.contains('hidden')) {
      panel.classList.add('hidden');
    }
  }

  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', init)
    : init();
})();

