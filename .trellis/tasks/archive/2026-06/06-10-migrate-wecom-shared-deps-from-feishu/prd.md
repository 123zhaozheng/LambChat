# migrate: WeCom 共享依赖从飞书模块迁移

## Goal

将 WeCom 依赖的两个飞书共享模块迁移到 WeCom 自身模块内，为后续删除飞书代码做准备。

## Requirements

* 将 `ConnectionState` enum 从 `src/infra/channel/feishu/state.py` 迁移到 `src/infra/channel/wecom/` 下（新建 `state.py` 或放入现有模块）
* 将 `_download_storage_object_to_file` 和相关下载常量从 `src/infra/channel/feishu/handler_helpers.py` 迁移到 `src/infra/channel/wecom/` 下（新建 `helpers.py`）
* 更新 WeCom 代码中所有 import 指向新位置
* 飞书模块中保留原代码（后续 Task 2 整体删除），不修改飞书代码
* WeCom 功能不受影响

## Acceptance Criteria

* [ ] WeCom 代码不再 import 任何飞书模块
* [ ] `grep -r "from src.infra.channel.feishu" src/infra/channel/wecom/` 无结果
* [ ] WeCom 功能正常运行
* [ ] 不修改飞书代码

## Technical Notes

* `ConnectionState` import: `src/infra/channel/wecom/channel.py:16` → `from src.infra.channel.feishu.state import ConnectionState`
* `_download_storage_object_to_file` imports: `src/infra/channel/wecom/handler.py:449-450, 503, 1143`
