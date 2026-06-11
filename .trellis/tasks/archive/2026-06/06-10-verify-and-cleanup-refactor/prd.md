# verify: 重构验证与清理

## Goal

全量验证重构结果，确保无残留无用代码、无 dead import、无孤立文件。

## Requirements

* 运行全量后端测试
* 运行前端 lint/typecheck
* 运行后端 ruff lint
* 检查无 dead import（`ruff check --select F401`）
* 检查无孤立文件（不被任何代码 import 的 .py/.ts 文件）
* 检查 i18n 无孤立 key
* 检查 `src/infra/channel/` 目录已删除
* 检查 `frontend/src/components/panels/channel/` 目录已删除
* 检查无 `feishu` / `FEISHU` / `instance_id` / `ChannelType` / `ChannelStorage` 残留引用

## Acceptance Criteria

* [ ] 全量后端测试通过
* [ ] 前端 lint/typecheck 通过
* [ ] 后端 ruff 通过
* [ ] 无 dead import
* [ ] 无孤立文件
* [ ] 无残留渠道框架引用
