"""SMB 远程存储 — 将视频文件直接写入 Windows 共享，不占用 VM 本地磁盘."""
import os
import uuid
import logging
from functools import lru_cache
from typing import Optional

from smbprotocol.connection import Connection
from smbprotocol.session import Session
from smbprotocol.tree import TreeConnect
from smbprotocol.open import (
    Open,
    FileAttributes,
    ShareAccess,
    CreateDisposition,
    CreateOptions,
)

logger = logging.getLogger("smb_storage")

SMB_HOST = os.environ.get("SMB_HOST", "192.168.1.6")
SMB_SHARE = os.environ.get("SMB_SHARE", "share")
SMB_USER = os.environ.get("SMB_USER", "Administrator")
SMB_PASSWORD = os.environ.get("SMB_PASSWORD", "")
SMB_ROOT_DIR = os.environ.get("SMB_ROOT_DIR", "comic_videos")


class SMBClient:
    """SMB 客户端，封装文件写入操作."""

    def __init__(
        self,
        host: str = SMB_HOST,
        share: str = SMB_SHARE,
        user: str = SMB_USER,
        password: str = SMB_PASSWORD,
    ):
        self.host = host
        self.share = share
        self.user = user
        self.password = password
        self._connection: Optional[Connection] = None
        self._session: Optional[Session] = None
        self._tree: Optional[TreeConnect] = None

    def connect(self):
        if self._tree:
            return
        self._connection = Connection(uuid.uuid4(), self.host, 445)
        self._connection.connect()
        self._session = Session(self._connection, self.user, self.password)
        self._session.connect()
        self._tree = TreeConnect(self._session, f"\\\\{self.host}\\{self.share}")
        self._tree.connect()
        logger.info("SMB connected to \\\\%s\\%s", self.host, self.share)

    def disconnect(self):
        if self._connection:
            try:
                self._connection.disconnect()
            except Exception:
                pass
        self._connection = None
        self._session = None
        self._tree = None

    def _to_win_path(self, path: str) -> str:
        """将路径转为 Windows 反斜杠格式（SMB 协议要求）。"""
        return path.replace("/", "\\")

    def ensure_dir(self, path: str):
        """确保 SMB 共享上的目录存在（类似 os.makedirs）。"""
        self.connect()
        parts = self._to_win_path(path).strip("\\").split("\\")
        current = ""
        for part in parts:
            current = f"{current}\\{part}" if current else part
            try:
                d = Open(self._tree, current)
                d.create(
                    2,
                    0x0012019F,
                    FileAttributes.FILE_ATTRIBUTE_DIRECTORY,
                    ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE,
                    CreateDisposition.FILE_OPEN_IF,
                    CreateOptions.FILE_DIRECTORY_FILE,
                )
                d.close()
            except Exception:
                pass

    def write_file(self, remote_path: str, content: bytes):
        """写入文件到 SMB 共享。"""
        self.connect()
        win_path = self._to_win_path(remote_path)
        dir_path = os.path.dirname(win_path).replace("/", "\\")
        if dir_path:
            self.ensure_dir(dir_path)

        f = Open(self._tree, win_path)
        f.create(
            2,
            0x0012019F,
            FileAttributes.FILE_ATTRIBUTE_NORMAL,
            ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE,
            CreateDisposition.FILE_SUPERSEDE,
            CreateOptions.FILE_NON_DIRECTORY_FILE,
        )
        f.write(content)
        f.close()
        logger.info("SMB wrote %d bytes to %s", len(content), remote_path)

    def file_exists(self, remote_path: str) -> bool:
        """检查 SMB 共享上的文件是否存在。"""
        self.connect()
        win_path = self._to_win_path(remote_path)
        try:
            f = Open(self._tree, win_path)
            f.create(
                2,
                0x0012019F,
                FileAttributes.FILE_ATTRIBUTE_NORMAL,
                ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE,
                CreateDisposition.FILE_OPEN,
                CreateOptions.FILE_NON_DIRECTORY_FILE,
            )
            f.close()
            return True
        except Exception:
            return False

    def read_file(self, remote_path: str) -> bytes:
        """读取 SMB 共享上的文件内容。"""
        self.connect()
        win_path = self._to_win_path(remote_path)
        f = Open(self._tree, win_path)
        f.create(
            2,
            0x0012019F,
            FileAttributes.FILE_ATTRIBUTE_NORMAL,
            ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE,
            CreateDisposition.FILE_OPEN,
            CreateOptions.FILE_NON_DIRECTORY_FILE,
        )
        info = f.query_info()
        size = info.get("end_of_file", 0)
        data = f.read(0, size)
        f.close()
        return data

    def delete_file(self, remote_path: str):
        """删除 SMB 共享上的文件。"""
        self.connect()
        win_path = self._to_win_path(remote_path)
        try:
            f = Open(self._tree, win_path)
            f.create(
                2,
                0x0012019F,
                FileAttributes.FILE_ATTRIBUTE_NORMAL,
                ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE,
                CreateDisposition.FILE_OPEN,
                CreateOptions.FILE_NON_DIRECTORY_FILE,
            )
            f.delete_on_close = True
            f.close()
        except Exception:
            pass


# 全局单例
_smb_client: Optional[SMBClient] = None


def get_smb_client() -> SMBClient:
    global _smb_client
    if _smb_client is None:
        _smb_client = SMBClient()
    return _smb_client


def smb_read(local_path: str) -> bytes:
    """从 SMB 共享读取文件内容。"""
    client = get_smb_client()
    filename = os.path.basename(local_path)
    remote_path = f"{SMB_ROOT_DIR}/{filename}" if SMB_ROOT_DIR else filename
    return client.read_file(remote_path)


def smb_write(local_path: str, content: bytes):
    """将内容写入 SMB 共享，提取文件名并拼上 SMB_ROOT_DIR。

    Args:
        local_path: 本地完整路径（如 .../backend/uploads/comic_videos/video_xxx.mp4）
        content: 文件内容
    """
    client = get_smb_client()
    # 只取文件名，拼上 SMB_ROOT_DIR 作为远程路径
    filename = os.path.basename(local_path)
    remote_path = f"{SMB_ROOT_DIR}/{filename}" if SMB_ROOT_DIR else filename
    client.write_file(remote_path, content)
