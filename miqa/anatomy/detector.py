"""MIQA Anatomy Detector — classifica imagem médica por modalidade + anatomia.

Duas fontes de informação (em ordem de prioridade):
  1. Metadados DICOM (BodyPartExamined, StudyDescription, SeriesDescription)
  2. Heurísticas de conteúdo de imagem (histograma, forma, estatísticas)

Saída padronizada: AnatomicalContext(modality, body_part, laterality, view)
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np
import pydicom


class BodyPart(str, Enum):
    UNKNOWN = "unknown"
    # RX
    CHEST = "chest"
    EXTREMITY = "extremity"  # mão, pé, braço, perna
    SKULL = "skull"
    ABDOMEN = "abdomen"
    SPINE = "spine"
    # US
    LIVER = "liver"
    OBSTETRIC = "obstetric"
    VASCULAR = "vascular"
    MSK = "msk"  # musculo-esqueletico
    CARDIAC = "cardiac"
    BREAST = "breast"
    # CT / MRI
    BRAIN = "brain"
    KNEE = "knee"


class Laterality(str, Enum):
    UNKNOWN = "unknown"
    LEFT = "left"
    RIGHT = "right"
    BILATERAL = "bilateral"


class View(str, Enum):
    UNKNOWN = "unknown"
    AP = "ap"
    PA = "pa"
    LATERAL = "lateral"
    AXIAL = "axial"
    CORONAL = "coronal"
    SAGITTAL = "sagittal"
    LONGITUDINAL = "longitudinal"
    TRANSVERSE = "transverse"


@dataclass(frozen=True)
class AnatomicalContext:
    modality: str  # rx, us, ct, mri
    body_part: BodyPart
    laterality: Laterality
    view: View
    confidence: float  # 0.0-1.0
    source: str  # "dicom", "heuristic", "default"


# ========== DICOM TAG PARSERS ==========

_BODYPART_KEYWORDS = {
    BodyPart.CHEST: ["chest", "thorax", "torax", "pulmonar", "lung", "rib"],
    BodyPart.EXTREMITY: ["extremity", "hand", "foot", "wrist", "ankle", "finger",
                         "toe", "arm", "leg", "elbow", "knee"],
    BodyPart.SKULL: ["skull", "cranial", "cranium", "head", "facial", "sinus"],
    BodyPart.ABDOMEN: ["abdomen", "abdominal", "pelvis", "renal", "kidney"],
    BodyPart.SPINE: ["spine", "vertebral", "column", "lumbar", "cervical", "thoracic"],
    BodyPart.BRAIN: ["brain", "cerebral", "head"],
    BodyPart.LIVER: ["liver", "hepatic", "gallbladder", "biliary"],
    BodyPart.OBSTETRIC: ["obstetric", "obstetrical", "fetal", "pregnancy", "gestational"],
    BodyPart.VASCULAR: ["vascular", "artery", "vein", "doppler", "carotid"],
    BodyPart.MSK: ["musculoskeletal", "muscle", "tendon", "shoulder", "hip", "joint"],
    BodyPart.CARDIAC: ["cardiac", "heart", "echocardiography", "echo"],
    BodyPart.BREAST: ["breast", "mammary", "mammo"],
    BodyPart.KNEE: ["knee", "patella", "meniscus"],
}

_VIEW_KEYWORDS = {
    View.AP: ["ap", "anteroposterior", "antero-posterior"],
    View.PA: ["pa", "posteroanterior", "postero-anterior"],
    View.LATERAL: ["lat", "lateral"],
    View.AXIAL: ["axial", "transverse", "transaxial"],
    View.CORONAL: ["coronal", "cor"],
    View.SAGITTAL: ["sagittal", "sag"],
    View.LONGITUDINAL: ["longitudinal", "long"],
}

_LATERALITY_KEYWORDS = {
    Laterality.LEFT: ["left", "lt", "esquerdo", "esq"],
    Laterality.RIGHT: ["right", "rt", "direito", "dir"],
    Laterality.BILATERAL: ["bilateral", "bilat", "both"],
}


def _match_keywords(text: str, keyword_map: dict) -> Optional[Enum]:
    text_lower = text.lower()
    best_match = None
    best_score = 0
    for enum_val, keywords in keyword_map.items():
        for kw in keywords:
            if kw in text_lower:
                # longer match = higher confidence
                score = len(kw)
                if score > best_score:
                    best_score = score
                    best_match = enum_val
    return best_match


def _parse_dicom_tags(ds) -> Optional[AnatomicalContext]:
    """Tenta extrair anatomia dos metadados DICOM."""
    texts = []
    for tag in ["BodyPartExamined", "StudyDescription", "SeriesDescription",
                "ProtocolName", "SeriesComments"]:
        val = ds.get(tag, "")
        if val:
            texts.append(str(val))
    if not texts:
        return None

    combined = " ".join(texts)
    modality = str(ds.get("Modality", "OT")).lower()
    # normalize modality
    modality_map = {"cr": "rx", "dx": "rx", "xr": "rx", "rf": "rx",
                    "us": "us", "ct": "ct", "mr": "mri", "nm": "rx"}
    modality = modality_map.get(modality, modality)

    body_part = _match_keywords(combined, _BODYPART_KEYWORDS) or BodyPart.UNKNOWN
    view = _match_keywords(combined, _VIEW_KEYWORDS) or View.UNKNOWN
    laterality = _match_keywords(combined, _LATERALITY_KEYWORDS) or Laterality.UNKNOWN

    # confidence based on how many tags matched
    matched = sum(1 for x in [body_part, view, laterality] if x.name != "UNKNOWN")
    confidence = min(0.3 + matched * 0.25, 0.95)

    return AnatomicalContext(
        modality=modality,
        body_part=body_part,
        laterality=laterality,
        view=view,
        confidence=confidence,
        source="dicom",
    )


# ========== HEURISTIC CLASSIFIERS ==========

def _heuristic_rx(img: np.ndarray) -> BodyPart:
    """Heurística RX: histograma + forma."""
    h, w = img.shape
    aspect = w / max(h, 1)
    med = float(np.median(img))
    p10 = float(np.percentile(img, 10))
    p90 = float(np.percentile(img, 90))
    # histogram spread
    spread = p90 - p10

    # Tórax: aspecto ~landscape (mais largo que alto), histograma bimodal (ar + tecido)
    if aspect > 1.2 and spread > 0.4 and med > 0.25:
        # Checa simetria bilateral (pulmão esquerdo ~ direito)
        left = img[:, :w//2]
        right = img[:, w//2:]
        sym = abs(float(left.mean()) - float(right.mean()))
        if sym < 0.1:
            return BodyPart.CHEST

    # Extremidade: aspecto próximo de 1.0, contraste alto (osso vs fundo)
    if 0.8 < aspect < 1.3 and p10 < 0.15 and p90 > 0.75:
        # Check for bone-like structure (high intensity lines)
        edges = np.abs(np.diff(img.mean(axis=0))).mean()
        if edges > 0.05:
            return BodyPart.EXTREMITY

    # Crânio: aspecto ~1.0, região central densa (cavea)
    center = img[h//3:2*h//3, w//3:2*w//3]
    if float(center.mean()) > med + 0.1:
        return BodyPart.SKULL

    # Abdome: landscape, médio contraste, sem padrão ósseo forte
    if aspect > 1.1 and 0.2 < med < 0.5 and spread < 0.5:
        return BodyPart.ABDOMEN

    return BodyPart.UNKNOWN


def _heuristic_us(img: np.ndarray) -> BodyPart:
    """Heurística US: análise de textura e geometria."""
    h, w = img.shape
    aspect = w / max(h, 1)

    # US abdominal/obstétrico: aspecto vertical (profundidade), textura speckle
    row_mu = img.mean(axis=1)
    top_mean = row_mu[:h//4].mean()
    bot_mean = row_mu[-h//4:].mean()
    attenuation = (top_mean - bot_mean) / max(top_mean, 1e-6)

    # Cardíaco: quadrado/proximo quadrado, baixa atenuação (TGC bom)
    if 0.9 < aspect < 1.2 and attenuation < 0.3:
        # Check for circular structure (ventricle)
        center = img[h//3:2*h//3, w//3:2*w//3]
        std_center = float(center.std())
        if std_center > 0.15:
            return BodyPart.CARDIAC

    # Obstétrico: grande área cística (escura) no centro
    center_dark = img[h//4:3*h//4, w//4:3*w//4]
    dark_frac = float((center_dark < 0.2).mean())
    if dark_frac > 0.3 and aspect > 0.7:
        return BodyPart.OBSTETRIC

    # Vascular: linear, pequeno, alto contraste
    if aspect > 1.5 and h < 400:
        return BodyPart.VASCULAR

    # MSK: padrão fibrilar visível
    # Compute local orientation variance
    gx = np.abs(np.diff(img, axis=1, append=img[:, -1:]))
    gy = np.abs(np.diff(img, axis=0, append=img[-1:, :]))
    orientation = np.arctan2(gy, gx)
    ori_std = float(orientation.std())
    if ori_std > 0.8 and aspect > 0.8:
        return BodyPart.MSK

    # Default abdominal (mais comum)
    if attenuation > 0.2:
        return BodyPart.LIVER

    return BodyPart.UNKNOWN


def _heuristic_ct(img: np.ndarray, hu_array: Optional[np.ndarray] = None) -> BodyPart:
    """Heurística CT: usa HU quando disponível."""
    if hu_array is not None:
        arr = hu_array
    else:
        arr = img

    h, w = arr.shape
    med = float(np.median(arr))
    # Air fraction
    air_frac = float((arr < -500).mean())
    # Bone fraction
    bone_frac = float((arr > 300).mean())
    # Soft tissue fraction
    soft_frac = float(((arr > -50) & (arr < 100)).mean())

    # Crânio: muito osso, pouco ar
    if bone_frac > 0.15 and air_frac < 0.3:
        return BodyPart.BRAIN

    # Tórax: muito ar (pulmão)
    if air_frac > 0.3 and soft_frac > 0.1:
        return BodyPart.CHEST

    # Abdome: mistura de gordura (-100) e tecido mole (40-60)
    fat_frac = float(((arr > -150) & (arr < -30)).mean())
    if soft_frac > 0.2 and fat_frac > 0.05:
        return BodyPart.ABDOMEN

    # Coluna: osso linear central
    center_bone = (arr[h//3:2*h//3, w//3:2*w//3] > 200).mean()
    if center_bone > 0.1 and bone_frac > 0.05:
        return BodyPart.SPINE

    return BodyPart.UNKNOWN


def _heuristic_mri(img: np.ndarray) -> BodyPart:
    """Heurística MRI: intensidade relativa e padrões."""
    h, w = img.shape
    med = float(np.median(img))

    # Cérebro: simetria bilateral, relação WM/GM visível
    left = img[:, :w//2]
    right = img[:, w//2:]
    sym = abs(float(left.mean()) - float(right.mean()))

    center = img[h//3:2*h//3, w//3:2*w//3]
    center_std = float(center.std())

    if sym < 0.08 and center_std > 0.12:
        # Check for ventricles (dark regions in center)
        dark_center = float((center < med * 0.5).mean())
        if dark_center > 0.05:
            return BodyPart.BRAIN

    # Joelho: osso branco, cartilagem cinza, formato circular
    if center_std > 0.15 and float((center > 0.6).mean()) > 0.2:
        return BodyPart.KNEE

    # Coluna: estrutura linear vertical, osso escuro em T2 / branco em T1
    vert_profile = img.mean(axis=1)
    vert_std = float(vert_profile.std())
    if vert_std > 0.1 and h > w * 1.2:
        return BodyPart.SPINE

    # Abdome: grande área homogênea (fígado)
    if float((center > med * 0.8).mean()) > 0.4:
        return BodyPart.ABDOMEN

    return BodyPart.UNKNOWN


# ========== PUBLIC API ==========

def detect_anatomy(path: Path, img: Optional[np.ndarray] = None,
                   hu_array: Optional[np.ndarray] = None) -> AnatomicalContext:
    """Detecta anatomia de uma imagem médica.

    Args:
        path: caminho do arquivo (usado para ler DICOM se for .dcm)
        img: imagem normalizada [0,1] float32 2D (opcional)
        hu_array: array em HU para CT (opcional)

    Returns:
        AnatomicalContext com modality, body_part, laterality, view
    """
    # 1. Tenta DICOM
    if path.suffix.lower() in (".dcm", ".dicom") or img is None:
        try:
            ds = pydicom.dcmread(path)
            dicom_ctx = _parse_dicom_tags(ds)
            if dicom_ctx and dicom_ctx.confidence >= 0.5:
                return dicom_ctx
        except Exception:
            pass

    # 2. Fallback heurístico
    if img is None:
        # Cannot do heuristic without image
        return AnatomicalContext(
            modality="unknown", body_part=BodyPart.UNKNOWN,
            laterality=Laterality.UNKNOWN, view=View.UNKNOWN,
            confidence=0.0, source="default",
        )

    # Infer modality from path/filename if not from DICOM
    fname = path.name.lower()
    modality = "rx"
    if "us" in fname or "ultra" in fname:
        modality = "us"
    elif "ct" in fname:
        modality = "ct"
    elif "mr" in fname or "mri" in fname:
        modality = "mri"

    # Run heuristic based on modality
    if modality == "rx":
        body_part = _heuristic_rx(img)
    elif modality == "us":
        body_part = _heuristic_us(img)
    elif modality == "ct":
        body_part = _heuristic_ct(img, hu_array)
    elif modality == "mri":
        body_part = _heuristic_mri(img)
    else:
        body_part = BodyPart.UNKNOWN

    confidence = 0.4 if body_part != BodyPart.UNKNOWN else 0.1
    source = "heuristic"

    # Check for laterality in filename
    laterality = Laterality.UNKNOWN
    if "_l" in fname or "left" in fname:
        laterality = Laterality.LEFT
    elif "_r" in fname or "right" in fname:
        laterality = Laterality.RIGHT

    return AnatomicalContext(
        modality=modality,
        body_part=body_part,
        laterality=laterality,
        view=View.UNKNOWN,
        confidence=confidence,
        source=source,
    )


def get_metrics_for_context(ctx: AnatomicalContext) -> list[str]:
    """Retorna lista de nomes de métricas recomendadas para o contexto anatômico."""
    from miqa.anatomy import metric_registry
    return metric_registry.get_recommended_metrics(ctx)
