import asyncio,json
from ziwei.config import Settings
from ziwei.db import Repository
from ziwei.search import Search,rrf_fuse
from ziwei.llm import LLM
from ziwei.zhipu import Zhipu

async def main():
 settings=Settings();repo=await Repository.connect(settings.database_url);z=Zhipu(settings);search=Search(settings,z);llm=LLM(settings)
 try:
  await search.load_catalog(repo)
  questions=['在天纪中，去单位上班拿固定工资和自己做生意，分别应该看什么宫？','命宫为什么还要一起看财帛、官禄和迁移？','化忌是什么意思，和化禄有什么区别？']
  for question in questions:
   vector=(await z.embed([question]))[0]
   warm=await asyncio.gather(search.es_search([question],size=12),repo.vector_search(vector,settings.zhipu_embedding_model,12))
   directory=search.directory_context(question,rrf_fuse(warm,24))
   keywords,subquestions,paths=await search.plan_query(question,llm,directory)
   print(json.dumps({'question':question,'keywords':keywords,'subquestions':subquestions,'directory_sections':len(directory['sections']),'heading_paths':len(paths)},ensure_ascii=False),flush=True)
   rows=await search.search(question,llm,repo)
   assert rows,question
   assert all(row['quote'].startswith('来源：') and row['sources'] and 0.5<row['rerank_score'] for row in rows)
   print(json.dumps({'hits':[{'book':row['book'],'h2':row['h2'],'h3':row['h3'],'index':row['chunk_index'],'total':row['chunk_total'],'score':row['rerank_score'],'sources':len(row['sources'])} for row in rows]},ensure_ascii=False),flush=True)
  print('LIVE_HYBRID_SEARCH_OK',flush=True)
 finally:
  await search.close();await z.close();await llm.close();await repo.pool.close()
asyncio.run(main())
