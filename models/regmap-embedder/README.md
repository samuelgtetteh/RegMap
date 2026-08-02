---
tags:
- sentence-transformers
- sentence-similarity
- feature-extraction
- generated_from_trainer
- dataset_size:159
- loss:MultipleNegativesRankingLoss
base_model: sentence-transformers/all-MiniLM-L6-v2
widget:
- source_sentence: 'Software, Firmware, and Information Integrity: Employ integrity
    verification tools to detect unauthorized changes to the following software, firmware,
    and information: [Assignment: org-defined] ; and Take the following actions when
    unauthorized changes to the software, firmware, and information are detected:
    [Assignment: org-defined].'
  sentences:
  - 'Maintenance Records (A): Implement policies and procedures to document repairs
    and modifications to the physical components of a facility which are related to
    security (for example, hardware, walls, doors, and locks).'
  - 'Integrity Controls (A): Implement security measures to ensure that electronically
    transmitted electronic protected health information is not improperly modified
    without detection until disposed of.'
  - 'Facility Security Plan (A): Implement policies and procedures to safeguard the
    facility and the equipment therein from unauthorized physical access, tampering,
    and theft.'
- source_sentence: 'Risk Response: Respond to findings from security and privacy assessments,
    monitoring, and audits in accordance with organizational risk tolerance.'
  sentences:
  - 'Person or Entity Authentication: Implement procedures to verify that a person
    or entity seeking access to electronic protected health information is the one
    claimed.'
  - 'Risk Management (R): Implement security measures sufficient to reduce risks and
    vulnerabilities to a reasonable and appropriate level to comply with §164.306(a).'
  - 'Response and Reporting (R): Identify and respond to suspected or known security
    incidents; mitigate, to the extent practicable, harmful effects of security incidents
    that are known to the covered entity or business associate; and document security
    incidents and their outcomes.'
- source_sentence: 'Role-based Training: Provide role-based security and privacy training
    to personnel with the following roles and responsibilities: [Assignment: org-defined]:
    Before authorizing access to the system, information, or performing assigned duties,
    and [Assignment: org-defined] thereafter; and When required by system changes;
    Update role-based training content [Assignment: org-defined] and following [Assignment:
    org-defined] ; and Incorporate lessons learned from internal or external security
    incidents or breaches into role-based training.'
  sentences:
  - 'Access Control: Implement technical policies and procedures for electronic information
    systems that maintain electronic protected health information to allow access
    only to those persons or software programs that have been granted access rights
    as specified in §164.308(a)(4).'
  - 'Risk Analysis (R): Conduct an accurate and thorough assessment of the potential
    risks and vulnerabilities to the confidentiality, integrity, and availability
    of electronic protected health information held by the covered entity or business
    associate.'
  - 'Protection from Malicious Software (A): Procedures for guarding against, detecting,
    and reporting malicious software.'
- source_sentence: 'Fire Protection: Employ and maintain fire detection and suppression
    systems that are supported by an independent energy source.'
  sentences:
  - 'Facility Security Plan (A): Implement policies and procedures to safeguard the
    facility and the equipment therein from unauthorized physical access, tampering,
    and theft.'
  - 'Person or Entity Authentication: Implement procedures to verify that a person
    or entity seeking access to electronic protected health information is the one
    claimed.'
  - 'Updates (R): Review documentation periodically, and update as needed, in response
    to environmental or operational changes affecting the security of the electronic
    protected health information.'
- source_sentence: 'Policy and Procedures: Develop, document, and disseminate to [Assignment:
    org-defined]: [Assignment: org-defined] physical and environmental protection
    policy that: Addresses purpose, scope, roles, responsibilities, management commitment,
    coordination among organizational entities, and compliance; and Is consistent
    with applicable laws, executive orders, directives, regulations, policies, standards,
    and guidelines; and Procedures to facilitate the implementation of the physical
    and environmental protection policy and the associated physical and environmental
    protection controls; Designate an [Assignment: org-defined] to manage the development,
    documentation, and dissemination of the physical and environmental protection
    policy and procedures; and Review and update the current physical and environmental
    protection: Policy [Assignment: org-defined] and following [Assignment: org-defined]
    ; and Procedures [Assignment: org-defined] and following [Assignment: org-defined].'
  sentences:
  - 'Facility Access Controls: Implement policies and procedures to limit physical
    access to its electronic information systems and the facility or facilities in
    which they are housed, while ensuring that properly authorized access is allowed.'
  - 'Password Management (A): Procedures for creating, changing, and safeguarding
    passwords.'
  - 'Workforce Security: Implement policies and procedures to ensure that all members
    of its workforce have appropriate access to electronic protected health information,
    as provided under paragraph (a)(4) of this section, and to prevent those workforce
    members who do not have access under paragraph (a)(4) from obtaining access to
    electronic protected health information.'
