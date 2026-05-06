# Generate Data Pipeline

This directory contains the pipeline for generating **ambiguous value data** for the VALASQL project. The pipeline extracts value entities from Text-to-SQL datasets (Spider, BIRD, WikiSQL), generates synonym and sub-class alternatives using an LLM, and produces modified databases and SQL queries for evaluation.

## Overview

The pipeline creates training/evaluation data where database values are replaced with ambiguous synonyms (e.g., "europe" → "european continent", "dog" → "canine"). This tests whether Text-to-SQL models can handle value ambiguity — when the user's phrasing differs from the exact value stored in the database.

```
Step 1: Filter & Reformat  →  Step 2: Synthesize & Merge  →  Step 3: Update DB & SQL
```

## Prerequisites

- Python 3.8+
- Required packages: `openai`, `sqlglot`, `tenacity`
- Datasets: Spider, BIRD, WikiSQL (with SQLite databases)
- OpenAI API key (for Step 2-1)
- Labeled CSV files for column type annotation (location/category)

Install dependencies:

```bash
pip install openai sqlglot tenacity
```

Set your API key:

```bash
export OPENAI_API_KEY="your-api-key"
```

## Pipeline Steps

### Step 1-1: Filter Datasets

Filters each dataset to extract samples where SQL WHERE conditions contain text values that also appear in the question. Removes numeric values, excluded column types (IDs, URLs, dates, etc.), and non-TEXT columns.

Run one script per dataset (order does not matter):

```bash
python step1_1_filter_spider.py     # → spider_dev_filtered.json
python step1_1_filter_bird.py       # → bird_new_train_filtered.json
python step1_1_filter_wikiSQL.py    # → wikisql_train_filtered.json
```

> **Note:** Edit the `file_name`, `file_table`, and `databases_dir` variables at the top of each script to point to your local dataset paths. Run each script once for dev and once for train splits as needed.

**Output:** `*_filtered.json` — flat list of filtered samples with extracted value entities.

---

### Step 1-2: Reformat Filtered Data

Groups the filtered data by `db_id → table → column`, consolidating all questions that reference the same column. Initializes empty `data_synonym` placeholders for Step 2-1.

```bash
python step1_2_reformat_data.py
```

> **Note:** Edit the `file_path_process` list to include only the filtered files you generated in Step 1-1.

**Output:** `*_filtered_reformat.json` — hierarchical JSON grouped by database/table/column.

---

### Step 2-1: Synthesize Ambiguous Values via LLM

Uses GPT-4o (or another OpenAI-compatible LLM) to generate synonym and sub-class values for each value entity. Requires manually labeled CSV files that classify each column as `location` or `category`.

The labeled CSV files should be placed in the `labeled_column/` directory with the naming convention `{dataset}{split}.csv` (e.g., `spiderdev.csv`, `birdtrain.csv`).

```bash
python step2_1_amb_value_synthesis_llm.py
```

> **Note:** 
> - Place labeled CSV files in the working directory (e.g., `spiderdev.csv`).
> - Set `model_llm_api` to your desired model (default: `gpt-4o`).
> - Edit `file_path_process` to match your input/output file names.
> - This step makes many API calls and may take significant time and cost.

**Output:** `*_syn_llm_{model}.json` — synonym/sub-class data grouped by value entity.

---

### Step 2-2: Reformat Ambiguous Value Data

Converts the value-entity-centric output from Step 2-1 back into the database-centric format (matching Step 1-2 structure). Fetches full distinct values from SQLite databases and handles WikiSQL lowercasing.

```bash
python step2_2_reformat_amb_value_data.py
```

> **Note:** 
> - Set `type_str` to `"dev"` or `"train"`.
> - Update database directory paths and `file_name_list` as needed.
> - Requires `wikisql_dict_2slqstr.json` and `wikisql_dict_dbid2schema.json` for WikiSQL SQL conversion.

**Output:** `*_reformat.json` — database-centric format with synonyms and sub-class values attached.

---

### Step 2-3: Combine Ambiguous Values with Questions

Merges question entries that share the same question text but reference different value entities (from different columns/tables) into a single `question_dict_merge` structure.

```bash
python step2_3_combine_amb_value_with_question.py
```

> **Note:** Set `type_str` and `model_llm_api` to match your previous outputs.

**Output:** `*_reformat_question_merge.json` — unified question structure with all value entities per question.

---

### Step 3-1: Update Database with Ambiguous Values

Copies the original SQLite databases and replaces values with their synonyms/sub-class alternatives. Uses multiprocessing for speed. Records which values were replaced for Step 3-2.

```bash
python step3_1_update_amb_value_into_database.py
```

> **Note:**
> - Set `type_str`, `model_llm_api`, and database directory paths.
> - Set `output_db_directory_path` for the modified databases.
> - The script uses a fixed random seed (271) for reproducibility.

**Output:**
- `database_synonym_newques_train/` — directory with modified SQLite databases
- `update2sqlite_{split}_{model}.json` — mapping of original → replaced values

---

### Step 3-2: Update SQL Queries

Updates the ground-truth SQL queries to account for the database modifications. Replaces `column = 'value'` with `column IN ('value', 'synonym1', ...)` using the replacement mapping from Step 3-1.

```bash
python step3_2_update_sql_query_with_amb_value.py
```

> **Note:** Set `type_str` and `model_llm_api` to match your previous outputs.

**Output:** `*_reformat_question_merge_newsql.json` — final data with `query_amb` field containing updated SQL queries.

---

## Full Pipeline (Quick Reference)

```bash
# Step 1: Filter and reformat
python step1_1_filter_spider.py
python step1_1_filter_bird.py
python step1_1_filter_wikiSQL.py
python step1_2_reformat_data.py

# Step 2: Generate synonyms and merge
python step2_1_amb_value_synthesis_llm.py
python step2_2_reformat_amb_value_data.py
python step2_3_combine_amb_value_with_question.py

# Step 3: Update databases and SQL
python step3_1_update_amb_value_into_database.py
python step3_2_update_sql_query_with_amb_value.py
```

## Data Flow Diagram

```
Spider/BIRD/WikiSQL datasets
        │
        ▼
  ┌─────────────┐
  │  Step 1-1   │  Filter samples with text value entities
  │  (per dataset)│
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Step 1-2   │  Reformat: group by db → table → column
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Step 2-1   │  LLM generates synonyms & sub-classes
  │  (API calls)│
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Step 2-2   │  Reformat back to db-centric structure
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Step 2-3   │  Merge multi-entity questions
  └──────┬──────┘
         ▼
  ┌──────┴──────┐
  │  Step 3-1   │  Update SQLite databases with synonyms
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Step 3-2   │  Update SQL: = → IN (synonym list)
  └──────┬──────┘
         ▼
  Final evaluation data + modified databases
```
