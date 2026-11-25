(()=>{'use strict';
const H=window.FLOW_US_GRAIN_HISTORY,D=window.FLOW_DATA,root=document.getElementById('us-grain-history');
if(!H||!root)return;
const names={corn:'玉米',soy:'大豆',wheat:'小麥'},colors=['#303840','#939393','#ae812c','#c94b4b','#337fc1'],dashes=['2 5','','7 5','',''],years=H.years,dayMs=86400000;
const nf=(v,n=2)=>v==null?'尚無資料':v.toLocaleString('zh-TW',{minimumFractionDigits:n,maximumFractionDigits:n});
const pct=(v,b)=>v==null||b==null?'尚無資料':b===0?'基期為零':(v>=b?'+':'')+nf((v/b-1)*100,1)+'%';
const previous=(date,days)=>new Date(Date.parse(date+'T00:00:00Z')-days*dayMs).toISOString().slice(0,10);
const offset=date=>(Date.parse('2000-'+date.slice(5)+'T00:00:00Z')-Date.UTC(2000,0,1))/dayMs;
const short=date=>date.replaceAll('-','/');
let key='corn',year=years.at(-1),selectedDate=H.displayEnd,geo={};
const points=()=>Object.entries(H.series[key]).filter(([date])=>date.startsWith(year+'')).map(([date,value])=>({date,value}));
root.innerHTML=`<div class="sectionline"><div><span class="eyebrow">UNITED STATES / FIVE-YEAR WEEKLY COMPARISON</span><h2>美國 · 海運出口檢驗歷年同期走勢</h2></div><div class="controls"><label>商品 <select class="us-history-series" aria-label="美國折線圖商品">${Object.entries(names).map(([k,n])=>`<option value="${k}">${n}</option>`).join('')}</select></label></div></div><div class="history-info"><span class="meta">${years[0]}–${years.at(-1)} · 每年一條線 · 最新資料週 ${short(H.displayEnd)}</span><span class="meta">週度 · 萬公噸</span></div><div class="history-statistics" aria-live="polite"></div><p class="meta us-history-average"></p><div class="history-legend" aria-label="美國折線圖觀察年度">${years.map((y,i)=>`<button type="button" data-us-year="${y}" aria-pressed="${y===year}"><svg width="28" height="12" aria-hidden="true"><line x1="1" x2="27" y1="6" y2="6" stroke="${colors[i]}" stroke-width="3" stroke-dasharray="${dashes[i]}"/></svg>${y}</button>`).join('')}</div><div class="history-plot"><svg role="img" aria-label="美國週度海運出口檢驗歷年同期折線圖"></svg></div><div class="history-scrub"><label>觀察週次 <input class="history-slider us-history-slider" type="range" min="1" step="1" aria-label="美國折線圖觀察週次"></label><span class="meta">選擇年份，再移動滑桿；也可點選折線查看該週</span></div><p class="note">USDA FGIS · 僅 SHIP 海運出口檢驗量，非出口銷售或全運具出口總量。橫軸依各週結束日對齊 1–12 月，保留週頻率，未加總成月量。WoW 對比 7 天前；YoY 對比 52 週（364 天）前，均列出實際基期；缺值不補零，間隔超過 10 天的折線斷開。2026 年只畫至已取得資料週。取得日期 ${short(H.retrieved)}。</p><p><a href="${H.source}" target="_blank" rel="noopener">USDA 官方資料來源 ↗</a>　<a href="us-grain-history.csv" download>下載週資料 CSV ↓</a>　<a href="us-grain-history.json" download>下載資料與口徑 JSON ↓</a></p><details><summary>查看週度數據、WoW 與 YoY</summary><div class="history-table table-wrap"></div></details>`;
const svg=root.querySelector('.history-plot svg'),slider=root.querySelector('.us-history-slider'),ns='http://www.w3.org/2000/svg';
function el(tag,attrs,text){const e=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));if(text!==undefined)e.textContent=text;svg.append(e);return e;}
const py=v=>geo.top+(1-v/geo.max)*geo.ph,px=date=>geo.left+offset(date)/365*geo.pw;
function select(){
 const arr=points();if(!arr.some(r=>r.date===selectedDate))selectedDate=arr.at(-1).date;
 const value=H.series[key][selectedDate],week=previous(selectedDate,7),prior=previous(selectedDate,364),index=arr.findIndex(r=>r.date===selectedDate);
 root.querySelector('.history-statistics').innerHTML=`<div><span>觀察資料週</span><strong>${short(selectedDate)}</strong></div><div><span>${names[key]} · 萬公噸</span><strong>${nf(value/10000)}</strong></div><div><span>WoW · ${short(week)}</span><strong>${pct(value,H.series[key][week])}</strong></div><div><span>YoY · ${short(prior)}</span><strong>${pct(value,H.series[key][prior])}</strong></div>`;
 const four=Array.from({length:4},(_,i)=>H.series[key][previous(selectedDate,i*7)]);
 root.querySelector('.us-history-average').textContent='近 4 週平均（含選取週）　'+(four.every(v=>v!=null)?nf(four.reduce((s,v)=>s+v,0)/4/10000)+' 萬公噸／週':'尚無完整 4 週資料');
 slider.max=arr.length;slider.value=index+1;slider.setAttribute('aria-valuetext',short(selectedDate)+' 當週');
 root.querySelectorAll('[data-us-year]').forEach(b=>b.setAttribute('aria-pressed',String(+b.dataset.usYear===year)));
 svg.querySelectorAll('[data-selected]').forEach(e=>e.remove());
 if(geo.pw){const x=px(selectedDate);el('line',{x1:x,x2:x,y1:geo.top,y2:geo.top+geo.ph,stroke:'#7aaab2','stroke-dasharray':'4 4','data-selected':'true'});el('circle',{cx:x,cy:py(value),r:6,fill:colors[years.indexOf(year)],stroke:'#fff','stroke-width':2,'data-selected':'true'});}
 svg.setAttribute('aria-label',`美國${names[key]}海運出口檢驗，${years[0]}至${years.at(-1)}每年一條線，橫軸1至12月，週度資料。選取${selectedDate}，${nf(value)}公噸。`);
}
function draw(){
 if(!root.clientWidth)return;
 const visible=Object.entries(H.series[key]).filter(([date])=>+date.slice(0,4)>=years[0]&&+date.slice(0,4)<=years.at(-1));
 const width=Math.max(280,root.querySelector('.history-plot').clientWidth),height=320,left=54,right=20,top=18,bottom=38;
 geo={width,height,left,top,pw:width-left-right,ph:height-top-bottom,max:Math.max(1,...visible.map(([,v])=>v))*1.12};
 svg.replaceChildren();svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.setAttribute('width',width);svg.setAttribute('height',height);
 for(let i=0;i<=4;i++){const y=top+geo.ph-i/4*geo.ph;el('line',{x1:left,x2:width-right,y1:y,y2:y,stroke:'#e2e9ed'});el('text',{x:left-8,y:y+4,'text-anchor':'end',fill:'#60717e','font-size':12},nf(geo.max*i/4/10000,0));}
 for(let m=1;m<=12;m++){const date=`2000-${String(m).padStart(2,'0')}-01`;el('text',{x:px(date),y:height-12,'text-anchor':'middle',fill:'#60717e','font-size':width<500?10:12},width<500?String(m):`${m}月`);}
 years.forEach((y,i)=>{let path='',previousDate;for(const [date,value] of visible.filter(([d])=>+d.slice(0,4)===y)){const join=previousDate&&(Date.parse(date)-Date.parse(previousDate))/dayMs<=10;path+=(join?' L':' M')+px(date)+','+py(value);previousDate=date;}el('path',{d:path,fill:'none',stroke:colors[i],'stroke-width':i===years.length-1?3:2,'stroke-dasharray':dashes[i],'stroke-linejoin':'round','stroke-linecap':'round','data-us-line-year':y});});
 const rows=visible.map(([date,value])=>{const w=previous(date,7),y=previous(date,364);return `<tr><td>${short(date)}</td><td>${nf(value,0)}</td><td>${pct(value,H.series[key][w])}</td><td>${short(w)}</td><td>${pct(value,H.series[key][y])}</td><td>${short(y)}</td></tr>`;}).join('');
 root.querySelector('.history-table').innerHTML=`<table><thead><tr><th>資料週</th><th>海運出口檢驗（公噸）</th><th>WoW</th><th>前週基期</th><th>YoY</th><th>52 週前基期</th></tr></thead><tbody>${rows}</tbody></table>`;
 select();
}
root.querySelector('.us-history-series').addEventListener('change',e=>{key=e.target.value;draw();});
root.querySelectorAll('[data-us-year]').forEach(b=>b.addEventListener('click',()=>{const md=selectedDate.slice(5);year=+b.dataset.usYear;const target=`${year}-${md}`,arr=points();selectedDate=arr.reduce((best,r)=>Math.abs(Date.parse(r.date)-Date.parse(target))<Math.abs(Date.parse(best.date)-Date.parse(target))?r:best,arr[0]).date;select();}));
slider.addEventListener('input',()=>{selectedDate=points()[+slider.value-1].date;select();});
svg.addEventListener('pointerdown',e=>{if(!geo.pw)return;const r=svg.getBoundingClientRect(),x=(e.clientX-r.left)*geo.width/r.width,y=(e.clientY-r.top)*geo.height/r.height;let nearest=null,distance=Infinity;years.forEach(yr=>Object.entries(H.series[key]).filter(([d])=>+d.slice(0,4)===yr).forEach(([date,value])=>{const dx=px(date)-x,dy=py(value)-y,dist=dx*dx+dy*dy;if(dist<distance){distance=dist;nearest={date,year:yr};}}));if(nearest){year=nearest.year;selectedDate=nearest.date;select();}});
new ResizeObserver(draw).observe(root.querySelector('.history-plot'));document.addEventListener('flow-view-change',()=>requestAnimationFrame(draw));draw();
})();
