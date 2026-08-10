<div align="center">

# 电商专利 Scout MCP

### E-commerce Patent Scout MCP

面向跨境电商商品调研的美国专利检索 MCP Server：支持多关键词、多来源、连续分页、引用扩展和历史召回评估。

[![Version](https://img.shields.io/badge/version-1.1.0-2563eb?style=flat-square)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/Python-3.10--3.13-3776ab?style=flat-square&logo=python&logoColor=white)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-compatible-7c3aed?style=flat-square)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/github/actions/workflow/status/zhan-1002/ecommerce-patent-scout-mcp/tests.yml?branch=main&style=flat-square&label=tests)](https://github.com/zhan-1002/ecommerce-patent-scout-mcp/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/zhan-1002/ecommerce-patent-scout-mcp?style=flat-square)](https://github.com/zhan-1002/ecommerce-patent-scout-mcp/releases/latest)
[![License](https://img.shields.io/badge/license-MIT-16a34a?style=flat-square)](LICENSE.md)

**[快速开始](#快速开始) · [Codex 配置](#codex-配置推荐) · [工具目录](#工具目录) · [搜索方法](#推荐搜索方法) · [故障排查](#故障排查)**

**教程： [中文](docs/quickstart.zh-CN.md) · [English](docs/quickstart.en.md) · [真实召回案例](docs/case-study-religious-cross.md)**

</div>

> [!IMPORTANT]
> 本项目用于专利检索、候选发现和初步风险筛查，不构成法律意见。是否侵权仍需结合有效权利要求、外观设计图样、法律状态和目标商品整体视觉印象，由专业人士判断。

---

## 为什么使用这个项目

普通专利搜索经常只返回有限的首屏结果。对于标题很短的美国外观设计专利，例如 `Cross`、`Nozzle`，仅靠商品关键词还容易漏掉真正相关的历史候选。

本项目针对这个问题提供一条可解释、可复测的搜索链路：

```text
商品描述
   ↓
关键词与同义词扩展
   ↓
Google Patents + USPTO PPUBS 分页搜索
   ↓
专利号规范化与跨来源去重
   ↓
发明人 / 受让人 / 双向引用网络扩展
   ↓
历史样本召回检查
   ↓
Codex 重点专利对比表
```

### 核心能力

| 能力 | 解决的问题 | 推荐入口 |
|---|---|---|
| 分页聚合搜索 | 避免把单页 `limit` 误认为全部结果 | `patent_search_aggregated` |
| 双来源检索 | 兼顾 Google 相关性与 USPTO 官方数据 | `sources="BOTH"` |
| 引用网络扩展 | 发现标题过短、关键词难以命中的设计专利 | `ppubs_get_citation_network` |
| 历史召回评估 | 防止新版本漏掉旧工具已发现的重点候选 | `patent_evaluate_recall` |
| Codex 专用输出 | 减少大段 JSON，优先展示可点击的重点结果 | `codex_markdown` |
| 有界请求预算 | 控制分页数量、网络调用和聊天等待时间 | `max_pages` / `max_requests` |

### 一个真实的召回改进

`religious_cross` 历史样本包含5件重点外观专利。关键词和标题检索最初只找到4件；新版从 `D656429` 的真实引用网络中发现标题过于宽泛的 `D1050666`，最终达到5/5召回。整个过程使用14次网络请求，合并得到114件设计候选，没有把预期专利号注入查询。

[阅读完整案例与适用边界 →](docs/case-study-religious-cross.md)

### 项目定位

本仓库基于 [riemannzeta/patent_mcp_server](https://github.com/riemannzeta/patent_mcp_server) 开发，重点服务中国跨境电商商品专利初筛。

- 核心 PPUBS、Google Patents、PDF、引用和商标搜索不要求 USPTO ODP API Key。
- 本项目聚焦商品发现和设计专利检索，不是上游全部 ODP、PTAB、诉讼及完整商标工具的等量替代。
- 需要通用专利事务研究时，请同时评估上游项目的完整工具范围。

---

## 快速开始

### 环境要求

- Python 3.10–3.13
- [uv](https://docs.astral.sh/uv/) 包管理器
- 可访问 USPTO PPUBS 和 Google Patents 的网络环境

### 安装并启动

```bash
git clone https://github.com/zhan-1002/ecommerce-patent-scout-mcp.git
cd ecommerce-patent-scout-mcp

uv sync
uv run patent-mcp-server
```

看到 MCP Server 启动日志即表示安装成功。核心搜索不需要把第三方 API Key 写入仓库。

### 30 秒验证

在支持 MCP 的客户端中提问：

```text
搜索美国外观设计专利 religious cross。
使用 PPUBS 和 Google Patents 聚合分页搜索，
运行 religious_cross 历史召回基线，并按 Codex 表格展示结果。
```

预期输出包含：

1. 每个关键词和数据源的检索数量；
2. 可点击的重点专利对比表；
3. 历史样本召回率和未召回号码；
4. 完整结构化 `results`，供需要时继续分析。

---

## 客户端配置

### Codex 配置（推荐）

仓库根目录已提供安全的 `.mcp.json`：

```json
{
  "mcpServers": {
    "patents": {
      "command": "uv",
      "args": ["run", "patent-mcp-server"],
      "description": "USPTO and Google Patents search optimized for Codex"
    }
  }
}
```

从仓库目录启动 Codex 后即可使用本地 `patents` MCP。

建议 Codex 遵循以下展示约定：

1. 优先输出 `codex_markdown`；
2. 正文只展示重点专利，不倾倒完整 JSON；
3. 明确说明查询词、来源、请求次数和部分失败；
4. 显示召回率、已召回和未召回专利号；
5. 用户要求时再展开完整 `results`。

### Claude Code 配置

```shell
claude mcp add-json patents '{"command":"uv","args":["--directory","/path/to/ecommerce-patent-scout-mcp","run","patent-mcp-server"]}'
```

Windows 用户请将 `/path/to/...` 替换为仓库绝对路径。

### Claude Desktop 配置

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

> [!CAUTION]
> 不要在 `.mcp.json`、README、命令历史或代码中硬编码 API Key。需要凭据时使用环境变量、客户端 Secrets 或本机不入库的私有配置；任何曾经提交到 Git 的 key 都应立即撤销并轮换。

---

## 使用示例

### 1. 商品专利完整搜索

```text
帮我搜索这个商品在美国的相关专利：

- 商品：Self Watering Pots with Water Level Indicator
- 关键特征：水位指示器、可拆卸底座、透明储水区
- 目标：优先检查有效的美国外观设计专利

请扩展英文同义词，执行分页聚合搜索，追踪发明人、受让人和引用网络，
最后按“专利、状态、初步风险、对比结论”输出表格。
```

典型工作流程：

1. 分析商品功能、结构、材质和外观特征；
2. 构建精确短语、通用名称、功能词和形状词；
3. 运行多关键词、多来源分页搜索；
4. 对核心候选扩展发明人、受让人和双向引用；
5. 下载官方 PDF 并比对图样；
6. 输出候选清单和需要人工复核的风险点。

### 2. 分页聚合并检查召回率

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

关键参数：

| 参数 | 作用 | 建议 |
|---|---|---|
| `queries` | 多组自然语言或搜索引擎查询 | 使用产品名、正式名称和同义词 |
| `type` | `DESIGN`、`PATENT` 或 `ANY` | 外观筛查优先 `DESIGN` |
| `sources` | `BOTH`、`GOOGLE` 或 `PPUBS` | 正式检索优先 `BOTH` |
| `page_size` | 每次请求数量 | Google 最大100，PPUBS最大500 |
| `max_pages` | 每个查询和来源的最大页数 | 初筛2–3，深搜按需增加 |
| `max_requests` | 全局网络请求预算 | 控制延迟和上游压力 |
| `max_results` | 合并后的最大结果数 | 不影响预算内已检索数据的召回计算 |
| `baseline_name` | 历史样本基线 | 用于版本回归，不用于号码注入 |
| `expand_citations` | 扩展重点设计专利引用 | 设计专利建议开启 |

### 3. 已知专利号核验

```text
查询 USD1066113S1 的 USPTO 官方记录、完整文档、PDF 和双向引用网络。
请区分外观设计号与同数字的实用专利，不要只按数字模糊匹配。
```

---

## 工具目录

当前版本注册24个 MCP tools、6个 prompts，以及5类固定 resources。

### 聚合与召回

| 工具 | 用途 |
|---|---|
| `patent_search_aggregated` | 多关键词、双来源、分页、去重、引用扩展及召回检查 |
| `patent_evaluate_recall` | 将实际结果与历史旧工具样本进行独立对比 |

### USPTO PPUBS

| 工具 | 用途 |
|---|---|
| `ppubs_search_patents` | 搜索授权专利 |
| `ppubs_search_applications` | 搜索公开申请 |
| `ppubs_get_patent_by_number` | 按规范化专利号精确查询 |
| `ppubs_get_full_document` | 获取完整专利文档 |
| `ppubs_download_patent_pdf` | 下载 USPTO 专利 PDF |
| `ppubs_search_combined` | 执行多种查询策略并合并结果 |
| `ppubs_search_by_ttl` | 按标题精确搜索 |
| `ppubs_search_by_inventor` | 按发明人搜索 |
| `ppubs_search_by_assignee` | 按受让人搜索 |
| `ppubs_get_inventor_patents` | 追踪发明人的相关专利族 |

### Google Patents

| 工具 | 用途 |
|---|---|
| `gp_search_patents` | Google Patents 搜索，支持类型和结果数量限制 |
| `gp_get_patent_detail` | 获取摘要、分类、缩略图和详情 |
| `gp_get_similar_patents` | 发现标题和分类相近的候选 |
| `gp_get_citations` | 获取 Google Patents 前向或后向引用 |

### 引用网络

| 工具 | 用途 |
|---|---|
| `ppubs_get_citation_network` | 一次获取重点专利的双向引用网络 |
| `ppubs_get_citations` | 从 PPUBS 完整文档提取后向引用 |
| `ppubs_get_cited_by` | 查询引用目标专利的较新专利 |

### 商标与辅助工具

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
| `patents://recall-baselines` | 历史召回基线名称、查询词和预期专利 |

---

## 推荐搜索方法

### 设计专利检索

```text
1. patent_search_aggregated(多组商品关键词, type="DESIGN")
2. ppubs_get_citation_network(重点候选)
3. gp_get_similar_patents(重点候选)
4. ppubs_search_by_inventor / ppubs_search_by_assignee
5. ppubs_download_patent_pdf
6. 人工比较图样所形成的整体视觉印象
```

### 为什么必须扩展引用网络

美国外观设计专利标题经常非常短，关键词搜索可能无法发现。双向引用网络可以补充：

- 目标专利引用的更早设计；
- 引用目标专利的后续设计；
- 同一发明人或申请人的连续改进；
- 名称不同但视觉结构接近的设计。

引用关系只说明技术或审查关联，不等于外观相似，也不自动代表侵权风险。

### 如何理解召回率

本项目中的召回率计算为：

```text
已召回的历史重点专利数 ÷ 历史重点专利总数
```

它用于回答“新版是否仍找到旧工具已经找到的候选”，不是代码覆盖率，也不代表搜索结果都相关。

当前基线来自7组历史产品、16件重点专利。100%基线召回只能证明这些已知样本没有退化，不能证明所有商品都能100%召回。实际质量还应同时关注：

- 精确率和无关结果比例；
- 重点候选在结果中的排名；
- 查询词覆盖面；
- 数据源可用性；
- 人工图样比对结论。

---

## 可靠性与限制

### 数据源降级

- Google Patents 可能返回503或触发访问限制。聚合工具会快速记录失败并继续 PPUBS，而不是长时间阻塞聊天。
- PPUBS 可能短时断开连接。单来源异常会写入 `query_stats`，其他可用来源继续返回部分结果。
- 部分结果不应被描述为完整检索；输出中必须保留来源错误和请求预算信息。

### 请求数量为什么有限

`limit`、`max_pages` 和 `max_requests` 用来平衡召回、响应时间和上游服务压力。默认值适合聊天式初筛，不代表专利数据库只有这些结果。

需要提高召回时，应优先：

1. 增加高质量同义词和正式标题词；
2. 使用 PPUBS 较大页尺寸；
3. 适度增加页数和请求预算；
4. 对高相关候选扩展引用、发明人和受让人；
5. 分批搜索，而不是一次无限扩大结果。

---

## 故障排查

<details>
<summary><strong>启动后客户端看不到 patents MCP</strong></summary>

1. 确认从仓库根目录启动客户端；
2. 运行 `uv sync`；
3. 手动执行 `uv run patent-mcp-server` 检查启动日志；
4. Windows 配置中使用仓库绝对路径；
5. 修改客户端配置后重启客户端。

</details>

<details>
<summary><strong>Google Patents 返回503</strong></summary>

优先使用 `sources="BOTH"`，让 PPUBS 在 Google 不可用时继续提供结果。不要通过高频重试规避上游限制。

</details>

<details>
<summary><strong>已知设计专利号返回了错误的实用专利</strong></summary>

保留 `D` 或完整 `USD...S1` 前缀，并使用 `ppubs_get_patent_by_number`。不要只传递数字部分。

</details>

<details>
<summary><strong>关键词没有召回历史候选</strong></summary>

检查专利正式标题、商品同义词、发明人、受让人和引用网络。商品名称与专利标题可能完全不同，例如商品称为 bottle pour spout，而正式标题可能是 olive oil nozzle。

</details>

---

## 开发与测试

```bash
# 安装开发依赖
uv sync

# 运行测试
uv run pytest

# 查看覆盖率
uv run pytest --cov=patent_mcp_server --cov-report=term-missing

# 构建发行包
uv build
```

当前版本验证结果：

- 87项自动化测试通过；
- 7/7组历史召回基线通过；
- 16/16件历史重点专利召回；
- 新增聚合纯逻辑模块覆盖率97%；
- 项目总覆盖率34%。

总覆盖率仍有提升空间。新增工具时应同时增加正常路径、参数边界、上游错误和部分失败测试。

---

## 版本说明

### v1.1.0

- 新增分页聚合搜索和历史召回评估；
- 新增 Google Patents、PPUBS 引用网络和电商专用查询；
- 优化专利号、PDF下载、Google结果限制和资源清理；
- 增加 Codex 专用聊天布局；
- 移除仓库配置中的硬编码第三方凭据。

完整记录见 [CHANGELOG.md](CHANGELOG.md)。

---

## 致谢

本项目基于 [riemannzeta/patent_mcp_server](https://github.com/riemannzeta/patent_mcp_server) 修改，感谢原作者 Michael Frank Martin 及所有贡献者。

原项目同时致谢 [Parker Hancock](https://github.com/parkerhancock) 的 [Patent Client](https://github.com/parkerhancock/patent_client) 项目，其对理解 Public Search API 提供了重要参考。

## 贡献

欢迎提交 Issue 和 Pull Request。建议在提交前说明：

- 目标商品或检索场景；
- 可复现的查询词和数据源；
- 预期专利与实际结果；
- 是否涉及召回率、精确率或接口兼容性；
- 已运行的测试。

## 许可证

[MIT License](LICENSE.md)

Copyright (c) 2025 Michael Frank Martin（原作者）
