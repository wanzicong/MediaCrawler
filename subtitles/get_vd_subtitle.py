# ===============================================================================
# @File:      get_vd_subtitle.py
# @Author:    wanzicong
# @Date:      2026/4/7
# @Description: 本地视频字幕生成工具 - 不依赖数据库，支持并发
# ===============================================================================

import os
import subprocess
import whisper
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Union


# 字幕模型缓存（确保只加载一次）
_model_cache = {}

# 支持的视频格式
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.webm', '.m4v'}

# 音频提取锁（保护同一视频不被并发重复提取）
_audio_extract_locks = {}
_audio_locks_mutex = threading.Lock()


def _get_whisper_model(model_size="base"):
    """获取Whisper模型（带缓存，线程安全）"""
    if model_size not in _model_cache:
        print(f"正在加载 Whisper {model_size} 模型...")
        _model_cache[model_size] = whisper.load_model(model_size)
        print(f"Whisper {model_size} 模型加载完成")
    return _model_cache[model_size]


def _format_time_srt(seconds):
    """格式化时间为SRT格式 (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_time_ass(seconds):
    """格式化时间为ASS格式 (H:MM:SS.cc)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _generate_srt(subtitles, output_path):
    """生成SRT格式字幕"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, seg in enumerate(subtitles, 1):
            start = _format_time_srt(seg['start'])
            end = _format_time_srt(seg['end'])
            text = seg['text'].strip()
            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{text}\n\n")


def _generate_json(subtitles, output_path):
    """生成JSON格式字幕"""
    import json
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            'version': '1.0',
            'subtitles': subtitles
        }, f, ensure_ascii=False, indent=2)


def _generate_lrc(subtitles, output_path):
    """生成LRC格式歌词"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for seg in subtitles:
            start = _format_time_srt(seg['start']).replace(',', '.')[:12]
            text = seg['text'].strip()
            f.write(f"[{start}]{text}\n")


