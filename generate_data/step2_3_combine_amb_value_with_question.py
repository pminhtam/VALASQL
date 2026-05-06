"""
Step 2-3: Combine Ambiguous Values with Questions

Merges questions that contain multiple value entities from different
table/column pairs into a single unified structure per question.

In the previous format (Step 2-2), each question_dict entry only tracks one
value entity from one column. However, a single question may reference multiple
value entities across different tables and columns. This script consolidates
all value entities for the same question under a "question_dict_merge" key.

Output data format:
{
    db_id: {
        "question_dict_merge": {
            question_text: [
                {
                    "value": value,
                    "value_ori": value_ori,
                    "query": query,
                    "column": column,
                    "table": table,
                    "value_dict": value_dict,
                    "evidence": evidence,
                    "value_sql": value,
                    "question_no_value": question_with_[VAL]_markers
                }
            ]
        },
        table: {
            column: {
                "distinct_value": [...],
                "data_synonym": { value: [synonyms] },
                "data_sub": { value: [sub_values] }
            }
        },
        "db_schema": db_schema
    }
}

Key fields:
  - "value": the value entity as it appears in the question
  - "value_ori": original value from the source dataset (differs only for
    synthetically generated questions)
  - "value_sql": the value as it appears in the SQL query

Input:
  - Reformatted JSON from Step 2-2

Output:
  - Merged question JSON (e.g., all_dev_gpt-4o_reformat_question_merge.json)
"""

import os
import re
import json
import random
from utils import get_sql_sqlglot

if __name__ == '__main__':
    type_str = "dev"
    model_llm_api = "gpt-4o"

    file_name = f"all_{type_str}_{model_llm_api}_reformat.json"

    with open(file_name) as inf:
        data_dict = json.load(inf)

    output_path = f"all_{type_str}_{model_llm_api}_reformat_question_merge.json"
    data_reformat_dict = data_dict.copy()
    num_question = 0

    # First pass: merge questions across all table/column pairs
    for db_id in data_reformat_dict:
        if "question_dict_merge" not in data_reformat_dict[db_id]:
            data_reformat_dict[db_id]["question_dict_merge"] = {}
        if "db_schema" not in data_reformat_dict[db_id]:
            continue

        for table in data_reformat_dict[db_id]:
            if table == "db_schema":
                continue
            for column in data_reformat_dict[db_id][table]:
                if "question_dict" not in data_reformat_dict[db_id][table][column]:
                    continue
                for question in data_reformat_dict[db_id][table][column]["question_dict"]:
                    question_text = question["question"]

                    # Only process questions with a query (skip synthetic questions without SQL)
                    if "query" not in question:
                        continue

                    query = question["query"]
                    evidence = question["evidence"]
                    parse_sql_result = get_sql_sqlglot(query)
                    value_dict = parse_sql_result["value_dict"]

                    question_entry = {
                        "value": question["value"],
                        "value_ori": question["value_ori"],
                        "query": query,
                        "column": column,
                        "table": table,
                        "value_dict": value_dict,
                        "evidence": evidence,
                    }

                    if question_text not in data_reformat_dict[db_id]["question_dict_merge"]:
                        num_question += 1
                        data_reformat_dict[db_id]["question_dict_merge"][question_text] = [question_entry]
                    else:
                        data_reformat_dict[db_id]["question_dict_merge"][question_text].append(question_entry)

        print(db_id, len(data_reformat_dict[db_id]["question_dict_merge"]))

    # Second pass: remove per-column question_dict, add value_sql and question_no_value
    for db_id in data_reformat_dict:
        print(db_id, len(data_reformat_dict[db_id]["question_dict_merge"]))
        if "db_schema" not in data_reformat_dict[db_id]:
            continue

        for table in data_reformat_dict[db_id]:
            if table == "db_schema":
                continue
            for column in data_reformat_dict[db_id][table]:
                if "question_dict" not in data_dict[db_id][table][column]:
                    continue
                del data_reformat_dict[db_id][table][column]["question_dict"]

        # Replace value occurrences in question text with [VAL:value_sql] markers
        for question_text in data_reformat_dict[db_id]["question_dict_merge"]:
            question_no_value = question_text
            for question_item in data_reformat_dict[db_id]["question_dict_merge"][question_text]:
                value = question_item["value"]
                question_item["value_sql"] = question_item["value"]
                value_sql = question_item["value_sql"]

                # Use word-boundary matching for single words, plain matching for multi-word values
                if " " in value:
                    re_str = re.escape(value)
                else:
                    re_str = r'\b' + re.escape(value) + r'\b'
                question_no_value = re.sub(re_str, f'[VAL:{value_sql}]', question_no_value,
                                           flags=re.IGNORECASE)

            for question_item in data_reformat_dict[db_id]["question_dict_merge"][question_text]:
                question_item["question_no_value"] = question_no_value

    print(f"Number of question : {num_question}")
    json.dump(data_reformat_dict, open(output_path, 'w'), indent=2, separators=(",", ": "))
