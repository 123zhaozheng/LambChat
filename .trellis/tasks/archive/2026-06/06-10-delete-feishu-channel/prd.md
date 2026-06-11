# delete: 飞书渠道全部删除

## Goal

删除所有飞书渠道相关代码，包括后端、前端、测试、i18n、共享引用。

## Requirements

* 删除 `src/infra/channel/feishu/` 整个目录
* 删除 `tests/infra/` 下所有飞书相关测试文件
* 删除前端飞书组件：`frontend/src/components/panels/channel/feishu/`
* 删除前端飞书类型/API：相关 FeishuPanel、FeishuPanelForm 等
* 删除 `src/kernel/schemas/feishu.py`
* 从 `ChannelType` 枚举删除 `FEISHU`
* 从 `src/api/routes/channels.py` 删除飞书注册路由
* 从 `main.py` startup 删除飞书启动逻辑
* 从 i18n 文件删除 `feishu.*` 相关 key（en/zh/ja/ko 等）
* 清理所有 `from src.infra.channel.feishu` import
* 清理所有 Feishu 相关 test fixture/fake
* 更新引用 `ChannelType.FEISHU` 的测试改用 `ChannelType.WECOM`

## Acceptance Criteria

* [ ] `grep -r "feishu" src/` 无匹配（除 comment 外）
* [ ] `grep -r "Feishu" frontend/src/` 无匹配
* [ ] `grep -r "FEISHU" src/` 无匹配
* [ ] WeCom 功能不受影响
* [ ] 所有非飞书测试通过

## Technical Notes

* 参考 `research/feishu-deletion-scope.md` 获取完整文件清单
* Task 1 已完成共享依赖迁移，飞书模块不再被 WeCom 引用
* 删除飞书后 `ChannelType` 枚举只剩 WECOM
