"""
Configuration for NSDDD v4.0 Installation

This module contains all configuration settings for downloading and installing
the National Security Documents Dataset (NSDDD) version 4.0 from the project's GitHub data release (pre-release) or, from the full release, Edinburgh DataShare.
Search model: Qwen3-Embedding-0.6B (multilingual), 256-dimension float16 index (chosen 2026-10-01 over bge-m3).
"""

# DataShare API endpoints
DATASHARE_API_BASE = 'https://datashare.ed.ac.uk/rest'

# DataShare handle: still the v3.5 record. NOT used by the 4.0 pre-release installer (see DATA_SOURCE below);
# replace with the 4.0 handle when the full 4.0 dataset is deposited.
# https://datashare.ed.ac.uk/handle/10283/9182
DATASHARE_HANDLE = '10283/9182'

# Construct base URL for files
DATASHARE_ITEM_URL = f'{DATASHARE_API_BASE}/handle/{DATASHARE_HANDLE}'

# Where install.py gets its files. 'github' = assets of the data release below (pre-release, until the full 4.0 is on DataShare);
# 'datashare' = the DataShare record above.
DATA_SOURCE = 'github'
DATA_RELEASE_OWNER = 'andrewneal78'
DATA_RELEASE_REPO = 'NSDDD_v4.0_installer'
DATA_RELEASE_TAG = 'data-4.0-pre'

# Local multilingual encoder bundled via DataShare (extracted to model/qwen3-embedding-0.6b/), not fetched from HF.
MODEL_NAME = 'Qwen/Qwen3-Embedding-0.6B'
ENCODER_DIR = 'qwen3-embedding-0.6b'

# Download specifications
DOWNLOADS = {
    # REQUIRED downloads (essential for semantic search)
    'model_files': {
        'filename': 'model_files.zip',
        'size_mb': 715.0,
        'size_gb': 0.70,
        'extract_to': 'model/',
        'expected_files': [
            'countries_dict.json',
            'documents_dict.json',
            'encoded_segments.json',
            'alignment_dict.json',
            'segments.sqlite',
            'short_mask.npy',
            'segment_encodings_metadata.json',
            'topic_of_row.npy',            # precomputed corpus topics: headings for result clusters
            'topic_labels.json',
            'topic_centroids.npy',
        ],
        'expected_any': [
            ['segment_encodings.f16.memmap'],
        ],
        'required': True,
        'description': 'Search index (Qwen3-Embedding-0.6B, 256-dim float16) and segment texts (~1 GB uncompressed)'
    },
    'encoder_model': {
        'filename': 'encoder_model.zip',
        'size_mb': 1140.0,
        'size_gb': 1.11,
        'extract_to': 'model/qwen3-embedding-0.6b/',
        'expected_files': [
            'config.json',
            'modules.json',
            'sentence_bert_config.json',
            'tokenizer.json',
        ],
        'expected_any': [
            ['pytorch_model.bin', 'model.safetensors'],
        ],
        'required': True,
        'description': 'Local Qwen3-Embedding-0.6B multilingual encoder (bfloat16); avoids a HuggingFace pull at install'
    },
    'metadata': {
        'filename': 'metadata.zip',
        'size_mb': 0.077,
        'size_gb': 0.000072,
        'extract_to': 'metadata/',
        'expected_files': [
            'document_metadata.csv',
            'Country_metadata.csv',
        ],
        'required': True,
        'description': 'Metadata: 680-document / 123-country-and-territory 4.0 reference CSVs'
    },
    'whats_new': {
        'filename': 'WHATS_NEW_IN_NSDDD_V4.0.md',
        'size_mb': 0.014,
        'size_gb': 0.000014,
        'extract_to': 'documentation/',
        'required': False,   # published with the full 4.0 release
        'description': 'Complete overview of v4.0 improvements and features'
    },
    'inclusion_criteria': {
        'filename': 'dataset_inclusion_criteria.md',
        'size_mb': 0.024,
        'size_gb': 0.000024,
        'extract_to': 'documentation/',
        'required': False,   # published with the full 4.0 release
        'description': 'Document selection criteria and methodology'
    },
    'readme': {
        'filename': 'README.txt',
        'size_mb': 0.010,
        'size_gb': 0.000010,
        'extract_to': 'documentation/',
        'required': False,   # published with the full 4.0 release
        'description': 'Quick start guide'
    },
    'citation': {
        'filename': 'CITATION.txt',
        'size_mb': 0.004,
        'size_gb': 0.000004,
        'extract_to': 'documentation/',
        'required': False,   # published with the full 4.0 release
        'description': 'Citation formats for research use'
    },
    'license': {
        'filename': 'LICENSE.txt',
        'size_mb': 0.006,
        'size_gb': 0.000006,
        'extract_to': 'documentation/',
        'required': False,   # published with the full 4.0 release
        'description': 'CC BY 4.0 license terms'
    },

    # SOFT download: fetched by the installer, but a failure never stops it (clusters stay numbered instead)
    'label_model': {
        'filename': 'label_model.zip',
        'size_mb': 499.0,
        'size_gb': 0.49,
        'extract_to': 'model/label_model/',
        'expected_files': [
            'qwen3-0.6b-q4_k_m.gguf',
        ],
        'soft': True,
        'description': 'Small local language model that writes cluster headings (optional; Apache 2.0)'
    },

    # OPTIONAL downloads (user chooses which to download)
    'clean_text': {
        'filename': 'clean_text_documents_English_and_translated.zip',
        'size_mb': 43.199,
        'size_gb': 0.040232,
        'extract_to': 'documents/',
        'optional': True,
        'description': '680 plain text documents (English + translated)'
    },
    'spacy': {
        'filename': 'spacy_documents.zip',
        'size_mb': 45.642,
        'size_gb': 0.042507,
        'extract_to': 'documents/',
        'optional': True,
        'description': '680 sentence-segmented documents'
    },
    'pdf_originals': {
        'filename': 'pdf_originals.zip',
        'size_mb': 7468.007,
        'size_gb': 6.955123,
        'extract_to': 'documents/',
        'optional': True,
        'description': '680 original PDFs organized by country'
    },
    'original_language': {
        'filename': 'original_language_documents.zip',
        'size_mb': 9.819,
        'size_gb': 0.009145,

        'extract_to': 'documents/',
        'optional': True,
        'description': '156 original-language plain text files (parallel reference)'
    },
    'original_language_spacy': {
        'filename': 'original_language_spacy.zip',
        'size_mb': 10.450,
        'size_gb': 0.009732,
        'extract_to': 'documents/',
        'optional': True,
        'description': '156 original-language sentence-segmented files'
    }
}

