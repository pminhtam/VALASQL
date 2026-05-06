"""
Step 2-2: Reformat Ambiguous Value Data

Converts the output from Step 2-1 (value-entity-centric format) back into the
database-centric format matching Step 1-2 output structure. This groups all
synonym/sub-class data under db_id -> table -> column.

Output data format:
{
    db_id: {
        table: {
            column: {
                "distinct_value": [value, ...],
                "question_dict": [
                    {"question": "...", "value": "...", "value_ori": "...",
                     "query": "...", "evidence": "..."}
                ],
                "data_synonym": { value: [synonym_values] },
                "data_sub": { value: [sub_class_values] },
                "type": "location" | "category",
                "is_time": bool
            }
        },
        "db_schema": db_schema
    }
}

Special handling for WikiSQL:
  - All values and synonyms are lowercased.
  - Distinct values are fetched from the WikiSQL JSONL table files.
  - SQL queries are converted from dict format to SQL string using
    a precomputed mapping (wikisql_dict_2slqstr.json).

Input:
  - Synonym JSON files from Step 2-1 (e.g., spider_dev_syn_llm_gpt-4o.json)
  - SQLite databases for Spider/BIRD
  - WikiSQL table JSONL files

Output:
  - Reformatted JSON (e.g., all_dev_gpt-4o_reformat.json)
"""

import os
import re
import json
import random


def convert_db_schema_to_dict(db_schema):
    """Convert raw table schema JSON into {table_name: [column_name, ...]} dict."""
    db_id2schema_dict = {}
    table_dict = {}
    for ti, table_name in enumerate(db_schema['table_names_original']):
        table_dict[ti] = table_name.lower()
    for ci, col in enumerate(db_schema["column_names_original"]):
        tbl_id, col_name = col
        if tbl_id != -1:
            if table_dict[tbl_id] in db_id2schema_dict:
                db_id2schema_dict[table_dict[tbl_id]].append(col_name.lower())
            else:
                db_id2schema_dict[table_dict[tbl_id]] = [col_name.lower()]
    return db_id2schema_dict


def get_all_db_id_from_data(data_json_path):
    """Extract all unique db_id values from a dataset JSON file."""
    with open(data_json_path) as inf:
        data_dict = json.load(inf)
    all_db_id = []
    for item in data_dict:
        db_id = item["db_id"]
        all_db_id.append(db_id)
    return all_db_id


import sqlite3


def get_distinct_value_from_db(database_path, table_name, column_name):
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT DISTINCT `{column_name}` FROM `{table_name}`")
    values = cursor.fetchall()
    return values


def wikisql_get_distinct_value_from_db(db_, column_name):
    """Get distinct values from WikiSQL in-memory table data (lowercased)."""
    values = []
    column_idx = db_["header"].index(column_name)
    for r in db_["rows"]:
        values.append(r[column_idx].lower())
    values = list(set(values))
    values = [[v] for v in values]
    return values


