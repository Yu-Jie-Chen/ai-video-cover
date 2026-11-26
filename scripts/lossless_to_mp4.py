#!/usr/bin/env python3
"""Remux videos to MP4 without re-encoding; preserve originals and verify media."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid


VIDEO_EXTENSIONS = {
    ".qt", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".flv", ".wmv",
    ".ts", ".mts", ".m2ts", ".mpg", ".mpeg", ".vob",
}


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_ffmpeg(explicit=None):
    selected = explicit or os.environ.get("FFMPEG_BINARY")
    if selected:
        resolved = shutil.which(selected)
        if resolved:
            return resolved
        raise RuntimeError(f"找不到指定的 FFmpeg：{selected}")

    candidates = [shutil.which("ffmpeg")]
    script_dir = Path(__file__).resolve().parent
    candidates += [script_dir / "ffmpeg.exe", script_dir / "ffmpeg"]
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"]) /
                          "ai-video-cover" / "ffmpeg" / "ffmpeg.exe")
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        raise RuntimeError(
            "未找到 FFmpeg。可安装 FFmpeg 并加入 PATH，或运行：\n"
            "  python -m pip install imageio-ffmpeg\n"
            "也可用 --ffmpeg 指定 ffmpeg.exe 的完整路径。") from None


def run_ffmpeg(ffmpeg, args):
    result = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-nostdin", *args],
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-6000:] or
                           f"FFmpeg 退出码：{result.returncode}")
    return result


def media_stream_hashes(ffmpeg, path):
    result = run_ffmpeg(ffmpeg, [
        "-v", "error", "-i", str(path), "-map", "0:v", "-map", "0:a?",
        "-c", "copy", "-f", "streamhash", "-hash", "sha256", "-",
    ])
    lines = [line.strip() for line in result.stdout.splitlines()
             if line.strip() and not line.startswith("#")]
    if not any(",v,SHA256=" in line for line in lines):
        raise RuntimeError("没有找到可校验的视频流。")
    return lines


def publish_without_overwrite(staging, destination):
    # Windows rename refuses an existing destination. POSIX rename would replace it.
    if os.name == "nt":
        os.rename(staging, destination)
    else:
        os.link(staging, destination)
        staging.unlink()


def convert_one(ffmpeg, source):
    destination = source.with_suffix(".mp4")
    record = {"source": str(source), "output": str(destination)}
    if destination.exists():
        return {**record, "status": "skipped_existing"}

    staging = None
    try:
        original_hash = file_sha256(source)
        fd, staging_name = tempfile.mkstemp(
            prefix=".mp4-remux-", suffix=".partial.mp4", dir=source.parent)
        os.close(fd)
        staging = Path(staging_name)
        # -y applies ONLY to the newly reserved staging file, never to the final file.
        remux = run_ffmpeg(ffmpeg, [
            "-v", "warning", "-y", "-i", str(source), "-map", "0",
            "-map_metadata", "0", "-map_chapters", "0", "-c", "copy",
            "-movflags", "+faststart", "-f", "mp4", str(staging),
        ])
        before = media_stream_hashes(ffmpeg, source)
        after = media_stream_hashes(ffmpeg, staging)
        if before != after:
            raise RuntimeError("转换前后音视频流 SHA-256 不一致，未发布 MP4。")
        decoded = run_ffmpeg(ffmpeg, [
            "-v", "error", "-xerror", "-i", str(staging), "-map", "0:v",
            "-map", "0:a?", "-f", "null", "-",
        ])
        if decoded.stderr.strip():
            raise RuntimeError("完整解码检查失败：" + decoded.stderr.strip()[-3000:])
        if original_hash != file_sha256(source):
            raise RuntimeError("校验期间源文件发生变化，未发布 MP4，请停止编辑原片后重试。")
        with staging.open("rb") as handle:
            header = handle.read(12)
        if header[4:8] != b"ftyp" or header[8:12] == b"qt  ":
            raise RuntimeError("输出不是预期的 MP4 容器。")

        record.update({
            "source_sha256": original_hash,
            "output_sha256": file_sha256(staging),
            "output_bytes": staging.stat().st_size,
            "audio_video_stream_sha256": after,
            "verified": {
                "audio_video_streams_identical": True,
                "full_decode_passed": True,
                "source_unchanged": True,
                "mp4_container": True,
            },
        })
        publish_without_overwrite(staging, destination)
        record["status"] = "converted"
        if remux.stderr.strip():
            record["ffmpeg_warnings"] = remux.stderr.strip()[-4000:]
        return record
    except FileExistsError:
        # Another process created the output after the initial check. Keep its file.
        return {"source": str(source), "output": str(destination),
                "status": "skipped_existing"}
    except (OSError, RuntimeError) as error:
        return {"source": str(source), "output": str(destination),
                "status": "failed", "error": str(error)}
    finally:
        if staging is not None:
            # This is the exact temporary file reserved by this invocation.
            staging.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(
        description="将文件夹内非 MP4 视频无损封装为 MP4，保留原片，不覆盖同名文件。")
    parser.add_argument("folder", nargs="?", default=".", help="视频文件夹（默认当前目录，不含子目录）")
    parser.add_argument("--ffmpeg", help="FFmpeg 可执行文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只列出计划，不转换、不生成报告")
    parser.add_argument("--report", type=Path, help="校验报告路径（必须是尚不存在的文件）")
    args = parser.parse_args()
    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        parser.error(f"文件夹不存在：{folder}")
    sources = sorted((p for p in folder.iterdir()
                      if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS),
                     key=lambda p: p.name.casefold())
    if not sources:
        print("没有需要转换的视频（已是 .mp4 的文件不会处理）。")
        return 0
    if args.dry_run:
        for source in sources:
            output = source.with_suffix(".mp4")
            status = "跳过：同名 MP4 已存在" if output.exists() else "计划无损封装"
            print(f"[{status}] {source.name} -> {output.name}")
        return 0

    report = (args.report.expanduser().resolve() if args.report else
              folder / ("无损转MP4-校验报告-" + datetime.now().strftime("%Y%m%d-%H%M%S")
                        + "-" + uuid.uuid4().hex[:6] + ".json"))
    if report.exists() or not report.parent.is_dir():
        parser.error("报告文件已存在，或报告所在目录不存在；请选择新的报告路径。")
    # Reserve the report before conversion so an existing file is never replaced.
    try:
        report_handle = report.open("x", encoding="utf-8")
    except OSError as error:
        parser.error(f"无法创建校验报告：{error}")
    results = []
    interrupted = False
    setup_error = None
    with report_handle:
        try:
            pending = any(not p.with_suffix(".mp4").exists() for p in sources)
            ffmpeg = find_ffmpeg(args.ffmpeg) if pending else None
            for index, source in enumerate(sources, 1):
                print(f"[{index}/{len(sources)}] {source.name}", flush=True)
                result = convert_one(ffmpeg, source)
                results.append(result)
                status = result["status"]
                if status == "converted":
                    print("  完成：流数据一致、完整解码通过、原片保留。", flush=True)
                elif status == "skipped_existing":
                    print("  跳过：同名 MP4 已存在；未改动、未重新校验。", flush=True)
                else:
                    print("  失败：" + result["error"], flush=True)
        except KeyboardInterrupt:
            interrupted = True
            print("\n已中断，原片保留。", file=sys.stderr)
        except (OSError, RuntimeError) as error:
            setup_error = str(error)
            print(setup_error, file=sys.stderr)
        summary = {status: sum(r["status"] == status for r in results)
                   for status in ("converted", "skipped_existing", "failed")}
        json.dump({
            "folder": str(folder), "created_at": datetime.now().astimezone().isoformat(),
            "method": "ffmpeg stream copy (-c copy), no re-encoding",
            "summary": summary, "interrupted": interrupted, "setup_error": setup_error,
            "results": results,
        }, report_handle, ensure_ascii=False, indent=2)
        report_handle.write("\n")
    print(f"完成 {summary['converted']}；跳过 {summary['skipped_existing']}；失败 {summary['failed']}。")
    print(f"校验报告：{report}")
    if interrupted:
        return 130
    return 1 if summary["failed"] or setup_error else 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
