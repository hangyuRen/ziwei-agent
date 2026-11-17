/* Three harmonies/opposite relation and SVG geometry ported from upstream
 * Renhuai123/ziwei-doushu ChartBoard.tsx (MIT), commit 7922285d947b.
 * This module renders the Python engine output; it does not calculate a natal chart.
 */
window.PalaceBoard=(()=>{
 const positions={5:[1,1],6:[1,2],7:[1,3],8:[1,4],4:[2,1],9:[2,4],3:[3,1],10:[3,4],2:[4,1],1:[4,2],0:[4,3],11:[4,4]};
 const branches=[5,6,7,8,4,9,3,10,2,1,0,11];
 const glyphs='子丑寅卯辰巳午未申酉戌亥';
 const relations=b=>[b,(b+6)%12,(b+4)%12,(b+8)%12];
 const ns='http://www.w3.org/2000/svg';
 const colors={'禄':'#27775b','权':'#b06923','科':'#346db2','忌':'#bd4147'};
 const coreStars=new Set(['左辅','右弼','文昌','文曲']);
 const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node};
 let observer;
 function center(j){
  const c=j.natal_chart,root=el('div','natalCenter compactCenter');
  root.append(el('strong','centerName',j.name||j.input_birth?.name||'紫微命盘'));
  root.append(el('div','centerClass',`${c.yinYangGender||''}　${c.five_elements_class}`));
  const reading=el('div','centerReading');reading.setAttribute('aria-live','polite');root.append(reading);
  const grids=el('div','centerPillars');
  for(const [label,values] of [['节气四柱',c.lunarInfo?.fourPillars],['农历四柱',c.lunarInfo?.fourPillarsLunar]]){
   const group=el('div','pillarGroup');group.append(el('small','',label));const cols=el('div','pillarColumns');
   for(const value of values||[]){const column=el('span','pillarColumn');for(const char of value){const unit=el('span','',char);const colors={'甲':'wood','乙':'wood','丙':'fire','丁':'fire','戊':'earth','己':'earth','庚':'metal','辛':'metal','壬':'water','癸':'water'};unit.dataset.element=colors[char]||'';column.append(unit)}cols.append(column)}
   group.append(cols);grids.append(group);
  }
  root.append(grids);
  const identity=el('div','centerIdentity');
  for(const [label,value] of [['命主',c.mingZhu||c.soul],['身主',c.shenZhu||c.body],['命宫',glyphs[c.mingGongBranch]],['身宫',glyphs[c.shenGongBranch]]]){const line=el('span');line.append(el('small','',label),el('b','',value||'—'));identity.append(line)}root.append(identity);
  const times=el('div','centerTimes');const correction=j.time_correction;
  const clock=t=>t?.replace('T',' ').slice(0,19);
  const input=j.input_birth;
  const solarInputClock=input?.calendar!=='lunar'&&input?.clock_hour!=null?`${input.year}-${String(input.month).padStart(2,'0')}-${String(input.day).padStart(2,'0')} ${String(input.clock_hour).padStart(2,'0')}:${String(input.minute||0).padStart(2,'0')}`:null;
    for(const [key,label,value] of [['solar','真太阳时',clock(correction?.true_solar_time)||'缺少原始出生时间或出生地'],['clock','钟表时间',clock(correction?.clock_time||j.clock_time)||solarInputClock||'未保存具体钟表时间'],['lunar','农历日期',c.lunar_date]]){
   const line=el('div','centerTimeRow');line.dataset.timeKind=key;line.append(el('small','',label),el('span','',value));times.append(line);
  }
  root.append(times);
  const dx=c.daXians?.[c.currentDaXianIndex];if(dx)root.append(el('div','centerDecadal',`当前大限 ${dx.startAge}–${dx.endAge}岁 · ${dx.palaceName}`));
  const selection=el('div','centerSelection','点击宫位查看三方四正');selection.setAttribute('aria-live','polite');root.append(selection);
  const content=el('div','centerContent');content.append(...root.childNodes);root.append(content);return root;
 }
 function fit(board){
  if(!board.offsetWidth)return;
  for(const cell of board.querySelectorAll('.natalCell')){
   const deck=cell.querySelector('.starDeck');
   for(let font=14;font>=8;font--){cell.style.setProperty('--star-font',font+'px');const rect=deck.getBoundingClientRect();if([...deck.children].every(s=>{const r=s.getBoundingClientRect();return r.bottom<=rect.bottom-.5&&r.right<=rect.right+.2}))break}
  }
  const center=board.querySelector('.compactCenter'),content=center?.querySelector('.centerContent');
  if(content)content.style.setProperty('--center-scale',Math.min(1,(center.clientHeight-16)/content.scrollHeight,(center.clientWidth-12)/content.scrollWidth));
 }
 function render(board,j,onSelect,options={}){
  if(observer)observer.disconnect();board.replaceChildren();const chart=j.natal_chart,byBranch=new Map(chart.palaces.map(p=>[p.branch,p]));
  const mode=options.mode||'sanhe',transforms=chart.transformations;board.dataset.mode=mode;
  const layer=options.layer==='annual'?transforms?.annual:options.layer==='daxian'?transforms?.daXians?.find(d=>d.index===options.daXianIndex):transforms?.natal;
  const layerName=options.layer==='annual'?`${layer?.year||''} 流年`:options.layer==='daxian'?'大限':'生年';
  const middle=center(j);board.append(middle);const cells=new Map();let selected=null;
  for(const branch of branches){
   const p=byBranch.get(branch);if(!p)continue;
   const cell=el('div','natalCell palaceCell');cell.dataset.branch=branch;cell.style.gridRow=positions[branch][0];cell.style.gridColumn=positions[branch][1];cell.setAttribute('role','button');cell.tabIndex=0;cell.setAttribute('aria-pressed','false');cell.setAttribute('aria-label',`${p.name}，${p.heavenly_stem}${p.earthly_branch}，查看三方四正`);
   cell.classList.toggle('isMing',p.isMingGong);cell.classList.toggle('currentDecadal',p.isCurrentDaXian);
   if(mode!=='sanhe')cell.setAttribute('aria-label',`${p.name}，${p.heavenly_stem}${p.earthly_branch}，${mode==='feixing'?'查看宫干飞化':'追溯四化来源'}`);
   const deck=el('div','starDeck');const rank={major:0,lucky:1,sha:2,minor:3};
   for(const star of [...p.stars].filter(s=>mode==='sanhe'||s.type==='major'||coreStars.has(s.name)).sort((a,b)=>(rank[a.type]??3)-(rank[b.type]??3))){
    const column=el('span','starColumn star-'+star.type);column.dataset.starName=star.name;const name=el('span','starName');name.setAttribute('aria-label',star.name);for(const character of star.name)name.append(el('span','starCharacter',character));column.append(name,el('span','starBrightness',star.brightnessRaw||'\u00a0'));
    if(star.siHua){const badge=el('span','siHuaBadge',star.siHua);badge.dataset.mutagen=star.siHua;column.append(badge)}
    column.title=star.name+(star.brightnessRaw?' · '+star.brightnessRaw:'')+(star.siHua?' · 化'+star.siHua:'');deck.append(column);
   }
   if(!p.stars.some(s=>s.type==='major'))deck.classList.add('emptyMajor');
   const footer=el('div','palaceFooter');const gods=el('div','palaceGods');
   for(const v of [p.boshi12,p.jiangqian12,p.suiqian12])if(v)gods.append(el('span','',v));
   const label=el('div','palaceIdentity');label.append(el('b','palaceStem',p.heavenly_stem+p.earthly_branch));
   const palace=el('span','palaceName',p.name+(p.isShenGong?' · 身':p.isMingGong?' · 命':''));label.append(palace);
   const ages=p.daXianAge||p.decadal?.range;const age=el('span','palaceAge',ages?`${ages[0]}–${ages[1]}`:'');
   footer.append(gods,age,label);cell.append(deck,footer);board.append(cell);cells.set(branch,cell);
   cell.onclick=()=>select(branch);cell.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(branch)}};
  }
  const svg=document.createElementNS(ns,'svg');svg.classList.add('palaceConnections');svg.setAttribute('aria-hidden','true');svg.setAttribute('width','100%');svg.setAttribute('height','100%');board.append(svg);
  function flightLines(edges){
   svg.setAttribute('viewBox','0 0 1000 1000');svg.setAttribute('preserveAspectRatio','none');
   const defs=document.createElementNS(ns,'defs');svg.append(defs);
   for(const [kind,color] of Object.entries(colors)){
    const marker=document.createElementNS(ns,'marker');marker.id='flight-arrow-'+kind;for(const [k,v] of Object.entries({viewBox:'0 0 10 10',refX:8,refY:5,markerWidth:7,markerHeight:7,orient:'auto-start-reverse'}))marker.setAttribute(k,v);
    const tip=document.createElementNS(ns,'path');tip.setAttribute('d','M 0 0 L 10 5 L 0 10 z');tip.setAttribute('fill',color);marker.append(tip);defs.append(marker);
   }
   for(const edge of edges){
    const point=b=>{const [row,col]=positions[b];return [(col-.5)*250,(row-.5)*250]};
    const [sx,sy]=point(edge.sourceBranch),[tx,ty]=point(edge.targetBranch);let d,lx,ly;
    if(edge.self){d=`M ${sx-20} ${sy+5} C ${sx-80} ${sy-100} ${sx+80} ${sy-100} ${sx+20} ${sy+5}`;lx=sx;ly=sy-65}
    else{const dx=tx-sx,dy=ty-sy,length=Math.hypot(dx,dy),ux=dx/length,uy=dy/length,offset=([-1.5,-.5,.5,1.5][Object.keys(colors).indexOf(edge.siHua)])*25;
     const x1=sx+ux*25,y1=sy+uy*25,x2=tx-ux*38,y2=ty-uy*38,cx=(sx+tx)/2-uy*offset,cy=(sy+ty)/2+ux*offset;d=`M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;lx=(x1+2*cx+x2)/4;ly=(y1+2*cy+y2)/4-7;
    }
    const path=document.createElementNS(ns,'path');path.setAttribute('d',d);path.setAttribute('fill','none');path.setAttribute('stroke',colors[edge.siHua]);path.setAttribute('marker-end',`url(#flight-arrow-${edge.siHua})`);path.classList.add('flightPath');path.dataset.siHua=edge.siHua;path.dataset.sourceBranch=edge.sourceBranch;path.dataset.targetBranch=edge.targetBranch;svg.append(path);
    const label=document.createElementNS(ns,'text');label.setAttribute('x',lx);label.setAttribute('y',ly);label.setAttribute('fill',colors[edge.siHua]);label.classList.add('flightLabel');label.textContent=edge.siHua;svg.append(label);
   }
  }
  function transformationReading(){
   if(mode==='sanhe')return;
   const reading=middle.querySelector('.centerReading');reading.replaceChildren();
   let edges=[],placements=[];
   if(mode==='feixing')edges=(transforms?.flyingStars||[]).filter(e=>e.sourceBranch===selected);
   else{
    placements=layer?.placements||[];
    if(selected!==null)edges=(transforms?.flyingStars||[]).filter(e=>e.targetBranch===selected&&placements.some(p=>p.starName===e.starName&&p.siHua===e.siHua));
   }
   for(const [branch,cell] of cells){
    cell.classList.toggle('transformationTarget',(mode==='feixing'?edges:placements).some(e=>e.targetBranch===branch));
    for(const column of cell.querySelectorAll('.starColumn')){
     column.querySelectorAll('.contextSiHua,.selfSihuaBadge').forEach(b=>b.remove());const name=column.dataset.starName;
     if(mode==='sihua')for(const self of transforms?.selfSihua?.[branch]||[]){if(self.starName===name){const badge=el('span','selfSihuaBadge','↺'+self.siHua);badge.style.color=colors[self.siHua];badge.title=`${byBranch.get(branch).heavenly_stem}干自化${self.siHua}`;badge.setAttribute('aria-label',badge.title);column.append(badge)}}
     for(const mark of (mode==='feixing'?edges:options.layer==='natal'?[]:placements)){
      if(mark.targetBranch===branch&&mark.starName===name){const badge=el('span','siHuaBadge contextSiHua',mark.self?'↺'+mark.siHua:mark.siHua);badge.dataset.mutagen=mark.siHua;badge.title=mode==='feixing'?`${mark.sourcePalace}${mark.stemName}干化${mark.siHua} → ${mark.targetPalace}`:`${layerName}化${mark.siHua}`;badge.setAttribute('aria-label',badge.title);column.append(badge)}
     }
    }
   }
   const source=byBranch.get(selected);
   const title=mode==='feixing'?(source?`${source.name} · ${source.heavenly_stem}干飞化`:'宫干飞星'):selected===null?`${layerName}四化 · ${layer?.stemName||'—'}干`:`${source.name} · ${layerName}四化来因`;
   reading.append(el('strong','centerReadingTitle',title));
   const row=(kind,text)=>{const line=el('div','centerFlightRow'),badge=el('b','',kind);badge.style.color=colors[kind];line.append(badge,el('span','',text));reading.append(line)};
   if(mode==='feixing')for(const edge of edges)row(edge.siHua,`${edge.starName} → ${edge.self?'本宫自化':edge.targetPalace}`);
   else if(selected===null)for(const target of placements)row(target.siHua,`${target.starName} → ${target.targetPalace}`);
   else{
    for(const target of placements.filter(p=>p.targetBranch===selected)){
     const incoming=edges.filter(e=>e.starName===target.starName&&e.siHua===target.siHua);row(target.siHua,`${target.starName} ← ${incoming.map(e=>e.self?'本宫自化':e.sourcePalace).join('、')}`);
    }
   }
   if(!reading.querySelector('.centerFlightRow'))reading.append(el('p','centerReadingEmpty',mode==='feixing'?'点击宫位查看宫干四化去向':!layer?'尚未进入大限，可选择其他大限查看。':'本宫没有所选层四化，点击着色宫位查看来源。'));
   middle.querySelector('.centerSelection').textContent=mode==='feixing'?'箭头为飞化去向，↺ 为本宫自化':'实底为生年四化，描边为运限四化，↺ 为宫干自化';
   flightLines(edges);
  }
  function select(branch,notify=true){
   selected=selected===branch?null:branch;const related=selected===null?[]:relations(selected);svg.replaceChildren();
   if(mode!=='sanhe'){
    for(const [b,cell] of cells){cell.classList.toggle('selectedPalace',b===selected);cell.setAttribute('aria-pressed',String(b===selected))}
    transformationReading();if(notify){options.onSelection?.(selected);if(selected!==null)onSelect?.(byBranch.get(selected))}requestAnimationFrame(()=>fit(board));return;
   }
   for(const [b,cell] of cells){cell.classList.toggle('selectedPalace',b===selected);cell.classList.toggle('relatedPalace',b!==selected&&related.includes(b));cell.classList.toggle('oppositePalace',selected!==null&&b===(selected+6)%12);cell.setAttribute('aria-pressed',String(b===selected))}
   const status=middle.querySelector('.centerSelection');
   if(selected===null){status.textContent='点击宫位查看三方四正';if(notify)options.onSelection?.(null);requestAnimationFrame(()=>fit(board));return}
   const coords=b=>{const [row,col]=positions[b];return [(col-.5)*25,(row-.5)*25]};
   const [b,opp,a,c]=related;
   for(const [from,to] of [[b,opp],[b,a],[a,c],[c,b]]){const line=document.createElementNS(ns,'line');const p0=coords(from),p1=coords(to);for(const [key,value] of Object.entries({x1:p0[0]+'%',y1:p0[1]+'%',x2:p1[0]+'%',y2:p1[1]+'%'}))line.setAttribute(key,value);svg.append(line)}
   for(const rb of related){const dot=document.createElementNS(ns,'circle'),point=coords(rb);dot.setAttribute('cx',point[0]+'%');dot.setAttribute('cy',point[1]+'%');dot.setAttribute('r',rb===selected?'3':'2.5');svg.append(dot)}
   status.textContent=`${byBranch.get(b).name} · 对宫 ${byBranch.get(opp).name} · 三合 ${byBranch.get(a).name}、${byBranch.get(c).name}`;
   if(notify){onSelect?.(byBranch.get(selected));options.onSelection?.(selected)}requestAnimationFrame(()=>fit(board));
  }
  board.onkeydown=e=>{if(e.key==='Escape'&&selected!==null)select(selected)};
  const initial=options.selectedBranch??(mode==='feixing'?chart.mingGongBranch:null);
  if(initial!==null&&byBranch.has(initial))select(initial,false);else transformationReading();
  requestAnimationFrame(()=>fit(board));if(document.fonts)document.fonts.ready.then(()=>fit(board));
  observer=new ResizeObserver(()=>fit(board));observer.observe(board);
 }
 return Object.freeze({render,relations,positions});
})();
