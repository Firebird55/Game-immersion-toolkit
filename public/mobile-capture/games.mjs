import {translate as t,languageName,getInterfaceLanguage,setInterfaceLanguage,subscribeInterfaceLanguage,bindStaticTranslation} from './interface-language.mjs';
bindStaticTranslation(document.body);
const interfaceSelect=document.getElementById('guide-interface');
interfaceSelect.value=getInterfaceLanguage();
interfaceSelect.onchange=()=>setInterfaceLanguage(interfaceSelect.value);
const $=id=>document.getElementById(id);
const data=await fetch(new URL('./games-data.json',import.meta.url)).then(response=>{if(!response.ok)throw Error('Support information unavailable');return response.json();}).catch(()=>null);
if(!data){$('filter-status').textContent='Support information could not load. Reconnect and reload, or open the project documentation.';$('release-info').textContent='Support information unavailable.';}
else {
 const controls={game:$('guide-game'),study:$('guide-study'),target:$('guide-target')};
 const names=data.languages, label=code=>getInterfaceLanguage()==='en'?(names[code]??code):languageName(code);
 const option=(value,text)=>new Option(text,value);
 for(const game of data.games)controls.game.add(option(game.id,game.name));
 for(const key of ['study','target'])for(const code of Object.keys(names).sort((a,b)=>label(a).localeCompare(label(b))))controls[key].add(option(code,label(code)));
 function releaseInfo(){ $('release-info').textContent=`${t('Reader capabilities')}: v${data.readerRelease} · ${t('Storefronts checked')}: ${data.checkedAt}`;}releaseInfo();
 function element(tag,text,className){const node=document.createElement(tag);if(text)node.textContent=t(text);if(className)node.className=className;return node;}
 function link(text,href){const node=element('a',text);node.href=href;return node;}
 function list(title,codes){const p=element('p',null,'language-list');p.append(element('strong',title),document.createTextNode(codes.map(label).join(' · ')));return p;}
 function status(game,source,target){
  if(!game.study.includes(source))return 'No toolkit learning-language support';
  if(game.unverified[target])return 'Translation locale unverified';
  if(!game.targets.includes(target))return 'No official toolkit translation';
  if(game.expectedTargets?.includes(target))return 'Expected with installed assets';
  return source===target?'Same-language reading':game.textOnly?'Supported text-only pair':'Supported with installed assets';
 }
 function card(game,source,target){
  const article=element('article',null,'game-card');article.id=game.id;article.append(element('h3',game.name));
  const meta=element('p',null,'game-meta');meta.append(link('Official language listing',game.source),' · ',link('Setup & tested coverage','https://github.com/Firebird55/Game-immersion-toolkit/blob/main/docs/'+game.guide));article.append(meta);
  const selected=source!=='all'||target!=='all';
  if(selected){const state=source!=='all'&&target!=='all'?status(game,source,target):'Choose both languages to check a pair';article.append(element('p',`${source==='all'?t('Any learning language'):label(source)} → ${target==='all'?t('Any translation'):label(target)}: ${t(state)}`,state.includes('Supported')?'tag':'warning'));}
  article.append(list(game.textOnly?'Learning text (text-only)':'Learning text + matching original voice',game.study),list('Supported official translation targets',game.targets),element('p',t('Expected support uses the same reader format; it does not require an export of every language.')));
  if(Object.keys(game.unverified).length){const p=element('p',null,'warning');p.append(element('strong','Storefront-listed, toolkit unverified'),document.createTextNode(Object.keys(game.unverified).map(label).join(' · ')));article.append(p);for(const [locale,note]of Object.entries(game.unverified))if(target===locale||target==='all')article.append(element('p',label(locale)+': '+note,'muted'));}
  const details=element('details'),summary=element('summary','Compare every language');details.append(summary);
  const scroll=element('div',null,'table-scroll');scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label',game.name+' language table');
  const table=element('table');table.append(element('caption',game.name+' — '+t('Language support matrix')));
  const head=element('thead'),row=element('tr');for(const name of ['Language','Game original voice','Game official text','Toolkit learning','Toolkit translation']){const th=element('th',name);th.scope='col';row.append(th);}head.append(row);table.append(head);
  const body=element('tbody');for(const locale of [...new Set([...game.officialText,...game.audio,...game.study])].sort((a,b)=>label(a).localeCompare(label(b)))){const tr=element('tr'),th=element('th',label(locale));th.scope='row';tr.append(th);const shared=locale==='zh-Hant'&&game.study.includes(locale)&&!game.textOnly;
   for(const value of [game.audio.includes(locale)?(locale==='zh-Hans'?'Yes — Mandarin':'Yes'):shared?'Shared Mandarin':'—',game.officialText.includes(locale)?'Yes':game.textOnly&&locale==='zh-Hans'?'Installed catalog':'—',game.study.includes(locale)?(game.textOnly?'Text only':shared?'Yes — Mandarin audio':'Yes'):'—',game.expectedTargets?.includes(locale)?'Expected support':game.targets.includes(locale)?'Supported':game.unverified[locale]?'Unverified':'—'])tr.append(element('td',value));body.append(tr);
  }table.append(body);scroll.append(table);details.append(scroll);article.append(details);return article;
 }
 function readURL(){const query=new URL(location.href).searchParams;for(const key of Object.keys(controls)){const value=query.get(key)??'all';controls[key].value=[...controls[key].options].some(o=>o.value===value)?value:'all';}}
 function render(updateURL=false){const {game,study,target}=Object.fromEntries(Object.entries(controls).map(([key,node])=>[key,node.value]));const selected=data.games.filter(g=>game==='all'||game===g.id);$('game-results').replaceChildren(...selected.map(g=>card(g,study,target)));const applicable=selected.filter(g=>(study==='all'||g.study.includes(study))&&(target==='all'||g.targets.includes(target))).length;
  $('filter-status').textContent=`${t('Shown')}: ${selected.length} · ${t('Matching combinations')}: ${applicable}`;
  const url=new URL(location.href);for(const [key,node]of Object.entries(controls))if(node.value==='all')url.searchParams.delete(key);else url.searchParams.set(key,node.value);$('selection-link').href=url.pathname+url.search+url.hash;if(updateURL)history.replaceState(null,'',url);
 }
 $('language-filters').addEventListener('submit',event=>{event.preventDefault();render(true);});for(const node of Object.values(controls))node.addEventListener('change',()=>render(true));addEventListener('popstate',()=>{readURL();render();});readURL();render();
 subscribeInterfaceLanguage(()=>{interfaceSelect.value=getInterfaceLanguage();for(const key of ['study','target'])for(const opt of controls[key].options)if(opt.value!=='all')opt.textContent=label(opt.value);releaseInfo();render();$('install-guide').href='https://github.com/Firebird55/Game-immersion-toolkit/blob/main/docs/languages/install-'+getInterfaceLanguage()+'.md';$('matrix-guide').href='https://github.com/Firebird55/Game-immersion-toolkit/blob/main/docs/languages/'+getInterfaceLanguage()+'.md';});
 setInterfaceLanguage(getInterfaceLanguage());
}
if('serviceWorker'in navigator)navigator.serviceWorker.register('./sw.js').then(registration=>{
 const notice=()=>{$('guide-update').hidden=!registration.waiting;};notice();registration.addEventListener('updatefound',()=>{const worker=registration.installing;worker?.addEventListener('statechange',notice);});
 $('update-guide').onclick=()=>{if(!registration.waiting)return;navigator.serviceWorker.addEventListener('controllerchange',()=>location.reload(),{once:true});registration.waiting.postMessage('activate-update');};
}).catch(()=>{});
