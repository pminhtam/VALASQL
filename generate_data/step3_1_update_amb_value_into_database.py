"""
Step 3-1: Update Ambiguous Values into Database

Modifies the SQLite database files by replacing original values with their
synonym and sub-class alternatives. This creates the "ambiguous" version of
each database for evaluation.

For each value entity in the reformatted data:
  1. Finds all rows in the database matching the original value.
  2. Selects up to k synonym/sub-class values based on the number of matching
     rows (k scales with row count: 1-5 synonyms).
  3. Randomly replaces a percentage (default 85%) of matching rows with
     synonym values.
  4. Records which values were replaced in a replacement dictionary for use
     in Step 3-2 (SQL query update).

The replacement is performed using SQL UPDATE statements with full row
matching (all non-NULL columns in WHERE clause) to ensure precise targeting.

Uses multiprocessing to parallelize updates across different databases.

Input:
  - Reformatted JSON from Step 2-2 (e.g., newques_all_train_..._reformat.json)
  - Original SQLite database files for Spider, BIRD, and WikiSQL

Output:
  - Modified SQLite databases in output directory (database_synonym_newques_train/)
  - Replacement value mapping JSON (e.g., update2sqlite_train_..._checked.json)
"""

import os
import re
import json
import time
import shutil
import sqlite3
import random
import multiprocessing
from collections import defaultdict


def sqlite_db(path):
    """Open a SQLite database connection with error-tolerant text decoding."""
    if not os.path.isfile(path):
        raise '%s is not a file' % path
    conn = sqlite3.connect(path)
    conn.text_factory = lambda b: b.decode(errors='ignore')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT 1 from sqlite_master where type = "table"')
    try:
        data = cur.fetchone()
    except sqlite3.DatabaseError:
        msg = '%s can\'t be read as SQLite DB' % path
        raise msg
    return conn


def func_update_db(db_path, db_id_list, reformat_data):
    """
    Update a single SQLite database file with ambiguous synonym values.

    Args:
        db_path: Path to the source SQLite database.
        db_id_list: List of db_ids that reside in this database file.
        reformat_data: The full reformatted data dictionary.

    Returns:
        Tuple of (replace_value_dict, k_synonym_stat_dict).
    """
    random.seed(271)
    print("func_update_db : ", db_path)
    k_synonym_stat_dict = {}
    replace_value_dict = {}

    for db_id in db_id_list:
        if db_id in db_path:
            db_path_dst = os.path.join(output_db_directory_path, db_id, db_id + ".sqlite")
            if not os.path.exists(os.path.join(output_db_directory_path, db_id)):
                os.makedirs(os.path.join(output_db_directory_path, db_id))
        else:
            # WikiSQL uses a single shared SQLite file
            db_path_dst = os.path.join(output_db_directory_path, "wikisql.sqlite")

        # Only copy the database file if it doesn't already exist
        if not os.path.exists(db_path_dst):
            shutil.copyfile(db_path, db_path_dst)

        db_conn = sqlite_db(db_path_dst)
        db_cursor = db_conn.cursor()

        for table in reformat_data[db_id]:
            if table == "db_schema":
                continue

            # Get table column info for building WHERE clauses
            db_cursor.execute(f"PRAGMA table_info(`{table}`)")
            primary_key_columns = []
            all_columns = []
            for column in db_cursor.fetchall():
                if column[5] == 1:
                    primary_key_columns.append(column[1])
                all_columns.append(column[1])

            for column in reformat_data[db_id][table]:
                if db_id not in replace_value_dict:
                    replace_value_dict[db_id] = {}
                if table not in replace_value_dict[db_id]:
                    replace_value_dict[db_id][table] = {}
                if column not in replace_value_dict[db_id][table]:
                    replace_value_dict[db_id][table][column] = {}

                for value in reformat_data[db_id][table][column]["data_synonym"]:
                    value_old = value

                    # Handle special cases for specific databases
                    if db_id == "flight_2" and table == "flights" and (
                            column == "destairport" or column == "sourceairport"):
                        value = " " + value
                    if db_id == "flight_2" and table == "airports" and column == "city":
                        value = value + " "
                    if db_id == "california_schools" and table == "schools" and column == "virtual" and value == "F (Virtual)":
                        value = "F"

                    # Select rows matching this value (case-insensitive)
                    try:
                        db_cursor.execute(f"SELECT *  FROM `{table}` WHERE `{column}` = '{value}' COLLATE NOCASE;")
                    except:
                        try:
                            db_cursor.execute(f'SELECT *  FROM `{table}` WHERE `{column}` = "{value}" COLLATE NOCASE;')
                        except Exception as e:
                            print("Error: ", e, "sql: ", f"SELECT *  FROM `{table}` WHERE `{column}` = '{value}' COLLATE NOCASE;")
                            continue

                    rows_to_update = db_cursor.fetchall()
                    num_val_update = len(rows_to_update)

                    # For few rows, use only synonyms; for many rows, include sub-class values
                    if num_val_update < 3:
                        data_synonym_val = reformat_data[db_id][table][column]["data_synonym"][value_old]
                    else:
                        data_synonym_val = (reformat_data[db_id][table][column]["data_synonym"][value_old] +
                                            reformat_data[db_id][table][column]["data_sub"][value_old])
                    data_synonym_val = list(set(data_synonym_val) - set([value]))

                    if len(data_synonym_val) <= 1:
                        continue

                    # Determine max number of synonym values based on row count
                    if num_val_update < 2:
                        k_synonym = min(len(data_synonym_val), 1)
                    elif num_val_update < 3:
                        k_synonym = min(len(data_synonym_val), 2)
                    elif num_val_update < 6:
                        k_synonym = min(len(data_synonym_val), 3)
                    elif num_val_update < 20:
                        k_synonym = min(len(data_synonym_val), 4)
                    else:
                        k_synonym = min(len(data_synonym_val), 5)

                    if k_synonym not in k_synonym_stat_dict:
                        k_synonym_stat_dict[k_synonym] = 0
                    k_synonym_stat_dict[k_synonym] += 1

                    data_synonym_val = random.choices(data_synonym_val, k=k_synonym)
                    percentage_replace = 0.85
                    threshold_count = 100

                    if num_val_update > threshold_count:
                        percentage_replace = 1.0
                    elif num_val_update == 1:
                        percentage_replace = 1.0

                    if value not in replace_value_dict[db_id][table][column]:
                        replace_value_dict[db_id][table][column][value] = []
                        replace_value_dict[db_id][table][column]["k_" + value] = k_synonym

                    for idx_row, row in enumerate(rows_to_update):
                        if idx_row > threshold_count:
                            break

                        is_replace = random.random() >= 1.0 - percentage_replace

                        if is_replace:
                            random_value = random.choice(data_synonym_val)
                            while random_value == value and len(data_synonym_val) > 1:
                                random_value = random.choice(data_synonym_val)

                            # Build WHERE clause excluding NULL columns
                            columns_in_where = []
                            row_values_in_where = []
                            for idx_column_row_item in range(len(row)):
                                if row[idx_column_row_item] is not None:
                                    columns_in_where.append(all_columns[idx_column_row_item])
                                    row_values_in_where.append(row[idx_column_row_item])
                            where_clause = " AND ".join([f"`{col}` = ?" for col in columns_in_where])

                            try:
                                db_cursor.execute(f"UPDATE `{table}` SET `{column}` = ? WHERE {where_clause}",
                                                  (random_value, *row_values_in_where))
                                db_conn.commit()

                                if random_value not in replace_value_dict[db_id][table][column][value]:
                                    replace_value_dict[db_id][table][column][value].append(random_value)
                            except Exception as e:
                                print("Error: ", e)
                                continue
                        else:
                            # Row not replaced; record original value as still present
                            if value not in replace_value_dict[db_id][table][column][value]:
                                replace_value_dict[db_id][table][column][value].append(value)

                        # If replacing all rows, also record original value (for remaining rows beyond threshold)
                        if percentage_replace == 1.0:
                            if value not in replace_value_dict[db_id][table][column][value]:
                                replace_value_dict[db_id][table][column][value].append(value)

        db_conn.commit()
        db_conn.close()

    return replace_value_dict, k_synonym_stat_dict