if __name__ == '__main__':
    type_str = "dev"

    model_llm_api = "gpt-4o-mini_gpt-4o_checked"

    # Input files: synonym data from Step 2-1 (including newly generated questions)
    file_name_list = [
        f"newques_{type_str}_syn_llm_{model_llm_api}.json",
        f"spider_{type_str}_syn_llm_{model_llm_api}.json",
        f"bird_{type_str}_syn_llm_{model_llm_api}.json",
        f"wikisql_{type_str}_syn_llm_{model_llm_api}.json",
    ]
    output_path = f"newques_all_{type_str}_{model_llm_api}_reformat.json"

    data_reformat_dict = {}

    # Database directories for Spider and BIRD
    databases_spider_dir = '/mnt/tampm/data_text2sql/spider_data/database'
    databases_bird_dir_dev = '/mnt/tampm/data_text2sql/bird/dev_20240627/dev_databases'
    databases_bird_dir_train = '/mnt/tampm/data_text2sql/bird/train/train_databases'

    # WikiSQL table files
    wikisql_db_file = [
        "/mnt/tampm/data_text2sql/wikisql/data/train.tables.jsonl",
        "/mnt/tampm/data_text2sql/wikisql/data/dev.tables.jsonl",
        "/mnt/tampm/data_text2sql/wikisql/data/test.tables.jsonl",
    ]
    wikisql_db_infor_dict = {}
    for db_file in wikisql_db_file:
        with open(db_file) as inf_db:
            for l in inf_db:
                ep = json.loads(l)
                wikisql_db_infor_dict[ep["id"]] = ep

    # Load table schemas for all datasets
    bird_train_table_json = json.load(open("/mnt/tampm/data_text2sql/bird/dev_20240627/dev_tables.json"))
    bird_dev_table_json = json.load(open("/mnt/tampm/data_text2sql/bird/train/train_tables.json"))
    spider_all_table_json = json.load(open("/mnt/tampm/data_text2sql/spider_data/tables.json"))

    spider_dev_all_db_id = get_all_db_id_from_data("/mnt/tampm/data_text2sql/spider_data/dev.json")
    spider_train_all_db_id = get_all_db_id_from_data("/mnt/tampm/data_text2sql/spider_data/train_spider.json")
    bird_dev_all_db_id = get_all_db_id_from_data("/mnt/tampm/data_text2sql/bird/dev_20240627/dev.json")
    bird_train_all_db_id = get_all_db_id_from_data("/mnt/tampm/data_text2sql/bird/train/train.json")

    dev_all_db_id = list(set(spider_dev_all_db_id + bird_dev_all_db_id))
    train_all_db_id = list(set(spider_train_all_db_id + bird_train_all_db_id))

    tables_dict_json = {table['db_id']: table for table in bird_train_table_json + bird_dev_table_json + spider_all_table_json}

    # Build schema dict and db_id mapping (for resolving table-name vs db_id confusion)
    db_id2schema_dict = {}
    db_id_fake2real_dict = {}
    for db_id in tables_dict_json:
        if (db_id in dev_all_db_id and type_str == "dev") or (db_id in train_all_db_id and type_str == "train"):
            db_id2schema_dict[db_id] = convert_db_schema_to_dict(tables_dict_json[db_id])
            db_id_fake2real_dict[db_id] = db_id
            for table_name in db_id2schema_dict[db_id]:
                db_id_fake2real_dict[table_name] = db_id

    # Add WikiSQL schemas
    wikisql_dict_2slqstr_path = 'wikisql_dict_2slqstr.json'
    wikisql_dict_dbid2schema_path = 'wikisql_dict_dbid2schema.json'
    wikisql_dict_2slqstr = json.load(open(wikisql_dict_2slqstr_path))
    wikisql_dict_dbid2schema = json.load(open(wikisql_dict_dbid2schema_path))

    for db_id in wikisql_dict_dbid2schema:
        db_id2schema_dict[db_id] = wikisql_dict_dbid2schema[db_id]
        db_id_fake2real_dict[db_id] = db_id

    # Process each input file
    for file_name in file_name_list:
        with open(file_name) as inf:
            data_dict = json.load(inf)

        for idx, value in enumerate(data_dict):
            synonym = data_dict[value]["synonym"]
            sub = data_dict[value]["sub"]
            distinct_value = []
            question = []
            value_ori_from_db = value

            for db_id_fake in data_dict[value_ori_from_db]["database"]:
                db_id = db_id_fake

                if db_id not in data_reformat_dict:
                    data_reformat_dict[db_id] = {}
                    # Add db_schema for Spider/BIRD databases
                    if 'db_schema' not in data_reformat_dict[db_id]:
                        if db_id in db_id2schema_dict:
                            data_reformat_dict[db_id]["db_schema"] = db_id2schema_dict[db_id]

                for table in data_dict[value_ori_from_db]["database"][db_id_fake]:
                    if table not in data_reformat_dict[db_id]:
                        data_reformat_dict[db_id][table] = {}
                    for column in data_dict[value_ori_from_db]["database"][db_id_fake][table]:
                        if column not in data_reformat_dict[db_id][table]:
                            data_reformat_dict[db_id][table][column] = {}
                            data_reformat_dict[db_id][table][column]["data_synonym"] = {}
                            data_reformat_dict[db_id][table][column]["data_sub"] = {}
                            data_reformat_dict[db_id][table][column]["question_dict"] = []

                            # Fetch full distinct values from the database
                            database_path = ""
                            if os.path.exists(os.path.join(databases_bird_dir_dev, db_id)):
                                database_path = f"{databases_bird_dir_dev}/{db_id}/{db_id}.sqlite"
                            elif os.path.exists(os.path.join(databases_bird_dir_train, db_id)):
                                database_path = f"{databases_bird_dir_train}/{db_id}/{db_id}.sqlite"
                            elif os.path.exists(os.path.join(databases_spider_dir, db_id)):
                                database_path = f"{databases_spider_dir}/{db_id}/{db_id}.sqlite"

                            if database_path != "":
                                distinct_value = get_distinct_value_from_db(database_path, table, column)
                                data_reformat_dict[db_id][table][column]["distinct_value"] = [v[0] for v in distinct_value]
                            else:
                                # WikiSQL: lowercase all values
                                distinct_value = wikisql_get_distinct_value_from_db(wikisql_db_infor_dict[table], column)
                                data_reformat_dict[db_id][table][column]["distinct_value"] = [v[0] for v in distinct_value]
                                value = value.lower()
                                synonym = [s.lower() for s in synonym]
                                sub = [s.lower() for s in sub]

                            data_reformat_dict[db_id][table][column]["type"] = data_dict[value_ori_from_db]["type"]
                            data_reformat_dict[db_id][table][column]["is_time"] = data_dict[value_ori_from_db]["is_time"]
                        else:
                            # Column already exists; check if WikiSQL needs lowercasing
                            database_path = ""
                            if os.path.exists(os.path.join(databases_bird_dir_dev, db_id)):
                                database_path = f"{databases_bird_dir_dev}/{db_id}/{db_id}.sqlite"
                            elif os.path.exists(os.path.join(databases_bird_dir_train, db_id)):
                                database_path = f"{databases_bird_dir_train}/{db_id}/{db_id}.sqlite"
                            elif os.path.exists(os.path.join(databases_spider_dir, db_id)):
                                database_path = f"{databases_spider_dir}/{db_id}/{db_id}.sqlite"
                            if database_path == "":
                                value = value.lower()
                                synonym = [s.lower() for s in synonym]
                                sub = [s.lower() for s in sub]

                        # Add question entries and synonym/sub data
                        for que in data_dict[value_ori_from_db]["database"][db_id_fake][table][column]["question"]:
                            if value == "F (Virtual)" and db_id == "california_schools" and table == "schools" and column == "virtual":
                                value = "F"

                            if db_id in wikisql_dict_dbid2schema:
                                if db_id + que["question"] in wikisql_dict_2slqstr:
                                    query = wikisql_dict_2slqstr[db_id + que["question"]]
                                else:
                                    query = que["query"]
                            else:
                                query = que["query"]

                            evidence = que["evidence"]
                            data_reformat_dict[db_id][table][column]["question_dict"].append({
                                "question": que["question"],
                                "value": value,
                                "value_ori": value,
                                "query": query,
                                "evidence": evidence,
                            })

                            if value not in data_reformat_dict[db_id][table][column]["data_synonym"]:
                                data_reformat_dict[db_id][table][column]["data_synonym"][value] = list(set(synonym))
                                data_reformat_dict[db_id][table][column]["data_sub"][value] = list(set(sub))
                            else:
                                data_reformat_dict[db_id][table][column]["data_synonym"][value] = list(set(
                                    data_reformat_dict[db_id][table][column]["data_synonym"][value] + synonym))
                                data_reformat_dict[db_id][table][column]["data_sub"][value] = list(set(
                                    data_reformat_dict[db_id][table][column]["data_sub"][value] + sub))

    json.dump(data_reformat_dict, open(output_path, 'w'), indent=2, separators=(",", ": "))
