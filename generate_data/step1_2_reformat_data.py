"""
Step 1-2: Reformat Filtered Data

Reads the filtered output from Step 1-1 (spider/bird/wikisql *_filtered.json)
and reorganizes the data by grouping value entities under their
database -> table -> column hierarchy.

Output data format:
{
    db_id: {
        table: {
            column: {
                "distinct_value": [value, ...],
                "question_dict": [
                    {"question": "...", "query": "...", "value": "...", "evidence": "..."}
                ],
                "data_synonym": {
                    value: []   // placeholder for synonym generation in Step 2-1
                }
            }
        },
        "db_schema": db_schema
    }
}

Questions referencing the same column are grouped together.
The data_synonym field is initialized with empty lists as placeholders;
actual synonym generation is handled by step2_1_amb_value_synthesis_llm.py.

Input:
  - Filtered JSON files from Step 1-1.

Output:
  - Reformatted JSON files (e.g., spider_dev_filtered_reformat.json).
"""

import os
import re
import json
import time

from openai import OpenAI


def main_func(file_name, output_path):
    with open(file_name) as inf:
        sql_data = json.load(inf)

    data_dict = {}
    for idx, data_item in enumerate(sql_data):
        if "db_id" in data_item:
            db_id = data_item["db_id"]          # BIRD, Spider
        elif "table_id" in data_item:
            db_id = data_item["table_id"]       # WikiSQL
        else:
            continue

        value_dict = data_item["value_dict"]
        distinct_value = data_item["distinct_value"]
        db_schema = data_item["db_schema"]
        question = data_item["question"]
        evidence = data_item.get("evidence", "")

        if "query" in data_item:
            query = data_item["query"]          # Spider
        elif "SQL" in data_item:
            query = data_item["SQL"]            # BIRD
        elif "sql" in data_item:
            query = data_item["sql"]            # WikiSQL
        else:
            continue

        if db_id not in data_dict:
            data_dict[db_id] = {}
            data_dict[db_id]["db_schema"] = db_schema

        for value in value_dict:
            table = value_dict[value]["table"]
            column = value_dict[value]["column"]

            if table not in data_dict[db_id]:
                data_dict[db_id][table] = {}
            if column not in data_dict[db_id][table]:
                data_dict[db_id][table][column] = {}
            if "data_synonym" not in data_dict[db_id][table][column]:
                data_dict[db_id][table][column]["data_synonym"] = {}

            # Store distinct values for this column
            if value not in distinct_value:
                data_dict[db_id][table][column]["distinct_value"] = []
            else:
                distinct_value_list = distinct_value[value]
                data_dict[db_id][table][column]["distinct_value"] = [i[0] for i in distinct_value_list]

            if "question_dict" not in data_dict[db_id][table][column]:
                data_dict[db_id][table][column]["question_dict"] = []

            question_item = {
                'question': question,
                'query': query,
                'value': value,
                'evidence': evidence,
            }
            data_dict[db_id][table][column]["question_dict"].append(question_item)

            # Initialize synonym placeholder (actual generation in Step 2-1)
            if value not in data_dict[db_id][table][column]["data_synonym"]:
                data_dict[db_id][table][column]["data_synonym"][value] = []

    json.dump(data_dict, open(output_path, 'w'), indent=2, separators=(",", ": "))


if __name__ == '__main__':

    file_path_process = [
        ('spider_dev_filtered.json', "spider_dev_filtered_reformat.json"),
        ('spider_train_filtered.json', "spider_train_filtered_reformat.json"),
        ('wikisql_dev_filtered.json', "wikisql_dev_filtered_reformat.json"),
        ('wikisql_test_filtered.json', "wikisql_test_filtered_reformat.json"),
        ('wikisql_train_filtered.json', "wikisql_train_filtered_reformat.json"),
        ('bird_new_dev_filtered.json', "bird_new_dev_filtered_reformat.json"),
        ('bird_new_train_filtered.json', "bird_new_train_filtered_reformat.json"),
    ]

    for file_name, output_path in file_path_process:
        main_func(file_name, output_path)
