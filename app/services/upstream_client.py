"""
PicGate Upstream OpenAI Client
Handles communication with upstream AI image generation APIs.
"""

import httpx
import logging
from typing import Optional, Dict, Any, List

from app.config import UPSTREAM_TRUST_ENV

logger = logging.getLogger(__name__)


class UpstreamClient:
    """Client for communicating with upstream OpenAI-compatible APIs."""
    
    def __init__(self, api_base: str, api_key: str, timeout: float = 600.0, trust_env: bool = UPSTREAM_TRUST_ENV):
        """
        Initialize the upstream client.
        
        Args:
            api_base: Base URL for the API (e.g., https://api.openai.com/v1)
            api_key: API key for authentication
            timeout: Request timeout in seconds
            trust_env: Whether httpx should use proxy and SSL settings from environment
        """
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.trust_env = trust_env
        
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    @staticmethod
    def _to_data_image_url(image_base64: str, content_type: str = "image/png") -> str:
        """Convert raw base64 image data to a data URL for image_url payloads."""
        if image_base64.startswith("data:image/"):
            return image_base64
        return f"data:{content_type};base64,{image_base64}"

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        """Best-effort extraction of an upstream error message."""
        try:
            error_json = response.json()
        except Exception:
            return response.text

        if isinstance(error_json, dict):
            error = error_json.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error)
            if error:
                return str(error)
            return str(error_json)

        return str(error_json)

    @staticmethod
    def _requires_images_image_url(error_message: str) -> bool:
        """Detect OpenAI-compatible providers that require images[].image_url."""
        normalized = error_message.lower()
        return "images[].image_url" in normalized and "required" in normalized

    @staticmethod
    def _supports_style_parameter(model: str) -> bool:
        """
        OpenAI-style `style` is only supported by DALL-E 3.
        Keep passthrough behavior for unknown model families.
        """
        model_name = (model or "").strip().lower()
        if not model_name:
            return False
        if model_name.startswith("dall-e-3"):
            return True
        if model_name.startswith("gpt-image-") or model_name == "chatgpt-image-latest":
            return False
        if model_name.startswith("dall-e-2"):
            return False
        return True
    
    async def generate_image(
        self,
        prompt: str,
        model: str,
        n: int = 1,
        size: str = "1024x1024",
        quality: Optional[str] = None,
        style: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate images from text prompt.
        
        Always requests base64 format (b64_json) for consistent handling.
        
        Returns:
            Response dict with 'created' and 'data' containing base64 images
        """
        url = f"{self.api_base}/images/generations"
        
        payload = {
            "prompt": prompt,
            "model": model,
            "n": n,
            "size": size,
            "response_format": "b64_json",  # Always request base64
        }
        
        # Add optional parameters if provided
        if quality:
            payload["quality"] = quality
        if style and self._supports_style_parameter(model):
            payload["style"] = style
        elif style:
            logger.info(
                "Dropping unsupported style parameter for model '%s'",
                model
            )
             
        # Add any extra parameters (for flexibility with different APIs)
        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value
        
        logger.info(f"Generating image with prompt: {prompt[:50]}...")
        
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=self.trust_env) as client:
            response = await client.post(
                url,
                json=payload,
                headers=self._get_headers()
            )
            
            if response.status_code != 200:
                logger.error(f"Upstream error: {response.status_code} - {response.text}")
                response.raise_for_status()
            
            return response.json()
    
    async def edit_image(
        self,
        image_base64: str,
        prompt: str,
        model: str,
        mask_base64: Optional[str] = None,
        n: int = 1,
        size: str = "1024x1024",
        source_image_url: Optional[str] = None,
        source_mask_url: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Edit/modify an existing image.
        
        Args:
            image_base64: Base64-encoded source image
            prompt: Edit instructions
            model: Model name
            mask_base64: Optional base64-encoded mask
            source_image_url: Original image URL from the client, if available
            source_mask_url: Original mask URL from the client, if available
            
        Returns:
            Response dict with 'created' and 'data' containing base64 images
        """
        url = f"{self.api_base}/images/edits"

        legacy_payload = {
            "image": image_base64,
            "prompt": prompt,
            "model": model,
            "n": n,
            "size": size,
            "response_format": "b64_json",
        }
        
        if mask_base64:
            legacy_payload["mask"] = mask_base64
            
        for key, value in kwargs.items():
            if value is not None:
                legacy_payload[key] = value

        image_url_payload = {
            "prompt": prompt,
            "model": model,
            "n": n,
            "size": size,
            "response_format": "b64_json",
            "images": [
                {
                    "image_url": source_image_url or self._to_data_image_url(image_base64)
                }
            ],
        }

        if mask_base64:
            image_url_payload["mask"] = source_mask_url or self._to_data_image_url(mask_base64)

        for key, value in kwargs.items():
            if value is not None:
                image_url_payload[key] = value
        
        logger.info(f"Editing image with prompt: {prompt[:50]}...")
        
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=self.trust_env) as client:
            if source_image_url:
                response = await client.post(
                    url,
                    json=image_url_payload,
                    headers=self._get_headers()
                )

                if response.status_code == 200:
                    return response.json()

                logger.error(
                    "Image URL edit payload failed: %s - %s",
                    response.status_code,
                    response.text
                )
                response.raise_for_status()

            response = await client.post(
                url,
                json=legacy_payload,
                headers=self._get_headers()
            )
            
            if response.status_code != 200:
                error_message = self._extract_error_message(response)

                if self._requires_images_image_url(error_message):
                    logger.info("Retrying image edit with images[].image_url payload")

                    response = await client.post(
                        url,
                        json=image_url_payload,
                        headers=self._get_headers()
                    )

                    if response.status_code == 200:
                        return response.json()

                    logger.error(f"Upstream error: {response.status_code} - {response.text}")
                    response.raise_for_status()

                logger.error(f"Upstream error: {response.status_code} - {response.text}")
                response.raise_for_status()
            
            return response.json()
    
    async def chat_completions(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send chat completion request (non-streaming).
        Used for multi-modal conversations with images.
        
        Args:
            messages: Chat messages array
            model: Model name
            
        Returns:
            Chat completion response
        """
        url = f"{self.api_base}/chat/completions"
        
        payload = {
            "messages": messages,
            "model": model,
            "stream": False,  # Always non-streaming
        }
        
        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value
        
        logger.info(f"Chat completion with {len(messages)} messages")
        
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=self.trust_env) as client:
            response = await client.post(
                url,
                json=payload,
                headers=self._get_headers()
            )
            
            if response.status_code != 200:
                logger.error(f"Upstream error: {response.status_code} - {response.text}")
                response.raise_for_status()
            
            return response.json()
    
    async def chat_completions_stream(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        **kwargs
    ):
        """
        Send streaming chat completion request.
        Yields SSE data lines as they arrive from upstream.
        
        Args:
            messages: Chat messages array
            model: Model name
            
        Yields:
            Raw SSE data lines (bytes)
        """
        url = f"{self.api_base}/chat/completions"
        
        payload = {
            "messages": messages,
            "model": model,
            "stream": True,
        }
        
        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value
        
        logger.info(f"Streaming chat completion with {len(messages)} messages")
        
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=self.trust_env) as client:
            async with client.stream(
                "POST",
                url,
                json=payload,
                headers=self._get_headers()
            ) as response:
                if response.status_code != 200:
                    # Read error response
                    error_body = await response.aread()
                    logger.error(f"Upstream stream error: {response.status_code} - {error_body}")
                    response.raise_for_status()
                
                # Yield lines as they come
                async for line in response.aiter_lines():
                    if line:
                        yield line

