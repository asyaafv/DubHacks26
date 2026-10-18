#!/usr/bin/env python3
"""
Train SetFit email classifier for Lapse.

Usage:
    python scripts/train_classifier.py

Trains on backend/extraction/data/classifier_train.jsonl
Saves model to backend/extraction/models/email_classifier/
"""

import json
import time
from pathlib import Path

import numpy as np
from datasets import Dataset
from setfit import SetFitModel, Trainer, TrainingArguments
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split

REPO_ROOT = Path(__file__).parent.parent
DATA_PATH = REPO_ROOT / "backend" / "extraction" / "data" / "classifier_train.jsonl"
MODEL_DIR = REPO_ROOT / "backend" / "extraction" / "models" / "email_classifier"
BASE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

LABELS = ["reward", "receipt", "promo", "other"]
LABEL_TO_ID = {label: i for i, label in enumerate(LABELS)}
ID_TO_LABEL = {i: label for label, i in LABEL_TO_ID.items()}


def load_data(path: Path) -> tuple[list[str], list[int]]:
    """Load training data from JSONL file."""
    texts = []
    labels = []
    with open(path, "r") as f:
        for line in f:
            item = json.loads(line)
            texts.append(item["text"])
            labels.append(LABEL_TO_ID[item["label"]])
    return texts, labels


def main():
    print(f"Loading training data from {DATA_PATH}...")
    texts, labels = load_data(DATA_PATH)
    print(f"Loaded {len(texts)} examples")

    label_counts = {}
    for label_id in labels:
        label = ID_TO_LABEL[label_id]
        label_counts[label] = label_counts.get(label, 0) + 1
    print(f"Label distribution: {label_counts}")

    print("\nSplitting data (80% train, 20% test)...")
    train_texts, test_texts, train_labels, test_labels = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )
    print(f"Train: {len(train_texts)}, Test: {len(test_texts)}")

    train_dataset = Dataset.from_dict({"text": train_texts, "label": train_labels})
    test_dataset = Dataset.from_dict({"text": test_texts, "label": test_labels})

    print(f"\nLoading base model: {BASE_MODEL}...")
    model = SetFitModel.from_pretrained(
        BASE_MODEL,
        labels=LABELS,
    )

    args = TrainingArguments(
        batch_size=16,
        num_epochs=1,
        num_iterations=20,
        output_dir=str(MODEL_DIR),
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_dataset,
        eval_dataset=test_dataset,
    )

    print("\nTraining SetFit model...")
    start_time = time.time()
    trainer.train()
    train_time = time.time() - start_time
    print(f"Training completed in {train_time:.2f} seconds")

    print("\nEvaluating on test set...")
    start_time = time.time()
    predictions = model.predict(test_texts)
    inference_time = time.time() - start_time
    
    if hasattr(predictions, "tolist"):
        pred_labels = predictions.tolist()
    else:
        pred_labels = list(predictions)
    
    if isinstance(pred_labels[0], str):
        pred_ids = [LABEL_TO_ID[p] for p in pred_labels]
    else:
        pred_ids = pred_labels

    accuracy = accuracy_score(test_labels, pred_ids)
    print(f"\nHoldout Accuracy: {accuracy:.2%}")
    print(f"Per-email latency: {(inference_time / len(test_texts)) * 1000:.2f} ms")

    pred_label_names = [ID_TO_LABEL[p] for p in pred_ids]
    true_label_names = [ID_TO_LABEL[t] for t in test_labels]
    print("\nClassification Report:")
    print(classification_report(true_label_names, pred_label_names, labels=LABELS))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nSaving model to {MODEL_DIR}...")
    model.save_pretrained(str(MODEL_DIR))

    label_map_path = MODEL_DIR / "label_map.json"
    with open(label_map_path, "w") as f:
        json.dump({"labels": LABELS, "label_to_id": LABEL_TO_ID}, f)
    print(f"Saved label map to {label_map_path}")

    print("\nDone! Model saved successfully.")
    print(f"  - Accuracy: {accuracy:.2%}")
    print(f"  - Per-email latency: {(inference_time / len(test_texts)) * 1000:.2f} ms")


if __name__ == "__main__":
    main()
