"""
IPFS Client — Upload de imagens médicas e resultados MIQA para IPFS/Filecoin

Usa a API pública do web3.storage (W3S) ou Lighthouse para pinning no Filecoin.
Garante soberania de dados para hospitais e clínicas do Global South:
- Dados ficam na rede descentralizada, não em servidores de terceiros
- CIDs imutáveis permitem auditoria e reprodutibilidade de resultados
- Open-source e compatível com qualquer nó IPFS
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

# Endpoint público Lighthouse (Filecoin pinning — sem custo para projetos OSS)
LIGHTHOUSE_UPLOAD_URL = "https://node.lighthouse.storage/api/v0/add"
# Endpoint alternativo: web3.storage
W3S_UPLOAD_URL = "https://api.web3.storage/upload"

# Timeout generoso para uploads de imagens médicas (podem ser grandes)
UPLOAD_TIMEOUT = 120  # segundos


@dataclass
class IPFSResult:
    """Resultado de um upload para IPFS/Filecoin"""
    success: bool
    cid: Optional[str]          # Content Identifier — endereço imutável no IPFS
    gateway_url: Optional[str]  # URL pública para acesso
    file_size_bytes: int
    item_uid: str
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "cid": self.cid,
            "gateway_url": self.gateway_url,
            "file_size_bytes": self.file_size_bytes,
            "item_uid": self.item_uid,
            "error": self.error,
        }


class IPFSClient:
    """
    Cliente IPFS para armazenamento descentralizado de imagens médicas.

    Suporta dois backends:
    - Lighthouse: Filecoin pinning gratuito para projetos open-source
    - Web3.Storage: Alternativa com suporte a CAR files

    Uso:
        client = IPFSClient(api_key="seu_lighthouse_token")
        result = await client.upload_image(path, item_uid="abc123", modality="mri")
        print(result.cid)  # QmXxx... ou bafy...
    """

    def __init__(self, api_key: Optional[str] = None, backend: str = "lighthouse"):
        """
        Args:
            api_key: Token de autenticação (Lighthouse ou W3S). Pode ser None
                     para uploads públicos limitados (apenas leitura de CID).
            backend: "lighthouse" (padrão) ou "w3s"
        """
        self.api_key = api_key
        self.backend = backend
        self._upload_url = LIGHTHOUSE_UPLOAD_URL if backend == "lighthouse" else W3S_UPLOAD_URL
        logger.info(f"IPFSClient iniciado — backend: {backend}")

    async def upload_image(
        self,
        image_path: Path,
        item_uid: str,
        modality: str = "unknown",
        metadata: Optional[dict] = None,
    ) -> IPFSResult:
        """
        Faz upload de uma imagem médica para IPFS/Filecoin.

        O arquivo original NÃO é modificado. O CID retornado é o endereço
        imutável e verificável do conteúdo na rede IPFS.

        Args:
            image_path: Caminho local da imagem (DICOM, PNG, JPEG)
            item_uid: SHA256 uid do arquivo (já calculado pelo FileListener)
            modality: Modalidade médica (mri, ct, us)
            metadata: Metadados adicionais para incluir no manifest JSON

        Returns:
            IPFSResult com CID e URL de gateway
        """
        if not image_path.exists():
            return IPFSResult(
                success=False,
                cid=None,
                gateway_url=None,
                file_size_bytes=0,
                item_uid=item_uid,
                error=f"Arquivo não encontrado: {image_path}",
            )

        file_size = image_path.stat().st_size
        logger.info(f"Iniciando upload IPFS: {image_path.name} ({file_size} bytes)")

        try:
            if self.backend == "lighthouse":
                return await self._upload_lighthouse(image_path, item_uid, file_size)
            else:
                return await self._upload_w3s(image_path, item_uid, file_size)

        except httpx.TimeoutException:
            return IPFSResult(
                success=False, cid=None, gateway_url=None,
                file_size_bytes=file_size, item_uid=item_uid,
                error=f"Timeout após {UPLOAD_TIMEOUT}s",
            )
        except Exception as e:
            logger.error(f"Erro no upload IPFS: {e}")
            return IPFSResult(
                success=False, cid=None, gateway_url=None,
                file_size_bytes=file_size, item_uid=item_uid,
                error=str(e),
            )

    async def upload_result_manifest(
        self,
        result_data: dict,
        item_uid: str,
        image_cid: Optional[str] = None,
    ) -> IPFSResult:
        """
        Faz upload do manifest JSON de resultado MIQA para IPFS.

        O manifest inclui o CID da imagem original (se disponível),
        criando uma cadeia de auditoria verificável.

        Args:
            result_data: Dict com resultado do MIQA (quality score, flags, etc.)
            item_uid: UID do item
            image_cid: CID da imagem original (para linkagem)

        Returns:
            IPFSResult com CID do manifest
        """
        manifest = {
            "schema_version": "1.0",
            "item_uid": item_uid,
            "image_cid": image_cid,
            "miqa_result": result_data,
            "produced_by": "WingsAI MIQA Backend Local",
            "license": "CC-BY-4.0",
            "open_source": "https://github.com/wingsai/miqa-backend-local",
        }

        # Serializar para bytes
        manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
        manifest_size = len(manifest_bytes)

        logger.info(f"Upload manifest IPFS: {item_uid[:16]}... ({manifest_size} bytes)")

        try:
            if self.backend == "lighthouse":
                return await self._upload_bytes_lighthouse(
                    manifest_bytes, f"{item_uid}_manifest.json",
                    item_uid, manifest_size
                )
            else:
                return await self._upload_bytes_w3s(
                    manifest_bytes, f"{item_uid}_manifest.json",
                    item_uid, manifest_size
                )
        except Exception as e:
            return IPFSResult(
                success=False, cid=None, gateway_url=None,
                file_size_bytes=manifest_size, item_uid=item_uid,
                error=str(e),
            )

    async def _upload_lighthouse(self, path: Path, item_uid: str, file_size: int) -> IPFSResult:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
            with open(path, "rb") as f:
                files = {"file": (path.name, f, "application/octet-stream")}
                response = await client.post(
                    LIGHTHOUSE_UPLOAD_URL,
                    files=files,
                    headers=headers,
                )

        if response.status_code == 200:
            data = response.json()
            cid = data.get("Hash") or data.get("cid")
            gateway = f"https://gateway.lighthouse.storage/ipfs/{cid}"
            logger.info(f"Upload IPFS OK: {cid}")
            return IPFSResult(
                success=True, cid=cid, gateway_url=gateway,
                file_size_bytes=file_size, item_uid=item_uid,
            )
        else:
            return IPFSResult(
                success=False, cid=None, gateway_url=None,
                file_size_bytes=file_size, item_uid=item_uid,
                error=f"HTTP {response.status_code}: {response.text[:200]}",
            )

    async def _upload_bytes_lighthouse(
        self, data: bytes, filename: str, item_uid: str, size: int
    ) -> IPFSResult:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=60) as client:
            files = {"file": (filename, data, "application/json")}
            response = await client.post(
                LIGHTHOUSE_UPLOAD_URL, files=files, headers=headers
            )

        if response.status_code == 200:
            resp_data = response.json()
            cid = resp_data.get("Hash") or resp_data.get("cid")
            gateway = f"https://gateway.lighthouse.storage/ipfs/{cid}"
            return IPFSResult(
                success=True, cid=cid, gateway_url=gateway,
                file_size_bytes=size, item_uid=item_uid,
            )
        return IPFSResult(
            success=False, cid=None, gateway_url=None,
            file_size_bytes=size, item_uid=item_uid,
            error=f"HTTP {response.status_code}",
        )

    async def _upload_w3s(self, path: Path, item_uid: str, file_size: int) -> IPFSResult:
        if not self.api_key:
            return IPFSResult(
                success=False, cid=None, gateway_url=None,
                file_size_bytes=file_size, item_uid=item_uid,
                error="Web3.Storage requer API key",
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-NAME": path.name,
        }

        async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
            with open(path, "rb") as f:
                response = await client.post(
                    W3S_UPLOAD_URL,
                    content=f.read(),
                    headers=headers,
                )

        if response.status_code == 200:
            data = response.json()
            cid = data.get("cid")
            gateway = f"https://{cid}.ipfs.w3s.link"
            return IPFSResult(
                success=True, cid=cid, gateway_url=gateway,
                file_size_bytes=file_size, item_uid=item_uid,
            )
        return IPFSResult(
            success=False, cid=None, gateway_url=None,
            file_size_bytes=file_size, item_uid=item_uid,
            error=f"HTTP {response.status_code}: {response.text[:200]}",
        )

    async def _upload_bytes_w3s(
        self, data: bytes, filename: str, item_uid: str, size: int
    ) -> IPFSResult:
        if not self.api_key:
            return IPFSResult(
                success=False, cid=None, gateway_url=None,
                file_size_bytes=size, item_uid=item_uid,
                error="Web3.Storage requer API key",
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-NAME": filename,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(W3S_UPLOAD_URL, content=data, headers=headers)

        if response.status_code == 200:
            resp_data = response.json()
            cid = resp_data.get("cid")
            gateway = f"https://{cid}.ipfs.w3s.link"
            return IPFSResult(
                success=True, cid=cid, gateway_url=gateway,
                file_size_bytes=size, item_uid=item_uid,
            )
        return IPFSResult(
            success=False, cid=None, gateway_url=None,
            file_size_bytes=size, item_uid=item_uid,
            error=f"HTTP {response.status_code}",
        )

    async def verify_cid(self, cid: str) -> bool:
        """
        Verifica se um CID está disponível no gateway público IPFS.

        Args:
            cid: Content Identifier a verificar

        Returns:
            True se o conteúdo está acessível
        """
        url = f"https://ipfs.io/ipfs/{cid}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.head(url)
                return response.status_code == 200
        except Exception:
            return False
