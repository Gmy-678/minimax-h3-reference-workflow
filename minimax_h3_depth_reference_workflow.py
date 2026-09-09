#!/usr/bin/env python3
import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


SUBMIT_URL = "https://metaso.cn/api/minimax/v2/video_generation"
QUERY_URL = "https://metaso.cn/api/minimax/v2/query/video_generation?task_id={task_id}"


PROMPTS = {
    "keep-background": (
        "严格按照参考素材制作。Image 1 是 Mixed 1：指定角色参考图，请锁定该角色的五官、发型、身材比例、"
        "服装装扮和整体身份特征，并在全片保持同一角色身份一致。Video 1 是 Mixed 2：动作、空间、遮挡、"
        "镜头和原始场景参考视频。请严格遵循 Video 1 的人物数量、相对站位、前后景关系、身体姿态、动作节奏、"
        "镜头移动轨迹、构图变化和场景布局，不要偏移。重点：保留 Video 1 的原始背景、地面、墙面、道具、"
        "材质、光影和空间锚点，不要清空背景，不要改成白棚，不要变成单调纯色背景。只替换人物或主体："
        "将 Video 1 中可见人物/主体替换为 Image 1 的角色形象；如果只有一张角色图而视频中有多人，"
        "所有人物都使用同一角色身份，但必须保留每个人各自的位置、姿态、动作时序、遮挡关系和人物数量。"
        "去掉原视频中的字幕和文字叠加。输出超写实短片，人物与原场景光照、透视、接触阴影和环境材质自然融合；"
        "画面流畅无崩坏，身体比例稳定，手脚不畸形，角色形象持续统一。"
    ),
    "studio": (
        "严格按照参考素材制作。Image 1 是 Mixed 1：指定角色参考图，请锁定该角色的五官、发型、身材比例、"
        "服装装扮和整体身份特征，并在全片保持同一角色身份一致。Video 1 是 Mixed 2：动作与空间参考视频，"
        "请严格遵循其中的空间纵深、人物姿态、动作节奏、镜头移动轨迹和画面结构，不要偏移。"
        "将 Video 1 中的人物替换为 Image 1 的角色形象；如果参考视频中存在不属于 Image 1 的包、道具、"
        "Logo 或杂物，请去掉。将参考视频结构转化为超写实真人短片：高调纯白无缝摄影棚，背景和地面都是干净纯白，"
        "无家具、凳子、电线、摄影器材、道具或其他杂物。还原真实环境材质、自然光影、人物动作和空间布局；"
        "画面流畅，身体不崩坏，手脚不畸形，角色服装和面部特征持续统一，持续匹配参考视频的空间和运动信息。"
    ),
}


def run(cmd: list[str]) -> None:
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def run_json(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout)


def probe_media(path: Path) -> dict:
    if not shutil.which("ffprobe"):
        return {"path": str(path), "probe_error": "ffprobe not found"}
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size:stream=index,codec_type,width,height,r_frame_rate,avg_frame_rate,nb_frames",
        "-of",
        "json",
        str(path),
    ]
    try:
        info = run_json(cmd)
    except Exception as exc:
        return {"path": str(path), "probe_error": str(exc)}
    info["path"] = str(path)
    return info


def data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def request_json(url: str, token: str, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def request_json_with_curl(url: str, token: str, payload_path: Path | None = None) -> dict:
    if not shutil.which("curl"):
        raise RuntimeError("curl is required for fallback submission but was not found")
    cmd = [
        "curl",
        "--silent",
        "--show-error",
        "--fail-with-body",
        "--request",
        "POST" if payload_path else "GET",
        "--url",
        url,
        "--header",
        f"Authorization: Bearer {token}",
        "--header",
        "Content-Type: application/json",
    ]
    if payload_path:
        cmd.extend(["--data", f"@{payload_path}"])
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout)


def submit_payload(url: str, token: str, payload: dict, payload_path: Path, method: str) -> dict:
    if method == "urllib":
        return request_json(url, token, payload)
    if method == "curl":
        return request_json_with_curl(url, token, payload_path)
    try:
        return request_json(url, token, payload)
    except Exception as exc:
        print(f"urllib_submit_failed={exc}", file=sys.stderr)
        print("retrying_with=curl", file=sys.stderr)
        return request_json_with_curl(url, token, payload_path)


