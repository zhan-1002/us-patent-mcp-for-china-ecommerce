# 电商专利 Scout MCP

> E-commerce Patent Scout MCP — 面向跨境电商的美国专利检索与风险筛查工具。

聚合 USPTO PPUBS 与 Google Patents 双引擎，将商品描述转化为可复现的多关键词检索，支持分页聚合、专利号规范化去重、引用网络扩展与历史召回评估。

[![Tests](https://img.shields.io/github/actions/workflow/status/zhan-1002/ecommerce-patent-scout-mcp/tests.yml?branch=main&style=flat-square&label=tests)](https://github.com/zhan-1002/ecommerce-patent-scout-mcp/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/zhan-1002/ecommerce-patent-scout-mcp?style=flat-square)](https://github.com/zhan-1002/ecommerce-patent-scout-mcp/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.10--3.13-3776ab?style=flat-square&logo=python&logoColor=white)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-16a34a?style=flat-square)](LICENSE.md)

## 目录

- [核心能力](#核心能力)
- [快速开始](#快速开始)
- [客户端配置](#客户端配置)
- [使用示例](#使用示例)
- [工具与接口](#工具与接口)
- [检索方法论](#检索方法论)
- [数据源与限制](#数据源与限制)
- [开发与验证](#开发与验证)
- [文档](#文档)
- [许可证](#许可证)

## 核心能力

| 能力 | 说明 |
|---|---|
| 双引擎检索 | USPTO PPUBS 官方全文与 Google Patents ML 排序互补 |
| 分页聚合 | 多关键词、多页、多来源检索，请求预算可控 |
| 专利号规范化 | 跨来源统一 `D` / `USD` / 实用专利格式并去重 |
| 引用网络扩展 | 通过双向引用发现标题过短的设计专利 |
| 历史召回评估 | 对 7 组历史样本、16 件重点专利执行回归检查 |
| 官方文档获取 | 全文、PDF、发明人、受让人、CPC、状态代码 |
| 商标检索 | USPTO 商标记录与序列号查询 |
| Agent 集成 | 返回结构化 Markdown 摘要，适配 Codex / Claude |

检索流程：

```text
商品描述
  → 关键词与同义词扩展
  → Google Patents + USPTO PPUBS 分页搜索
  → 专利号规范化与跨来源去重
  → 引用 / 发明人 / 受让人扩展
  → 历史样本召回检查
  → 结构化候选清单
```

## 快速开始

### 环境要求

- Python 3.10 – 3.13
- [uv](https://docs.astral.sh/uv/) 包管理器
- 可访问 USPTO PPUBS 与 Google Patents 的网络环境

### 安装与启动

```bash
git clone https://github.com/zhan-1002/ecommerce-patent-scout-mcp.git
cd ecommerce-patent-scout-mcp

uv sync
uv run patent-mcp-server
```

核心 PPUBS、Google Patents 与商标检索无需 USPTO ODP API Key。

## 客户端配置

### Codex

仓库根目录提供 `.mcp.json`：

```json
{
  "mcpServers": {
    "patents": {
      "command": "uv",
      "args": ["run", "patent-mcp-server"],
      "description": "E-commerce Patent Scout MCP optimized for Codex"
    }
  }
}
```

### Claude Code

```shell
claude mcp add-json patents '{"command":"uv","args":["--directory","/path/to/ecommerce-patent-scout-mcp","run","patent-mcp-server"]}'
```

### Claude Desktop

编辑 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "patents": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/ecommerce-patent-scout-mcp",
        "run",
        "patent-mcp-server"
      ]
    }
  }
}
```

## 使用示例

### 商品专利检索

```text
搜索该商品在美国的相关专利：

- 商品：Self Watering Pots with Water Level Indicator
- 关键特征：水位指示器、可拆卸底座、透明储水区
- 目标：优先检查有效的美国外观设计专利

扩展英文同义词，执行分页聚合搜索，追踪发明人、受让人与引用网络，
按“专利、状态、初步风险、对比结论”输出表格。
```

### 分页聚合搜索

```text
调用 patent_search_aggregated：
- queries: ["bottle pour spout", "bottle pourer", "olive oil nozzle"]
- type: DESIGN
- sources: BOTH
- page_size: 100
- max_pages: 3
- max_requests: 18
- baseline_name: liquor_pour_spout
- minimum_recall: 1.0
```

| 参数 | 作用 | 建议 |
|---|---|---|
| `queries` | 多组检索词 | 覆盖产品名、正式名称与同义词 |
| `type` | `DESIGN` / `PATENT` / `ANY` | 外观筛查使用 `DESIGN` |
| `sources` | `BOTH` / `GOOGLE` / `PPUBS` | 正式检索使用 `BOTH` |
| `page_size` | 单次请求数量 | Google ≤100，PPUBS ≤500 |
| `max_pages` | 每个查询、来源的最大页数 | 初筛 2–3 页 |
| `max_requests` | 全局请求预算 | 控制延迟与上游压力 |
| `max_results` | 合并后最大结果数 | 不影响已检索数据的召回计算 |
| `baseline_name` | 历史召回基线 | 用于版本回归检查 |
| `expand_citations` | 扩展重点候选引用 | 设计专利建议开启 |

### 已知专利号核验

```text
查询 USD1066113S1 的 USPTO 官方记录、完整文档、PDF 与双向引用网络。
区分外观设计号与同数字的实用专利，不要只按数字模糊匹配。
```

## 工具与接口

当前版本注册 24 个 MCP tools、6 个 prompts 与 5 类固定 resources。

### 聚合与召回

| 工具 | 用途 |
|---|---|
| `patent_search_aggregated` | 多关键词、双来源、分页、去重、引用扩展与召回检查 |
| `patent_evaluate_recall` | 将实际结果与历史样本独立对比 |

### USPTO PPUBS

| 工具 | 用途 |
|---|---|
| `ppubs_search_patents` | 搜索授权专利 |
| `ppubs_search_applications` | 搜索公开申请 |
| `ppubs_get_patent_by_number` | 按规范化专利号精确查询 |
| `ppubs_get_full_document` | 获取完整专利文档 |
| `ppubs_download_patent_pdf` | 下载 USPTO 专利 PDF |
| `ppubs_search_combined` | 执行多策略查询并合并结果 |
| `ppubs_search_by_ttl` | 按标题精确搜索 |
| `ppubs_search_by_inventor` | 按发明人搜索 |
| `ppubs_search_by_assignee` | 按受让人搜索 |
| `ppubs_get_inventor_patents` | 追踪发明人的相关专利族 |

### Google Patents

| 工具 | 用途 |
|---|---|
| `gp_search_patents` | Google Patents 搜索，支持类型与数量限制 |
| `gp_get_patent_detail` | 获取摘要、分类、缩略图与详情 |
| `gp_get_similar_patents` | 发现标题与分类相近的候选 |
| `gp_get_citations` | 获取前向或后向引用 |

### 引用网络

| 工具 | 用途 |
|---|---|
| `ppubs_get_citation_network` | 获取重点专利的双向引用网络 |
| `ppubs_get_citations` | 从完整文档提取后向引用 |
| `ppubs_get_cited_by` | 查询引用目标专利的后续专利 |

### 商标与辅助

| 工具 | 用途 |
|---|---|
| `tmsearch_search` | 搜索 USPTO 商标记录 |
| `tmsearch_get_by_serial` | 按序列号获取商标记录 |
| `get_cpc_info` | 查询 CPC 分类信息 |
| `get_status_code` | 查询专利状态代码 |
| `check_api_status` | 检查已配置数据源状态 |

### Prompts

- `product_patent_search`：电商商品专利搜索工作流
- `prior_art_search`：现有技术搜索
- `patent_validity_analysis`：有效性分析
- `competitor_portfolio_analysis`：竞争对手组合分析
- `freedom_to_operate`：FTO 初步分析
- `patent_landscape`：专利景观分析

### Resources

| URI | 内容 |
|---|---|
| `patents://cpc` | CPC 分类参考 |
| `patents://status-codes` | 状态代码说明 |
| `patents://sources` | 数据源说明 |
| `patents://search-syntax` | PPUBS 查询语法 |
| `patents://recall-baselines` | 历史召回基线 |

## 检索方法论

### 关键词构建

从商品描述提取多维度检索词：

| 维度 | 示例 |
|---|---|
| 通用产品名 | bottle pourer |
| 正式或行业名称 | olive oil nozzle |
| 功能 | drip-free pouring |
| 结构 | tapered stopper, air tube |
| 形状 | curved spout |
| 使用场景 | liquor bottle, oil bottle |

商品名称与专利正式标题可能不同；`bottle pour spout` 的正式标题可能是 `olive oil nozzle`。

### 设计专利检索

```text
1. patent_search_aggregated（多组商品关键词，type="DESIGN"）
2. ppubs_get_citation_network（重点候选）
3. gp_get_similar_patents（重点候选）
4. ppubs_search_by_inventor / ppubs_search_by_assignee
5. ppubs_download_patent_pdf
6. 人工比较图样形成的整体视觉印象
```

美国外观设计专利标题通常很短，关键词检索可能遗漏。双向引用网络可补充更早设计、后续设计、连续改进及名称不同但结构接近的候选。引用关系代表检索或审查关联，不自动代表外观相似或侵权风险。

### 召回评估

```text
召回率 = 已召回的历史重点专利数 ÷ 历史重点专利总数
```

召回率用于回答“新版是否仍能召回旧版已发现的重点专利”，不等同于代码覆盖率，也不表示所有返回结果均相关。当前基线覆盖 7 组产品、16 件重点专利；基线通过仅证明已知样本未退化，实际质量仍需结合精确率、结果排名、数据源可用性与人工图样比对。

## 数据源与限制

- PPUBS 为 USPTO 官方全文检索，核心使用无需 API Key。
- Google Patents 可能返回 503 或触发访问限制；聚合工具会快速记录失败并继续 PPUBS。
- PPUBS 网络异常会写入 `query_stats`，其他可用来源继续返回部分结果。
- `limit`、`max_pages`、`max_requests` 是请求预算，不代表数据库总结果数。
- 需要提高召回时，优先增加高质量同义词，其次增加页数与预算，并对高相关候选扩展引用、发明人和受让人。

## 安全

不要在仓库、配置文件或代码中硬编码 API Key。需要凭据时使用环境变量、客户端 Secrets 或本机私有配置；任何曾提交到 Git 的凭据应立即撤销并轮换。

## 开发与验证

```bash
uv sync
uv run pytest
uv build
```

当前验证结果：

- 87 项自动化测试通过
- GitHub Actions 覆盖 Python 3.10–3.13 与发行包构建
- 7/7 组历史召回基线通过
- 16/16 件历史重点专利召回
- 聚合模块覆盖率 97%，项目总覆盖率 34%
- v1.1.0 Release 已发布（wheel + sdist）

版本记录见 [CHANGELOG.md](CHANGELOG.md)。

## 文档

- [中文实战教程](docs/quickstart.zh-CN.md)
- [English Tutorial](docs/quickstart.en.md)
- [召回案例：引用网络发现泛化标题设计专利](docs/case-study-religious-cross.md)

## 许可证

[MIT License](LICENSE.md)

本项目基于 [riemannzeta/patent_mcp_server](https://github.com/riemannzeta/patent_mcp_server) 开发，感谢原作者 Michael Frank Martin 及所有贡献者。
