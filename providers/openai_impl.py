import asyncio
import io
import aiohttp
import base64
import json
from typing import Any

from astrbot.api import logger
from ..constants import MAX_IMAGE_BYTES
from ..core.image_options import is_gif_request

from .base import (
    BaseProvider,
    MAX_REFERENCE_IMAGE_BYTES,
    MAX_REFERENCE_TOTAL_BYTES,
    build_image_edits_endpoint,
    build_image_generations_endpoint,
    extract_error_message,
    extract_image_url_from_response,
    read_response_text_limited,
    summarize_payload_json_for_log,
    summarize_response_text_for_log,
    validate_gif_result,
)

def prepare_edit_references(refs):
    prepared = []
    total = 0
    for index, (payload, mime_type) in enumerate(refs, start=1):
        if mime_type == "image/gif":
            from PIL import Image

            try:
                with Image.open(io.BytesIO(payload)) as image:
                    if image.width * image.height > 24_000_000:
                        raise ValueError("GIF 像素过大")
                    still = image.convert("RGBA")
                    frame_limit = min(32, max(1, 24_000_000 // (image.width * image.height)))
                    for frame_index in range(frame_limit):
                        try:
                            image.seek(frame_index)
                        except EOFError:
                            break
                        candidate = image.convert("RGBA")
                        visible = candidate.getbbox()
                        if not visible:
                            continue
                        extrema = candidate.crop(visible).convert("RGB").getextrema()
                        if still.getbbox() is None:
                            still = candidate
                        if any(low != high for low, high in extrema):
                            still = candidate
                            break
                    if still.getbbox() is None:
                        raise ValueError("未找到可见画面")
                    output = io.BytesIO()
                    still.save(output, format="PNG")
                    payload = output.getvalue()
                mime_type = "image/png"
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                raise ValueError(f"第 {index} 张 GIF 参考图无法转换为静态 PNG：{exc}") from exc
        total += len(payload)
        if len(payload) > MAX_REFERENCE_IMAGE_BYTES or total > MAX_REFERENCE_TOTAL_BYTES:
            raise ValueError("转换后参考图超过大小上限")
        prepared.append((payload, mime_type))
    return prepared


class OpenAIProvider(BaseProvider):
    async def generate_image(self, prompt: str, **kwargs: Any) -> str:
        current_key = self.get_current_key()
        if not current_key:
            raise ValueError("节点未配置 API Key！")

        base_url = self.config.base_url
        ref_images = self.get_reference_images(**kwargs)

        logger.info(f"📝 [标准通道] 最终发送给 API 的核心提示词:\n{prompt}")

        api_kwargs = self.filter_api_kwargs(kwargs)
        gif_requested = is_gif_request(api_kwargs)

        if ref_images:
            url = build_image_edits_endpoint(base_url, force_edits=gif_requested)
            logger.info(f"✅ 检测到 {len(ref_images)} 张参考图，正切换至标准改图通道: {url}")
            max_images = 3 if url.lower().split("?", 1)[0].endswith("/images/generations") else 14
            loaded_refs = await self.load_reference_images(ref_images, max_images=max_images)

            if url.lower().split("?", 1)[0].endswith("/images/generations"):
                payload = {
                    "model": self.config.model,
                    "prompt": prompt,
                    "n": 1,
                }
                for idx, (image_bytes, mime_type) in enumerate(loaded_refs, start=1):
                    image_value = f"data:{mime_type};base64," + base64.b64encode(image_bytes).decode("utf-8")
                    payload["image" if idx == 1 else f"image{idx}"] = image_value
                payload.update(api_kwargs)
                log_payload = {k: v for k, v in payload.items() if not str(k).startswith("image")}
                logger.info(f"📤 [标准通道] 附带高级参数的请求体摘要: {summarize_payload_json_for_log(log_payload)}")
                headers = {"Content-Type": "application/json", "Authorization": "Bearer " + current_key}
                timeout_obj = aiohttp.ClientTimeout(total=self.config.timeout)
                async with self.session.post(url, json=payload, headers=headers, timeout=timeout_obj) as response:
                    return await self._parse_response(response, base_url, gif_requested=gif_requested)

            data = aiohttp.FormData()
            loaded_refs = await asyncio.to_thread(prepare_edit_references, loaded_refs)
            for idx, (image_bytes, mime_type) in enumerate(loaded_refs, start=1):
                extension = {"image/jpeg": "jpg", "image/webp": "webp", "image/png": "png"}.get(mime_type, "bin")
                data.add_field(
                    "image[]",
                    image_bytes,
                    filename=f"reference_{idx}.{extension}",
                    content_type=mime_type,
                )

            data.add_field('prompt', prompt)
            data.add_field('model', self.config.model)
            data.add_field('n', '1')

            # 高级参数注入表单
            for k, v in api_kwargs.items():
                data.add_field(k, str(v))

            headers = {"Authorization": "Bearer " + current_key}
            timeout_obj = aiohttp.ClientTimeout(total=self.config.timeout)
            async with self.session.post(url, data=data, headers=headers, timeout=timeout_obj) as response:
                return await self._parse_response(response, base_url, gif_requested=gif_requested)

        else:
            url = build_image_generations_endpoint(base_url)

            # 基础 Payload
            payload = {
                "model": self.config.model,
                "prompt": prompt,
                "n": 1
            }

            # 🚀 完美兼容 gptimage2 / gemini-3.1-image 规范
            # 暴力将所有高级参数塞入 JSON 的最外层，中转 API 会直接识别并调用底层
            payload.update(api_kwargs)

            logger.info(f"📤 [标准通道] 附带高级参数的请求体摘要: {summarize_payload_json_for_log(payload)}")

            headers = {"Content-Type": "application/json", "Authorization": "Bearer " + current_key}

            timeout_obj = aiohttp.ClientTimeout(total=self.config.timeout)
            async with self.session.post(url, json=payload, headers=headers, timeout=timeout_obj) as response:
                return await self._parse_response(response, base_url, gif_requested=gif_requested)

    async def _parse_response(
        self, response: aiohttp.ClientResponse, base_url: str, *, gif_requested: bool = False,
    ) -> str:
        status = response.status
        response_text = await read_response_text_limited(response)
        if status != 200:
            logger.error("💥 API 返回错误摘要: " + summarize_response_text_for_log(response_text, max_string_length=500))
            error_msg = extract_error_message(response_text)

            raise RuntimeError("HTTP " + str(status) + ": " + error_msg)

        try:
            result = json.loads(response_text)
        except Exception:
            raise ValueError("API 返回结构异常，响应不是 JSON: " + summarize_response_text_for_log(response_text))
        image_url = extract_image_url_from_response(
            result, base_url, max_inline_bytes=MAX_IMAGE_BYTES if gif_requested else None,
        )
        if image_url:
            return validate_gif_result(image_url) if gif_requested else image_url

        raise ValueError(
            "API 返回结构异常，未找到图片数据: "
            + summarize_payload_json_for_log(result, max_string_length=500)
        )
