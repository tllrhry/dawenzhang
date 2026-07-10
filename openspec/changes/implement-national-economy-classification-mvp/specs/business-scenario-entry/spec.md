## ADDED Requirements

### Requirement: Business scenario availability
系统 SHALL 展示国民经济行业分类、涉农和五篇大文章业务场景；五篇大文章 SHALL 显示科技金融、绿色金融、养老金融、数字金融四个子类。国民经济行业分类 SHALL 是唯一可用场景，其余场景 SHALL 明确显示“暂未开放”且不得进入上传或判定流程。

#### Scenario: Select the available national-economy scenario
- **WHEN** 用户在场景页选择国民经济行业分类
- **THEN** 系统进入国民经济模板下载与上传步骤

#### Scenario: View an unavailable scenario
- **WHEN** 用户查看涉农或五篇大文章任一场景
- **THEN** 系统显示该场景暂未开放且不显示可执行的上传或判定操作

### Requirement: National-economy template download
系统 SHALL 在国民经济行业分类上传步骤提供原始 `国民经济类别模版.docx` 的下载操作，下载文件 SHALL 保持可供用户填写的 Word 格式。

#### Scenario: Download the template
- **WHEN** 用户点击国民经济模板下载
- **THEN** 浏览器下载 Word 模板文件而不创建分类案例
