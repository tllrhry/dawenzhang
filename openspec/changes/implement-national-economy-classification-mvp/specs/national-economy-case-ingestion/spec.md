## ADDED Requirements

### Requirement: Single-enterprise template ingestion
系统 SHALL 接收一份已填写的国民经济 Word 模板作为一个企业分类案例，并从模板提取企业名称、统一社会信用代码、营业执照经营范围、主营业务、主营业务及营收占比、核心产品/服务、贷款用途、交易对手、交易对手行业、交易品类/服务、产业链定位、行业定位与核心竞争力、授信审批意见这 13 个字段。

#### Scenario: Upload a valid filled template
- **WHEN** 用户上传符合模板标签的单企业 `.docx` 文件
- **THEN** 系统创建一个待分类案例并保存 13 个结构化字段，未填写字段保存为空值

#### Scenario: Upload an unparseable template
- **WHEN** 上传文件缺少、重复或改写了必须识别的模板标签
- **THEN** 系统不创建分类案例，并返回包含问题标签的可操作错误信息

### Requirement: Case input retrieval
系统 SHALL 允许前端按案例标识读取已保存的结构化输入、原始文件名和处理状态，以便在分类前和导出前展示。

#### Scenario: Retrieve a newly uploaded case
- **WHEN** 前端请求一个已成功解析的案例
- **THEN** 系统返回该案例的 13 个输入字段、场景类型和待分类状态
