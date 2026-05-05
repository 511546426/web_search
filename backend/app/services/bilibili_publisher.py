"""B站个人账号发布 — bilibili-api-python，扫码登录，上传+发布视频."""
import os
import json
import time
import logging
import subprocess
from typing import Optional

logger = logging.getLogger("bilibili_publisher")

BILIBILI_CREDENTIAL_PATH = os.environ.get(
    "BILIBILI_CREDENTIAL_PATH",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "bilibili_credential.json",
    ),
)


class BilibiliError(Exception):
    pass


class BilibiliPublisher:
    """B站视频发布客户端（个人账号，扫码登录）。"""

    def __init__(self):
        self._credential = None
        self._load_credential()

    # ---- 凭据管理 ----

    def _load_credential(self):
        """从文件加载已保存的登录凭据。"""
        path = BILIBILI_CREDENTIAL_PATH
        if not os.path.exists(path):
            return
        try:
            from bilibili_api import Credential

            with open(path) as f:
                data = json.load(f)
            self._credential = Credential.from_cookies(data)
            logger.info(f"已加载B站登录凭据: {path}")
        except Exception as e:
            logger.warning(f"加载B站凭据失败: {e}")

    def _save_credential(self):
        """保存登录凭据到文件。"""
        if not self._credential:
            return
        path = BILIBILI_CREDENTIAL_PATH
        try:
            cookies = self._credential.get_cookies()
            with open(path, "w") as f:
                json.dump({k: v for k, v in cookies.items() if v}, f, ensure_ascii=False)
            logger.info(f"B站登录凭据已保存: {path}")
        except Exception as e:
            logger.warning(f"保存B站凭据失败: {e}")

    # ---- 登录状态 ----

    @property
    def is_logged_in(self) -> bool:
        """凭据是否已加载（不一定有效）。"""
        return self._credential is not None

    def check_login_valid(self) -> bool:
        """检查凭据是否有效。"""
        if not self._credential:
            return False
        try:
            from bilibili_api import sync
            return sync(self._credential.check_valid())
        except Exception:
            return False

    # ---- 扫码登录 ----

    def generate_qrcode(self, output_dir: str = "") -> dict:
        """生成登录二维码，不等待扫码。

        Args:
            output_dir: 二维码图片输出目录（默认凭据文件所在目录）

        Returns:
            {"image_path": str, "qr_key": str, "url": str}
            或失败时 {"error": str}
        """
        from bilibili_api import sync
        from bilibili_api.login_v2 import QrCodeLogin

        try:
            qr = QrCodeLogin()
            sync(qr.generate_qrcode())
        except Exception as e:
            return {"error": f"生成二维码失败: {e}"}

        if not output_dir:
            output_dir = os.path.dirname(BILIBILI_CREDENTIAL_PATH)

        os.makedirs(output_dir, exist_ok=True)
        img_path = os.path.join(output_dir, "bilibili_qrcode.png")

        pic = qr.get_qrcode_picture()
        with open(img_path, "wb") as f:
            f.write(pic.content)

        # 终端也打印一份
        try:
            qr.get_qrcode_terminal()
        except Exception:
            pass

        logger.info(f"B站二维码已生成: {img_path}")
        return {"image_path": img_path, "url": "see image_path"}

    def _complete_login(self):
        """完成登录（由子类或外部在扫码后调用）。"""
        # 重新加载凭据（扫码后 save_credential 会被其他流程调用）
        self._load_credential()

    # ---- 发布 ----

    def _refresh_credential(self):
        """检查并刷新凭据."""
        from bilibili_api import sync

        try:
            valid = sync(self._credential.check_valid())
            if not valid:
                sync(self._credential.refresh())
                self._save_credential()
        except Exception as e:
            self._credential = None
            raise BilibiliError(f"B站登录凭据已失效，请重新登录: {e}")

    def publish(
        self,
        file_path: str,
        title: str,
        description: str = "",
        tags: Optional[list] = None,
        tid: int = 174,
        copyright: int = 2,
    ) -> dict:
        """通过 Playwright 浏览器自动化上传并发布视频到 B站。

        B站已全面关闭个人账号的 API 直接发布接口（code 21150），
        此方法使用 Playwright 操控浏览器 UI 完成投稿，绕过风控。

        Args:
            file_path: 视频文件路径
            title: 视频标题
            description: 视频简介
            tags: 标签列表
            tid: 分区 ID (默认 174=生活-日常)
            copyright: 1=自制 2=转载

        Returns:
            {"bvid": str, "url": str}
        """
        if not self.is_logged_in:
            raise BilibiliError("B站未登录，请先扫码登录")

        self._refresh_credential()

        # 使用 Playwright 浏览器自动化完成上传+发布
        from .bilibili_browser_publisher import publish_video_sync

        logger.info(f"通过浏览器发布: {title}")
        result = publish_video_sync(
            file_path=file_path,
            title=title,
            description=description or f"AI 生成的漫剧视频 - {title}",
            tags=tags or ["漫剧", "AI视频", "AI生成"],
            tid=tid,
            copyright=copyright,
        )

        if result.get("bvid"):
            logger.info(f"浏览器发布成功: {result['bvid']}")
        else:
            logger.info("浏览器发布完成（可能为草稿）")

        return result