def _generate_ass(subtitles, output_path, title="Subtitle"):
    """生成ASS格式字幕"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("[Script Info]\n")
        f.write(f"Title: {title}\n")
        f.write("ScriptType: v4.00+\n")
        f.write("Collisions: Normal\n")
        f.write("PlayDepth: 0\n\n")

        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write("Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n\n")

        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

        for seg in subtitles:
            start = _format_time_ass(seg['start'])
            end = _format_time_ass(seg['end'])
            text = seg['text'].strip().replace('\n', '\\N')
            text = text.replace('{', '\\{').replace('}', '\\}')
            f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")


def _get_audio_lock(video_path):
    """获取视频对应的音频提取锁（线程安全）"""
    abs_path = os.path.abspath(video_path)
    with _audio_locks_mutex:
        if abs_path not in _audio_extract_locks:
            _audio_extract_locks[abs_path] = threading.Lock()
        return _audio_extract_locks[abs_path]


def _get_video_hash(video_path):
    """获取视频文件的唯一hash（基于绝对路径+文件大小+修改时间）"""
    abs_path = os.path.abspath(video_path)
    stat = os.stat(abs_path)
    unique_str = f"{abs_path}_{stat.st_size}_{stat.st_mtime}"
    return hashlib.md5(unique_str.encode('utf-8')).hexdigest()[:12]


def _extract_audio(video_path, audio_output_dir=None):
    """从视频提取音频（线程安全，支持并发）

    Args:
        video_path: 视频文件路径
        audio_output_dir: 音频输出目录，默认None则使用视频同目录

    Returns:
        tuple: (音频路径, 是否使用临时音频)
    """
    video_abs_path = os.path.abspath(video_path)
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    video_hash = _get_video_hash(video_path)

    if audio_output_dir is None:
        audio_output_dir = os.path.dirname(video_abs_path) or '.'
    os.makedirs(audio_output_dir, exist_ok=True)

    # 使用 hash 确保唯一性，避免同名视频覆盖
    audio_path = os.path.join(audio_output_dir, f"{video_name}_{video_hash}.wav")

    # 获取该视频的锁，防止同一视频被并发重复提取
    lock = _get_audio_lock(video_path)

    with lock:
        # 再次检查（获取锁之后，可能其他线程已刚完成）
        if os.path.exists(audio_path):
            file_size = os.path.getsize(audio_path)
            if file_size > 0:
                print(f"音频已存在，跳过提取: {audio_path}")
                return audio_path, False
            else:
                # 文件存在但为空，删除后重新提取
                os.remove(audio_path)
                print(f"音频文件为空，重新提取: {audio_path}")

        print(f"正在提取音频: {video_path}")
        cmd = ['ffmpeg', '-y', '-i', video_path, '-vn', '-acodec', 'pcm_s16le',
               '-ar', '16000', '-ac', '1', audio_path]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')

        if result.returncode == 0:
            # 验证提取的音频文件是否有效
            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                print(f"音频提取成功: {audio_path}")
                return audio_path, False
            else:
                print(f"音频提取失败，文件无效: {audio_path}")
                return video_path, True
        else:
            print(f"音频提取失败，使用原视频: {video_path}, 错误: {result.stderr[:200] if result.stderr else '未知'}")
            return video_path, True


def _process_single_video(args):
    """处理单个视频（供并发调用，共享模型）"""
    video_path, output_dir, audio_output_dir, formats, model = args
    return _transcribe_with_model(video_path, output_dir, audio_output_dir, formats, model)


def _transcribe_with_model(video_path, output_dir, audio_output_dir, formats, model):
    """
    使用已加载的模型转录音幕

    Args:
        video_path: 视频文件路径
        output_dir: 字幕输出目录
        audio_output_dir: 音频输出目录
        formats: 字幕格式列表
        model: 已加载的Whisper模型

    Returns:
        dict: 转录结果
    """
    if formats is None:
        formats = ['srt']
    elif isinstance(formats, str):
        formats = [formats]

    try:
        # 验证视频文件
        if not os.path.exists(video_path):
            return {
                'success': False,
                'video_path': video_path,
                'error': f'视频文件不存在: {video_path}'
            }

        # 确定输出目录
        if output_dir is None:
            output_dir = os.path.dirname(video_path) or '.'
        os.makedirs(output_dir, exist_ok=True)

        # 获取视频文件名（不含扩展名）作为字幕基础名
        video_name = os.path.splitext(os.path.basename(video_path))[0]

        # 提取音频
        print(f"正在提取音频: {video_path}")
        audio_path = _extract_audio(video_path, audio_output_dir)

        # 使用传入的模型转录
        print(f"开始转录音频...")
        result = model.transcribe(
            audio_path,
            language='zh',
            initial_prompt="请用简体中文输出"
        )

        # 提取字幕数据
        subtitles = []
        for segment in result['segments']:
            subtitles.append({
                'start': segment['start'],
                'end': segment['end'],
                'text': segment['text']
            })

        if not subtitles:
            return {
                'success': False,
                'video_path': video_path,
                'error': '未能识别到字幕内容'
            }

        # 生成字幕文件
        subtitle_files = []
        for fmt in formats:
            if fmt == 'srt':
                output_path = os.path.join(output_dir, f"{video_name}.srt")
                _generate_srt(subtitles, output_path)
            elif fmt == 'json':
                output_path = os.path.join(output_dir, f"{video_name}.json")
                _generate_json(subtitles, output_path)
            elif fmt == 'lrc':
                output_path = os.path.join(output_dir, f"{video_name}.lrc")
                _generate_lrc(subtitles, output_path)
            elif fmt == 'ass':
                output_path = os.path.join(output_dir, f"{video_name}.ass")
                _generate_ass(subtitles, output_path, video_name)
            else:
                continue

            if os.path.exists(output_path):
                subtitle_files.append(output_path)
                print(f"已生成字幕: {output_path}")

        if subtitle_files:
            return {
                'success': True,
                'video_path': video_path,
                'subtitle_files': subtitle_files
            }
        else:
            return {
                'success': False,
                'video_path': video_path,
                'error': '字幕生成失败'
            }

    except Exception as e:
        return {
            'success': False,
            'video_path': video_path,
            'error': str(e)
        }


def generate_subtitle(video_path, output_dir=None, audio_output_dir=None, formats=None, model_size='base'):
    """
    生成视频字幕（单线程版本）

    Args:
        video_path: 视频文件路径
        output_dir: 字幕输出目录，默认为视频所在目录
        audio_output_dir: 音频输出目录，默认为视频所在目录
        formats: 需要生成的字幕格式列表，默认为 ['srt']
        model_size: Whisper模型大小 'tiny', 'base', 'small', 'medium', 'large'

    Returns:
        dict: {
            'success': True/False,
            'video_path': '视频路径',
            'subtitle_files': ['字幕文件路径列表'],
            'error': '错误信息'
        }
    """
    model = _get_whisper_model(model_size)
    return _transcribe_with_model(video_path, output_dir, audio_output_dir, formats, model)


def generate_subtitles_concurrent(
    video_paths: List[str],
    output_dir: str = None,
    audio_output_dir: str = None,
    formats: Union[str, List[str]] = None,
    model_size: str = 'base',
    max_workers: int = 2
):
    """
    批量并发生成视频字幕（模型只加载一次，所有任务共享）

    Args:
        video_paths: 视频文件路径列表
        output_dir: 字幕输出目录，默认为视频所在目录
        audio_output_dir: 音频输出目录，默认为视频所在目录
        formats: 需要生成的字幕格式列表，默认为 ['srt']
        model_size: Whisper模型大小
        max_workers: 最大并发数，默认2（不建议设置太高）

    Returns:
        dict: {
            'success_count': 成功数量,
            'failed_count': 失败数量,
            'results': [每个视频的结果列表]
        }
    """
    if isinstance(video_paths, str):
        video_paths = [video_paths]

    # 预先加载模型（只加载一次，所有线程共享）
    print(f"正在预加载 Whisper {model_size} 模型...")
    model = _get_whisper_model(model_size)
    print(f"模型加载完成，开始并发处理...")

    results = []
    success_count = 0
    failed_count = 0
    completed = 0
    total = len(video_paths)

    print(f"开始并发处理 {total} 个视频，最大并发数: {max_workers}")

    # 准备参数（传入已加载的模型）
    args_list = [(vp, output_dir, audio_output_dir, formats, model) for vp in video_paths]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_process_single_video, args): args[0] for args in args_list}

        for future in as_completed(futures):
            video_path = futures[future]
            completed += 1
            try:
                result = future.result()
                results.append(result)
                if result['success']:
                    success_count += 1
                    print(f"[{completed}/{total}] 成功: {os.path.basename(video_path)}")
                else:
                    failed_count += 1
                    print(f"[{completed}/{total}] 失败: {os.path.basename(video_path)} - {result.get('error', '未知错误')}")
            except Exception as e:
                failed_count += 1
                print(f"[{completed}/{total}] 异常: {os.path.basename(video_path)} - {str(e)}")

    return {
        'success_count': success_count,
        'failed_count': failed_count,
        'results': results
    }


def generate_subtitles_from_folder(
    folder_path: str,
    output_dir: str = None,
    audio_output_dir: str = None,
    formats: Union[str, List[str]] = None,
    model_size: str = 'base',
    max_workers: int = 2,
    recursive: bool = False
):
    """
    扫描文件夹内所有视频并并发生成字幕

    Args:
        folder_path: 文件夹路径
        output_dir: 字幕输出目录，默认为视频所在目录
        audio_output_dir: 音频输出目录，默认为视频所在目录
        formats: 需要生成的字幕格式列表，默认为 ['srt']
        model_size: Whisper模型大小
        max_workers: 最大并发数，默认2（不建议设置太高）
        recursive: 是否递归扫描子文件夹，默认False

    Returns:
        dict: {
            'success_count': 成功数量,
            'failed_count': 失败数量,
            'total_found': 找到的视频数量,
            'results': [每个视频的结果列表]
        }
    """
    if not os.path.exists(folder_path):
        return {
            'success_count': 0,
            'failed_count': 0,
            'total_found': 0,
            'error': f'文件夹不存在: {folder_path}',
            'results': []
        }

    if not os.path.isdir(folder_path):
        return {
            'success_count': 0,
            'failed_count': 0,
            'total_found': 0,
            'error': f'路径不是文件夹: {folder_path}',
            'results': []
        }

    # 扫描视频文件
    video_paths = []
    if recursive:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in VIDEO_EXTENSIONS:
                    video_paths.append(os.path.join(root, file))
    else:
        for file in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file)
            if os.path.isfile(file_path):
                ext = os.path.splitext(file)[1].lower()
                if ext in VIDEO_EXTENSIONS:
                    video_paths.append(file_path)

    total_found = len(video_paths)
    print(f"在文件夹中找到 {total_found} 个视频: {folder_path}")

    if total_found == 0:
        return {
            'success_count': 0,
            'failed_count': 0,
            'total_found': 0,
            'results': []
        }

    # 调用并发处理
    result = generate_subtitles_concurrent(
        video_paths,
        output_dir=output_dir,
        audio_output_dir=audio_output_dir,
        formats=formats,
        model_size=model_size,
        max_workers=max_workers
    )

    result['total_found'] = total_found
    return result

if __name__ == '__main__':
    result = generate_subtitles_from_folder(
        r"C:\Users\wanzicong\快抖下载器\面试小达达_2026-04-07_10-41-51",
        output_dir="./output",
        audio_output_dir="./audio",
        formats="srt",
        model_size="base",
        max_workers=1,
    )
    print(f"\n完成！找到: {result['total_found']}, 成功: {result['success_count']}, 失败: {result['failed_count']}")
