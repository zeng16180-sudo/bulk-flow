(()=>{'use strict';
const D=window.FLOW_SUPPLY_OUTLOOK,root=document.getElementById('supply');
if(!D||!root)return;
const n=v=>v.toLocaleString('zh-TW',{maximumFractionDigits:1}),range=a=>`${n(a[0])}–${n(a[1])}%`;
const scenarios=D.bimcoLatest.scenarios;
let scenario=Object.keys(scenarios)[0];
const controls=root.querySelector('#supply-scenarios');
for(const [key,value] of Object.entries(scenarios)){
 const button=document.createElement('button');
 button.type='button';button.dataset.supplyScenario=key;button.textContent=value.label;
 controls.appendChild(button);
}
function draw(){
 const s=D.bimcoLatest.scenarios[scenario],years=Object.keys(s.years);
 root.querySelector('#supply-scenario-note').textContent=s.assumption;
 root.querySelectorAll('[data-supply-scenario]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.supplyScenario===scenario)));
 const values=Object.values(s.years).flatMap(y=>[...y.supply,...y.demand]);
 const min=Math.min(0,Math.floor(Math.min(...values))),max=Math.max(1,Math.ceil(Math.max(...values))+1);
 const left=108,right=585,scale=v=>left+(v-min)/(max-min)*(right-left),parts=[],height=34+years.length*105;
 for(let i=min;i<=max;i+=Math.max(1,Math.ceil((max-min)/8))){const x=scale(i);parts.push(`<line x1="${x}" x2="${x}" y1="28" y2="${height-12}" stroke="#dce5e9"/><text x="${x}" y="18" text-anchor="middle" fill="#60717e" font-size="12">${i}%</text>`);}
 years.forEach((year,yi)=>{
  const top=60+yi*105;
  parts.push(`<text x="12" y="${top+22}" fill="#182d3b" font-size="16" font-weight="600">${year}</text>`);
  [['demand','#166e79',top],['supply','#bc8339',top+34]].forEach(([key,color,y])=>{
   const a=s.years[year][key],x1=scale(a[0]),x2=scale(a[1]);
   parts.push(`<line x1="${x1}" x2="${x2}" y1="${y}" y2="${y}" stroke="${color}" stroke-width="12" stroke-linecap="round"/><text x="${x2+14}" y="${y+4}" fill="#182d3b" font-size="12">${range(a)}</text>`);
  });
 });
 root.querySelector('#supply-balance-chart').innerHTML=`<svg viewBox="0 0 690 ${height}" role="img" aria-label="${years.map(y=>`${y}年船舶需求增長${range(s.years[y].demand)}、有效供給增長${range(s.years[y].supply)}`).join('；')}">${parts.join('')}</svg>`;
 root.querySelector('#supply-balance-rows').innerHTML=years.map(y=>{
  const {demand,supply}=s.years[y];
  const balance=supply[0]>demand[1]?'供給增速區間較高':demand[0]>supply[1]?'需求增速區間較高':'增速區間重疊';
  return `<tr><td>${y}</td><td>${range(demand)}</td><td>${range(supply)}</td><td><span class="supply-balance-badge">${balance}</span></td></tr>`;
 }).join('');
}
root.querySelectorAll('[data-supply-scenario]').forEach(b=>b.addEventListener('click',()=>{scenario=b.dataset.supplyScenario;draw();}));

draw();
})();
