#!/usr/bin/env python3
"""
Download embedding model for Legal QA System.
Supports multiple download sources for Chinese users.
"""
import os
import sys

MODEL_CACHE_DIR = "./backend/data/model_cache"

# Set HF mirror for Chinese users
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
os.environ['TRANSFORMERS_CACHE'] = MODEL_CACHE_DIR
os.environ['SENTENCE_TRANSFORMERS_HOME'] = MODEL_CACHE_DIR

os.makedirs(MODEL_CACHE_DIR, exist_ok=True)


def download_from_modelscope():
    """Download model from ModelScope (best for Chinese users)"""
    try:
        from modelscope.hub.snapshot_download import snapshot_download
        print("Downloading model from ModelScope...")
        model_dir = snapshot_download(
            "iic/nlp_corom_sentence-embedding_chinese-base",
            cache_dir=MODEL_CACHE_DIR
        )
        print(f"Model downloaded to: {model_dir}")
        return model_dir
    except ImportError:
        print("modelscope not installed, skipping...")
        return None
    except Exception as e:
        print(f"ModelScope download failed: {e}")
        return None


def download_from_hf_mirror():
    """Download model from Hugging Face mirror"""
    try:
        from sentence_transformers import SentenceTransformer
        print("Downloading model from HF mirror...")
        model = SentenceTransformer("shibing624/text2vec-base-chinese")
        save_path = os.path.join(MODEL_CACHE_DIR, "shibing624_text2vec-base-chinese")
        print(f"Model downloaded and cached at: {save_path}")
        return True
    except Exception as e:
        print(f"HF mirror download failed: {e}")
        return False


def download_lightweight():
    """Download a lightweight fallback model"""
    try:
        from sentence_transformers import SentenceTransformer
        print("Downloading lightweight model from HF mirror...")
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        print("Lightweight model downloaded!")
        return True
    except Exception as e:
        print(f"Lightweight model download failed: {e}")
        return False


def main():
    print("=" * 60)
    print("  Model Downloader for Legal QA System")
    print("=" * 60)
    print()
    print(f"Model cache directory: {MODEL_CACHE_DIR}")
    print()

    # Check if model is already cached
    if os.path.exists(MODEL_CACHE_DIR) and os.listdir(MODEL_CACHE_DIR):
        print("Models already exist in cache directory.")
        print("Contents:")
        for item in os.listdir(MODEL_CACHE_DIR):
            print(f"  - {item}")
        print()
        print("No need to download. You can start the system now.")
        return

    # Strategy 1: ModelScope
    print("Strategy 1: Download from ModelScope...")
    result = download_from_modelscope()
    if result:
        print("Success! Model downloaded from ModelScope.")
        return

    # Strategy 2: HF Mirror
    print("\nStrategy 2: Download from HF Mirror...")
    result = download_from_hf_mirror()
    if result:
        print("Success! Model downloaded from HF Mirror.")
        return

    # Strategy 3: Lightweight
    print("\nStrategy 3: Download lightweight model...")
    result = download_lightweight()
    if result:
        print("Success! Lightweight model downloaded.")
        return

    print("\n" + "=" * 60)
    print("  All download strategies failed!")
    print("=" * 60)
    print()
    print("Please try one of the following:")
    print("1. Check your network connection")
    print("2. Manually download the model and place it in:")
    print(f"   {os.path.abspath(MODEL_CACHE_DIR)}")
    print()
    print("Or use the system without semantic search by running:")
    print("  python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload")
    print()

if __name__ == "__main__":
    main()
