"""视频后期处理 — TTS 配音 + 字幕烧录."""
import json
import os
import re
import logging
import subprocess
import asyncio
from typing import Dict, List, Optional

logger = logging.getLogger("video_postprocessor")

TTS_VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")


def _extract_scenes(script_data: dict) -> List[dict]:
    """从剧本中提取场景列表（兼容新旧格式）。"""
    scenes = script_data.get("scenes") or script_data.get("script") or []
    return scenes if isinstance(scenes, list) else []


def _has_content(scenes: List[dict]) -> bool:
    """判断是否有需要 TTS 的内容（旁白或对白）。"""
    for s in scenes:
        if s.get("narration", "").strip():
            return True
        dialogues = s.get("dialogues") or []
        if dialogues and any(d.get("line", "").strip() for d in dialogues):
            return True
    return False


def _build_script_text(scenes: List[dict]) -> str:
    """将剧本场景拼接为 TTS 朗读文本，返回 (full_text, segments)."""
    segments = []
    for s in scenes:
        narration = s.get("narration", "").strip()
        if narration:
            segments.append({"type": "narration", "scene": s.get("scene", 0), "text": narration})

        dialogues = s.get("dialogues") or []
        for d in dialogues:
            line = d.get("line", "").strip()
            character = d.get("character", "").strip()
            if line:
                text = f"{character}说：{line}" if character else line
                segments.append({"type": "dialogue", "scene": s.get("scene", 0), "character": character, "text": line, "display": f"{character}：{line}" if character else line})

    return [seg["text"] for seg in segments], segments


def _build_srt(segments: List[dict], total_duration: float) -> str:
    """根据 TTS 总时长生成 SRT 字幕。"""
    if not segments or total_duration <= 0:
        return ""

    # 每段字幕的显示文本
    subtitle_texts = []
    for seg in segments:
        if seg["type"] == "narration":
            subtitle_texts.append(seg["text"])
        else:
            subtitle_texts.append(seg.get("display", seg["text"]))

    if not subtitle_texts:
        return ""

    # 按文本长度分配时间
    total_chars = sum(len(t) for t in subtitle_texts) or 1
    srt_lines = []
    current_time = 0.0
    idx = 1

    for text in subtitle_texts:
        if not text.strip():
            continue
        # 按字符比例分配时间，每段至少 1.5 秒
        ratio = len(text) / total_chars
        duration = max(1.5, total_duration * ratio)
        end_time = min(current_time + duration, total_duration)

        # 写入 SRT 条目
        start_str = _srt_time(current_time)
        end_str = _srt_time(end_time)
        srt_lines.append(f"{idx}\n{start_str} --> {end_str}\n{text}\n")
        idx += 1
        current_time = end_time

    return "\n".join(srt_lines)


def _srt_time(seconds: float) -> str:
    """将秒转为 SRT 时间格式 HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


async def _generate_tts_audio(texts: List[str], output_path: str) -> float:
    """使用 edge-tts 生成完整配音音频，返回时长（秒）。"""
    import edge_tts

    full_text = "。".join(texts)
    if not full_text.strip():
        return 0.0

    # 分段生成（edge-tts 单次有长度限制）
    chunk_size = 500  # 每段最多 500 字
    chunks = [full_text[i:i + chunk_size] for i in range(0, len(full_text), chunk_size)]

    temp_files = []
    total_duration = 0.0

    try:
        for i, chunk in enumerate(chunks):
            temp_path = output_path.replace(".mp3", f"_part{i}.mp3")
            communicate = edge_tts.Communicate(chunk, TTS_VOICE)
            await communicate.save(temp_path)
            temp_files.append(temp_path)

            # 获取音频时长
            dur_result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", temp_path],
                capture_output=True, text=True, timeout=30,
            )
            chunk_dur = float(dur_result.stdout.strip() or 0)
            total_duration += chunk_dur
            logger.info(f"TTS chunk {i + 1}/{len(chunks)}: {chunk_dur:.1f}s, text={len(chunk)}chars")

        # 合并所有音频段
        if len(temp_files) == 1:
            os.replace(temp_files[0], output_path)
        elif len(temp_files) > 1:
            # 使用 ffmpeg concat 合并
            concat_file = output_path.replace(".mp3", "_concat.txt")
            with open(concat_file, "w") as f:
                for tf in temp_files:
                    f.write(f"file '{tf}'\n")
            subprocess.run(
                ["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_file,
                 "-c", "copy", output_path, "-y"],
                capture_output=True, timeout=120,
            )
            os.unlink(concat_file)
            for tf in temp_files:
                os.unlink(tf)

        logger.info(f"TTS audio generated: {output_path}, total={total_duration:.1f}s")
        return total_duration

    except Exception as e:
        logger.exception(f"TTS generation failed: {e}")
        return 0.0


def _get_video_duration(video_path: str) -> float:
    """获取视频时长（秒）。"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip() or 0)
    except Exception:
        return 0.0


