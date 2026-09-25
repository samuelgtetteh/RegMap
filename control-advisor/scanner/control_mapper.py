"""
Maps discovered resource categories (from network_scan.py's fingerprinting) to
relevant NIST SP 800-53 controls.

Reuses the same fine-tuned Sentence-BERT model trained for RegMap (Exhibit 11)
rather than building a second model: each resource category is described in
plain language, embedded, and compared by cosine similarity against the same
133-control NIST corpus RegMap already maps against HIPAA. This is a genuine
reuse of existing infrastructure, not a coincidence of convenience — the
underlying task (retrieve the most semantically relevant control text for a
plain-language description) is identical in both tools.
"""
from pathlib import Path

import pandas as pd
import torch
from sentence_transformers import SentenceTransformer

MODEL_PATH = Path(__file__).parent.parent.parent / "models" / "regmap-embedder"
CORPUS_CSV = Path(__file__).parent.parent.parent / "data" / "processed" / "labeled_pairs.csv"

# Plain-language description of what each network_scan.py category means,
# written as the kind of sentence the embedder was trained to match against
# NIST control text (short, concrete, control-relevant risk statements).
CATEGORY_DESCRIPTIONS = {
    "web_insecure": "An unencrypted HTTP web service is exposed, transmitting data in plaintext without encryption in transit.",
    "web": "An HTTPS web service is exposed to the network and should be reviewed for proper access control and configuration.",
    "database": "A database service is exposed on the network, potentially storing sensitive data that requires access control and encryption.",
    "remote_access": "A remote administrative access service (SSH, RDP, or VNC) is available, allowing remote login to the system.",
    "remote_access_insecure": "An unencrypted remote access service (Telnet) is exposed, transmitting login credentials and session data in plaintext.",
    "file_sharing": "A network file-sharing service (SMB/NetBIOS) is exposed, allowing remote access to shared files and folders.",
    "file_transfer_insecure": "An unencrypted file transfer service (FTP) is exposed, transmitting files and credentials in plaintext.",
    "email": "An email service (SMTP, IMAP, or POP3) is running and handling message transmission or retrieval.",
    "dns": "A DNS service is running, resolving domain names for hosts on the network.",
    "windows_rpc": "A Windows RPC endpoint mapper service is exposed, used for remote procedure calls between systems.",
    "unknown": "An unidentified network service was detected running on a non-standard port.",
    # Cloud resource categories (cloud_scan.py) — same embedder, same matching
    # logic, just a different discovery source than a network port scan.
    "cloud_storage_public": "A cloud storage bucket is publicly accessible, allowing anyone on the internet to read its contents without authentication.",
    "cloud_storage_private": "A cloud storage bucket exists and is not publicly accessible, restricted to authorized access only.",
    "cloud_network_exposed": "A cloud network security group allows inbound access from any internet address on a sensitive administrative port such as SSH or RDP.",
    "cloud_network_restricted": "A cloud network security group restricts inbound access to specific trusted addresses rather than the entire internet.",
    "cloud_iam_overprivileged": "A cloud identity and access management user or role has been granted overly broad permissions, such as full administrative access to all resources and actions.",
    "cloud_iam_scoped": "A cloud identity and access management user or role has been granted narrowly scoped permissions limited to what is needed for their role.",
}

_model = None
_corpus_ids = None
_corpus_texts = None
_corpus_embeddings = None


def get_model():
    """Shared accessor so other modules (interview.py) reuse this same loaded
    model instead of each loading their own ~90MB copy into memory."""
    _load()
    return _model


def _load():
    global _model, _corpus_ids, _corpus_texts, _corpus_embeddings
    if _model is not None:
        return
    _model = SentenceTransformer(str(MODEL_PATH), local_files_only=True)

    df = pd.read_csv(CORPUS_CSV)
    unique = df.drop_duplicates(subset=["nist_control_id"])[["nist_control_id", "nist_text"]]
    _corpus_ids = unique["nist_control_id"].tolist()
    _corpus_texts = unique["nist_text"].tolist()
    _corpus_embeddings = _model.encode(_corpus_texts, convert_to_tensor=True)


def recommend_for_category(category, top_k=3):
    _load()
    description = CATEGORY_DESCRIPTIONS.get(category, CATEGORY_DESCRIPTIONS["unknown"])
    query_embed = _model.encode(description, convert_to_tensor=True)
    scores = torch.nn.functional.cosine_similarity(query_embed, _corpus_embeddings)
    top = torch.topk(scores, k=min(top_k, len(_corpus_ids)))

    return [
        {
            "control_id": _corpus_ids[idx],
            "control_text": _corpus_texts[idx][:300],
            "score": round(float(scores[idx]), 4),
        }
        for idx in top.indices
    ]


def recommend_for_host(host_result, top_k=3):
    """host_result: one entry from network_scan.scan()'s results list."""
    recommendations = {}
    for category in host_result["categories"]:
        recommendations[category] = recommend_for_category(category, top_k=top_k)
    return {
        "ip": host_result["ip"],
        "categories": host_result["categories"],
        "recommended_controls": recommendations,
    }


def recommend_for_scan(scan_report, top_k=3):
    """scan_report: the full dict returned by network_scan.scan()."""
    return {
        "cidr": scan_report["cidr"],
        "hosts": [recommend_for_host(h, top_k=top_k) for h in scan_report["results"]],
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            scan_report = json.load(f)
        print(json.dumps(recommend_for_scan(scan_report), indent=2))
    else:
        for cat in CATEGORY_DESCRIPTIONS:
            print(f"=== {cat} ===")
            for rec in recommend_for_category(cat):
                print(f"  {rec['control_id']} (score={rec['score']}): {rec['control_text'][:100]}...")
