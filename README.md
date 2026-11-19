# AI video cover

从口播稿、人物照片和风格参考中，制作贴合视频内容的封面标题、完整生图提示词与静态 AI 视频封面。

A reusable Codex skill for script-grounded video covers and image-generation prompts.

## 能做什么

- 提炼发布标题与封面短标题，兼顾吸引力和内容一致性。
- 分清人物身份参考与视觉风格参考，保留人物特征，避免带入旧封面文案。
- 延续同系列的配色与版式，每期使用本轮人像和内容；本次指定的新比例、风格优先。
- 支持教育、知识分享、产品讲解等主题，按参考风格与横竖比例调整。
- 支持“直接生成封面”和“只写提示词”。
- 输出完整提示词，便于在其他图片生成工具中复用。
- 统一定稿文字、上图文字与交付记录；生成后读取实际尺寸，区分目标比例和实测结果。

本项目制作的是视频的静态封面，不生成动态视频。

## 在 Codex 中安装

将整个仓库放到个人技能目录。默认路径为 `~/.codex/skills/ai-video-cover`；设置了 `CODEX_HOME` 时，使用该目录下的 `skills/ai-video-cover`。目标目录已存在时先检查现有内容。

默认路径安装命令：

```sh
git clone https://github.com/Yu-Jie-Chen/ai-video-cover.git ~/.codex/skills/ai-video-cover
```

## 使用

附上口播稿和可用参考图，输入：

```text
请使用 $ai-video-cover，为这篇口播制作封面。
图1只参考排版和配色，图2是我的人物照片。
标题要吸引人，但必须与正文相关。
```

连续制作同系列：

```text
请使用 $ai-video-cover，沿用上次黄白大字、人物特写和底部白条的风格。
这次用新上传的照片作为人物参考，旧封面只参考风格。
根据本轮口播重新选标题和背景，画面改成9:16。
```

可复用的 [真人口播系列预设](references/portrait-series.md) 提供版式起点。它不会覆盖本次指定的风格或尺寸，也不要求所有主题都用黄白配色。

只要提示词：

```text
请使用 $ai-video-cover，只写提示词，不生图。
内容是：新手手冲咖啡先固定粉水比和水温，每次只改变一个变量并记录口感。
没有人物照片。用黑金极简风格，16:9横版。
```

无需安装技能也可以直接复制 [通用 AI 指令](references/universal-prompt.md)，或者使用 [生图提示词模板](references/cover-prompt-template.md)。

## 文件

| 文件 | 用途 |
| --- | --- |
| [SKILL.md](SKILL.md) | 技能入口、触发条件与工作方法 |
| [agents/openai.yaml](agents/openai.yaml) | Codex 显示名称和默认调用指令 |
| [references/universal-prompt.md](references/universal-prompt.md) | 可复制到 AI 助手的完整通用指令 |
| [references/cover-prompt-template.md](references/cover-prompt-template.md) | 发给图片生成工具的结构化模板 |
| [references/portrait-series.md](references/portrait-series.md) | 黄白大字真人口播系列的可选样式与换比例规则 |

## 工具与数据

撰写提示词不需要图片生成服务。实际生成图片需要当前运行环境提供相应工具；在 Codex 中优先使用内置图片生成能力及其可用规则。该技能自身不附带 API 密钥，也不自动配置付费服务。

个人照片、口播原始资料与生成成图保存在使用者自己的工作目录。仓库只提供通用指令与文字示例。

## License

[MIT](LICENSE)
