# delete: WeCom 实例模型残余清理

## Goal

删除所有 WeCom 实例模型残余代码，确保无 instance_id 引用、无旧 WeComPanel、无旧 schema。

## Requirements

* 删除 `src/infra/channel/wecom/` 整个目录（Task 5 已搬运到 `src/infra/agent/wecom/`）
* 删除 `src/kernel/schemas/wecom.py`（旧 WeComConfig schema）
* 删除前端 `frontend/src/components/panels/channel/wecom/`（WeComPanel、WeComPanelForm）
* 删除前端 `frontend/src/components/panels/channel/` 目录（已空）
* 删除 WeCom 实例相关 i18n key
* 清理所有 `instance_id` 引用（handler、manager、channel、test）
* 清理 `WeComConfig`（旧）相关 import
* 清理 WeCom 相关旧测试文件（`tests/infra/channel/wecom/`）

## Acceptance Criteria

* [ ] `grep -r "instance_id" src/infra/agent/wecom/` 无匹配
* [ ] `grep -r "WeComConfig" src/` 无匹配（新 schema 除外）
* [ ] `grep -r "WeComPanel" frontend/src/` 无匹配
* [ ] `src/infra/channel/` 目录不存在或为空
* [ ] 无 dead import
* [ ] 所有测试通过

## Technical Notes

* 此任务在 Task 5 完成后执行，确认搬运完成后再删除源目录
