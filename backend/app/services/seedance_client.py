"""Seedance 2.0 API 客户端 — 火山引擎视频生成."""
import os
import time
import httpx
from typing import Dict, List, Optional

from dotenv import load_dotenv
_ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), ".env")
load_dotenv(_ENV_FILE)

SEEDANCE_API_KEY = os.getenv("SEEDANCE_API_KEY", "")
SEEDANCE_BASE_URL = os.getenv(
    "SEEDANCE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
)
SEEDANCE_MODEL = os.getenv("SEEDANCE_MODEL", "doubao-seedance-2-0-260128")


class SeedanceError(Exception):
    pass


class SeedanceClient:
    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key or SEEDANCE_API_KEY
        self.base_url = base_url or SEEDANCE_BASE_URL
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    def create_video_task(
        self,
        prompt: str,
        duration: int = 5,
        resolution: str = "720p",
        ratio: str = "9:16",
        generate_audio: bool = True,
        reference_images: Optional[List[str]] = None,
    ) -> dict:
        """创建视频生成任务，返回 {task_id, status, ...}."""
        content: List[Dict] = [
            {"type": "text", "text": prompt}
        ]
        if reference_images:
            for url in reference_images[:9]:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": url},
                    "role": "reference_image",
                })

        body: Dict = {
            "model": SEEDANCE_MODEL,
            "content": content,
            "ratio": ratio,
            "duration": duration,
            "resolution": resolution,
            "generate_audio": generate_audio,
            "watermark": False,
        }

        resp = self._client.post(
            "/contents/generations/tasks", json=body, timeout=30.0
        )
        if resp.status_code != 200:
            raise SeedanceError(f"Seedance API error: {resp.status_code} {resp.text}")
        data = resp.json()
        return {"task_id": data.get("id", ""), "status": "queued"}

    def query_task(self, task_id: str) -> dict:
        """查询任务状态。状态: queued → running → succeeded / failed."""
        resp = self._client.get(f"/contents/generations/tasks/{task_id}")
        if resp.status_code != 200:
            raise SeedanceError(f"Query error: {resp.status_code} {resp.text}")
        data = resp.json()
        status = data.get("status", "unknown")
        video_url = ""
        if status == "succeeded":
            video_url = data.get("content", {}).get("video_url", "")
        return {
            "task_id": task_id,
            "status": status,
            "video_url": video_url,
            "error": data.get("error", {}).get("message", ""),
        }

    def wait_for_completion(
        self, task_id: str, poll_interval: int = 10, max_wait: int = 600
    ) -> dict:
        """轮询等待视频生成完成，返回结果."""
        start = time.time()
        while time.time() - start < max_wait:
            result = self.query_task(task_id)
            status = result["status"]
            if status == "succeeded":
                return result
            if status in ("failed", "expired", "cancelled"):
                raise SeedanceError(f"Video generation {status}: {result.get('error')}")
            time.sleep(poll_interval)
        raise SeedanceError(f"Video generation timed out after {max_wait}s")

    def download_video(self, video_url: str, output_path: str) -> str:
        """下载生成的视频到本地."""
        resp = httpx.get(video_url, timeout=120.0, follow_redirects=True)
        resp.raise_for_status()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return output_path

    def create_and_download(
        self,
        prompt: str,
        output_path: str,
        duration: int = 5,
        resolution: str = "720p",
        ratio: str = "9:16",
    ) -> dict:
        """一键：创建任务 → 等待完成 → 下载视频."""
        task = self.create_video_task(
            prompt=prompt,
            duration=duration,
            resolution=resolution,
            ratio=ratio,
        )
        result = self.wait_for_completion(task["task_id"])
        if result.get("video_url"):
            self.download_video(result["video_url"], output_path)
            result["local_path"] = output_path
        return result


seedance_client = SeedanceClient()
