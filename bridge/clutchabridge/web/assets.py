"""Static assets: one stylesheet and one small script, inlined into the page."""

from __future__ import annotations

CSS = r"""
:root{
  color-scheme: light dark;
  --bg:#0e1014; --panel:#15181f; --panel-2:#1b1f28; --border:#242a35;
  --text:#d9dee8; --muted:#8b95a8; --dim:#5d6678;
  --accent:#8fc7ff; --accent-2:#b79cff; --accent-soft:#1d2b3d;
  --ok:#5fd39a; --warn:#f0c05a; --err:#ff8f8f;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;
  --radius:14px;
}
:root[data-theme="light"]{
  color-scheme: light;
  --bg:#f6f7fa; --panel:#ffffff; --panel-2:#f0f2f7; --border:#e3e7ef;
  --text:#1a2233; --muted:#5d6880; --dim:#8b94a8;
  --accent:#1c64c9; --accent-2:#6a3fc4; --accent-soft:#e8f0fd;
  --ok:#12855a; --warn:#9a6b06; --err:#c02a2a;
}
*{box-sizing:border-box}
html,body{margin:0}
body{
  background:var(--bg); color:var(--text);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;
  -webkit-font-smoothing:antialiased;
}
a{color:var(--accent); text-decoration:none}

/* header */
header.top{
  padding:26px 20px 14px; text-align:center; position:relative;
  border-bottom:1px solid var(--border);
  background:linear-gradient(180deg,var(--panel),transparent);
}
header.top h1{margin:0; font-size:22px; letter-spacing:.2px; font-weight:650}
header.top h1 .ver{
  font:600 11px/1 var(--mono); color:var(--accent); background:var(--accent-soft);
  padding:3px 7px; border-radius:999px; margin-left:8px; vertical-align:3px;
}
header.top .statusline{
  margin-top:7px; font-size:12.5px; color:var(--muted);
  display:flex; gap:8px; align-items:center; justify-content:center; flex-wrap:wrap;
}
/* The one diagram: app -> mailbox -> bridge -> pi. Wraps on narrow windows
   rather than shrinking to unreadable. */
.flow-row{display:flex; align-items:center; justify-content:center; gap:8px; flex-wrap:wrap; margin-top:4px}
.flow .node{
  border:1px solid var(--border); background:var(--panel-2); border-radius:10px;
  padding:7px 11px; display:flex; flex-direction:column; gap:1px; min-width:0;
}
.flow .node b{font-size:13px; font-weight:600}
.flow .node span{font-size:11px; color:var(--dim)}
.flow .node.here{border-color:var(--accent); background:var(--accent-soft)}
.flow .node.here b{color:var(--accent)}
.flow .arrow{font:600 11px/1 var(--mono); color:var(--dim); white-space:nowrap}
.flow .note{margin:10px 0 0; text-align:center}

.dot{width:8px; height:8px; border-radius:50%; background:var(--dim); display:inline-block}
.dot.ok{background:var(--ok); box-shadow:0 0 0 3px rgba(95,211,154,.15)}
.dot.warn{background:var(--warn)}
.dot.err{background:var(--err)}
.dot.busy{background:var(--accent); animation:pulse 1.2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
/* Both header buttons live in one absolutely positioned row: as separate
   absolute elements they would land on the same pixel and hide each other. */
.top-actions{position:absolute; top:18px; right:18px; display:flex; gap:8px; z-index:2}
.theme{
  width:36px; height:30px; padding:0;
  display:inline-flex; align-items:center; justify-content:center;
  border:1px solid var(--border); background:var(--panel-2); color:var(--text);
  border-radius:999px; cursor:pointer; font-size:14px; line-height:1;
}
/* The language chip holds two letters, so it needs a smaller size and its own
   tracking to sit optically centred against the theme glyph. */
#lang{font-size:11px; font-weight:650; letter-spacing:.04em}
.theme:hover{background:var(--panel)}

/* tabs */
nav.tabs{display:flex; justify-content:center; gap:6px; padding:14px 16px; flex-wrap:wrap}
nav.tabs a{
  padding:8px 18px; border-radius:999px; color:var(--muted); font-size:14px; font-weight:550;
  border:1px solid transparent;
}
nav.tabs a:hover{color:var(--text); background:var(--panel-2)}
nav.tabs a.on{color:var(--accent); background:var(--accent-soft); border-color:color-mix(in srgb,var(--accent) 30%,transparent)}

main{max-width:1080px; margin:0 auto; padding:8px 18px 48px}
footer{
  max-width:1080px; margin:0 auto; padding:0 18px 40px;
  color:var(--dim); font-size:12px;
  display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap;
}

/* cards */
.grid{display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(215px,1fr)); margin-bottom:14px}
.grid.two{grid-template-columns:repeat(auto-fit,minmax(330px,1fr))}
.card{
  background:var(--panel); border:1px solid var(--border); border-radius:var(--radius);
  padding:16px 18px; margin-bottom:14px;
}
.card > h2{
  margin:0 0 14px; font-size:12px; letter-spacing:.09em; text-transform:uppercase;
  color:var(--muted); font-weight:650; display:flex; justify-content:space-between; align-items:center; gap:10px;
}
.card > h2 .hint{font-size:11px; letter-spacing:0; text-transform:none; color:var(--dim); font-weight:400}
.card.tight{padding:14px 16px}

/* stats */
.stat .label{font-size:11.5px; letter-spacing:.07em; text-transform:uppercase; color:var(--muted)}
.stat .value{font-size:26px; font-weight:600; margin-top:6px; letter-spacing:-.4px}
.stat .value.small{font-size:17px; font-weight:550}
.stat .sub{font-size:12px; color:var(--dim); margin-top:4px; min-height:16px}
.stat .value.ok{color:var(--ok)} .stat .value.err{color:var(--err)} .stat .value.warn{color:var(--warn)}

/* charts */
.chart{width:100%; overflow:hidden}
.chart svg{display:block; width:100%; height:auto}
.chart .empty{color:var(--dim); font-size:13px; padding:26px 0; text-align:center}
.legend{display:flex; gap:14px; flex-wrap:wrap; font-size:12px; color:var(--muted); margin-top:10px}
.legend i{display:inline-block; width:9px; height:9px; border-radius:3px; margin-right:6px}

/* activity */
table{width:100%; border-collapse:collapse; font-size:13px}
th,td{text-align:left; padding:7px 8px; border-bottom:1px solid var(--border); vertical-align:top}
th{color:var(--muted); font-size:11px; letter-spacing:.07em; text-transform:uppercase; font-weight:600}
tbody tr:last-child td{border-bottom:0}
td.time{color:var(--dim); font:12px/1.4 var(--mono); white-space:nowrap; width:1%}
.tag{
  display:inline-block; font:600 10.5px/1 var(--mono); letter-spacing:.04em; text-transform:uppercase;
  padding:4px 6px; border-radius:6px; background:var(--panel-2); color:var(--muted); white-space:nowrap;
}
.tag.poll{background:var(--accent-soft); color:var(--accent)}
.tag.receive{background:color-mix(in srgb,var(--ok) 16%,transparent); color:var(--ok)}
.tag.send{background:color-mix(in srgb,var(--warn) 16%,transparent); color:var(--warn)}
.tag.agent{background:color-mix(in srgb,var(--accent-2) 18%,transparent); color:var(--accent-2)}
.tag.error{background:color-mix(in srgb,var(--err) 16%,transparent); color:var(--err)}
.tag.runtime,.tag.service{background:var(--panel-2); color:var(--dim)}
.scroll{max-height:420px; overflow:auto}

/* forms */
.row{display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
.field{display:flex; flex-direction:column; gap:5px; margin-bottom:12px}
.field label{font-size:12px; color:var(--muted)}
input,select,textarea{
  background:var(--panel-2); border:1px solid var(--border); color:var(--text);
  padding:9px 11px; border-radius:9px; font-size:13.5px; font-family:inherit; width:100%;
  line-height:1.35;
}
/* A native <select> sizes itself from the OS, so its box ends up a couple of
   pixels shorter than a text input next to it. Pin both to one height and
   draw our own chevron. */
input,select{height:38px; padding-top:0; padding-bottom:0}
select{
  appearance:none; -webkit-appearance:none; cursor:pointer; padding-right:32px;
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'><path d='M1 1.5 6 6.5 11 1.5' fill='none' stroke='%238a94a6' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/></svg>");
  background-repeat:no-repeat; background-position:right 11px center; background-size:11px;
}
select option{background:var(--panel-2); color:var(--text)}
textarea{font-family:var(--mono); font-size:12.5px; line-height:1.5; resize:vertical; min-height:74px; height:auto}
input:focus,select:focus,textarea:focus{outline:2px solid color-mix(in srgb,var(--accent) 45%,transparent); outline-offset:1px; border-color:var(--accent)}
input.mono,textarea.mono{font-family:var(--mono); font-size:12.5px}
.checks{display:flex; gap:18px; flex-wrap:wrap; margin:2px 0 14px}
.checks label{display:flex; gap:7px; align-items:center; font-size:13px; color:var(--text)}
.checks input{width:auto; height:auto}

/* token field */
.token-field{position:relative}
.token-wrap{display:flex; gap:6px; align-items:center}
.token-wrap input{flex:1; margin:0; font-family:var(--mono); letter-spacing:.06em}
.token-wrap input[type="password"]{letter-spacing:.18em}
.eye-btn{flex-shrink:0; width:38px; height:38px; display:flex; align-items:center; justify-content:center; font-size:15px; padding:0; border-radius:9px; background:var(--panel-2)}
.eye-btn:hover{background:var(--border)}
.eye-btn.revealed{background:color-mix(in srgb,var(--accent) 28%,var(--panel-2)); border-color:var(--accent)}
.actions{display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-top:6px}
button{
  font:inherit; font-size:13.5px; font-weight:550; cursor:pointer;
  padding:9px 16px; border-radius:9px; border:1px solid var(--border);
  background:var(--panel-2); color:var(--text);
}
button:hover{background:var(--border)}
button.primary{background:var(--accent); border-color:var(--accent); color:#0b1220}
:root[data-theme="light"] button.primary{color:#fff}
button.primary:hover{filter:brightness(1.08)}
button:disabled{opacity:.5; cursor:default}
.note{font-size:12.5px; color:var(--dim); line-height:1.6}
.note code,code{font-family:var(--mono); font-size:12px; background:var(--panel-2); padding:1px 5px; border-radius:5px}
pre{
  font-family:var(--mono); font-size:12.5px; background:var(--panel-2);
  border:1px solid var(--border); border-radius:9px; padding:11px 13px;
  overflow:auto; margin:0; white-space:pre-wrap; word-break:break-word;
}
details summary{cursor:pointer; color:var(--muted); font-size:12.5px}
details[open] summary{margin-bottom:10px}

.lang-block{display:block}
[hidden]{display:none !important}

/* numbered help steps */
ol.steps{margin:0; padding-left:20px; font-size:13px; line-height:1.75; color:var(--text)}
ol.steps li{margin-bottom:8px}
ol.steps pre{margin:6px 0; font-size:12px}
details.advanced{margin-top:4px}
details.advanced > summary{
  cursor:pointer; color:var(--muted); font-size:12.5px; padding:9px 0;
  border-top:1px solid var(--border);
}

/* pairing */
.pairing{display:flex; gap:20px; align-items:flex-start; flex-wrap:wrap}
.pairing img{
  background:#fff; padding:10px; border-radius:12px; width:208px; height:208px;
  image-rendering:pixelated; border:1px solid var(--border);
}
.pairing .meta{flex:1; min-width:210px}
.kv{display:grid; grid-template-columns:auto 1fr; gap:6px 14px; font-size:13px; margin-bottom:12px}
.kv dt{color:var(--muted)}
.kv dd{margin:0; font-family:var(--mono); font-size:12.5px; word-break:break-all}
.kv dd.prose{font-family:inherit; font-size:13px; word-break:normal; line-height:1.55}

/* dialogs (the cleanup log) */
dialog{
  border:1px solid var(--border); border-radius:var(--radius); background:var(--panel);
  color:var(--text); padding:18px 20px; max-width:min(92vw,760px); width:100%;
}
dialog::backdrop{background:rgba(0,0,0,.55)}
dialog h2{
  margin:0 0 12px; font-size:12px; letter-spacing:.09em; text-transform:uppercase;
  color:var(--muted); font-weight:650; display:flex; justify-content:space-between; gap:10px;
}
dialog h2 .hint{font-size:11px; letter-spacing:0; text-transform:none; color:var(--dim); font-weight:400}

/* toast */
#toast{
  position:fixed; left:50%; bottom:26px; transform:translate(-50%,20px);
  background:var(--panel); border:1px solid var(--border); border-radius:11px;
  padding:11px 17px; font-size:13.5px; box-shadow:0 12px 34px rgba(0,0,0,.35);
  opacity:0; pointer-events:none; transition:.22s; max-width:min(92vw,560px); z-index:50;
}
#toast.show{opacity:1; transform:translate(-50%,0)}
#toast.ok{border-color:color-mix(in srgb,var(--ok) 55%,var(--border))}
#toast.err{border-color:color-mix(in srgb,var(--err) 55%,var(--border))}
.empty-state{color:var(--dim); font-size:13.5px}
"""


