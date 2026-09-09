# Case: Multi-Person Character Replacement With Original Background

## Goal

Replace every visible person in a multi-person reference video with one consistent character identity, while preserving the original scene, props, camera movement, spatial layout, and occlusion relationships.

This case came from a short scene with several people near a red wall and shallow water. A white-studio prompt produced a strange result because it removed the visual anchors that made the scene believable. The better direction was to keep the original background and replace only the people.

## Inputs

- `Mixed 1 / reference_image`: one character turnaround reference image
- `Mixed 2 / reference_video`: one multi-person source video
- Mode: `keep-background`

## Prompt Strategy

The prompt should explicitly separate what to preserve from what to replace.

Preserve:

- original background
- wall, floor, water, props, and scene materials
- people count
- relative positions
- body poses
- action timing
- foreground/background occlusion
- camera movement and framing

Replace:

- visible people or target subjects
- clothing, hair, and identity traits according to the reference image
- subtitles and text overlays

Avoid:

- pure white studio unless the user explicitly asks for it
- deleting props that act as spatial anchors
- merging people
- losing background depth cues

## Example Command

```bash
export METASO_API_KEY='your-metaso-api-key'

python3 minimax_h3_depth_reference_workflow.py \
  --reference-image inputs/character-reference.png \
  --reference-video inputs/source-video.mov \
  --prompt-file prompts/keep-background.txt \
  --out outputs/result_keep_background.mp4 \
  --mode custom \
  --resolution 2K \
  --duration 10 \
  --ratio 16:9 \
  --image-width 1024 \
  --video-max-width 960 \
  --video-crf 32 \
  --submit-method auto
```

## Verified Run

- `task_id`: `2097616247729123328`
- status: `succeeded`
- model: `MiniMax-H3`
- resolution: `2K`
- ratio: `16:9`
- output duration: `10s`
- usage: `input_seconds=10`, `input_image_count=1`, `output_seconds=10`

## Product Lesson

For strong narrative scenes, keep-background mode should be the default. The background is not just decoration: it carries depth cues, contact shadows, object scale, and scene meaning. Removing it can make a technically successful generation feel cheap or uncanny.
