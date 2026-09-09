# 超低成本替换人物

## 产品定义

用一张人物参考图和一段原视频，低成本生成“换人不换动作、保留原场景”的新视频。系统把参考图作为 `Mixed 1 / reference_image`，把参考视频作为 `Mixed 2 / reference_video`，调用 Metaso MiniMax-H3 完成人物替换。

这套工作流默认采用**保留原背景模式**：保留原视频的场景、道具、地面、墙面、光影、遮挡关系和镜头运动，只替换人物或主体。它的目标不是做重资产逐帧特效，而是用参考图 + 参考视频 + H3 多模态输入，快速得到可预览、可迭代的人物替换版本。

## 输入

- `--reference-image`：用户上传的主体参考图
  - 可以是三视图、单人图、多人图、服装图、产品图
- `--reference-video`：用户上传的动作/空间参考视频
  - 可以是原视频、黑白深度视频、动作视频、镜头轨迹参考视频
- `--prompt-file`：可选，自定义生成要求

## 输出

每次运行输出一组文件：

- `result.mp4`：最终视频
- `result_preview.jpg`：预览帧
- `result_metadata.json`：任务状态、task_id、usage、压缩参数、素材信息
- `result_payload_summary.json`：不含 base64 的请求摘要
- `work/.../payload.with_data_uri.json`：完整请求体，仅用于调试，不建议长期保存

## Cases

- [Multi-person keep-background replacement](cases/obama-multi-person-keep-background.md)

案例目录只放脱敏后的流程说明、prompt、metadata 和 payload 摘要，不提交原始视频、生成视频、完整 base64 payload 或任何 API key。

## 推荐命令

默认保留原背景：

```bash
export METASO_API_KEY='your-metaso-api-key'

python3 outputs/minimax_h3_depth_reference_workflow.py \
  --reference-image path/to/mixed1.png \
  --reference-video path/to/mixed2.mp4 \
  --out outputs/result.mp4 \
  --mode keep-background \
  --resolution 2K \
  --duration 10 \
  --ratio 16:9 \
  --image-width 1024 \
  --video-max-width 960 \
  --video-crf 32
```

白棚模式：

```bash
python3 outputs/minimax_h3_depth_reference_workflow.py \
  --reference-image path/to/mixed1.png \
  --reference-video path/to/mixed2.mp4 \
  --out outputs/result_studio.mp4 \
  --mode studio
```

自定义 prompt：

```bash
python3 outputs/minimax_h3_depth_reference_workflow.py \
  --reference-image path/to/mixed1.png \
  --reference-video path/to/mixed2.mp4 \
  --prompt-file path/to/prompt.txt \
  --out outputs/result_custom.mp4 \
  --mode custom
```

只生成 payload，不提交付费任务：

```bash
python3 outputs/minimax_h3_depth_reference_workflow.py \
  --reference-image path/to/mixed1.png \
  --reference-video path/to/mixed2.mp4 \
  --out outputs/dry_run.mp4 \
  --dry-run
```

## 模式选择

### `keep-background`

默认模式。适用于影视片段、短剧、舞台、生活场景、古装场景等强场景视频。

保留：

- 原背景
- 地面/墙面/水面
- 道具
- 光影和材质
- 人物站位
- 前后景遮挡
- 镜头轨迹

只替换：

- 人物或主体身份
- 服装/五官/发型等角色特征
- 字幕和不需要的文字叠加

### `studio`

适用于动作复刻、产品展示、T 台、教学动作。会把原视频空间结构迁移到纯白摄影棚，容易失去原场景语义，不建议用于强叙事素材。

### `custom`

完全使用 `--prompt-file`。适合产品端让用户编辑生成要求。

## 多人视频规则

如果只有一张参考图但参考视频里有多人，默认策略是：

- 所有人都替换为同一个参考角色
- 保留每个人原本的位置、姿态、动作时序和遮挡关系
- 不允许人物合并、消失、串位或数量减少

如果后续要支持“多人各自换成不同角色”，脚本应升级为多个 `--reference-image` 输入，并在 prompt 中明确：

```text
Video 1 中从左到右的第 1 个人对应 Image 1，第 2 个人对应 Image 2，第 3 个人对应 Image 3。
```

## 上传稳定性

Metaso H3 当前可以吃 `data:` URI，但大请求体有时会慢或断开。推荐默认压缩参数：

- `--image-width 1024`
- `--video-max-width 960`
- `--video-crf 32`

脚本支持：

- `--submit-method auto`：默认，先用 Python 请求，失败后自动切到 curl
- `--submit-method curl`：直接用 curl，适合较大 payload
- `--warn-payload-bytes`：超过阈值时提示继续压缩

## 验证标准

任务成功后看 `metadata.json` 里的 usage：

- `input_image_count > 0`：参考图实际被使用
- `input_seconds > 0`：参考视频实际被使用
- `output_seconds > 0`：生成视频成功计费

这比只看 `task_id` 更可靠。

## 已验证样例

保留原背景重试版：

- `task_id`: `2097616247729123328`
- 标题：`红墙水畔多人动作替换为奥巴马形象`
- `resolution`: `2K`
- `ratio`: `16:9`
- `duration`: `10s`
- `usage`: `input_seconds=10`, `input_image_count=1`, `output_seconds=10`
- 输出文件：`outputs/metaso_minimax_h3_obama_multi_person_keep_bg_0909.mp4`

## 安全注意

- 这个工作流会真实创建视频任务，可能消耗额度。
- 不要把真实 API Key 写进脚本、文档、payload summary 或聊天记录。
- `payload.with_data_uri.json` 含完整 base64 媒体，适合调试，不建议长期保存。
