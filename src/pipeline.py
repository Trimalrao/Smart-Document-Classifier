"""
Document Classification Pipeline
End-to-end orchestration: extract → preprocess → classify → enrich.
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .extractor import extract_text_from_file
from .preprocessor import preprocess, extract_key_fields
from .classifier import (
    ClassificationResult,
    RulesBasedClassifier,
    EnsembleClassifier,
    MLClassifier,
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    file_path: str
    raw_text: str
    cleaned_text: str
    extraction_method: str
    classification: ClassificationResult
    extracted_fields: dict = field(default_factory=dict)
    processing_time_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "file": self.file_path,
            "label": self.classification.label,
            "confidence": self.classification.confidence,
            "method": self.classification.method,
            "extraction_method": self.extraction_method,
            "extracted_fields": self.extracted_fields,
            "scores": self.classification.scores,
            "reasoning": self.classification.reasoning,
            "processing_time_ms": self.processing_time_ms,
            "error": self.error,
        }


class DocumentClassificationPipeline:
    """
    Full pipeline for classifying a document from disk.

    Usage:
        pipeline = DocumentClassificationPipeline()
        result = pipeline.run("invoice.pdf")
        print(result.classification.label, result.classification.confidence)
    """

    def __init__(
        self,
        classifier: Optional[EnsembleClassifier | RulesBasedClassifier] = None,
        aggressive_preprocessing: bool = False,
    ):
        self.classifier = classifier or RulesBasedClassifier()
        self.aggressive_preprocessing = aggressive_preprocessing

    def run(self, file_path: str | Path) -> PipelineResult:
        t0 = time.perf_counter()
        path = Path(file_path)
        raw_text = ""
        extraction_method = "unknown"

        try:
            # Step 1: Extract text
            logger.info("[1/4] Extracting text from %s", path.name)
            raw_text, extraction_method = extract_text_from_file(path)

            # Step 2: Preprocess
            logger.info("[2/4] Preprocessing text (%d chars)", len(raw_text))
            cleaned = preprocess(raw_text, aggressive=self.aggressive_preprocessing)

            if len(cleaned.strip()) < 20:
                logger.debug("Very little text extracted from %s", path.name)

            # Step 3: Classify
            logger.info("[3/4] Classifying document")
            result = self.classifier.classify(cleaned)

            # Step 4: Extract structured fields
            logger.info("[4/4] Extracting key fields")
            fields = extract_key_fields(cleaned)

            ms = round((time.perf_counter() - t0) * 1000, 1)
            logger.info(
                "✓ %s → %s (confidence=%.2f, %.1fms)",
                path.name, result.label, result.confidence, ms
            )
            return PipelineResult(
                file_path=str(path),
                raw_text=raw_text,
                cleaned_text=cleaned,
                extraction_method=extraction_method,
                classification=result,
                extracted_fields=fields,
                processing_time_ms=ms,
            )

        except Exception as exc:
            logger.error("Pipeline failed for %s: %s", path, exc, exc_info=True)
            ms = round((time.perf_counter() - t0) * 1000, 1)
            from .classifier import ClassificationResult
            return PipelineResult(
                file_path=str(path),
                raw_text=raw_text,
                cleaned_text="",
                extraction_method=extraction_method,
                classification=ClassificationResult(
                    label="Others", confidence=0.0, method="error"
                ),
                processing_time_ms=ms,
                error=str(exc),
            )

    def run_batch(self, file_paths: list[str | Path]) -> list[PipelineResult]:
        """Classify a list of files."""
        results = []
        for fp in file_paths:
            results.append(self.run(fp))
        return results