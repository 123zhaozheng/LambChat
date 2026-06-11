# delete: 通用渠道框架删除

## Goal

删除通用渠道框架代码。删除飞书后只剩 WeCom 一个渠道，通用框架成为过度抽象。

## Requirements

* 删除 `src/infra/channel/base.py`（BaseChannel、UserChannelManager）
* 删除 `src/infra/channel/manager.py`（ChannelCoordinator）
* 删除 `src/infra/channel/channel_storage.py`（ChannelStorage）
* 删除 `src/infra/channel/pubsub.py`（ChannelConfigPubSub）
* 删除 `src/kernel/schemas/channel.py`（ChannelType 枚举、ChannelConfigResponse）
* 删除 `src/api/routes/channels.py`（channel API routes）
* 删除前端 `frontend/src/components/panels/channel/` 目录（ChannelsPage、ChannelPanel）
* 删除前端 `frontend/src/services/api/channel.ts`
* 删除前端 `frontend/src/types/channel.ts`
* 从 `main.py` 删除渠道框架启动逻辑
* 从 i18n 删除 `channel.*` 相关 key
* WeCom 对接逻辑暂时保留在 `src/infra/channel/wecom/`，但不再继承 BaseChannel

## Acceptance Criteria

* [ ] `grep -r "ChannelStorage\|ChannelType\|ChannelCoordinator\|BaseChannel\|UserChannelManager" src/` 无匹配（WeCom 模块外的）
* [ ] `grep -r "channel" frontend/src/services/api/` 无匹配（WeCom API service 另建）
* [ ] WeCom WS 连接和消息处理正常
* [ ] 所有非渠道框架测试通过

## Technical Notes

* WeCom 模块需先脱离 BaseChannel 继承，改为独立类
* `WeComChannelManager` 不再继承 `UserChannelManager`，改为独立实现
* channel_storage 的加密/解密逻辑如果 WeCom 仍在用，先迁移到 WeCom 模块内
