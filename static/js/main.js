/* main.js — lightweight UI helpers, no framework required */

// ── Keywords tag input ───────────────────────────────────────────────

function handleKwInput(e, fieldName) {
  if (e.key === 'Enter' || e.key === ',') {
    e.preventDefault();
    const input = e.target;
    const val = input.value.trim().replace(/,$/, '');
    if (val) {
      addPill(fieldName, val);
      input.value = '';
    }
  } else if (e.key === 'Backspace' && e.target.value === '') {
    const pillsRow = document.getElementById(`pills_${fieldName}`);
    const pills = pillsRow.querySelectorAll('.pill-editable');
    if (pills.length > 0) {
      pills[pills.length - 1].remove();
      syncHidden(fieldName);
    }
  }
}

function addPill(fieldName, text) {
  const pillsRow = document.getElementById(`pills_${fieldName}`);
  const pill = document.createElement('span');
  pill.className = 'pill pill-editable';
  pill.innerHTML = `${escHtml(text)}<button type="button" class="pill-remove" onclick="removePill(this)">✕</button>`;
  pillsRow.appendChild(pill);
  syncHidden(fieldName);
}

function removePill(btn) {
  const pill = btn.closest('.pill-editable');
  const fieldName = pill.closest('[id^="kw_"]').id.replace('kw_', '');
  pill.remove();
  syncHidden(fieldName);
}

function syncHidden(fieldName) {
  const pillsRow = document.getElementById(`pills_${fieldName}`);
  const pills = pillsRow.querySelectorAll('.pill-editable');
  const values = Array.from(pills).map(p => p.childNodes[0].textContent.trim());
  document.getElementById(`kw_hidden_${fieldName}`).value = JSON.stringify(values);
}

function escHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Multilingual toggle ──────────────────────────────────────────────

function toggleHiddenLangs(btn) {
  const wrap = btn.closest('.multilingual-wrap');
  const hidden = wrap.querySelectorAll('.lang-row-hidden');
  if (hidden.length > 0) {
    hidden.forEach(r => r.classList.remove('lang-row-hidden'));
    btn.textContent = '− hide empty languages';
  } else {
    // Re-hide rows that are still empty
    wrap.querySelectorAll('.lang-row').forEach(r => {
      const input = r.querySelector('input');
      if (input && input.value.trim() === '') {
        r.classList.add('lang-row-hidden');
      }
    });
    btn.textContent = '+ show all languages';
  }
}

// ── Setup page: tab switching ────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;
      tabBtns.forEach(b => b.classList.toggle('active', b.dataset.tab === target));
      document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.style.display = panel.id === `tab-${target}` ? '' : 'none';
      });
    });
  });
});

// ── Setup page: schema editor (add / remove field rows) ──────────────

document.addEventListener('DOMContentLoaded', () => {
  const tbody = document.getElementById('fields-tbody');
  const countInput = document.getElementById('field-count');
  const addBtn = document.getElementById('add-field');
  const template = document.getElementById('field-row-template');
  if (!tbody || !addBtn || !template) return;

  function currentCount() { return parseInt(countInput.value, 10); }

  function reindex() {
    const rows = tbody.querySelectorAll('tr.field-row');
    rows.forEach((row, i) => {
      row.querySelectorAll('input, select, textarea').forEach(el => {
        if (el.name) el.name = el.name.replace(/(field_\w+_)\d+/, `$1${i}`);
        if (el.dataset && el.dataset.idx !== undefined) el.dataset.idx = i;
      });
    });
    countInput.value = rows.length;
  }

  addBtn.addEventListener('click', () => {
    const idx = currentCount();
    const clone = template.content.cloneNode(true);
    clone.querySelectorAll('input, select, textarea').forEach(el => {
      if (el.name) el.name = el.name.replace('NEW', idx);
    });
    const typeSelect = clone.querySelector('.type-select');
    if (typeSelect) typeSelect.dataset.idx = idx;
    tbody.appendChild(clone);
    countInput.value = idx + 1;
    attachTypeListeners();
  });

  tbody.addEventListener('click', e => {
    if (e.target.classList.contains('remove-field')) {
      const row = e.target.closest('tr.field-row');
      // Also remove the companion lang-row if present
      const next = row.nextElementSibling;
      if (next && next.classList.contains('lang-row')) next.remove();
      row.remove();
      reindex();
    }
  });

  function attachTypeListeners() {
    tbody.querySelectorAll('.type-select').forEach(sel => {
      sel.removeEventListener('change', onTypeChange);
      sel.addEventListener('change', onTypeChange);
    });
  }

  function onTypeChange(e) {
    const sel = e.target;
    const row = sel.closest('tr.field-row');
    const idx = Array.from(tbody.querySelectorAll('tr.field-row')).indexOf(row);
    const next = row.nextElementSibling;
    if (sel.value === 'multilingual') {
      if (!next || !next.classList.contains('lang-row')) {
        const langRow = document.createElement('tr');
        langRow.className = 'lang-row';
        langRow.dataset.for = idx;
        langRow.innerHTML = `<td colspan="8" class="lang-cell">
          <label class="field-label small">Languages JSON</label>
          <textarea name="field_languages_${idx}" rows="3" placeholder='[{"code":"en","label":"English"}]'></textarea>
        </td>`;
        row.after(langRow);
      }
    } else {
      if (next && next.classList.contains('lang-row')) next.remove();
    }
  }

  attachTypeListeners();
});

// ── Image URL preview ────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.image-wrap input[type="text"]').forEach(input => {
    const fieldName = input.name;
    input.addEventListener('change', () => {
      const preview = document.getElementById(`preview_${fieldName}`);
      if (!preview) return;
      const url = input.value.trim();
      if (url) {
        if (preview.tagName === 'IMG') {
          preview.src = url;
        } else {
          const img = document.createElement('img');
          img.src = url;
          img.alt = '';
          img.className = 'image-preview';
          img.id = preview.id;
          preview.replaceWith(img);
        }
      }
    });
  });

  // Auto-submit search form on clear
  const searchInput = document.querySelector('.search-input');
  if (searchInput) {
    searchInput.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        searchInput.value = '';
        searchInput.form.submit();
      }
    });
  }
});