def _burn_subtitles_only(
    video_path: str,
    srt_content: str,
    output_path: str,
) -> str:
    """仅烧录字幕到视频，保留原音频不变。"""
    srt_path = output_path.replace(".mp4", ".srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    subtitle_filter = (
        f"subtitles={srt_path}:force_style="
        f"'FontName=Noto Sans CJK SC,FontSize=14,"
        f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        f"BorderStyle=1,Outline=1,MarginV=24'"
    )

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", subtitle_filter,
        "-c:v", "libx264", "-crf", "23",
        "-c:a", "copy",  # 原音频不变
        "-y", output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error(f"ffmpeg subtitle burn failed: {result.stderr[:500]}")
            return video_path
        logger.info(f"Subtitles burned: {output_path}")
        return output_path
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg subtitle burn timed out")
        return video_path
    finally:
        if os.path.exists(srt_path):
            os.unlink(srt_path)


def _merge_audio_subtitles(
    video_path: str,
    audio_path: str,
    srt_content: str,
    output_path: str,
) -> str:
    """将配音音频和字幕合并到视频中，返回输出文件路径。"""
    srt_path = output_path.replace(".mp4", ".srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    cmd = [
        "ffmpeg", "-i", video_path, "-i", audio_path,
        "-filter_complex",
        "[1:a]adelay=1|1[voice];"
        "[0:a]volume=0.15[bg];"
        "[voice][bg]amix=inputs=2:duration=first[aud]",
        "-map", "0:v",
        "-map", "[aud]",
        "-vf", f"subtitles={srt_path}:force_style='FontName=Noto Sans CJK SC,FontSize=14,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=1,MarginV=24'",
        "-c:v", "libx264", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-y", output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error(f"ffmpeg merge failed: {result.stderr[:500]}")
            return video_path
        logger.info(f"Post-processed video: {output_path}")
        return output_path
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg merge timed out")
        return video_path
    finally:
        if os.path.exists(srt_path):
            os.unlink(srt_path)


def postprocess_video(video_path: str, script_data: dict, tts_enabled: bool = False) -> str:
    """对视频进行后期处理：字幕烧录（可选 TTS 配音）。

    Args:
        video_path: 原始视频路径
        script_data: 剧本数据（含 scenes/script 数组）
        tts_enabled: 是否启用 TTS 配音（默认关闭，仅烧录字幕）

    Returns:
        处理后的视频路径（失败时返回原路径）
    """
    scenes = _extract_scenes(script_data)
    if not scenes or not _has_content(scenes):
        logger.info("No narration/dialogue content, skipping post-processing")
        return video_path

    if not os.path.exists(video_path):
        logger.warning(f"Video file not found: {video_path}")
        return video_path

    try:
        # 1. 构建文本
        texts, segments = _build_script_text(scenes)
        if not texts or not any(t.strip() for t in texts):
            logger.info("Empty text, skipping")
            return video_path

        output_path = video_path.replace(".mp4", "_processed.mp4")

        if tts_enabled:
            # 2. TTS 配音模式：生成配音 → 按配音时长分配字幕 → 混合音频+烧录字幕
            audio_dir = os.path.join(os.path.dirname(video_path), "audio")
            os.makedirs(audio_dir, exist_ok=True)
            audio_path = os.path.join(audio_dir, f"{os.path.basename(video_path)}.mp3")

            tts_duration = asyncio.run(_generate_tts_audio(texts, audio_path))
            if tts_duration <= 0:
                logger.warning("TTS generation returned no audio")
                return video_path

            srt_content = _build_srt(segments, tts_duration)
            if not srt_content:
                return video_path

            result_path = _merge_audio_subtitles(video_path, audio_path, srt_content, output_path)

            if os.path.exists(audio_path):
                os.unlink(audio_path)
        else:
            # 2. 纯字幕模式：按视频时长分配字幕，不替换音频
            video_duration = _get_video_duration(video_path)
            if video_duration <= 0:
                logger.warning("Could not determine video duration")
                return video_path

            srt_content = _build_srt(segments, video_duration)
            if not srt_content:
                return video_path

            result_path = _burn_subtitles_only(video_path, srt_content, output_path)

        return result_path

    except Exception as e:
        logger.exception(f"Video post-processing failed: {e}")
        return video_path