# 全局单例
_publisher: Optional[BilibiliPublisher] = None
_active_qr_login = None  # 当前活跃的二维码登录


def get_publisher() -> Optional[BilibiliPublisher]:
    """获取 BilibiliPublisher 实例。"""
    global _publisher
    if _publisher is None:
        _publisher = BilibiliPublisher()
    return _publisher


def generate_qrcode_login(output_dir: str = "") -> dict:
    """生成二维码并存储登录会话，供后续 check_qrcode_login() 完成登录。

    Args:
        output_dir: 二维码图片输出目录

    Returns:
        {"image_path": str, ...}
    """
    global _active_qr_login

    from bilibili_api import sync
    from bilibili_api.login_v2 import QrCodeLogin

    try:
        qr = QrCodeLogin()
        sync(qr.generate_qrcode())
    except Exception as e:
        return {"error": f"生成二维码失败: {e}"}

    if not output_dir:
        output_dir = os.path.dirname(BILIBILI_CREDENTIAL_PATH)
    os.makedirs(output_dir, exist_ok=True)

    img_path = os.path.join(output_dir, "bilibili_qrcode.png")
    pic = qr.get_qrcode_picture()
    with open(img_path, "wb") as f:
        f.write(pic.content)

    try:
        qr.get_qrcode_terminal()
    except Exception:
        pass

    _active_qr_login = qr
    logger.info(f"B站二维码已生成: {img_path}")
    return {"image_path": img_path, "qr_key": _active_qr_login._QrCodeLogin__qr_key}


def check_qrcode_login() -> dict:
    """检查当前二维码登录状态，完成登录后保存凭据。

    Returns:
        {"status": "scanning"|"done"|"timeout"|"error", ...}
    """
    global _active_qr_login
    from bilibili_api import sync
    from bilibili_api.login_v2 import QrCodeLoginEvents

    if _active_qr_login is None:
        return {"status": "error", "message": "未生成二维码"}

    try:
        state = sync(_active_qr_login.check_state())
    except Exception as e:
        return {"status": "error", "message": str(e)}

    if state == QrCodeLoginEvents.DONE:
        credential = _active_qr_login.get_credential()
        pub = get_publisher()
        pub._credential = credential
        pub._save_credential()
        _active_qr_login = None
        return {"status": "done", "message": "登录成功"}
    elif state == QrCodeLoginEvents.SCAN:
        return {"status": "scanning", "message": "已扫码，等待确认"}
    elif state == QrCodeLoginEvents.TIMEOUT:
        _active_qr_login = None
        return {"status": "timeout", "message": "二维码已过期"}
    else:
        return {"status": "scanning", "message": "等待扫码"}