# System requirements
PYTHON_VERSION_MIN = (3, 11)
DISK_SPACE_REQUIRED_MIN_GB = 8   # installed ~4 GB (index 0.6, texts 0.36, model 1.1, XHR 0.5, Python 1-2) + zips
RAM_REQUIRED_GB = 8              # measured: the app peaks at 3.0 GB (2026-10-01), plus the OS, interface and browser
RAM_RECOMMENDED_GB = 16          # comfortable alongside other work

# Installation directory naming
DEFAULT_INSTALL_DIR = 'NSDDD_v4.0_workspace'

# Dependencies (from requirements.txt)
CORE_DEPENDENCIES = ['torch==2.9.1', 'transformers==4.53.2', 'sentence-transformers==4.1.0', 'huggingface_hub==0.36.2', 'tokenizers==0.21.4', 'safetensors==0.5.3', 'numpy==2.0.2', 'scipy==1.17.1', 'scikit-learn==1.6.1', 'pandas==2.2.3', 'networkx==3.2.1', 'matplotlib==3.10.8', 'seaborn==0.13.2', 'ipywidgets==8.1.5', 'ipykernel==6.29.5', 'jupyter_core==5.7.2', 'jupyter_server==2.16.0', 'nbconvert==7.16.6', 'voila==0.5.11', 'tqdm==4.67.1', 'requests==2.32.3', 'psutil==7.2.1']
# Optional dependencies for future extensions
OPTIONAL_DEPENDENCIES = [
]

# Download and verification settings
CHUNK_SIZE = 8192  # Bytes per chunk for downloads
RETRY_ATTEMPTS = 3
TIMEOUT_SECONDS = 30

# Dataset information
DATASET_NAME = 'National Security and Defence Documents Dataset (1987-2026) v4.0'
DATASET_DOCUMENTS = 680
DATASET_COUNTRIES = 123
DATASET_YEARS = '1987–2026'
DATASET_SEGMENTS = 1156105
DATASET_ENCODING_DIM = 256