def download(url: str, out: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "codex-metaso-h3-workflow/1"})
    with urllib.request.urlopen(req, timeout=300) as resp, out.open("wb") as fh:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)


def prepare_media(
    reference_image: Path,
    reference_video: Path,
    work_dir: Path,
    image_width: int,
    video_max_width: int,
    video_crf: int,
) -> tuple[Path, Path]:
    work_dir.mkdir(parents=True, exist_ok=True)
    image_out = work_dir / "mixed1_reference_image.jpg"
    video_out = work_dir / "mixed2_reference_video_15s.mp4"

    run([
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(reference_image),
        "-vf",
        f"scale={image_width}:-1",
        "-q:v",
        "3",
        str(image_out),
    ])
    run([
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(reference_video),
        "-t",
        "15",
        "-vf",
        f"scale='min({video_max_width},iw)':-2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        str(video_crf),
        "-preset",
        "veryfast",
        "-an",
        str(video_out),
    ])
    return image_out, video_out


def poll_until_done(task_id: str, token: str, interval_seconds: int, max_wait_seconds: int) -> dict:
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        time.sleep(interval_seconds)
        status_doc = request_json(QUERY_URL.format(task_id=task_id), token)
        item = next(
            (candidate for candidate in status_doc.get("items", []) if str(candidate.get("id")) == str(task_id)),
            None,
        )
        print(json.dumps(item or status_doc, ensure_ascii=False))
        if item and item.get("status") == "succeeded":
            return item
        if item and item.get("status") in {"failed", "cancelled"}:
            raise RuntimeError(f"task ended with status={item.get('status')}: {json.dumps(item, ensure_ascii=False)}")
    raise TimeoutError(f"task {task_id} did not finish within {max_wait_seconds}s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mixed 1 reference image + Mixed 2 reference video -> MiniMax-H3 video")
    parser.add_argument("--reference-image", help="Mixed 1, arbitrary character/product/person reference image path")
    parser.add_argument("--reference-video", help="Mixed 2, arbitrary motion/depth/structure reference video path")
    parser.add_argument("--character-image", help="Backward-compatible alias for --reference-image")
    parser.add_argument("--depth-video", help="Backward-compatible alias for --reference-video")
    parser.add_argument("--out", required=True, help="Output mp4 path")
    parser.add_argument("--prompt-file", help="Optional UTF-8 prompt file. Defaults to the selected mode prompt.")
    parser.add_argument("--mode", default="keep-background", choices=["keep-background", "studio", "custom"])
    parser.add_argument("--resolution", default="2K", choices=["768P", "2K"])
    parser.add_argument("--duration", type=int, default=15)
    parser.add_argument("--ratio", default="9:16")
    parser.add_argument("--work-dir", default="work/minimax_h3_depth_reference")
    parser.add_argument("--poll-interval", type=int, default=20)
    parser.add_argument("--max-wait", type=int, default=1800)
    parser.add_argument("--image-width", type=int, default=1536)
    parser.add_argument("--video-max-width", type=int, default=1280)
    parser.add_argument("--video-crf", type=int, default=23)
    parser.add_argument("--submit-method", default="auto", choices=["auto", "urllib", "curl"])
    parser.add_argument("--dry-run", action="store_true", help="Prepare media and payload only; do not create a paid task.")
    parser.add_argument("--warn-payload-bytes", type=int, default=2_000_000)
    args = parser.parse_args()

    token = os.environ.get("METASO_API_KEY")
    if not token and not args.dry_run:
        print("Please set METASO_API_KEY first. Example: export METASO_API_KEY='your-metaso-api-key'", file=sys.stderr)
        return 2
    if not shutil.which("ffmpeg"):
        print("ffmpeg is required but was not found in PATH.", file=sys.stderr)
        return 2

    reference_image_arg = args.reference_image or args.character_image
    reference_video_arg = args.reference_video or args.depth_video
    if not reference_image_arg or not reference_video_arg:
        parser.error("please provide --reference-image and --reference-video")

    reference_image = Path(reference_image_arg).expanduser().resolve()
    reference_video = Path(reference_video_arg).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(args.work_dir).expanduser().resolve()

    prompt = PROMPTS["keep-background" if args.mode == "custom" else args.mode]
    if args.prompt_file:
        prompt = Path(args.prompt_file).expanduser().read_text(encoding="utf-8").strip()
    elif args.mode == "custom":
        parser.error("--mode custom requires --prompt-file")

    prepared_image, prepared_video = prepare_media(
        reference_image,
        reference_video,
        work_dir,
        args.image_width,
        args.video_max_width,
        args.video_crf,
    )
    payload = {
        "model": "MiniMax-H3",
        "content": [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": data_uri(prepared_image, "image/jpeg")},
                "role": "reference_image",
            },
            {
                "type": "video_url",
                "video_url": {"url": data_uri(prepared_video, "video/mp4")},
                "role": "reference_video",
            },
        ],
        "resolution": args.resolution,
        "duration": args.duration,
        "ratio": args.ratio,
    }

    payload_path = work_dir / "payload.with_data_uri.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"payload={payload_path} bytes={payload_path.stat().st_size}")
    if payload_path.stat().st_size > args.warn_payload_bytes:
        print(
            f"payload_warning=payload is larger than {args.warn_payload_bytes} bytes; "
            "consider --image-width 1024 --video-max-width 960 --video-crf 32",
            file=sys.stderr,
        )

    payload_summary = {
        "prompt_mode": args.mode,
        "model": payload["model"],
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "role": "reference_image", "source": str(reference_image), "prepared": str(prepared_image)},
            {"type": "video_url", "role": "reference_video", "source": str(reference_video), "prepared": str(prepared_video)},
        ],
        "resolution": args.resolution,
        "duration": args.duration,
        "ratio": args.ratio,
        "compression": {
            "image_width": args.image_width,
            "video_max_width": args.video_max_width,
            "video_crf": args.video_crf,
        },
        "source_media": {
            "reference_image": probe_media(reference_image),
            "reference_video": probe_media(reference_video),
            "prepared_reference_image": probe_media(prepared_image),
            "prepared_reference_video": probe_media(prepared_video),
        },
    }
    summary_path = out_path.with_name(out_path.stem + "_payload_summary.json")
    summary_path.write_text(json.dumps(payload_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"payload_summary={summary_path}")

    if args.dry_run:
        print("dry_run=true")
        return 0

    result = submit_payload(SUBMIT_URL, token, payload, payload_path, args.submit_method)
    print(json.dumps(result, ensure_ascii=False))
    task_id = result.get("task_id")
    if not task_id:
        raise RuntimeError(f"No task_id returned: {json.dumps(result, ensure_ascii=False)}")

    item = poll_until_done(task_id, token, args.poll_interval, args.max_wait)
    download(item["content"]["url"], out_path)
    print(f"downloaded={out_path}")
    print(f"usage={json.dumps(item.get('usage', {}), ensure_ascii=False)}")

    metadata_path = out_path.with_name(out_path.stem + "_metadata.json")
    metadata = {
        "task_id": task_id,
        "status": item.get("status"),
        "title": item.get("title"),
        "model": item.get("model"),
        "resolution": item.get("resolution"),
        "duration": item.get("duration"),
        "ratio": item.get("ratio"),
        "usage": item.get("usage", {}),
        "prompt_mode": args.mode,
        "output_video": str(out_path),
        "reference_image": str(reference_image),
        "reference_video": str(reference_video),
        "prepared_reference_image": str(prepared_image),
        "prepared_reference_video": str(prepared_video),
        "payload_summary": str(summary_path),
        "compression": payload_summary["compression"],
        "source_media": payload_summary["source_media"],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"metadata={metadata_path}")

    preview_path = out_path.with_name(out_path.stem + "_preview.jpg")
    preview_seconds = str(max(0.0, float(item.get("duration") or args.duration) / 2))
    run([
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-ss",
        preview_seconds,
        "-i",
        str(out_path),
        "-frames:v",
        "1",
        str(preview_path),
    ])
    print(f"preview={preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
