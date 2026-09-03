"""Legacy processing pipeline for v4."""
from .coal_data_processor import CoalDataProcessor
from .data_splitter import DataSplitter, TargetAnalyzer
from .data_merger import DataMerger, TargetAssembler
from .utils import FileHandler, DataFrameProcessor, TextNormalizer

__all__ = [
    "CoalDataProcessor",
    "DataSplitter",
    "TargetAnalyzer",
    "DataMerger",
    "TargetAssembler",
    "FileHandler",
    "DataFrameProcessor",
    "TextNormalizer",
]

