# USPTO Patent MCP Server (PPUBS + Google Patents)

> 🇨🇳 专为跨境电商产品设计人员优化的双引擎美国专利查询工具
>
> A dual-engine USPTO Patent MCP Server optimized for China e-commerce product patent search.

## Codex 优化（v1.1.0）

本版本针对 Codex 的工具调用和聊天阅读体验进行了专项优化：

- 使用 `patent_search_aggregated` 自动执行多关键词、双来源和多页检索，不再把单页 `limit` 当成完整结果。
- 使用 `patent_evaluate_recall` 将新结果与旧工具历史样本对比；历史候选未召回时明确列出，不允许静默退化。
- 聚合结果同时返回完整结构化数据和 `codex_markdown`。Codex 应优先展示“检索情况、重点专利对比、历史样本召回”三部分。
- 重点候选使用可点击的 Google Patents 链接；聊天正文默认只展示前 12 条，避免大段 JSON 挤占上下文。
- 完整结果仍保留在 `results`，用户要求时再展开，不因聊天折叠而降低实际检索数量。

推荐在 Codex 中直接提出：

```text
使用 patent_search_aggregated 搜索 religious cross，
同时运行 religious_cross 历史召回基线，并按 codex_markdown 展示结果。
```

可用召回基线见资源 `patents://recall-baselines`。

