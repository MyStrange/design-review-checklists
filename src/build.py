"""Сборка статической HTML-страницы из data/checklists.json.

Навигация: Дизайнер → Дата → Проект → пункты-чекбоксы.
Галочки сохраняются в localStorage браузера (личные у каждого).
Страница самодостаточна (один index.html), хостится где угодно.
"""
import html
from datetime import datetime

from . import config

CSS = """
:root{--bg:#0f1115;--card:#181b22;--line:#262b35;--fg:#e7e9ee;--muted:#9aa3b2;--accent:#5b8cff;--done:#5a6472}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--fg)}
.top{padding:20px 24px;border-bottom:1px solid var(--line)}
.top h1{margin:0;font-size:20px}
.hint{margin:4px 0 0;color:var(--muted);font-size:13px}
#app{padding:18px 24px;max-width:920px;margin:0 auto}
#designers{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px}
#designers button{background:var(--card);color:var(--fg);border:1px solid var(--line);padding:8px 14px;border-radius:999px;cursor:pointer;font-size:14px}
#designers button.active{background:var(--accent);border-color:var(--accent);color:#fff}
.dates{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px}
.dates button{background:transparent;color:var(--muted);border:1px solid var(--line);padding:6px 12px;border-radius:8px;cursor:pointer;font-size:13px}
.dates button.active{color:var(--fg);border-color:var(--accent)}
.project{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:14px}
.project h3{margin:0 0 10px;font-size:16px}
ul.items{list-style:none;margin:0;padding:0}
.item{padding:7px 0;border-top:1px solid var(--line)}
.item:first-child{border-top:none}
.item label{display:flex;align-items:flex-start;gap:10px;cursor:pointer}
.item input{margin-top:3px;width:17px;height:17px;accent-color:var(--accent);flex:none}
.item.done .txt{text-decoration:line-through;color:var(--done)}
.empty{color:var(--muted);margin:0;font-size:13px}
.placeholder{color:var(--muted);text-align:center;padding:60px 20px}
"""

JS = """
(function(){
  var KEY='dr_checked_v1';
  function load(){try{return new Set(JSON.parse(localStorage.getItem(KEY)||'[]'))}catch(e){return new Set()}}
  function save(s){try{localStorage.setItem(KEY,JSON.stringify(Array.from(s)))}catch(e){}}
  var checked=load();
  document.querySelectorAll('input[type=checkbox][data-id]').forEach(function(cb){
    var id=cb.getAttribute('data-id');
    if(checked.has(id)){cb.checked=true;cb.closest('.item').classList.add('done');}
    cb.addEventListener('change',function(){
      var li=cb.closest('.item');
      if(cb.checked){checked.add(id);li.classList.add('done');}
      else{checked.delete(id);li.classList.remove('done');}
      save(checked);
    });
  });
  function selectDate(id){
    var panel=document.getElementById(id); if(!panel)return;
    var sec=panel.closest('.designer');
    sec.querySelectorAll('.date-panel').forEach(function(p){p.hidden=(p.id!==id);});
    sec.querySelectorAll('.dates button').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-target')===id);});
  }
  function selectDesigner(id){
    document.querySelectorAll('.designer').forEach(function(s){s.hidden=(s.id!==id);});
    document.querySelectorAll('#designers button').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-target')===id);});
    var sec=document.getElementById(id);
    var first=sec&&sec.querySelector('.dates button');
    if(first)selectDate(first.getAttribute('data-target'));
  }
  document.querySelectorAll('#designers button').forEach(function(b){b.onclick=function(){selectDesigner(b.getAttribute('data-target'));};});
  document.querySelectorAll('.dates button').forEach(function(b){b.onclick=function(){selectDate(b.getAttribute('data-target'));};});
  var firstD=document.querySelector('#designers button');
  if(firstD)selectDesigner(firstD.getAttribute('data-target'));
})();
"""


def fmt_date(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return iso or "без даты"


def _pivot(sessions):
    """name -> { date_iso: {weekday, part, projects:[...]} }"""
    designers = {}
    for s in sessions:
        for d in s.get("designers", []):
            name = d.get("name") or "Не указан"
            by_name = designers.setdefault(name, {})
            key = s.get("date") or ""
            entry = by_name.setdefault(
                key, {"weekday": s.get("weekday", ""), "part": s.get("part", ""), "projects": []}
            )
            entry["projects"].extend(d.get("projects", []))
    return designers


def _render_projects(projects):
    out = []
    for p in projects:
        out.append('<div class="project">')
        out.append("<h3>" + html.escape(p.get("name") or "Без названия") + "</h3>")
        items = p.get("items", [])
        if items:
            out.append('<ul class="items">')
            for it in items:
                iid = html.escape(it.get("id", ""))
                txt = html.escape(it.get("text", ""))
                out.append(
                    '<li class="item"><label><input type="checkbox" data-id="'
                    + iid
                    + '"><span class="txt">'
                    + txt
                    + "</span></label></li>"
                )
            out.append("</ul>")
        else:
            out.append('<p class="empty">Конкретных правок не зафиксировано.</p>')
        out.append("</div>")
    return "".join(out)


def build_html(data):
    sessions = data.get("sessions", [])
    designers = _pivot(sessions)

    body = []
    if not designers:
        body.append(
            '<div class="placeholder">Пока нет ни одного ревью.<br>'
            "Как только придёт первый конспект — он появится здесь.</div>"
        )
    else:
        nav = ['<nav id="designers">']
        sections = []
        for di, name in enumerate(sorted(designers.keys(), key=lambda x: x.lower())):
            did = "d%d" % di
            nav.append('<button data-target="' + did + '">' + html.escape(name) + "</button>")

            dates = designers[name]
            date_keys = sorted(dates.keys(), reverse=True)
            sec = ['<section class="designer" id="' + did + '" hidden>', '<div class="dates">']
            for ti, dk in enumerate(date_keys):
                tid = "%s-t%d" % (did, ti)
                meta = dates[dk]
                sub = [x for x in (meta.get("weekday", ""), meta.get("part", "")) if x]
                label = fmt_date(dk) + (" · " + " · ".join(sub) if sub else "")
                sec.append('<button data-target="' + tid + '">' + html.escape(label) + "</button>")
            sec.append("</div>")
            for ti, dk in enumerate(date_keys):
                tid = "%s-t%d" % (did, ti)
                sec.append('<div class="date-panel" id="' + tid + '" hidden>')
                sec.append(_render_projects(dates[dk]["projects"]))
                sec.append("</div>")
            sec.append("</section>")
            sections.append("".join(sec))
        nav.append("</nav>")
        body.append("".join(nav))
        body.append("<main>" + "".join(sections) + "</main>")

    title = html.escape(config.SITE_TITLE)
    return (
        '<!doctype html>\n<html lang="ru">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="robots" content="noindex, nofollow">\n'
        "<title>" + title + "</title>\n"
        "<style>" + CSS + "</style>\n"
        "</head>\n<body>\n"
        '<header class="top"><h1>' + title + "</h1>"
        '<p class="hint">Отметки галочками сохраняются только в этом браузере (на этом устройстве).</p></header>\n'
        '<div id="app">' + "".join(body) + "</div>\n"
        "<script>" + JS + "</script>\n"
        "</body>\n</html>\n"
    )


def build_site(data):
    config.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (config.DOCS_DIR / "index.html").write_text(build_html(data), encoding="utf-8")
    (config.DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")
    (config.DOCS_DIR / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    print("Страница собрана:", config.DOCS_DIR / "index.html")
