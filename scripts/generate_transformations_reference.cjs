// Regenerate frozen outputs by running the unmodified upstream TypeScript helpers.
// node this-file /path/to/typescript/lib/typescript.js /path/to/lunar-javascript
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),zlib=require('node:zlib');
const ts=require(path.resolve(process.argv[2]));
const root=path.resolve(__dirname,'..'),reference=path.join(root,'tests/upstream_reference');
const output=fs.mkdtempSync(path.join(os.tmpdir(),'ziwei-sihua-reference-'));
fs.mkdirSync(path.join(output,'node_modules'));
fs.symlinkSync(path.resolve(process.argv[3]),path.join(output,'node_modules/lunar-javascript'),'dir');
for(const name of ['constants','sihua','yunxian-context']){
 const source=fs.readFileSync(path.join(reference,name+'.ts'),'utf8');
 fs.writeFileSync(path.join(output,name+'.js'),ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText);
}
const api=require(path.join(output,'sihua.js'));
const bundle=JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(root,'tests/fixtures/upstream-parity.json.gz'))));
const kinds=['禄','权','科','忌'],seen=new Set(),cases=[];
function layer(chart,raw){
 return {...raw,placements:kinds.map(siHua=>{
  const starName=raw.transforms[siHua],palace=chart.palaces.find(p=>p.stars.some(s=>s.name===starName));
  if(!palace)throw Error('Missing '+starName);
  return {siHua,starName,targetBranch:palace.branch,targetPalace:palace.name};
 })};
}
const stems=require(path.join(output,'constants.js')).STEMS;
for(const item of bundle.cases){
 if(!item.expected)continue;
 const chart=item.expected,inp=item.input,key=JSON.stringify([chart.lunarInfo.yearStem,inp.hour,inp.gender,inp.policy,inp.school]);
 if(seen.has(key))continue;seen.add(key);
 const nativeStem=chart.lunarInfo.yearStem;
 const natal=layer(chart,{stemIndex:nativeStem,stemName:stems[nativeStem],transforms:api.getSiHuaByStem(nativeStem)});
 const flights=[];
 for(const target of chart.palaces)for(const star of target.stars)for(const siHua of kinds){
  for(const source of api.findIncomingPalaces(chart,star.name,siHua))flights.push({siHua,starName:star.name,
   targetBranch:target.branch,targetPalace:target.name,sourceBranch:source.branch,sourcePalace:source.name,
   stemIndex:source.stem,stemName:stems[source.stem],self:source.branch===target.branch});
 }
 flights.sort((a,b)=>a.sourceBranch-b.sourceBranch||kinds.indexOf(a.siHua)-kinds.indexOf(b.siHua));
 cases.push({input:inp,expected:{reference:bundle.ref,natal,
  daXians:chart.daXians.map((d,index)=>({index,...d,...layer(chart,api.getDaXianSiHua(chart,index))})),
  annual:{year:2026,...layer(chart,api.getLiuNianSiHua(2026))},
  flyingStars:flights,selfSihua:api.buildAllSelfSihua(chart)}});
}
fs.writeFileSync(path.join(root,'tests/fixtures/upstream-transformations.json.gz'),zlib.gzipSync(JSON.stringify({ref:bundle.ref,cases})));
console.log('REFERENCE CASES',cases.length);
