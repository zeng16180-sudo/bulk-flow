(()=>{'use strict';
const D=window.FLOW_SUPPLY_OUTLOOK,root=document.getElementById('supply');
if(!D||!root)return;
const n=v=>v.toLocaleString('zh-TW',{maximumFractionDigits:1}),range=a=>`${n(a[0])}–${n(a[1])}%`;
let scenario='closed';
function draw(){
 const s=D.bimcoLatest.scenarios[scenario],years=Object.keys(s.years);
 root.querySelector('#supply-scenario-note').textContent=s.assumption;
 root.querySelectorAll('[data-supply-scenario]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.supplyScenario===scenario)));
 const left=108,right=592,scale=v=>left+v/6*(right-left),parts=[];
 for(let i=0;i<=6;i++){const x=scale(i);parts.push(`<line x1="${x}" x2="${x}" y1="28" y2="227" stroke="#dce5e9"/><text x="${x}" y="18" text-anchor="middle" fill="#60717e" font-size="12">${i}%</text>`);}
 years.forEach((year,yi)=>{
  const top=65+yi*112;
  parts.push(`<text x="12" y="${top+22}" fill="#182d3b" font-size="16" font-weight="600">${year}</text>`);
  [['demand','#166e79',top],['supply','#bc8339',top+34]].forEach(([key,color,y])=>{
   const a=s.years[year][key],x1=scale(a[0]),x2=scale(a[1]);
   parts.push(`<line x1="${x1}" x2="${x2}" y1="${y}" y2="${y}" stroke="${color}" stroke-width="12" stroke-linecap="round"/><text x="${x2+14}" y="${y+4}" fill="#182d3b" font-size="12">${range(a)}</text>`);
  });
 });
 root.querySelector('#supply-balance-chart').innerHTML=`<svg viewBox="0 0 690 240" role="img" aria-label="${s.label}情境：${years.map(y=>`${y}年船舶需求增長${range(s.years[y].demand)}、有效供給增長${range(s.years[y].supply)}`).join('；')}。${scenario==='open'?'2027年依原文增加1個百分點換算。':''}">${parts.join('')}</svg>`;
 root.querySelector('#supply-balance-rows').innerHTML=years.map(y=>`<tr><td>${y}</td><td>${range(s.years[y].demand)}</td><td>${range(s.years[y].supply)}</td><td><span class="supply-balance-badge">供給增速較高</span></td></tr>`).join('');
}
root.querySelectorAll('[data-supply-scenario]').forEach(b=>b.addEventListener('click',()=>{scenario=b.dataset.supplyScenario;draw();}));

draw();
})();
