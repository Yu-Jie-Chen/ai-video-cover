"""Real FFmpeg integration tests; all media is generated in temporary folders."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lossless_to_mp4.py"
FFMPEG = os.environ.get("FFMPEG_BINARY") or shutil.which("ffmpeg")


@unittest.skipUnless(FFMPEG, "Set FFMPEG_BINARY or install ffmpeg to run integration tests")
class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mp4-test-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "中文 视频"
        self.folder.mkdir()
        self.report = Path(self.temp.name) / "report.json"

    def media(self, name="测试.qt", *, audio=True, unsupported=False):
        path = self.folder / name
        args = [str(FFMPEG), "-v", "error", "-nostdin", "-f", "lavfi",
                "-i", "testsrc2=size=64x96:rate=12:duration=0.5"]
        if audio:
            args += ["-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
                     "-map", "0:v", "-map", "1:a", "-c:a", "aac"]
        args += ["-c:v", "libvpx" if unsupported else "libx264"]
        args += ["-f", "matroska" if unsupported else "mov", str(path)]
        subprocess.run(args, check=True, capture_output=True)
        return path

    def run_converter(self, *extra):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.folder), "--ffmpeg", str(FFMPEG),
             "--report", str(self.report), *extra],
            capture_output=True, text=True, encoding="utf-8", errors="replace")

    def stream_hash(self, path):
        result = subprocess.run(
            [str(FFMPEG), "-v", "error", "-i", str(path), "-map", "0:v",
             "-map", "0:a?", "-c", "copy", "-f", "streamhash", "-hash", "sha256", "-"],
            check=True, capture_output=True)
        return result.stdout

    def test_preserves_original_and_both_streams_in_unicode_folder(self):
        source = self.media()
        original = source.read_bytes()
        result = self.run_converter()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        target = source.with_suffix(".mp4")
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(target.read_bytes()[4:8], b"ftyp")
        self.assertEqual(self.stream_hash(source), self.stream_hash(target))
        entry = json.loads(self.report.read_text(encoding="utf-8"))["results"][0]
        self.assertEqual(entry["status"], "converted")
        self.assertTrue(entry["verified"]["audio_video_streams_identical"])
        self.assertTrue(entry["verified"]["full_decode_passed"])
        self.assertEqual(entry["source_sha256"], hashlib.sha256(original).hexdigest())

    def test_video_without_audio_and_uppercase_extension(self):
        source = self.media("静音.MOV", audio=False)
        result = self.run_converter()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.stream_hash(source), self.stream_hash(source.with_suffix(".mp4")))

    def test_existing_mp4_is_never_overwritten_or_claimed_verified(self):
        source = self.media()
        target = source.with_suffix(".mp4")
        target.write_bytes(b"existing user file")
        result = self.run_converter()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(target.read_bytes(), b"existing user file")
        entry = json.loads(self.report.read_text(encoding="utf-8"))["results"][0]
        self.assertEqual(entry["status"], "skipped_existing")
        self.assertNotIn("verified", entry)

    def test_corrupt_input_fails_without_partial_output_and_batch_continues(self):
        bad = self.folder / "a坏文件.qt"
        bad.write_bytes(b"not a video")
        good = self.media("b正常.qt")
        result = self.run_converter()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(bad.read_bytes(), b"not a video")
        self.assertFalse(bad.with_suffix(".mp4").exists())
        self.assertTrue(good.with_suffix(".mp4").exists())
        self.assertEqual(len(list(self.folder.iterdir())), 3)

    def test_incompatible_codec_is_rejected_without_reencoding(self):
        source = self.media("不兼容.mkv", unsupported=True)
        original = source.read_bytes()
        result = self.run_converter()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(source.with_suffix(".mp4").exists())
        self.assertEqual(list(self.folder.iterdir()), [source])

    def test_dry_run_does_not_change_folder_or_write_report(self):
        source = self.media()
        original = source.read_bytes()
        result = self.run_converter("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(list(self.folder.iterdir()), [source])
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(self.report.exists())

    @unittest.skipUnless(os.name == "nt", "Windows launcher")
    def test_windows_double_click_launcher_and_repeat_run(self):
        source = self.media()
        original = source.read_bytes()
        launcher = self.folder / "无损转换为MP4.cmd"
        shutil.copy2(SCRIPT, self.folder / SCRIPT.name)
        shutil.copy2(SCRIPT.parent / launcher.name, launcher)
        env = {**os.environ, "FFMPEG_BINARY": str(FFMPEG), "PYTHONUTF8": "1"}
        command = ["cmd.exe", "/d", "/c", str(launcher)]
        first = subprocess.run(command, cwd=self.folder, env=env, input="\n",
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        target = source.with_suffix(".mp4")
        converted = target.read_bytes()
        modified = target.stat().st_mtime_ns
        second = subprocess.run(command, cwd=self.folder, env=env, input="\n",
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(target.read_bytes(), converted)
        self.assertEqual(target.stat().st_mtime_ns, modified)
        reports = sorted(self.folder.glob("无损转MP4-校验报告-*.json"),
                         key=lambda p: p.stat().st_mtime_ns)
        entry = json.loads(reports[-1].read_text(encoding="utf-8"))["results"][0]
        self.assertEqual(entry["status"], "skipped_existing")
        self.assertNotIn("verified", entry)


if __name__ == "__main__":
    unittest.main()
