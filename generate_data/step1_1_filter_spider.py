"""
Step 1-1: Filter Spider Dataset

Filters the Spider dataset to extract samples containing ambiguous text values
in SQL WHERE conditions. Spider has pre-labeled value tokens in the query, but
this script uses the SQL parser (sqlglot) to extract values and their
associated table/column mappings.

Filtering conditions:
  1. The SQL query contains a WHERE condition.
  2. All condition values appear in the question text.
  3. String values have length > 1.
  4. The associated column name does not match excluded patterns
     (e.g., "_id", "url", "email", "date", "name", etc.).
  5. The column type is TEXT.

Output fields added per sample:
  - db_schema, value_list_parse, value_dict, idx_val_in_question,
    question_no_value, evidence_no_value, distinct_value

Input:
  - Spider dev/train JSON file, table schema JSON, and SQLite databases.

Output:
  - Filtered JSON file (e.g., spider_dev_filtered.json).
"""

import re
import json
import random
from extract_sql.utils import get_sql_sqlglot, convert_db_schema_to_dict
import sqlite3


def get_distinct_value_from_db(database_path, table_name, column_name):
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT DISTINCT {column_name} FROM {table_name}")
    values = cursor.fetchall()
    return values


EXCLUDED_COLUMN_KEYWORDS = [
    "_id", " id", "url", "email", "web", "time", "phone", "date", "address",
    "name", "number", "count", "code", "title", "player", "team",
    "theme", "writer", "publisher", "nominee", "building", "customer_details",
    "eliminated_by", "campus", "director", "prof_office", "class_room",
    "aircraft", "organization_details", "division",
]


if __name__ == '__main__':

    file_name = '/mnt/tampm/data_text2sql/spider_data/dev.json'
    file_table = "/mnt/tampm/data_text2sql/spider_data/tables.json"
    databases_dir = '/mnt/tampm/data_text2sql/spider_data/database'

    all_table_json = json.load(open(file_table))
    tables_dict_json = {table['db_id']: table for table in all_table_json}

    with open(file_name) as inf:
        sql_data = json.load(inf)

    total_sample_have_val = 0
    total_sample = 0
    all_data_filtered = []

    for idx, data_item in enumerate(sql_data):
        total_sample += 1
        db_id = data_item["db_id"]
        sql = data_item["query"]
        db_schema_json = tables_dict_json[db_id]
        db_schema_entity2id_dict, inv_db_schema_entity2id_dict, table2column_dict, column_types_dict = convert_db_schema_to_dict(db_schema_json)
        database_path = f"{databases_dir}/{db_id}/{db_id}.sqlite"

        question = data_item["question"]
        query_toks_no_value = data_item["query_toks_no_value"]
        query_toks = data_item["query_toks"]

        # Extract values using SQL parser (sqlglot)
        sql = data_item["query"]
        parse_sql_result = get_sql_sqlglot(sql)
        value_list_parse_ori = parse_sql_result["value_list"]
        value_dict = parse_sql_result["value_dict"]
        value_list_parse = []
        distinct_value = {}
        print(value_list_parse_ori)

        for value in parse_sql_result["value_list"]:
            if value not in value_dict:
                continue
            column = value_dict[value]["column"]

            # Skip if table name is empty (parsing issue)
            if value_dict[value]["table"] == '':
                continue

            # Skip if column does not exist in the table schema
            if column not in column_types_dict[value_dict[value]["table"]]:
                continue

            # Condition 5: Column type must be TEXT
            print("column_types : ", column_types_dict[value_dict[value]["table"]][column])
            if column_types_dict[value_dict[value]["table"]][column] != "text":
                continue

            # Condition 4: Exclude columns matching keyword patterns
            if any(keyword in column.lower() for keyword in EXCLUDED_COLUMN_KEYWORDS) or column.endswith("Id"):
                continue

            # Condition 3: Value must not be purely numeric
            if not value.replace('.', '').isdigit():
                value_list_parse.append(value)
                print("table : ", value_dict[value]["table"], " | column : ", column)
                value_dis_column = get_distinct_value_from_db(database_path, value_dict[value]["table"], column)

                # Sample at most 10 distinct values to keep output manageable
                if len(value_dis_column) > 20:
                    value_dis_column = random.choices(value_dis_column, k=10)
                distinct_value[value] = value_dis_column

        print(value_list_parse)

        # Find positions of each value in the question text
        idx_val_in_question = []
        len_idx_val = 0
        question_no_value = question.lower()

        for value in value_list_parse:
            # Handle single-character gender values (M/F) with exact matching
            if value in ['M', "m", "F", "f"]:
                idx_val_in_question.append(
                    [m.start() for m in re.finditer("(?='" + value + "')", question)])
            else:
                idx_val_in_question.append(
                    [m.start() for m in re.finditer('(?=' + value.lower() + ')', question.lower())])
            len_idx_val += len(idx_val_in_question[-1])
            question_no_value = question_no_value.replace(value.lower(), " [VAL] ")

        print(idx_val_in_question)
        print(question)
        print(sql)
        print("=====================================")

        # Condition 2: Every value must appear at least once in the question
        if len_idx_val > 0 and [] not in idx_val_in_question:
            total_sample_have_val += 1
            data_item['db_schema'] = table2column_dict
            data_item['value_list_parse'] = value_list_parse
            data_item['value_dict'] = value_dict
            data_item['idx_val_in_question'] = idx_val_in_question
            data_item['question_no_value'] = question_no_value
            data_item['evidence_no_value'] = ''
            data_item['distinct_value'] = distinct_value
            all_data_filtered.append(data_item)

    print("Total sample : ", total_sample)
    print("Total sample have val : ", total_sample_have_val)
    json.dump(all_data_filtered, open("spider_dev_filtered.json", "w"), indent=4, separators=(",", ": "))