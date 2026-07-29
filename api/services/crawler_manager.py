# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/api/services/crawler_manager.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

import asyncio
import re
import subprocess
import signal
import os
import sys
from typing import Optional, List
from datetime import datetime
from pathlib import Path

from ..schemas import CrawlerStartRequest, LogEntry


class CrawlerManager:
    """Crawler process manager"""

    def __init__(self):
        self._lock = asyncio.Lock()
        self.process: Optional[subprocess.Popen] = None
        self.status = "idle"
        self.started_at: Optional[datetime] = None
        self.current_config: Optional[CrawlerStartRequest] = None
        self.error_message: Optional[str] = None
        self._sensitive_values: set[str] = set()
        self._log_id = 0
        self._logs: List[LogEntry] = []
        self._read_task: Optional[asyncio.Task] = None
        # Project root directory
        self._project_root = Path(__file__).parent.parent.parent
        # Log queue - for pushing to WebSocket
        self._log_queue: Optional[asyncio.Queue] = None

    @property
    def logs(self) -> List[LogEntry]:
        return self._logs

    def get_log_queue(self) -> asyncio.Queue:
        """Get or create log queue"""
        if self._log_queue is None:
            self._log_queue = asyncio.Queue()
        return self._log_queue

    def _create_log_entry(self, message: str, level: str = "info") -> LogEntry:
        """Create log entry"""
        self._log_id += 1
        entry = LogEntry(
            id=self._log_id,
            timestamp=datetime.now().strftime("%H:%M:%S"),
            level=level,
            message=self._redact_message(message),
        )
        self._logs.append(entry)
        # Keep last 500 logs
        if len(self._logs) > 500:
            self._logs = self._logs[-500:]
        return entry

    def _redact_message(self, message: str) -> str:
        """Remove known credentials and cookie assignments from all log paths."""
        redacted = message
        for secret in sorted(self._sensitive_values, key=len, reverse=True):
            if secret:
                redacted = redacted.replace(secret, "[REDACTED]")
        redacted = re.sub(
            r"(?i)\b(cookie|cookies|MEDIACRAWLER_COOKIES)\b"
            r"(\s*[:=]\s*)[^\r\n]*",
            r"\1\2[REDACTED]",
            redacted,
        )
        return re.sub(
            r"(?i)\b(sessionid|sid_guard|ttwid|passport_csrf_token|msToken)"
            r"\s*=\s*[^;\s]+",
            r"\1=[REDACTED]",
            redacted,
        )

    async def _push_log(self, entry: LogEntry):
        """Push log to queue"""
        if self._log_queue is not None:
            try:
                self._log_queue.put_nowait(entry)
            except asyncio.QueueFull:
                pass

    def _parse_log_level(self, line: str) -> str:
        """Parse log level"""
        line_upper = line.upper()
        if "ERROR" in line_upper or "FAILED" in line_upper:
            return "error"
        elif "WARNING" in line_upper or "WARN" in line_upper:
            return "warning"
        elif "SUCCESS" in line_upper or "完成" in line or "成功" in line:
            return "success"
        elif "DEBUG" in line_upper:
            return "debug"
        return "info"

    async def start(self, config: CrawlerStartRequest) -> bool:
        """Start crawler process"""
        async with self._lock:
            if self.process and self.process.poll() is None:
                return False
            await self._wait_for_reader()

            # Clear old logs
            self._logs = []
            self._log_id = 0
            self.error_message = None
            self._sensitive_values.clear()
            if config.cookies:
                self._sensitive_values.add(config.cookies)

            # Clear pending queue (don't replace object to avoid WebSocket broadcast coroutine holding old queue reference)
            if self._log_queue is None:
                self._log_queue = asyncio.Queue()
            else:
                try:
                    while True:
                        self._log_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass

            # Build command line arguments
            cmd = self._build_command(config)
            process_env = self._build_process_env(config)

            # Log start information
            entry = self._create_log_entry(f"Starting crawler: {' '.join(cmd)}", "info")
            await self._push_log(entry)

            try:
                # Start subprocess
                popen_kwargs = {}
                if os.name == "nt":
                    popen_kwargs["creationflags"] = (
                        subprocess.CREATE_NEW_PROCESS_GROUP
                    )
                else:
                    popen_kwargs["start_new_session"] = True

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                    cwd=str(self._project_root),
                    env=process_env,
                    **popen_kwargs,
                )
                self.process = process

                self.status = "running"
                self.started_at = datetime.now()
                self.current_config = config.model_copy(update={"cookies": ""})

                entry = self._create_log_entry(
                    f"Crawler started on platform: {config.platform.value}, type: {config.crawler_type.value}",
                    "success",
                )
                await self._push_log(entry)

                # Start log reading task
                self._read_task = asyncio.create_task(
                    self._read_output(process)
                )

                return True
            except Exception as e:
                self.status = "error"
                self.error_message = str(e)
                entry = self._create_log_entry(
                    f"Failed to start crawler: {str(e)}", "error"
                )
                await self._push_log(entry)
                self.current_config = None
                self._sensitive_values.clear()
                return False

    async def stop(self) -> bool:
        """Stop crawler process"""
        async with self._lock:
            if not self.process or self.process.poll() is not None:
                return False
            process = self.process

            self.status = "stopping"
            entry = self._create_log_entry(
                "Sending SIGTERM to crawler process...", "warning"
            )
            await self._push_log(entry)

            try:
                self._terminate_process_tree(force=False)

                # Wait for graceful exit (up to 15 seconds)
                for _ in range(30):
                    if process.poll() is not None:
                        break
                    await asyncio.sleep(0.5)

                # If still not exited, force kill
                if process.poll() is None:
                    entry = self._create_log_entry(
                        "Process not responding, sending SIGKILL...", "warning"
                    )
                    await self._push_log(entry)
                    self._terminate_process_tree(force=True)

                if process.poll() is None:
                    try:
                        await asyncio.wait_for(
                            asyncio.get_running_loop().run_in_executor(
                                None,
                                process.wait,
                            ),
                            timeout=10,
                        )
                    except asyncio.TimeoutError as exc:
                        raise RuntimeError(
                            "crawler process tree did not terminate"
                        ) from exc

                entry = self._create_log_entry("Crawler process terminated", "info")
                await self._push_log(entry)
                await self._wait_for_reader()

            except Exception as e:
                self.status = "error"
                self.error_message = str(e)
                entry = self._create_log_entry(
                    f"Error stopping crawler: {str(e)}", "error"
                )
                await self._push_log(entry)
                return False

            self.status = "idle"
            self.current_config = None
            self.error_message = None
            self._sensitive_values.clear()
            if self.process is process:
                self.process = None

            return True

    async def _wait_for_reader(self, timeout: float = 5.0) -> None:
        """Finish the previous process reader before reusing manager state."""
        task = self._read_task
        if task is None or task is asyncio.current_task():
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        except asyncio.CancelledError:
            if not task.cancelled():
                raise
        finally:
            if self._read_task is task:
                self._read_task = None

    def _terminate_process_tree(self, force: bool) -> None:
        """Signal the crawler process group, including browser descendants."""
        process = self.process
        if process is None or process.poll() is not None:
            return

        if os.name == "nt":
            if not force:
                try:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                    return
                except (OSError, ValueError):
                    pass

            command = ["taskkill", "/PID", str(process.pid), "/T"]
            if force:
                command.append("/F")
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
            if force and process.poll() is None and completed.returncode != 0:
                process.kill()
            return

        try:
            process_group_id = os.getpgid(process.pid)
            os.killpg(
                process_group_id,
                signal.SIGKILL if force else signal.SIGTERM,
            )
        except ProcessLookupError:
            return

    def get_status(self) -> dict:
        """Get current status"""
        return {
            "status": self.status,
            "platform": self.current_config.platform.value
            if self.current_config
            else None,
            "crawler_type": self.current_config.crawler_type.value
            if self.current_config
            else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "error_message": self.error_message,
        }

    def _build_command(self, config: CrawlerStartRequest) -> list:
        """Build main.py command line arguments"""
        cmd = [sys.executable, "-u", "main.py"]

        cmd.extend(["--platform", config.platform.value])
        cmd.extend(["--lt", config.login_type.value])
        cmd.extend(["--type", config.crawler_type.value])
        cmd.extend(["--save_data_option", config.save_option.value])

        # Pass different arguments based on crawler type
        if config.crawler_type.value == "search" and config.keywords:
            cmd.extend(["--keywords", config.keywords])
        elif config.crawler_type.value == "detail" and config.specified_ids:
            cmd.extend(["--specified_id", config.specified_ids])
        elif config.crawler_type.value == "creator" and config.creator_ids:
            cmd.extend(["--creator_id", config.creator_ids])

        if config.start_page != 1:
            cmd.extend(["--start", str(config.start_page)])

        cmd.extend(["--get_comment", "true" if config.enable_comments else "false"])
        cmd.extend(
            ["--get_sub_comment", "true" if config.enable_sub_comments else "false"]
        )
        cmd.extend(
            [
                "--download_media",
                "true" if config.download_media or config.transcribe_media else "false",
            ]
        )
        cmd.extend(
            ["--transcribe_media", "true" if config.transcribe_media else "false"]
        )
        cmd.extend(["--whisper_backend", config.whisper_backend])
        cmd.extend(["--whisper_model", config.whisper_model])
        cmd.extend(["--whisper_language", config.whisper_language])

        if config.max_notes_count is not None:
            cmd.extend(["--crawler_max_notes_count", str(config.max_notes_count)])

        if config.max_comments_count is not None:
            cmd.extend(
                ["--max_comments_count_singlenotes", str(config.max_comments_count)]
            )

        cmd.extend(["--headless", "true" if config.headless else "false"])

        return cmd

    @staticmethod
    def _build_process_env(config: CrawlerStartRequest) -> dict:
        """Build a child environment without exposing cookies in argv/logs."""
        process_env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        process_env.pop("MEDIACRAWLER_COOKIES", None)
        if config.cookies:
            process_env["MEDIACRAWLER_COOKIES"] = config.cookies
        return process_env

    async def _read_output(self, process: subprocess.Popen):
        """Asynchronously read process output"""
        loop = asyncio.get_event_loop()
        stdout = process.stdout

        try:
            while process.poll() is None:
                # Read a line in thread pool
                if stdout is None:
                    break
                line = await loop.run_in_executor(None, stdout.readline)
                if line:
                    line = line.strip()
                    if line:
                        level = self._parse_log_level(line)
                        entry = self._create_log_entry(line, level)
                        await self._push_log(entry)

            # Read remaining output
            if stdout:
                remaining = await loop.run_in_executor(None, stdout.read)
                if remaining:
                    for line in remaining.strip().split("\n"):
                        if line.strip():
                            level = self._parse_log_level(line)
                            entry = self._create_log_entry(line.strip(), level)
                            await self._push_log(entry)

            # Process ended
            if self.process is process and self.status == "running":
                exit_code = process.returncode
                if exit_code == 0:
                    entry = self._create_log_entry(
                        "Crawler completed successfully", "success"
                    )
                    self.status = "idle"
                    self.error_message = None
                else:
                    entry = self._create_log_entry(
                        f"Crawler exited with code: {exit_code}", "error"
                    )
                    self.status = "error"
                    self.error_message = f"Crawler exited with code: {exit_code}"
                await self._push_log(entry)
                self.current_config = None
                self._sensitive_values.clear()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            if self.process is process:
                self.status = "error"
                self.error_message = str(e)
                entry = self._create_log_entry(
                    f"Error reading output: {str(e)}", "error"
                )
                await self._push_log(entry)
                self.current_config = None
                self._sensitive_values.clear()
        finally:
            current_task = asyncio.current_task()
            if self._read_task is current_task:
                self._read_task = None


# Global singleton
crawler_manager = CrawlerManager()