JS = r"""
(function(){
  var root=document.documentElement;
  var saved=localStorage.getItem('clutcha-theme');
  if(saved) root.setAttribute('data-theme',saved);
  else root.removeAttribute('data-theme');
  var btn=document.getElementById('theme');
  function current(){return root.getAttribute('data-theme')|| (window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');}
  function paint(){btn.textContent = current()==='light' ? '☀' : '☾';}
  paint();
  btn.addEventListener('click',function(){
    var next = current()==='light' ? 'dark' : 'light';
    root.setAttribute('data-theme',next);
    localStorage.setItem('clutcha-theme',next);
    paint();
  });

  // The letter's Language select only decides which language the letter is
  // written in — not the page. Both blocks and both previews are already in the
  // document, so switching is a visibility flip, not a round trip.
  var letterLang=document.querySelector('select[name="lang"][data-resolved]');
  if(letterLang){
    var autoLang=letterLang.dataset.resolved||'zh';
    var paintLetter=function(){
      var target=letterLang.value==='auto'?autoLang:letterLang.value;
      document.querySelectorAll('[data-letter-lang]').forEach(function(el){
        el.hidden = el.dataset.letterLang!==target;
      });
    };
    letterLang.addEventListener('change',paintLetter);
    paintLetter();
  }

  // <dialog> rather than a hand-rolled overlay: focus trapping, Escape and the
  // backdrop come with it.
  document.querySelectorAll('[data-dialog]').forEach(function(button){
    button.addEventListener('click',function(){
      var box=document.getElementById(button.dataset.dialog);
      if(box && box.showModal) box.showModal();
    });
  });
  document.querySelectorAll('[data-close-dialog]').forEach(function(button){
    button.addEventListener('click',function(){
      var box=document.getElementById(button.dataset.closeDialog);
      if(box) box.close();
    });
  });

  var toastTimer=null;
  window.toast=function(message,kind){
    var el=document.getElementById('toast');
    el.textContent=message;
    el.className='show '+(kind||'');
    clearTimeout(toastTimer);
    toastTimer=setTimeout(function(){el.className='';},4200);
  };

  window.api=function(path,body){
    var options={headers:{'Content-Type':'application/json'}};
    if(body!==undefined){options.method='POST';options.body=JSON.stringify(body);}
    return fetch(path,options).then(function(response){
      return response.json().catch(function(){return {};}).then(function(data){
        if(!response.ok) { throw new Error((data&&(data.error||(data.problems&&data.problems.join('; '))))||('HTTP '+response.status)); }
        return data;
      });
    });
  };

  document.querySelectorAll('form[data-api]').forEach(function(form){
    form.addEventListener('submit',function(event){
      event.preventDefault();
      var data={};
      new FormData(form).forEach(function(value,key){
        var field=form.querySelector('[name="'+key+'"]');
        if(field && field.type==='checkbox') data[key]=field.checked;
        else data[key]=value;
      });
      var button=form.querySelector('button[type="submit"]');
      if(button) button.disabled=true;
      api(form.dataset.api,data).then(function(result){
        toast(result.message||'Saved','ok');
        if(result.reload) setTimeout(function(){location.reload();},700);
      }).catch(function(error){toast(error.message,'err');})
        .finally(function(){ if(button) button.disabled=false; });
    });
  });

  document.querySelectorAll('[data-post]').forEach(function(button){
    button.addEventListener('click',function(){
      var payload={};
      if(button.dataset.payload){ try{payload=JSON.parse(button.dataset.payload);}catch(e){} }
      if(button.dataset.from){
        var scope=button.closest('form')||document;
        button.dataset.from.split(',').forEach(function(name){
          var field=scope.querySelector('[name="'+name+'"]');
          if(!field) return;
          payload[name]= field.type==='checkbox' ? field.checked : field.value;
        });
      }
      button.disabled=true;
      api(button.dataset.post,payload).then(function(result){
        toast(result.message||'Done','ok');
        if(result.reload) setTimeout(function(){location.reload();},700);
        else if(result.output!==undefined){
          var box=document.getElementById(button.dataset.output||'');
          if(box){ box.textContent=result.output||'(empty)'; box.hidden=false; }
        }
      }).catch(function(error){toast(error.message,'err');})
        .finally(function(){ button.disabled=false; });
    });
  });

  /* token eye toggle: reveal the saved token in place */
  document.querySelectorAll('.eye-btn').forEach(function(btn){
    var input=document.querySelector('input[name="'+btn.dataset.target+'"]');
    if(!input) return;
    btn.addEventListener('click',function(){
      var show=input.type==='password';
      input.type=show?'text':'password';
      btn.classList.toggle('revealed',show);
      btn.title=show?'Hide token':'Show token';
    });
  });

  /* language tabs: they switch what is visible, both blocks still submit */

  /* show a field only when a <select> has one of the listed values */
  document.querySelectorAll('[data-control]').forEach(function(field){
    var scope=field.closest('form')||document;
    var control=scope.querySelector('[name="'+field.dataset.control+'"]');
    if(!control) return;
    var allowed=(field.dataset.showWhen||'').split('|');
    function paint(){ field.hidden = allowed.indexOf(control.value)===-1; }
    control.addEventListener('change',paint);
    paint();
  });

  /* copy the text of a referenced element */
  document.querySelectorAll('[data-copy]').forEach(function(btn){
    btn.addEventListener('click',function(){
      var source=document.querySelector(btn.dataset.copy);
      if(!source) return;
      if(navigator.clipboard && navigator.clipboard.writeText){
        navigator.clipboard.writeText(source.textContent).then(
          function(){ toast('Copied','ok'); },
          function(){ toast('Could not copy','err'); }
        );
      } else {
        var area=document.createElement('textarea');
        area.value=source.textContent; document.body.appendChild(area);
        area.select(); try{ document.execCommand('copy'); toast('Copied','ok'); }
        catch(e){ toast('Could not copy','err'); }
        document.body.removeChild(area);
      }
    });
  });
})();
"""
