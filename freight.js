(()=>{'use strict';
function mount(code){
const D=window.FLOW_FREIGHT_INDICES[code],$=s=>document.querySelector(s),fmt=n=>n.toLocaleString('zh-TW'),dayMs=86400000;
const offset=s=>(Date.parse('2000-'+s.slice(5))-Date.UTC(2000,0,1))/dayMs;
const years=[2022,2023,2024,2025,2026],colors={2022:'#262626',2023:'#858585',2024:'#111111',2025:'#ca4b4b',2026:'#5083bd'},dashes={2022:'1 6',2024:'8 6'};
const series=Object.fromEntries(years.map(y=>[y,D.rows.filter(r=>+r.date.slice(0,4)===y).map(r=>({...r,x:offset(r.date)}))]));
const missingDays=D.validation.missingAgainstBDI||[];
const active=new Set(years),last=D.rows.at(-1),prior=D.rows.at(-2),nChange=last.value-prior.value;
const signed=n=>(n>=0?'+':'−')+Math.abs(n).toFixed(1)+'%';
function annual(r){
 if(!r)return {value:'—',note:'尚無本期資料'};
 const year=+r.date.slice(0,4)-1;
 const monthDay=r.date.slice(5)==='02-29'?'02-28':r.date.slice(5);
 const target=`${year}-${monthDay}`,base=D.rows.findLast(b=>b.date<=target&&b.date.startsWith(String(year)));
 if(!base||(Date.parse(target)-Date.parse(base.date))/dayMs>7)return {value:'—',note:'尚無去年比較基期'};
 return {value:signed((r.value/base.value-1)*100),note:`基期 ${base.date.replaceAll('-','/')} · ${fmt(base.value)} 點`};
}
const latestYoY=annual(last);
const rate=signed(nChange/prior.value*100),latestYear=series[2026],peak=Math.max(...latestYear.map(r=>r.value)),low=Math.min(...latestYear.map(r=>r.value));
if(code==='BDI')$('#overview-bdi').innerHTML=`<span>BDI · ${last.date.replaceAll('-','/')}</span><strong>${fmt(last.value)}<small>點</small></strong><div class="overview-rates"><span>較前次公布 <b>${nChange>=0?'+':''}${fmt(nChange)} 點（${rate}）</b></span><span>YoY <b>${latestYoY.value}</b></span></div><span class="metric-bottom">${latestYoY.note}</span>`;
$('#freight-metrics').innerHTML=[['最新 '+code,fmt(last.value)+'<span class="unit">點</span>',last.date.replaceAll('-','/')+' · 最新公布日'],['較前次公布',rate,`${nChange>=0?'+':''}${fmt(nChange)} 點 · 比較 ${prior.date.replaceAll('-','/')}`],['今年至今區間',fmt(low)+'–'+fmt(peak),`2026 年 · ${latestYear.length} 筆日資料`]].map(([t,v,n])=>`<article class="metric"><span class="metric-top">${t}</span><strong class="metric-value">${v}</strong><span class="metric-bottom">${n}</span></article>`).join('');
$('#freight-metrics .metric').insertAdjacentHTML('beforeend',`<div class="change-line">YoY <b>${latestYoY.value}</b></div><span class="metric-bottom">${latestYoY.note}</span>`);
$('#freight-legend').innerHTML=years.map(y=>`<button type="button" data-year="${y}" aria-pressed="true"><svg width="36" height="12" aria-hidden="true"><path d="M2 6H34" stroke="${colors[y]}" stroke-width="${y===2026?4:3}" stroke-linecap="round" ${dashes[y]?`stroke-dasharray="${dashes[y]}"`:''}/></svg>${code} ${y}</button>`).join('');
let selected=offset(last.date);const slider=$('#freight-day');slider.value=selected;
const plot=$('#freight-chart'),W=1080,H=490,L=60,R=24,T=30,B=42,max=Math.ceil(Math.max(...D.rows.map(r=>r.value))*1.08/500)*500,pw=W-L-R,ph=H-T-B;
const x=d=>L+d/365*pw,y=v=>T+(1-v/max)*ph;
function render(){
 let out=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-labelledby="bdi-title bdi-desc"><title id="bdi-title">2022 至 2026 年 ${code} 歷年同期折線圖</title><desc id="bdi-desc">橫軸一月至十二月，縱軸指數點數。${code} 最新公布日為 ${last.date}，${last.value} 點，可用下方日期滑桿查看各年數值。</desc><text x="${L}" y="15" fill="#60717e" font-size="12">${code} · 點</text>`;
 for(let v=0;v<=max;v+=(max>4500?1000:500))out+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="#dce2e7"/><text x="${L-12}" y="${y(v)+4}" text-anchor="end" fill="#60717e" font-size="13">${fmt(v)}</text>`;
 for(let m=0;m<12;m++){const d=(Date.UTC(2000,m,1)-Date.UTC(2000,0,1))/dayMs;out+=`<text x="${x(d)}" y="${H-14}" text-anchor="middle" fill="#60717e" font-size="13">${m+1} 月</text>`;}
 for(const yr of years){if(!active.has(yr))continue;let previous;const path=series[yr].map(r=>{const move=!previous||(Date.parse(r.date)-Date.parse(previous.date))/dayMs>7||missingDays.some(d=>previous&&d>previous.date&&d<r.date);previous=r;return `${move?'M':'L'}${x(r.x).toFixed(2)},${y(r.value).toFixed(2)}`;}).join(' ');out+=`<path class="bdi-line" data-series="${yr}" d="${path}" fill="none" stroke="${colors[yr]}" stroke-width="${yr===2026?4:2.8}" stroke-linecap="round" stroke-linejoin="round" ${dashes[yr]?`stroke-dasharray="${dashes[yr]}"`:''}/>`;}
 if(active.has(2026))out+=`<circle cx="${x(offset(last.date))}" cy="${y(last.value)}" r="9" fill="white" stroke="${colors[2026]}" stroke-width="2.5"/><circle cx="${x(offset(last.date))}" cy="${y(last.value)}" r="3.5" fill="${colors[2026]}"/>`;
 out+=`<g id="freight-cursor" pointer-events="none"></g><rect id="freight-hit" x="${L}" y="${T}" width="${pw}" height="${ph}" fill="transparent"/></svg>`;
 plot.innerHTML=out;$('#freight-hit').addEventListener('pointermove',e=>{if(e.pointerType==='touch')return;selectPointer(e);});$('#freight-hit').addEventListener('click',selectPointer);inspect();
}
function selectPointer(e){const rect=plot.querySelector('svg').getBoundingClientRect();selected=Math.max(0,Math.min(365,Math.round(((e.clientX-rect.left)/rect.width*W-L)/pw*365)));slider.value=selected;inspect();}
function inspect(){
 const md=new Date(Date.UTC(2000,0,1)+selected*dayMs).toISOString().slice(5,10);$('#freight-day-label').textContent=md.replace('-',' / ');slider.setAttribute('aria-valuetext',md.replace('-','月')+'日');
 let markers=`<line x1="${x(selected)}" x2="${x(selected)}" y1="${T}" y2="${H-B}" stroke="#afbbc5" stroke-dasharray="3 5"/>`;
 $('#freight-values').innerHTML=years.filter(yr=>active.has(yr)).map(yr=>{
  const arr=series[yr];let r=arr.findLast(r=>r.x<=selected);
  if(selected>arr.at(-1).x||!r||selected-r.x>7)r=null;
  if(r)markers+=`<circle cx="${x(r.x)}" cy="${y(r.value)}" r="4" fill="white" stroke="${colors[yr]}" stroke-width="2"/>`;
  const comparison=annual(r);
  return `<div style="border-top-color:${colors[yr]}"><span>${code} ${yr}</span><strong>${r?fmt(r.value):'—'}</strong><small>${r?r.date.replaceAll('-','/')+' · 點':'此日期尚無資料'}</small><div class="change-line">YoY <b>${comparison.value}</b></div><small>${comparison.note}</small></div>`;
 }).join('');$('#freight-cursor').innerHTML=markers;
}
slider.oninput=()=>{selected=+slider.value;inspect();};
$('#freight-legend').onclick=e=>{const button=e.target.closest('button');if(!button)return;const yr=+button.dataset.year;if(active.has(yr)){if(active.size===1)return;active.delete(yr);}else active.add(yr);button.setAttribute('aria-pressed',String(active.has(yr)));render();};
render();
$('#freight-title').textContent=code+' · '+D.label+' 歷年同期走勢';
$('#freight-source').innerHTML=`<p class="note">原始指數：<a href="https://www.balticexchange.com/en/data-services/market-information0/dry-services.html" target="_blank" rel="noopener">Baltic Exchange</a>。資料取自 <a href="${D.sourceUrl}" target="_blank" rel="noopener">東方財富公開資料</a>，共 ${fmt(D.rows.length)} 筆（${D.rows[0].date}–${last.date}），於 ${D.retrieved} 取得。屬靜態快照，非直接取得 Baltic 授權歷史檔。</p><p class="note">${D.validation.note}${code!=='BDI'?` <a href="${D.validation.source}" target="_blank" rel="noopener">最新值交叉核對來源 ↗</a> 相較已取得的 BDI 公布日期，缺 ${D.validation.missingAgainstBDI.length} 日；不補值。`:''}</p>${code==='BSI'?'<p class="note">BSI 船型／航線基準曾調整；本圖沿用資料來源公布序列，未自行重編歷史，跨年度與 YoY 比較須留意口徑變更。<a href="https://www.balticexchange.com/en/data-services/Circulars/market-announcements-/category-a/2024/circular-19-24-announcement--end-of-dual-reporting-for-bsi.html" target="_blank" rel="noopener">Baltic 2024 年基準變更公告 ↗</a></p>':''}<p><a href="${code.toLowerCase()}-history.csv" download>下載 ${code} 每日數據 CSV ↓</a>　<a href="${code.toLowerCase()}-history.json" download>下載資料與來源 JSON ↓</a></p>`;
}
document.querySelector('#freight-index').addEventListener('change',e=>mount(e.target.value));
mount('BDI');
})();