pipeline_tag: sentence-similarity
library_name: sentence-transformers
metrics:
- cosine_accuracy@1
- cosine_accuracy@3
- cosine_accuracy@5
- cosine_accuracy@10
- cosine_precision@1
- cosine_precision@3
- cosine_precision@5
- cosine_precision@10
- cosine_recall@1
- cosine_recall@3
- cosine_recall@5
- cosine_recall@10
- cosine_ndcg@10
- cosine_mrr@10
- cosine_map@100
model-index:
- name: SentenceTransformer based on sentence-transformers/all-MiniLM-L6-v2
  results:
  - task:
      type: information-retrieval
      name: Information Retrieval
    dataset:
      name: val hipaa
      type: val-hipaa
    metrics:
    - type: cosine_accuracy@1
      value: 0.27586206896551724
      name: Cosine Accuracy@1
    - type: cosine_accuracy@3
      value: 0.6206896551724138
      name: Cosine Accuracy@3
    - type: cosine_accuracy@5
      value: 0.7586206896551724
      name: Cosine Accuracy@5
    - type: cosine_accuracy@10
      value: 0.896551724137931
      name: Cosine Accuracy@10
    - type: cosine_precision@1
      value: 0.27586206896551724
      name: Cosine Precision@1
    - type: cosine_precision@3
      value: 0.2068965517241379
      name: Cosine Precision@3
    - type: cosine_precision@5
      value: 0.1517241379310345
      name: Cosine Precision@5
    - type: cosine_precision@10
      value: 0.08965517241379312
      name: Cosine Precision@10
    - type: cosine_recall@1
      value: 0.27586206896551724
      name: Cosine Recall@1
    - type: cosine_recall@3
      value: 0.6206896551724138
      name: Cosine Recall@3
    - type: cosine_recall@5
      value: 0.7586206896551724
      name: Cosine Recall@5
    - type: cosine_recall@10
      value: 0.896551724137931
      name: Cosine Recall@10
    - type: cosine_ndcg@10
      value: 0.575067378776433
      name: Cosine Ndcg@10
    - type: cosine_mrr@10
      value: 0.4737000547345374
      name: Cosine Mrr@10
    - type: cosine_map@100
      value: 0.4781465157145738
      name: Cosine Map@100
---

# SentenceTransformer based on sentence-transformers/all-MiniLM-L6-v2

