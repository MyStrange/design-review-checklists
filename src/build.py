"""Сборка статической HTML-страницы из data/checklists.json.

Дизайн повторяет исходный артефакт (светлая тема, Golos Text, сайдбар встреч,
карточки по дизайнерам, теги, зелёные чекбоксы, localStorage) и добавляет режим
«Дизайнеры»: выбираешь дизайнера — видишь только его правки по всем встречам.

Страница самодостаточна (один index.html), хостится где угодно.
"""
import html
import json
from datetime import datetime

from . import config

RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #DCE4EF; font-family: 'Golos Text', sans-serif; font-size: 15px; line-height: 1.5; min-height: 100vh; display: flex; color: #1a1a1a; }
.sidebar { width: 220px; flex-shrink: 0; background: #fff; padding: 24px 0; display: flex; flex-direction: column; position: fixed; top: 0; left: 0; bottom: 0; overflow-y: auto; }
.mode-toggle { display: flex; gap: 4px; margin: 0 16px 16px; background: #f0f0ee; border-radius: 8px; padding: 3px; }
.mode-btn { flex: 1; text-align: center; font-size: 12px; font-weight: 600; padding: 6px 4px; border-radius: 6px; cursor: pointer; color: #999; border: none; background: transparent; font-family: inherit; transition: all .12s; }
.mode-btn.active { background: #fff; color: #1a1a1a; }
.sidebar-title { font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: #bbb; padding: 0 20px; margin-bottom: 12px; }
.nav-item { padding: 10px 20px; cursor: pointer; transition: background .12s; border-left: 2px solid transparent; }
.nav-item:hover { background: #fafafa; }
.nav-item.active { border-left-color: #1a1a1a; background: #DCE4EF; }
.nav-main { font-size: 14px; font-weight: 600; color: #1a1a1a; }
.nav-item:not(.active) .nav-main { color: #888; font-weight: 500; }
.nav-sub { font-size: 12px; color: #bbb; margin-top: 1px; }
.nav-empty { padding: 10px 20px; color: #bbb; font-size: 13px; }
.nav-divider { height: 1px; background: #cdd6e4; margin: 12px 16px 10px; }
.main { margin-left: 220px; flex: 1; padding: 40px 40px 80px; max-width: 800px; }
.session-header { margin-bottom: 28px; }
.session-meta { font-size: 12px; color: #999; margin-bottom: 6px; letter-spacing: 0.04em; }
h1 { font-size: 60px; font-weight: 600; color: #1a1a1a; letter-spacing: -0.02em; line-height: 1.05; }
.crown-h1 { font-size: 34px; vertical-align: middle; }
.card-date { font-size: 12px; font-weight: 600; color: #999; margin: 22px 0 8px 2px; }
.card-date:first-child { margin-top: 0; }
.project { background: #fff; border-radius: 20px; margin-bottom: 14px; overflow: hidden; }
.project-header { padding: 18px 20px; display: flex; align-items: center; justify-content: space-between; cursor: pointer; user-select: none; gap: 12px; }
.project-header:hover { background: #fafafa; }
.author { font-size: 15px; font-weight: 600; color: #1a1a1a; }
.project-name { font-size: 13px; color: #999; margin-top: 1px; }
.project-right { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.count { font-size: 13px; color: #bbb; font-weight: 500; }
.count.done { color: #199AF0; }
.chevron { color: #ccc; font-size: 11px; transition: transform 0.2s; }
.project.collapsed .chevron { transform: rotate(-90deg); }
.project.collapsed .tasks { display: none; }
.tasks { border-top: 1px solid #f0f0f0; }
.task { display: flex; align-items: flex-start; gap: 12px; padding: 14px 20px; border-bottom: 1px solid #f0f0f0; cursor: pointer; }
.task:last-child { border-bottom: none; }
.task:hover { background: #fafafa; }
.checkbox { width: 17px; height: 17px; border-radius: 4px; border: 1.5px solid #d0d0d0; flex-shrink: 0; margin-top: 2px; display: flex; align-items: center; justify-content: center; transition: all .15s; background: #fff; }
.task.checked .checkbox { background: #199AF0; border-color: #199AF0; }
.task.checked .checkbox::after { content: ''; width: 4px; height: 8px; border: solid #fff; border-width: 0 2px 2px 0; transform: rotate(45deg); margin-top: -2px; }
.task-text { font-size: 14px; color: #333; flex: 1; padding-top: 1px; }
.task.checked .task-text { color: #bbb; text-decoration: line-through; text-decoration-color: #ccc; }
.tag { display: inline-block; font-size: 10px; font-weight: 600; letter-spacing: 0.05em; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; margin-left: 6px; vertical-align: middle; position: relative; top: -1px; }
.tag.ux { color: #e07b3a; background: #fef0e6; }
.tag.dev { color: #3a7be0; background: #e6effe; }
.tag.discuss { color: #9b59b6; background: #f5edfc; }
.placeholder { color: #bbb; text-align: center; padding: 80px 20px; }
.reset-btn { position: fixed; bottom: 24px; right: 24px; background: #fff; border: 1px solid #e0e0e0; color: #999; font-family: 'Golos Text', sans-serif; font-size: 12px; padding: 8px 14px; border-radius: 8px; cursor: pointer; transition: all .15s; }
.reset-btn:hover { color: #555; border-color: #bbb; }
@media (max-width: 640px) {
  body { flex-direction: column; }
  .sidebar { width: 100%; position: static; padding: 12px 0; }
  .mode-toggle { margin: 0 12px 10px; }
  .sidebar-title { display: none; }
  #nav-list { display: flex; overflow-x: auto; gap: 4px; padding: 0 8px; }
  .nav-item { flex-shrink: 0; border-left: none; border-bottom: 2px solid transparent; padding: 6px 12px; border-radius: 8px; }
  .nav-item.active { border-bottom-color: #1a1a1a; background: #DCE4EF; }
  .main { margin-left: 0; padding: 24px 16px 80px; }
  h1 { font-size: 38px; }
}
"""

JS = """
const DATA = /*__DATA__*/;
const STORAGE_KEY = 'review-state-v3';
let state = (()=>{ try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); } catch(e){ return {}; } })();
const save = ()=> localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
const tagLabel = { ux:'UX', dev:'Разработка', discuss:'Уточнить' };

function esc(s){ return (''+s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function plural(n,a,b,c){ const m=n%100, d=n%10; if(m>=11&&m<=14) return c; if(d===1) return a; if(d>=2&&d<=4) return b; return c; }

const projById = {};
DATA.sessions.forEach(s=> s.projects.forEach(p=>{ projById[p.id]=p; }));
const DIDX = {};
DATA.sessions.forEach(s=> s.projects.forEach(p=>{ (DIDX[p.author]=DIDX[p.author]||[]).push({ dateLabel:s.dateLabel, sid:s.id, project:p }); }));
function meetingsOf(n){ const seen={}; DIDX[n].forEach(e=>{ seen[e.sid]=1; }); return Object.keys(seen).length; }
// сортируем по активности: кто чаще приходил — выше; разово заходившие опускаются вниз
const designerNames = Object.keys(DIDX).sort((a,b)=>{ const d=meetingsOf(b)-meetingsOf(a); return d!==0 ? d : a.localeCompare(b,'ru'); });
const maxMeetings = designerNames.length ? Math.max(...designerNames.map(meetingsOf)) : 0;
// корона тем, кто ходил больше всех (если у лидера хотя бы 2 встречи)
function isTop(n){ return maxMeetings>=2 && meetingsOf(n)===maxMeetings; }

let mode='designers', sIdx=0, dIdx=0;
const elNav=document.getElementById('nav-list');
const elMain=document.getElementById('main');

function countDone(tasks){ let n=0; tasks.forEach(t=>{ if(state[t.id]) n++; }); return n; }
function taskHTML(t,projId){
  return `<div class="task ${state[t.id]?'checked':''}" id="task-${t.id}" onclick="toggleTask('${t.id}','${projId}')">
    <div class="checkbox"></div>
    <div class="task-text">${esc(t.text)}<span class="tag ${t.tag}">${tagLabel[t.tag]||''}</span></div></div>`;
}
function cardHTML(p,headline){
  const done=countDone(p.tasks), total=p.tasks.length;
  return `<div class="project" id="proj-${p.id}">
    <div class="project-header" onclick="toggleProj('${p.id}')">
      <div><div class="author">${esc(headline)}</div><div class="project-name">${esc(p.title)}</div></div>
      <div class="project-right"><div class="count ${done===total&&total>0?'done':''}" id="count-${p.id}">${done}/${total}</div><div class="chevron">▾</div></div>
    </div>
    <div class="tasks">${p.tasks.map(t=>taskHTML(t,p.id)).join('')}</div></div>`;
}
function emptyHTML(){ return '<div class="placeholder">Пока нет ни одного ревью.<br>Как только придёт первый конспект — он появится здесь.</div>'; }

function renderNav(){
  if(mode==='meetings'){
    if(!DATA.sessions.length){ elNav.innerHTML='<div class="nav-empty">Нет встреч</div>'; return; }
    elNav.innerHTML = DATA.sessions.map((s,i)=>`<div class="nav-item ${i===sIdx?'active':''}" onclick="selectSession(${i})">
      <div class="nav-main">${esc(s.dateLabel)}</div>
      <div class="nav-sub">${s.designersCount} ${plural(s.designersCount,'дизайнер','дизайнера','дизайнеров')}</div></div>`).join('');
  } else {
    if(!designerNames.length){ elNav.innerHTML='<div class="nav-empty">Нет дизайнеров</div>'; return; }
    const parts=[]; let prevMulti=null;
    designerNames.forEach((n,i)=>{
      const mc=meetingsOf(n);
      if(prevMulti===true && mc===1) parts.push('<div class="nav-divider"></div>');
      prevMulti = mc>1;
      const crown = isTop(n) ? ' <span class="crown">👑</span>' : '';
      parts.push(`<div class="nav-item ${i===dIdx?'active':''}" onclick="selectDesigner(${i})">
        <div class="nav-main">${esc(n)}${crown}</div>
        <div class="nav-sub">${mc} ${plural(mc,'встреча','встречи','встреч')}</div></div>`);
    });
    elNav.innerHTML = parts.join('');
  }
}
function renderMain(){
  if(mode==='meetings'){
    const s=DATA.sessions[sIdx];
    if(!s){ elMain.innerHTML=emptyHTML(); return; }
    elMain.innerHTML = `<div class="session-header"><h1>Чеклист правок</h1></div>`
      + (s.projects.map(p=>cardHTML(p,p.author)).join('') || emptyHTML());
  } else {
    const n=designerNames[dIdx];
    if(!n){ elMain.innerHTML=emptyHTML(); return; }
    const crownH = isTop(n) ? ' <span class="crown-h1">👑</span>' : '';
    elMain.innerHTML = `<div class="session-header"><h1>${esc(n)}${crownH}</h1></div>`
      + DIDX[n].map(x=>cardHTML(x.project,x.dateLabel)).join('');
  }
}
function render(){ renderNav(); renderMain(); }
function setMode(m){ if(mode===m) return; mode=m;
  document.getElementById('mb-meetings').classList.toggle('active', m==='meetings');
  document.getElementById('mb-designers').classList.toggle('active', m==='designers');
  render(); }
function selectSession(i){ sIdx=i; render(); }
function selectDesigner(i){ dIdx=i; render(); }
function toggleProj(id){ const el=document.getElementById('proj-'+id); if(el) el.classList.toggle('collapsed'); }
function toggleTask(taskId,projId){
  state[taskId]=!state[taskId]; save();
  const te=document.getElementById('task-'+taskId); if(te) te.classList.toggle('checked', state[taskId]);
  const p=projById[projId]; if(p){ const done=countDone(p.tasks), total=p.tasks.length;
    const ce=document.getElementById('count-'+projId); if(ce){ ce.textContent=done+'/'+total; ce.className='count'+(done===total&&total>0?' done':''); } }
}
function resetCurrent(){
  if(!confirm('Сбросить все отметки в этом разделе?')) return;
  let tasks=[];
  if(mode==='meetings'){ const s=DATA.sessions[sIdx]; if(s) s.projects.forEach(p=>tasks.push(...p.tasks)); }
  else { const n=designerNames[dIdx]; (DIDX[n]||[]).forEach(x=>tasks.push(...x.project.tasks)); }
  tasks.forEach(t=> delete state[t.id]); save(); renderMain();
}
render();
"""

TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>__TITLE__</title>
<link href="https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600&display=swap" rel="stylesheet">
<style>__CSS__</style>
</head>
<body>
<nav class="sidebar">
  <div class="mode-toggle">
    <button class="mode-btn active" id="mb-designers" onclick="setMode('designers')">Дизайнеры</button>
    <button class="mode-btn" id="mb-meetings" onclick="setMode('meetings')">Встречи</button>
  </div>
  <div id="nav-list"></div>
</nav>
<main class="main" id="main"></main>
<button class="reset-btn" onclick="resetCurrent()">Сбросить</button>
<script>__JS__</script>
</body>
</html>
"""


def _date_label(iso):
    try:
        dt = datetime.strptime(iso, "%Y-%m-%d")
        return "%d %s" % (dt.day, RU_MONTHS[dt.month - 1])
    except Exception:
        return iso or "без даты"


def _meta(iso, part, weekday):
    try:
        dt = datetime.strptime(iso, "%Y-%m-%d")
        head = "%d %s %d" % (dt.day, RU_MONTHS[dt.month - 1], dt.year)
    except Exception:
        head = iso or "без даты"
    suffix = " · ".join([x for x in (part, weekday) if x]) or "дизайна"
    return "%s · Ревью %s" % (head, suffix)


def _to_data(sessions):
    """Преобразует наши данные в структуру, которую рендерит JS на странице."""
    out = []
    # новые встречи сверху
    ordered = sorted(sessions, key=lambda s: s.get("date") or "", reverse=True)
    for i, s in enumerate(ordered):
        iso = s.get("date") or ""
        sid = "s" + iso.replace("-", "")
        if s.get("part"):
            sid += "p" + "".join(ch for ch in s["part"] if ch.isdigit())
        sid += "i%d" % i
        projects = []
        names = set()
        for di, d in enumerate(s.get("designers", [])):
            raw_name = d.get("name") or "Не указан"
            author = config.NAME_MAP.get(raw_name, raw_name)
            names.add(author)
            for pi, p in enumerate(d.get("projects", [])):
                projects.append({
                    "id": "%s-%d-%d" % (sid, di, pi),
                    "author": author,
                    "title": p.get("name") or "Без названия",
                    "tasks": [
                        {"id": it.get("id", ""), "text": it.get("text", ""),
                         "tag": it.get("tag", "ux")}
                        for it in p.get("items", [])
                    ],
                })
        out.append({
            "id": sid,
            "date": iso,
            "dateLabel": _date_label(iso),
            "meta": _meta(iso, s.get("part", ""), s.get("weekday", "")),
            "designersCount": len([n for n in names if n]),
            "projects": projects,
        })
    return {"sessions": out}


def build_html(data):
    payload = _to_data(data.get("sessions", []))
    data_json = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")
    js = JS.replace("/*__DATA__*/", data_json)
    return (TEMPLATE
            .replace("__TITLE__", html.escape(config.SITE_TITLE))
            .replace("__CSS__", CSS)
            .replace("__JS__", js))


def build_site(data):
    config.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (config.DOCS_DIR / "index.html").write_text(build_html(data), encoding="utf-8")
    (config.DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")
    (config.DOCS_DIR / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    print("Страница собрана:", config.DOCS_DIR / "index.html")
