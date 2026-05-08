# USPTO Patent MCP Server (PPUBS-Only Version)

> 🇨🇳 专为跨境电商产品设计人员优化的美国专利查询工具
>
> A simplified USPTO Patent MCP Server optimized for China e-commerce product patent search.

基于 [riemannzeta/patent_mcp_server](https://github.com/riemannzeta/patent_mcp_server) 修改的精简版本。

## 与原版的区别

| 特性 | 原版 | 本版本 |
|------|------|--------|
| API Key | ODP 工具需要 | **无需任何 API Key** |
| 工具数量 | 52 个 | 13 个（精简核心功能） |
| 目标用户 | 专业专利研究人员 | 跨电商产品设计人员 |
| 搜索工作流 | 通用专利研究 | 产品专利搜索优化 |

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

### 新增搜索工具（本版本独有）

| 工具 | 功能 | 优势 |
|------|------|------|
| `ppubs_search_combined` | 多策略组合搜索 | 自动执行4种搜索策略 |
| `ppubs_search_by_ttl` | 标题精确搜索 | 设计专利命中率最高 |
| `ppubs_search_by_inventor` | 发明人搜索 | 按发明人名称搜索 |
| `ppubs_search_by_assignee` | 申请人搜索 | 按公司名称搜索 |
| `ppubs_get_inventor_patents` | 自动发明人追踪 | 一键查找同发明人专利 |

## 搜索技巧

### 设计专利搜索
```
使用 ppubs_search_by_ttl 进行标题精确搜索
例：ppubs_search_by_ttl("self watering pot")
```

### 功能专利搜索
```
使用 ppubs_search_combined 进行多策略搜索
例：ppubs_search_combined("camping table folding mechanism")
```

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