This is a [sentence-transformers](https://www.SBERT.net) model finetuned from [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2). It maps sentences & paragraphs to a 384-dimensional dense vector space and can be used for retrieval.

## Model Details

### Model Description
- **Model Type:** Sentence Transformer
- **Base model:** [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) <!-- at revision 1110a243fdf4706b3f48f1d95db1a4f5529b4d41 -->
- **Maximum Sequence Length:** 256 tokens
- **Output Dimensionality:** 384 dimensions
- **Similarity Function:** Cosine Similarity
- **Supported Modality:** Text
<!-- - **Training Dataset:** Unknown -->
<!-- - **Language:** Unknown -->
<!-- - **License:** Unknown -->

### Model Sources

- **Documentation:** [Sentence Transformers Documentation](https://sbert.net)
- **Repository:** [Sentence Transformers on GitHub](https://github.com/huggingface/sentence-transformers)
- **Hugging Face:** [Sentence Transformers on Hugging Face](https://huggingface.co/models?library=sentence-transformers)

### Full Model Architecture

```
SentenceTransformer(
  (0): Transformer({'transformer_task': 'feature-extraction', 'modality_config': {'text': {'method': 'forward', 'method_output_name': 'last_hidden_state'}}, 'module_output_name': 'token_embeddings', 'architecture': 'BertModel'})
  (1): Pooling({'embedding_dimension': 384, 'pooling_mode': 'mean', 'include_prompt': True})
  (2): Normalize({})
)
```

## Usage

### Direct Usage (Sentence Transformers)

First install the Sentence Transformers library:

```bash
pip install -U sentence-transformers
```
Then you can load this model and run inference.
```python
from sentence_transformers import SentenceTransformer

# Download from the 🤗 Hub
model = SentenceTransformer("sentence_transformers_model_id")
# Run inference
queries = [
    'Policy and Procedures: Develop, document, and disseminate to [Assignment: org-defined]: [Assignment: org-defined] physical and environmental protection policy that: Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and Procedures to facilitate the implementation of the physical and environmental protection policy and the associated physical and environmental protection controls; Designate an [Assignment: org-defined] to manage the development, documentation, and dissemination of the physical and environmental protection policy and procedures; and Review and update the current physical and environmental protection: Policy [Assignment: org-defined] and following [Assignment: org-defined] ; and Procedures [Assignment: org-defined] and following [Assignment: org-defined].',
]
documents = [
    'Facility Access Controls: Implement policies and procedures to limit physical access to its electronic information systems and the facility or facilities in which they are housed, while ensuring that properly authorized access is allowed.',
    'Password Management (A): Procedures for creating, changing, and safeguarding passwords.',
    'Workforce Security: Implement policies and procedures to ensure that all members of its workforce have appropriate access to electronic protected health information, as provided under paragraph (a)(4) of this section, and to prevent those workforce members who do not have access under paragraph (a)(4) from obtaining access to electronic protected health information.',
]
query_embeddings = model.encode_query(queries)
document_embeddings = model.encode_document(documents)
print(query_embeddings.shape, document_embeddings.shape)
# [1, 384] [3, 384]

# Get the similarity scores for the embeddings
similarities = model.similarity(query_embeddings, document_embeddings)
print(similarities)
# tensor([[0.4287, 0.0978, 0.1891]])
```
<!--
### Direct Usage (Transformers)

<details><summary>Click to see the direct usage in Transformers</summary>

</details>
-->

<!--
### Downstream Usage (Sentence Transformers)

You can finetune this model on your own dataset.

<details><summary>Click to expand</summary>

</details>
-->

<!--
### Out-of-Scope Use

*List how the model may foreseeably be misused and address what users ought not to do with the model.*
-->

## Evaluation

### Metrics

#### Information Retrieval

* Dataset: `val-hipaa`
* Evaluated with [<code>InformationRetrievalEvaluator</code>](https://sbert.net/docs/package_reference/sentence_transformer/evaluation.html#sentence_transformers.sentence_transformer.evaluation.InformationRetrievalEvaluator)

| Metric              | Value      |
|:--------------------|:-----------|
| cosine_accuracy@1   | 0.2759     |
| cosine_accuracy@3   | 0.6207     |
| cosine_accuracy@5   | 0.7586     |
| cosine_accuracy@10  | 0.8966     |
| cosine_precision@1  | 0.2759     |
| cosine_precision@3  | 0.2069     |
| cosine_precision@5  | 0.1517     |
| cosine_precision@10 | 0.0897     |
| cosine_recall@1     | 0.2759     |
| cosine_recall@3     | 0.6207     |
| cosine_recall@5     | 0.7586     |
| cosine_recall@10    | 0.8966     |
| **cosine_ndcg@10**  | **0.5751** |
| cosine_mrr@10       | 0.4737     |
| cosine_map@100      | 0.4781     |

<!--
## Bias, Risks and Limitations

*What are the known or foreseeable issues stemming from this model? You could also flag here known failure cases or weaknesses of the model.*
-->

<!--
### Recommendations

*What are recommendations with respect to the foreseeable issues? For example, filtering explicit content.*
-->

## Training Details

### Training Dataset

#### Unnamed Dataset

* Size: 159 training samples
* Columns: <code>sentence_0</code> and <code>sentence_1</code>
* Approximate statistics based on the first 100 samples:
  |          | sentence_0                                                                           | sentence_1                                                                         |
  |:---------|:-------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------|
  | type     | string                                                                               | string                                                                             |
  | modality | text                                                                                 | text                                                                               |
  | details  | <ul><li>min: 19 tokens</li><li>mean: 105.12 tokens</li><li>max: 256 tokens</li></ul> | <ul><li>min: 13 tokens</li><li>mean: 36.99 tokens</li><li>max: 72 tokens</li></ul> |
* Samples:
  | sentence_0                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | sentence_1                                                                                                                                                                                                                                                  |
  |:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
  | <code>Policy and Procedures: Develop, document, and disseminate to [Assignment: org-defined]: [Assignment: org-defined] physical and environmental protection policy that: Addresses purpose, scope, roles, responsibilities, management commitment, coordination among organizational entities, and compliance; and Is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines; and Procedures to facilitate the implementation of the physical and environmental protection policy and the associated physical and environmental protection controls; Designate an [Assignment: org-defined] to manage the development, documentation, and dissemination of the physical and environmental protection policy and procedures; and Review and update the current physical and environmental protection: Policy [Assignment: org-defined] and following [Assignment: org-defined] ; and Procedures [Assignment: org-defined] and following [Assignment: org-defined].</code> | <code>Facility Access Controls: Implement policies and procedures to limit physical access to its electronic information systems and the facility or facilities in which they are housed, while ensuring that properly authorized access is allowed.</code> |
  | <code>Unsuccessful Logon Attempts: Enforce a limit of [Assignment: org-defined] consecutive invalid logon attempts by a user during a [Assignment: org-defined] ; and Automatically [Assignment: org-defined] when the maximum number of unsuccessful attempts is exceeded.</code>                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | <code>Log-in Monitoring (A): Procedures for monitoring log-in attempts and reporting discrepancies.</code>                                                                                                                                                  |
  | <code>Separation of Duties: Identify and document [Assignment: org-defined] ; and Define system access authorizations to support separation of duties.</code>                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | <code>Information Access Management: Implement policies and procedures for authorizing access to electronic protected health information that are consistent with the applicable requirements of subpart E of this part.</code>                             |
* Loss: [<code>MultipleNegativesRankingLoss</code>](https://sbert.net/docs/package_reference/sentence_transformer/losses.html#multiplenegativesrankingloss) with these parameters:
  ```json
  {
      "scale": 20.0,
      "similarity_fct": "cos_sim",
      "gather_across_devices": false,
      "directions": [
          "query_to_doc"
      ],
      "partition_mode": "joint",
      "hardness_mode": null,
      "hardness_strength": 0.0
  }
  ```

### Training Hyperparameters
#### Non-Default Hyperparameters

- `per_device_train_batch_size`: 16
- `num_train_epochs`: 10
- `per_device_eval_batch_size`: 16
- `multi_dataset_batch_sampler`: round_robin

#### All Hyperparameters
<details><summary>Click to expand</summary>

- `per_device_train_batch_size`: 16
- `num_train_epochs`: 10
- `max_steps`: -1
- `learning_rate`: 5e-05
- `lr_scheduler_type`: linear
- `lr_scheduler_kwargs`: None
- `warmup_steps`: 0
- `optim`: adamw_torch_fused
- `optim_args`: None
- `weight_decay`: 0.0
- `adam_beta1`: 0.9
- `adam_beta2`: 0.999
- `adam_epsilon`: 1e-08
- `optim_target_modules`: None
- `gradient_accumulation_steps`: 1
- `average_tokens_across_devices`: True
- `max_grad_norm`: 1
- `label_smoothing_factor`: 0.0
- `bf16`: False
- `fp16`: False
- `bf16_full_eval`: False
- `fp16_full_eval`: False
- `tf32`: None
- `gradient_checkpointing`: False
- `gradient_checkpointing_kwargs`: None
- `torch_compile`: False
- `torch_compile_backend`: None
- `torch_compile_mode`: None
- `use_liger_kernel`: False
- `liger_kernel_config`: None
- `use_cache`: False
- `neftune_noise_alpha`: None
- `torch_empty_cache_steps`: None
- `auto_find_batch_size`: False
- `log_on_each_node`: True
- `logging_nan_inf_filter`: True
- `include_num_input_tokens_seen`: no
- `log_level`: passive
- `log_level_replica`: warning
- `disable_tqdm`: False
- `project`: huggingface
- `trackio_space_id`: None
- `trackio_bucket_id`: None
- `trackio_static_space_id`: None
- `per_device_eval_batch_size`: 16
- `prediction_loss_only`: True
- `eval_on_start`: False
- `eval_do_concat_batches`: True
- `eval_use_gather_object`: False
- `eval_accumulation_steps`: None
- `include_for_metrics`: []
- `batch_eval_metrics`: False
- `save_only_model`: False
- `save_on_each_node`: False
- `enable_jit_checkpoint`: False
- `push_to_hub`: False
- `hub_private_repo`: None
- `hub_model_id`: None
- `hub_strategy`: every_save
- `hub_always_push`: False
- `hub_revision`: None
- `load_best_model_at_end`: False
- `ignore_data_skip`: False
- `restore_callback_states_from_checkpoint`: False
- `full_determinism`: False
- `seed`: 42
- `data_seed`: None
- `use_cpu`: False
- `accelerator_config`: {'split_batches': False, 'dispatch_batches': None, 'even_batches': True, 'use_seedable_sampler': True, 'non_blocking': False, 'gradient_accumulation_kwargs': None}
- `parallelism_config`: None
- `dataloader_drop_last`: False
- `dataloader_num_workers`: 0
- `dataloader_pin_memory`: True
- `dataloader_persistent_workers`: False
- `dataloader_prefetch_factor`: None
- `remove_unused_columns`: True
- `label_names`: None
- `train_sampling_strategy`: random
- `length_column_name`: length
- `ddp_find_unused_parameters`: None
- `ddp_bucket_cap_mb`: None
- `ddp_broadcast_buffers`: False
- `ddp_static_graph`: None
- `ddp_backend`: None
- `ddp_timeout`: 1800
- `fsdp`: None
- `fsdp_config`: None
- `deepspeed`: None
- `debug`: []
- `skip_memory_metrics`: True
- `do_predict`: False
- `resume_from_checkpoint`: None
- `warmup_ratio`: None
- `local_rank`: -1
- `prompts`: None
- `batch_sampler`: batch_sampler
- `multi_dataset_batch_sampler`: round_robin
- `router_mapping`: {}
- `learning_rate_mapping`: {}

</details>

### Training Logs
| Epoch | Step | val-hipaa_cosine_ndcg@10 |
|:-----:|:----:|:------------------------:|
| 1.0   | 10   | 0.5441                   |
| 2.0   | 20   | 0.5707                   |
| 3.0   | 30   | 0.5721                   |
| 4.0   | 40   | 0.5357                   |
| 5.0   | 50   | 0.5519                   |
| 6.0   | 60   | 0.5627                   |
| 7.0   | 70   | 0.5631                   |
| 8.0   | 80   | 0.5751                   |


### Training Time
- **Training**: 7.9 minutes

### Framework Versions
- Python: 3.14.6
- Sentence Transformers: 5.5.1
- Transformers: 5.12.1
- PyTorch: 2.12.0+cpu
- Accelerate: 1.14.0
- Datasets: 5.0.0
- Tokenizers: 0.22.2

## Citation

### BibTeX

#### Sentence Transformers
```bibtex
@inproceedings{reimers-2019-sentence-bert,
    title = "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks",
    author = "Reimers, Nils and Gurevych, Iryna",
    booktitle = "Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing",
    month = "11",
    year = "2019",
    publisher = "Association for Computational Linguistics",
    url = "https://arxiv.org/abs/1908.10084",
}
```

#### MultipleNegativesRankingLoss
```bibtex
@misc{oord2019representationlearningcontrastivepredictive,
      title={Representation Learning with Contrastive Predictive Coding},
      author={Aaron van den Oord and Yazhe Li and Oriol Vinyals},
      year={2019},
      eprint={1807.03748},
      archivePrefix={arXiv},
      primaryClass={cs.LG},
      url={https://arxiv.org/abs/1807.03748},
}
```

<!--
## Glossary

*Clearly define terms in order to be accessible across audiences.*
-->

<!--
## Model Card Authors

*Lists the people who create the model card, providing recognition and accountability for the detailed work that goes into its construction.*
-->

<!--
## Model Card Contact

*Provides a way for people who have updates to the Model Card, suggestions, or questions, to contact the Model Card authors.*
-->