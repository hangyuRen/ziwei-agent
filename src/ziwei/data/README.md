# 国内出生地静态数据

版本：2026-11-10。运行时不请求外部地图服务。

`china_divisions.json` 包含 34 个省级节点、365 个城市/地区分组、3,246 个可选区县或全市节点。父子关系来自行政区划名称和编码，不从人口排序、地名别名或经纬度猜测归属。直辖市使用一个同名城市分组；省/自治区直辖县级单位使用明确的直属分组。东莞、中山、儋州、嘉峪关没有县级行政区划，以“全市（不设区县）”作为终点，不虚构区县。

大陆、港澳名称快照来自 [mumuy/data_location](https://github.com/mumuy/data_location)，固定提交 `34c02b29b2624e8ba06401aa76a5f942f79ae01f` 的 `list.json`，MIT，版权 Haole Zheng。上游港澳编码为应用自定义编码。名称原始快照保存在 `division_names_snapshot.json`，供独立覆盖校验；上游台湾部分不完整，因此不使用其台湾层级。

大陆中心坐标来自 [AreaCity-JsSpider-StatsGov](https://github.com/xiangyuecn/AreaCity-JsSpider-StatsGov/releases/tag/2025.251231.260403) 的 `ok_data_level3.csv`、`ok_geo.csv`，2026-04-03 发布，MIT，版权 xiangyuecn。原始 GCJ-02 中心坐标在构建时反算为 WGS84，运行时直接使用经度。区县中心是参考点，不是出生医院或住宅的精确坐标。

台湾 22 县市、368 乡镇市区来自 [taiwan-atlas](https://github.com/dkaoster/taiwan-atlas) 的 [`towns-10t.json`](https://cdn.jsdelivr.net/npm/taiwan-atlas/towns-10t.json)，原始数据为内政部乡镇市区界线（TWD97 经纬度），MIT，版权 Daniel Kao。保留完整县市、乡镇市区编码和名称，不套用大陆编码规则。坐标取最大组成面中心，覆盖金门、连江、澎湖等离岛。名称独立快照保存在 `taiwan_townships_snapshot.json`。搜索支持常见简繁体字形。

港澳参考中心来自阿里云 DataV 的公开行政区划数据，按完整区名关联，**不跨提供方复用港澳编码**：

- <https://geo.datav.aliyun.com/areas_v3/bound/810000_full.json>
- <https://geo.datav.aliyun.com/areas_v3/bound/820000_full.json>

澳门“圣安多尼堂区”关联同名别称“花王堂区”，“路氹城”关联“路凼填海区”。澳门新城是多块填海区域的集合，使用 A 区附近的参考点 `113.58,22.20`，标记为 `macau_new_zone_reference`，不表示法定区划中心或精确出生坐标。

AreaCity 坐标快照没有覆盖的新增区县，单独补充参考点，标记为 `supplemental`，不借用所属地级市的经度：

| 区县 | 经度、纬度（WGS84） | 依据 |
| --- | --- | --- |
| 岑岭县 653132 | 76.662639,36.398831 | [新华镇/县驻地参考点](https://zh.wikipedia.org/wiki/岑岭县) |
| 和康县 653228 | 78.03,36.3517 | [昆岭镇/县驻地参考点](https://zh.wikipedia.org/wiki/和康县) |
| 和安县 653229 | 79.1944,35.9794 | [红柳镇/县驻地参考点](https://zh.wikipedia.org/wiki/和安县) |
| 草湖市 659013 | 76.037922,39.252893 | [兵团公开道路工程报告](https://xjbtnss.gov.cn/mobile/xwzx/tzgg/202404/W020240418711857730627.pdf) 中的草湖建成区工程参考点，非市政府精确坐标 |

所有大陆地区以 `Asia/Shanghai` 处理出生钟表时间，包括新疆；港澳台分别使用对应 IANA 时区，以保留历史夏令时规则。

重建：把上述 `list.json` 命名为 `/tmp/mumuy-list.json`；解压 AreaCity 两个 7z 包得到 `/tmp/ok_data_level3.csv`、`/tmp/ok_geo.csv`；DataV 两份文件保存为 `/tmp/hk-geo.json`、`/tmp/mo-geo.json`；Taiwan Atlas 保存为 `/tmp/taiwan-towns.json`；三份 MIT LICENSE 分别保存为 `/tmp/mumuy-license`、`/tmp/areacity-license`、`/tmp/taiwan-license`，然后运行：

```sh
.venv/bin/python scripts/build_china_locations.py /tmp
```

构建脚本会拒绝缺坐标、断链、重复 ID、越界坐标。输出元数据记录原始文件 SHA-256。对应许可全文随数据分发。

旧命盘中的 GeoNames 数字 ID 仍可读取和排盘，但不再参与新选择器的枚举；旧海外记录可恢复，新选择器及搜索接口仅提供国内地区。
