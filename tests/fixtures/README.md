# 上游对拍基准

来源：Renhuai123/ziwei-doushu，提交 7922285d947b36610e7e31c232d8f1e2a0d0871d。
`upstream-parity.json.gz` 由未经修改的上游 `generateChart` 产生，不由 Python 实现生成。
参考引擎依赖 iztro 2.6.1、lunar-javascript 1.7.7；完整引用源码和依赖锁保存在 tests/upstream_reference。

共 2528 组输入，其中 2520 组上游返回命盘，8 组上游自行抛错（2017-08-21 闰六月三十 origin-month × 4 时辰 × 男女）。8 组错误单独记录，不计为成功对拍。Python 使用 lunar-python 可处理该农历日期，网站默认 split 不涉及此上游错误。

覆盖：2000–2026 年固定日期，12 地支/10 天干、男女、早子/丑/午/亥，各闰月首日/十五/十六/末日及四种归属，四套亮度表。冻结参考时点为 2026-11-09，用于当前虚岁/大限断言。

在项目根目录运行 `PYTHONPATH=src python scripts/verify_upstream_parity.py`，或 `pytest tests/test_upstream_parity.py`。逐宫比较宫干、宫名、星名/类型/四化/亮度、命身宫、大限、空宫借星；另比较五行局、命身主、阴阳性别、节气及农历四柱。

重新生成：在 tests/upstream_reference 目录安装 npm ci；按 reference.ts 中的 /work 路径将目录挂载至 Node 测试容器；TZ=Asia/Shanghai 运行 tsx reference.ts。Node 只用于重新生成参考输出，生产环境和 Python 测试均不依赖 Node。


四化与飞星独立基准：`upstream-transformations.json.gz` 为同一固定提交的 `sihua.ts` 实际输出，使用 344 组互异的农历年干、时辰、性别、闰月规则及亮度表组合。通过 `getSiHuaByStem`、`getDaXianSiHua`、`getLiuNianSiHua`、`findIncomingPalaces`、`buildAllSelfSihua` 计算，未调用 Python 四化实现。

重新生成时，把 TypeScript 5.9.3 和 lunar-javascript 1.7.7 安装到临时目录，再运行 `node scripts/generate_transformations_reference.cjs /path/to/typescript/lib/typescript.js /path/to/lunar-javascript`。生成器只转译原始 TypeScript 引用文件，不修改其中的算法；输出包含生年、大限、2026 流年四化、48 条有向宫干飞化与自化。普通 Python 测试只读取冻结数据，无需 Node。