if __name__ == '__main__':
    type_str = "train"
    model_llm_api = "gpt-4o-mini_gpt-4o_checked"

    databases_spider_dir = '/mnt/tampm/data_text2sql/spider_data/database'
    databases_bird_dir_dev = '/mnt/tampm/data_text2sql/bird/dev_20240627/dev_databases'
    databases_bird_dir_train = '/mnt/tampm/data_text2sql/bird/train/train_databases'

    output_db_directory_path = 'database_synonym_newques_train'
    if not os.path.exists(output_db_directory_path):
        os.makedirs(output_db_directory_path)

    file_name = f"newques_all_{type_str}_{model_llm_api}_reformat.json"
    output_replace_value_path = f"update2sqlite_{type_str}_{model_llm_api}.json"

    with open(file_name) as inf:
        reformat_data = json.load(inf)

    with multiprocessing.Manager() as manager:
        # Group databases by their file path for parallel processing
        args_dict = {}
        for db_id in reformat_data:
            if os.path.exists(os.path.join(databases_spider_dir, db_id)):
                db_path = os.path.join(databases_spider_dir, db_id, db_id + ".sqlite")
            elif os.path.exists(os.path.join(databases_bird_dir_dev, db_id)):
                db_path = os.path.join(databases_bird_dir_dev, db_id, db_id + ".sqlite")
            elif os.path.exists(os.path.join(databases_bird_dir_train, db_id)):
                db_path = os.path.join(databases_bird_dir_train, db_id, db_id + ".sqlite")
            else:
                # WikiSQL: single merged SQLite file
                db_path = "/mnt/tampm/data_text2sql/wikisql/data/all.sqlite"

            if db_path not in args_dict:
                args_dict[db_path] = [db_id]
            else:
                args_dict[db_path].append(db_id)

        args_list = [(db_path, db_ids, reformat_data) for db_path, db_ids in args_dict.items()]

        with multiprocessing.Pool(processes=multiprocessing.cpu_count()) as pool:
            results = pool.starmap(func_update_db, args_list)

    print("done")

    # Merge results from all processes
    final_replace_value_dict = {}
    final_k_synonym_stat_dict = defaultdict(int)
    for replace_value_dict, k_synonym_stat_dict in results:
        final_replace_value_dict.update(replace_value_dict)
        for key, value in k_synonym_stat_dict.items():
            final_k_synonym_stat_dict[key] += value

    print(final_k_synonym_stat_dict)
    json.dump(final_replace_value_dict, open(output_replace_value_path, 'w'), indent=2, separators=(",", ": "))