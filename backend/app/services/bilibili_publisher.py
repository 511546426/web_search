"""B站开放平台 — 视频自动上传与发布.

使用前需在 B站开放平台 (https://openhome.bilibili.com) 注册开发者账号并创建应用.
"""
import os
import json
import time
import hashlib
import logging
from typing import Optional
from urllib.parse import urlencode

import httpx

logger = logging.getLogger("bilibili_publisher")

BILIBILI_APP_KEY = os.environ.get("BILIBILI_APP_KEY", "")
BILIBILI_APP_SECRET = os.environ.get("BILIBILI_APP_SECRET", "")
BILIBILI_REFRESH_TOKEN = os.environ.get("BILIBILI_REFRESH_TOKEN", "")

API_BASE = "https://api.bilibili.com/x"


class BilibiliError(Exception):
    pass


class BilibiliPublisher:
    """B站视频发布客户端."""

    def __init__(
        self,
        app_key: str = BILIBILI_APP_KEY,
        app_secret: str = BILIBILI_APP_SECRET,
        refresh_token: str = BILIBILI_REFRESH_TOKEN,
    ):
        self.app_key = app_key
        self.app_secret = app_secret
        self._refresh_token = refresh_token
        self._access_token: str = ""
        self._client = httpx.Client(base_url=API_BASE, timeout=30.0)

    # ---- OAuth2 ----

    def _refresh_access_token(self) -> str:
        """用 refresh_token 换取新的 access_token."""
        params = {
            "client_id": self.app_key,
            "client_secret": self.app_secret,
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }
        resp = self._client.post("/oauth2/token", params=params)
        data = self._handle_response(resp)
        self._access_token = data.get("access_token", "")
        new_refresh = data.get("refresh_token", "")
        if new_refresh:
            self._refresh_token = new_refresh
        logger.info("Bilibili access token refreshed")
        return self._access_token

    def _ensure_token(self):
        """确保 access_token 有效."""
        if not self._access_token:
            self._refresh_access_token()

    def _headers(self) -> dict:
        self._ensure_token()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    # ---- 视频上传 ----

    def _pre_upload(self, file_name: str, file_size: int) -> dict:
        """预上传：获取上传 URL 和参数."""
        self._ensure_token()
        params = {
            "access_token": self._access_token,
            "appkey": self.app_key,
            "name": file_name,
            "size": str(file_size),
            "ts": str(int(time.time())),
        }
        params["sign"] = self._sign(params)
        resp = self._client.get(
            "https://member.bilibili.com/x/v2/video/upload/apply",
            params=params,
        )
        return self._handle_response(resp)

    def _sign(self, params: dict) -> str:
        """B站 API 签名算法."""
        keys = sorted(params.keys())
        query = "&".join(f"{k}={params[k]}" for k in keys)
        sign_str = query + self.app_secret
        return hashlib.md5(sign_str.encode("utf-8")).hexdigest()

    def upload_video(self, file_path: str) -> str:
        """上传视频文件到 B站，返回 filename (oss_key)。"""
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)

        # 1. 预上传
        upload_info = self._pre_upload(file_name, file_size)
        upload_url = upload_info.get("upload_url", "")
        if not upload_url:
            raise BilibiliError("预上传失败：未获取到 upload_url")

        logger.info("Bilibili pre-upload done, uploading %s (%d bytes)...", file_name, file_size)

        # 2. 上传文件内容到预签名 URL
        with open(file_path, "rb") as f:
            resp = httpx.put(upload_url, content=f, timeout=600.0)
        if resp.status_code not in (200, 201):
            raise BilibiliError(f"文件上传失败: HTTP {resp.status_code}")

        # 3. 上传完成确认
        confirm_params = {
            "access_token": self._access_token,
            "appkey": self.app_key,
            "upload_id": upload_info.get("upload_id", ""),
            "ts": str(int(time.time())),
            "biz_id": upload_info.get("biz_id", ""),
        }
        confirm_params["sign"] = self._sign(confirm_params)
        confirm_resp = self._client.post(
            "https://member.bilibili.com/x/v2/video/upload/complete",
            params=confirm_params,
        )
        confirm_data = self._handle_response(confirm_resp)
        filename = confirm_data.get("filename", "") or confirm_data.get("oss_key", "")
        logger.info("Bilibili upload complete, filename=%s", filename)
        return filename

    # ---- 视频创建 ----

    def create_video(
        self,
        title: str,
        description: str,
        filename: str,
        tags: Optional[list] = None,
        tid: int = 174,  # 默认分区：生活 > 日常
        source: str = "",
        copyright_type: int = 1,  # 1=自制, 2=转载
    ) -> dict:
        """创建视频投稿.

        Args:
            title: 视频标题
            description: 视频简介
            filename: 上传后得到的 filename (oss_key)
            tags: 标签列表
            tid: 分区 ID (默认 174=生活-日常)
            source: 转载来源
            copyright_type: 1=自制, 2=转载

        Returns:
            { "aid": int, "bvid": str, "url": str }
        """
        self._ensure_token()
        if tags is None:
            tags = ["漫剧", "AI生成"]

        data = {
            "access_token": self._access_token,
            "appkey": self.app_key,
            "build": 1002000,
            "copyright": copyright_type,
            "desc": description,
            "dynamic": "",
            "filename": filename,
            "no_reprint": 0,
            "open_elec": 0,
            "open_subtitle": 0,
            "platform": "web",
            "source": source,
            "tag": ",".join(tags),
            "tid": tid,
            "title": title,
            "ts": str(int(time.time())),
        }
        data["sign"] = self._sign(data)

        resp = self._client.post("/v2/video/create", data=data)
        result = self._handle_response(resp)

        aid = result.get("aid", 0)
        bvid = result.get("bvid", "")
        logger.info("Bilibili video created: aid=%s, bvid=%s", aid, bvid)
        return {
            "aid": aid,
            "bvid": bvid,
            "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
        }

    # ---- 发布（上传 + 创建） ----

    def publish(
        self,
        file_path: str,
        title: str,
        description: str = "",
        tags: Optional[list] = None,
        tid: int = 174,
        copyright_type: int = 1,
    ) -> dict:
        """一键上传并发布视频到 B站.

        Returns:
            { "aid": int, "bvid": str, "url": str }
        """
        filename = self.upload_video(file_path)
        return self.create_video(
            title=title,
            description=description,
            filename=filename,
            tags=tags,
            tid=tid,
            copyright_type=copyright_type,
        )

    # ---- 辅助 ----

    @staticmethod
    def _handle_response(resp: httpx.Response) -> dict:
        """解析 B站 API 响应."""
        try:
            data = resp.json()
        except Exception:
            raise BilibiliError(f"Bilibili API 响应异常: HTTP {resp.status_code}")

        if data.get("code", -1) != 0:
            msg = data.get("message", "未知错误")
            raise BilibiliError(f"Bilibili API 错误: {msg} (code={data.get('code')})")

        return data.get("data", {})


# 全局单例
_publisher: Optional[BilibiliPublisher] = None


def get_publisher() -> Optional[BilibiliPublisher]:
    """获取 BilibiliPublisher 实例（未配置时返回 None）。"""
    global _publisher
    if not BILIBILI_APP_KEY or not BILIBILI_APP_SECRET or not BILIBILI_REFRESH_TOKEN:
        return None
    if _publisher is None:
        _publisher = BilibiliPublisher()
    return _publisher
