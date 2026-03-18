/* SITREP — main.js */

// Score color utility
function scoreClass(score) {
  score = parseInt(score) || 0;
  if (score >= 70) return 'high';
  if (score >= 40) return 'mid';
  return 'low';
}

// Score color hex
function scoreColor(score) {
  score = parseInt(score) || 0;
  if (score >= 70) return '#34d399';
  if (score >= 40) return '#fbbf24';
  return '#f87171';
}

// Copy to clipboard
function copyText(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    btn.style.color = '#34d399';
    setTimeout(() => { btn.textContent = orig; btn.style.color = ''; }, 2000);
  });
}

// Open modal
function openModal(id) {
  document.getElementById(id).classList.add('open');
  document.body.style.overflow = 'hidden';
}

// Close modal
function closeModal(id) {
  document.getElementById(id).classList.remove('open');
  document.body.style.overflow = '';
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('open');
    document.body.style.overflow = '';
  }
});

// Close on Escape
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open').forEach(m => {
      m.classList.remove('open');
    });
    document.body.style.overflow = '';
  }
});

// Format date
function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// Debounce
function debounce(fn, delay) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), delay); };
}

// Build mini bar HTML
function miniBar(pct, color) {
  return `<div class="source-bar-bg"><div class="source-bar-fill" style="width:${pct}%;background:${color}"></div></div>`;
}

// Skill tags HTML
function skillTags(skillStr) {
  if (!skillStr) return '<span style="color:var(--text-muted)">None listed</span>';
  return skillStr.split(',').map(s => s.trim()).filter(Boolean).map(s =>
    `<span class="skill-tag">${s}</span>`
  ).join('');
}

// Status color map
const STATUS_COLORS = {
  discovered:  { bg: 'var(--bg-elevated)',  text: 'var(--text-secondary)' },
  targeted:    { bg: 'var(--blue-bg)',      text: 'var(--blue)' },
  applied:     { bg: 'var(--purple-bg)',    text: 'var(--purple)' },
  interviewing:{ bg: 'var(--amber-bg)',     text: 'var(--amber)' },
  offer:       { bg: 'var(--green-bg)',     text: 'var(--green)' },
  rejected:    { bg: 'var(--red-bg)',       text: 'var(--red)' },
};

function statusBadge(status) {
  const c = STATUS_COLORS[status] || STATUS_COLORS.discovered;
  return `<span style="background:${c.bg};color:${c.text};padding:2px 9px;border-radius:20px;font-size:11px;font-family:var(--font-mono)">${status}</span>`;
}
