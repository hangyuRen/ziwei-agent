import fs from 'node:fs';
import zlib from 'node:zlib';
import { generateChart,setBrightnessSchool } from './algorithm';
import { SCHOOL_AX } from './school-tables.generated';
import { SCHOOL_STAR_ID_TO_NAME } from './school-data';
import { LunarYear,Lunar } from 'lunar-javascript';
const ref=fs.readFileSync('/work/COMMIT','utf8').trim();
fs.writeFileSync('/work/tables.json',JSON.stringify({ref,axes:SCHOOL_AX,names:SCHOOL_STAR_ID_TO_NAME}));
const cases:any[]=[];
function add(y:number,m:number,d:number,policy='split',school='QS'){
 for(const h of [0,1,6,11])for(const g of ['male','female'])cases.push({year:y,month:m,day:d,hour:h,gender:g,policy,school});
}
for(let y=2000;y<=2026;y++)for(const [m,d] of [[2,4],[3,1],[8,16],[12,31]])add(y,m,d);
for(let y=2000;y<=2026;y++){
 const ly=LunarYear.fromYear(y);
 for(const lm of ly.getMonthsInYear())if(lm.getMonth()<0){
  for(const day of [1,15,16,lm.getDayCount()]){
   const s=Lunar.fromYmd(y,lm.getMonth(),day).getSolar();
   for(const p of ['split','prev-month','next-month','origin-month'])add(s.getYear(),s.getMonth(),s.getDay(),p);
  }
 }
}
for(const school of ['QS','XD1','ZZ','XD2'])for(let m=1;m<=12;m++)add(2001,m,16,'split',school);
const results=cases.map(input=>{setBrightnessSchool(input.school);try{return {input,expected:generateChart(input,{leapMonth:input.policy})}}catch(e){return {input,error:String(e)}}});
fs.writeFileSync('/work/parity.json.gz',zlib.gzipSync(JSON.stringify({ref,cases:results})));
console.log('REFERENCE CASES',results.length);
