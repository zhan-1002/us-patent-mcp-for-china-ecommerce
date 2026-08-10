# 电商专利 Scout MCP：中文实战教程

本教程演示如何从一个电商商品描述出发，完成美国专利候选发现、分页聚合、引用扩展和历史召回检查。

## 1. 安装

```bash
git clone https://github.com/zhan-1002/ecommerce-patent-scout-mcp.git
cd ecommerce-patent-scout-mcp
uv sync
uv run patent-mcp-server
```

核心PPUBS、Google Patents和商标搜索不需要USPTO ODP API Key。不要把第三方凭据写入仓库。

## 2. 连接Codex

仓库根目录已经包含 `.mcp.json`。从该目录启动Codex后，确认可以看到名为 `patents` 的MCP Server。

推荐的第一条消息：

```text
使用 patents MCP 搜索美国外观设计专利 religious cross。
请扩展 wooden cross、heart cross、cross ornament 等同义词，
执行PPUBS和Google Patents分页聚合，并按codex_markdown展示结果。
```

## 3. 构建搜索词

不要只翻译商品标题。至少覆盖以下维度：

| 维度 | 示例 |
|---|---|
| 通用产品名 | bottle pourer |
| 正式或行业名称 | olive oil nozzle |
| 功能 | drip-free pouring |
| 结构 | tapered stopper, air tube |
| 形状 | curved spout |
| 场景 | liquor bottle, oil bottle |

商品标题与专利正式标题可能完全不同。D951706在商品语境中是倒酒嘴，但专利标题是 `Olive oil nozzle`。

## 4. 执行分页聚合

向Codex明确要求使用 `patent_search_aggregated`：

```text
queries:
- bottle pour spout
- bottle pourer
- olive oil nozzle
type: DESIGN
sources: BOTH
page_size: 100
max_pages: 3
max_requests: 18
expand_citations: true
```

关注输出中的四组信息：

1. 每个查询和来源实际执行了多少请求；
2. 是否有来源返回503或网络错误；
3. 合并去重后的候选数量；
4. 引用网络使用了哪些种子专利。

`max_requests` 是网络预算，不是数据库总结果数。需要扩大搜索时，优先增加高质量同义词，其次才增加页数。

## 5. 检查历史召回

如果产品已有旧工具测试结果，指定对应基线：

```text
baseline_name: liquor_pour_spout
minimum_recall: 1.0
```

召回率回答的是“新版是否仍找到旧版已经找到的重点专利”，不是代码覆盖率，也不表示所有返回结果都相关。

## 6. 扩展重点候选

对高相关外观专利继续执行：

```text
ppubs_get_citation_network
gp_get_similar_patents
ppubs_search_by_inventor
ppubs_search_by_assignee
ppubs_download_patent_pdf
```

引用、同发明人或同受让人只是候选发现信号。最终外观风险需要比较官方图样形成的整体视觉印象。

## 7. 推荐输出格式

要求Codex先显示：

1. 检索情况；
2. 重点专利对比表；
3. 历史召回结果；
4. 部分失败和检索边界；
5. 需要人工核对的PDF图样。

不要在聊天正文中展开数百条完整JSON；完整数据保留在结构化 `results` 中即可。

## 8. 常见错误

- 只搜一个中文直译词；
- 把单页 `limit` 当作全部结果；
- 忽略标题很短的设计专利；
- Google 503后反复高频重试；
- 把历史样本号直接注入查询以制造100%召回；
- 仅凭专利标题判断侵权。

完成以上流程后，得到的是可解释的候选清单和初步风险筛查，不是法律意见。
