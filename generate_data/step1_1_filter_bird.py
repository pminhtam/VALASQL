"""
Step 1-1: Filter BIRD Dataset

Filters the BIRD dataset to extract samples containing ambiguous text values
in SQL WHERE conditions. BIRD does not have pre-labeled values like Spider,
so values are extracted from the question text and SQL query.

Filtering conditions:
  1. The SQL query contains a WHERE condition.
  2. All condition values appear in the question text.
  3. String values have length > 1.
  4. The associated column name does not match excluded patterns
     (e.g., "_id", "url", "email", "date", "name", etc.).
  5. The column type is TEXT (or CHAR variant).
  6. The maximum length of distinct values in the column is <= 100
     (to exclude free-text/paragraph columns).

Output fields added per sample:
  - db_schema, value_list_parse, value_dict, idx_val_in_question,
    question_no_value, evidence_no_value, distinct_value

Input:
  - BIRD train/dev JSON file, table schema JSON, and SQLite databases.

Output:
  - Filtered JSON file (e.g., bird_new_train_filtered.json).
"""

import re
import json
import random
from extract_sql.utils import get_sql_sqlglot, convert_db_schema_to_dict
import sqlite3


def get_distinct_value_from_db(database_path, table_name, column_name):
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT DISTINCT `{column_name}` FROM `{table_name}`")
    values = cursor.fetchall()
    return values


EXCLUDED_COLUMN_KEYWORDS = [
    "_id", " id", "url", "email", "web", "time", "phone", "date", "address",
    "name", "number", "code", "zip", "charternum", "title", "text",
    "link_to_major", "element", "id", "first", "last", "reviews", "summary",
    "path", "fullcomment", "donation_message",
]


if __name__ == '__main__':

    file_name = '/mnt/tampm/data_text2sql/bird/train/train.json'
    file_table = "/mnt/tampm/data_text2sql/bird/train/train_tables.json"
    databases_dir = '/mnt/tampm/data_text2sql/bird/train/train_databases'

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
        sql = data_item["SQL"]
        db_schema_json = tables_dict_json[db_id]
        db_schema_entity2id_dict, inv_db_schema_entity2id_dict, table2column_dict, column_types_dict = convert_db_schema_to_dict(db_schema_json)
        database_path = f"{databases_dir}/{db_id}/{db_id}.sqlite"
        question = data_item["question"] + data_item["evidence"]

        parse_sql_result = get_sql_sqlglot(sql)
        value_list_parse_ori = parse_sql_result["value_list"]
        value_dict = parse_sql_result["value_dict"]
        value_list_parse = []
        distinct_value = {}

        for value in parse_sql_result["value_list"]:
            if value not in value_dict:
                continue
            column = value_dict[value]["column"]

            # Skip if parsed table name does not exist in schema
            if value_dict[value]["table"] not in table2column_dict:
                continue

            # Skip if column does not exist in the table
            if column not in column_types_dict[value_dict[value]["table"]]:
                continue

            # Condition 5: Column type must be TEXT or CHAR
            col_type = column_types_dict[value_dict[value]["table"]][column]
            if col_type != "text" and ("char" not in col_type):
                continue

            # Condition 4: Exclude columns matching keyword patterns
            if any(keyword in column.lower() for keyword in EXCLUDED_COLUMN_KEYWORDS) or column.endswith("Id"):
                continue

            # Condition 3: Value must not be purely numeric
            if not value.replace('.', '').isdigit():
                print(database_path, value_dict[value]["table"], column)
                value_dis_column = get_distinct_value_from_db(database_path, value_dict[value]["table"], column)

                try:
                    max_len_item = max([len(str(value_item[0])) for value_item in value_dis_column])
                except:
                    max_len_item = 0

                # Skip columns where values are too long (likely free-text)
                if max_len_item > 100:
                    continue

                # Sample at most 10 distinct values to keep output manageable
                if len(value_dis_column) > 20:
                    print(database_path, value_dict[value]["table"], column)
                    value_dis_column = random.choices(value_dis_column, k=10)

                value_list_parse.append(value)
                distinct_value[value] = value_dis_column

        # Find positions of each value in the question text
        idx_val_in_question = []
        len_idx_val = 0
        question_no_value = data_item["question"].lower()
        evidence_no_value = data_item["evidence"].lower()

        for value in value_list_parse:
            idx_val_in_question.append([m.start() for m in re.finditer(re.escape(value.lower()), question.lower())])
            len_idx_val += len(idx_val_in_question[-1])
            question_no_value = question_no_value.replace(value.lower(), " [VAL] ")
            evidence_no_value = evidence_no_value.replace(value.lower(), " [VAL] ")

        # Condition 2: Every value must appear at least once in the question
        if len_idx_val > 0 and [] not in idx_val_in_question:
            total_sample_have_val += 1

            data_item['db_schema'] = table2column_dict
            data_item['value_list_parse'] = value_list_parse
            data_item['value_dict'] = value_dict
            data_item['idx_val_in_question'] = idx_val_in_question
            data_item['question_no_value'] = question_no_value
            data_item['evidence_no_value'] = evidence_no_value
            data_item['distinct_value'] = distinct_value
            all_data_filtered.append(data_item)

    print("Total sample : ", total_sample)
    print("Total sample have val : ", total_sample_have_val)
    json.dump(all_data_filtered, open("bird_new_train_filtered.json", "w"), indent=4)
