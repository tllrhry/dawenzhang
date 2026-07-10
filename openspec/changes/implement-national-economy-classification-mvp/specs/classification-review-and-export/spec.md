## ADDED Requirements

### Requirement: Classification result review
系统 SHALL 在案例结果页展示最新结论的四级行业代码、行业名称、百分比置信度、匹配依据和 AI 总结，并提供该案例全部判定版本的时间顺序历史。

#### Scenario: View a completed case
- **WHEN** 用户打开一个已有成功结论的案例
- **THEN** 系统展示最新结论及其全部历史版本，而不隐藏原判定

#### Scenario: View a case pending manual review
- **WHEN** 用户打开一个最新版本为“候选均不匹配”的案例
- **THEN** 系统展示待人工复核状态、候选快照与模型理由，并引导用户通过异议补充经营信息触发重判

### Requirement: Objection-driven reclassification
系统 SHALL 允许用户针对当前结论提交非空异议说明。系统 SHALL 以原始企业输入和异议说明重新检索并分类，新增一个结果版本，而不得覆盖原判定或异议记录。

#### Scenario: Reclassify after an objection
- **WHEN** 用户提交针对已完成案例的异议说明且重判成功
- **THEN** 系统保存该异议和新的结论版本，将新版本显示为当前结论，并保留原结论

#### Scenario: Reject an empty objection
- **WHEN** 用户提交空白异议说明
- **THEN** 系统不触发重判并提示用户填写异议内容

### Requirement: Excel case export
系统 SHALL 为任一案例生成 Excel 导出文件，至少包含“案例输入”“当前结论”和“判定历史”工作表。当前结论工作表 SHALL 包含行业代码、行业名称、置信度、匹配依据和 AI 总结；判定历史工作表 SHALL 包含每版结论和关联异议。

#### Scenario: Export a completed case
- **WHEN** 用户对已有成功结论的案例执行导出
- **THEN** 系统下载一个包含案例输入、最新结论及完整历史的 Excel 文件