基于 [riemannzeta/patent_mcp_server](https://github.com/riemannzeta/patent_mcp_server) 修改的增强版本。

## 与原版的区别

| 特性 | 原版 | 本版本 |
|------|------|--------|
| API Key | ODP 工具需要 | **无需任何 API Key** |
| 工具数量 | 52 个 | 24 个（专利、商标、聚合与召回评估） |
| 搜索引擎 | PPUBS 单一引擎 | PPUBS + Google Patents 双引擎 |
| 设计专利 | TF-IDF（效果差） | Google ML 排序 + 引用网络 |
| 引用分析 | 无 | 双向引用网络 + urpn 提取 |
| 目标用户 | 专业专利研究人员 | 跨境电商产品设计人员 |

## 主要功能

### 1. 专利搜索（无需 API Key）
- 搜索授权专利和公开申请
- 全文搜索（标题、摘要、权利要求、说明书）
- 支持设计专利（D系列）和实用新型专利

### 2. 专利文档获取
- 获取专利全文内容
- 下载专利 PDF 文件

### 3. 产品专利搜索工作流（新增）
基于实际搜索经验总结的优化搜索流程：
- **多策略组合搜索** - 自动执行精确短语、标题、关键词组合等搜索
- **发明人追踪** - 发现同发明人相关专利
- **申请人追踪** - 发现公司专利家族
- **精确标题搜索** - 设计专利高效搜索

## 快速开始

### 环境要求
- Python 3.10-3.13
- [UV](https://docs.astral.sh/uv/) 包管理器

### 安装

```bash
# 克隆仓库
git clone https://github.com/zhan-1002/us-patent-mcp-for-china-ecommerce.git
cd us-patent-mcp-for-china-ecommerce

# 安装依赖
uv sync

# 验证安装
uv run patent-mcp-server
```

### Codex 配置（推荐）

仓库已包含 `.mcp.json`。从仓库目录启动 Codex 后，使用本地 `patents` MCP 即可。不要把 API key 写入仓库配置；需要令牌时使用环境变量。

Codex 聊天展示约定：

1. 先显示 `codex_markdown` 中的检索情况。
2. 用可点击表格展示重点专利，不在正文倾倒完整 JSON。
3. 明确显示历史召回率和遗漏号码。
4. 只有用户要求时才展开完整 `results`。

### Claude Code 配置

```shell
claude mcp add-json patents '{"command": "uv", "args": ["--directory", "/path/to/us-patent-mcp-for-china-ecommerce", "run", "patent-mcp-server"]}'
```

### Claude Desktop 配置

编辑 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "patents": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/us-patent-mcp-for-china-ecommerce",
        "run",
        "patent-mcp-server"
      ]
    }
  }
}
```

## 使用示例

### 产品专利搜索

使用 `/patent-search` 技能启动优化搜索流程：

```
帮我搜索这个产品的专利：
- 产品名称：Self Watering Pots with Water Level Indicator（可以直接复制亚马逊标题）
- 关键特征：水位指示器、可拆卸底座（补充说明产品功能特征有利于搜索隐藏专利）
- 产品图片：上传产品图片用于模型视觉分析
```

系统会自动：
1. 分析产品关键特征
2. 构建搜索关键词
3. 执行多策略搜索
4. 追踪发明人和申请人
5. 生成搜索报告

## 主要工具

### 基础搜索工具

| 工具 | 功能 | 使用场景 |
|------|------|----------|
| `ppubs_search_patents` | 搜索授权专利 | 查找已授权专利 |
| `ppubs_search_applications` | 搜索专利申请 | 查找申请中的专利 |
| `ppubs_get_patent_by_number` | 按专利号获取 | 获取已知专利详情 |
| `ppubs_get_full_document` | 获取完整文档 | 获取专利全文 |
| `ppubs_download_patent_pdf` | 下载 PDF | 保存专利文档 |

### 增强搜索工具

| 工具 | 功能 | 优势 |
|------|------|------|
| `ppubs_search_combined` | 多策略组合搜索 | 自动执行4种搜索策略 |
| `ppubs_search_by_ttl` | 标题精确搜索 | 设计专利命中率最高 |
| `ppubs_search_by_inventor` | 发明人搜索 | 按发明人名称搜索 |
| `ppubs_search_by_assignee` | 申请人搜索 | 按公司名称搜索 |
| `ppubs_get_inventor_patents` | 自动发明人追踪 | 一键查找同发明人专利 |
| `patent_search_aggregated` | 双来源分页聚合搜索 | 多查询、多页、去重、请求预算与历史召回检查 |
| `patent_evaluate_recall` | 历史样本召回评估 | 防止新版本遗漏旧工具已找到的重点专利 |

### Google Patents 工具（双引擎）

| 工具 | 功能 | 优势 |
|------|------|------|
| `gp_search_patents` | ML 排序搜索 | DESIGN/PATENT/ANY 分面，设计专利效果远超 PPUBS |
| `gp_get_patent_detail` | 专利详情 | 含摘要、CPC、引用、缩略图 |
| `gp_get_similar_patents` | ML 相似专利 | 基于 CPC + 标题关键词的相似设计发现 |
| `gp_get_citations` | Google 引用图 | forward/backward/both 引用方向 |

### 引用分析工具（新增）

| 工具 | 功能 | 优势 |
|------|------|------|
| `ppubs_get_citation_network` | **双向引用网络（推荐）** | 一次调用获取 backward + forward 完整专利族 |
| `ppubs_get_citations` | 提取 urpn 引用 | 从 PPUBS 完整文档提取引用专利号 |
| `ppubs_get_cited_by` | 反向引用查询 | 发现哪些较新专利引用了目标专利 |

## 搜索策略

### 设计专利搜索（推荐工作流）
```
1. gp_search_patents("产品关键词", "DESIGN")       → ML 排序发现核心设计专利
2. ppubs_get_citation_network("核心专利号")          → 双向引用获取完整专利族
3. gp_get_similar_patents("专利号")                  → ML 推荐相似设计
4. ppubs_get_full_document(guid, "USPAT")           → 获取完整权利要求
```

### 关键策略：双向引用网络
设计专利常有极短标题（如"Cross"），关键词搜索无法发现。
**必须对每个核心专利运行 `ppubs_get_citation_network`**，获取向前和向后完整引用链。

### 发明人追踪
```
发现相关专利后，使用 ppubs_get_inventor_patents
常发现：不同名称但结构相似的专利、延续申请、改进版本
```

## 致谢

本项目基于 [riemannzeta/patent_mcp_server](https://github.com/riemannzeta/patent_mcp_server) 修改，感谢原作者 Michael Frank Martin 的开源贡献。

原项目致谢：
- [Parker Hancock](https://github.com/parkerhancock) 的 [Patent Client 项目](https://github.com/parkerhancock/patent_client) 为理解 Public Search API 提供了重要参考

## 许可证

MIT License - 详见 [LICENSE.md](LICENSE.md)

Copyright (c) 2025 Michael Frank Martin (原作者)
