# 万象画卷 · OmniDraw 二开版

面向 AstrBot QQ 群聊的参考图扩展：把群友头像、聊天图片和已保存的参考图词条直接用进绘图指令。

[下载 Release](https://github.com/Yamabuki-Kirio/astrbot_plugin_omnidraw/releases) · [更新日志](CHANGELOG.md) · [问题反馈](https://github.com/Yamabuki-Kirio/astrbot_plugin_omnidraw/issues)

## 群参考图词条

| 操作 | 命令 |
| --- | --- |
| 保存或替换 | 附图或回复含图消息，发送 `/参考图 塔菲` |
| 绘图时使用 | `/画 塔菲在耕作`，也可以同时附图或引用图片 |
| 查看名称 | `/参考图 列表` |
| 输出预览卡 | `/参考图 输出参考图`，或 `/参考图 输出参考图 塔菲` |
| 删除 | `/参考图 删除 塔菲` |

同名保存会整组替换，读取失败时保留旧图。词条保存的是图片内容，不依赖 QQ 临时链接。新群词条按 Bot 和群隔离，有插件使用权限的群成员可以使用、替换或删除；旧个人词条不会出现在群预览中。

中文词条按字面子串匹配，同一位置优先长词。例如「塔菲猫」优先于「塔菲」，但「小华为奶奶倒水」也会命中「华为」。每群每 Bot 最多保存 10 个群词条，单词条最多 14 张、合计 20 MiB。绘图节点可能有更低的参考图上限。

## QQ 多人头像与聊天图片

- **多人头像**：在 `/画` 后插入真实的 QQ `@`，例如 `/画 @甲 和 @乙 一起打羽毛球`。插件按首次出现顺序为每人分配编号，并在提示词里注明头像对应的图片序号。重复 `@` 同一人复用编号和头像；唤醒机器人的 `@` 和引用消息里的 `@` 不参与绑定。绑定能减少错配，但不能保证模型完全遵循。
- **聊天记录**：直接附图，或回复含图消息、合并转发后发送 `/画 提示词`。支持读取嵌套转发，具体取决于 OneBot 客户端是否提供 `get_msg` 和 `get_forward_msg`。
- **GIF 参考图**：OpenAI 标准改图分支会把 GIF 转为一帧静态 PNG 上传，原动图和词条文件不变。这只影响参考图输入，不影响 `/gif` 动图输出。

## Web 管理

打开 AstrBot 的 **Pages → 插件配置 → 参考图词条**。列表显示词条的会话、Bot 和归属，可逐张预览图片，并在确认后删除。删除立即生效，不需要再点击保存配置。

## 安装与升级

从本仓库的 [Releases](https://github.com/Yamabuki-Kirio/astrbot_plugin_omnidraw/releases) 下载插件包。宿主版本要求为 AstrBot `>=4.16,<5`；依赖见 [`requirements.txt`](requirements.txt)。安装后，在配置面板选择绘图节点并配置 API 地址、模型和密钥，再用 `/万象帮助` 查看指令。

升级前请备份插件配置和 `data/plugin_data/astrbot_plugin_omnidraw/`，特别是已有的 `reference_library.sqlite3`。参考图预览卡在本地生成，不用另配渲染服务。

原版的文生图、图生图、人设自拍、GIF 输出、视频、预设和节点调度仍可使用。本 README 主要介绍二开新增的参考图能力。

## 项目来源

基于 [diaomin66/astrbot_plugin_omnidraw](https://github.com/diaomin66/astrbot_plugin_omnidraw) 二次开发。第三方组件及许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
