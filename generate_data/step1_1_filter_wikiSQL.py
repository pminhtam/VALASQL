"""
Step 1-1: Filter WikiSQL Dataset

Filters the WikiSQL dataset to extract samples containing ambiguous text values
in SQL WHERE conditions. WikiSQL uses a different format: data is stored in
JSONL files and SQL queries are represented as dictionaries rather than strings.

Each WikiSQL table is a standalone table (one table per database).

Filtering conditions:
  1. The SQL query contains a WHERE condition.
  2. All condition values appear in the question text.
  3. String values have length > 1 and are not purely numeric.
  4. The associated column name does not match excluded patterns.
  5. The column type is TEXT.

Output fields added per sample:
  - db_schema, value_list_parse, value_dict, idx_val_in_question,
    question_no_value, distinct_value

Input:
  - WikiSQL JSONL data file and corresponding tables JSONL file.

Output:
  - Filtered JSON file (e.g., wikisql_train_filtered.json).
"""

import re
import json

cond_ops = ['=', '>', '<', 'OP']


def get_distinct_value_from_db(db_, column_idx):
    values = []
    for r in db_["rows"]:
        values.append(r[column_idx])
    values = list(set(values))
    values = [[v] for v in values]
    return values


EXCLUDED_COLUMN_KEYWORDS = [
    "_id", " id", "url", "email", "web", "time", "phone", "date", "address",
    "name", "number", "count", "code", "percent", "no.(s)", "no. in season",
    "score", "area (sq. mi.)", "heavy vehicle (2 axles)", "id",
    "w-l-d", "median house- hold income", "height",
    "rounds", "longitude", "latitude", "%", "capacity", "speed (mph)",
    "weight", "core ( mhz )", "money list rank", "formula", "notation",
    "(rating/share)", "ratio", "torque", "player",
]


if __name__ == '__main__':

    db_file = "/mnt/tampm/data_text2sql/wikisql/data/train.tables.jsonl"
    file_name = '/mnt/tampm/data_text2sql/wikisql/data/train.jsonl'

    # Load WikiSQL table schemas
    db_infor_dict = {}
    with open(db_file) as inf_db:
        for l in inf_db:
            ep = json.loads(l)
            db_infor_dict[ep["id"]] = ep

    total_sample_have_val = 0
    total_sample = 0
    all_data_filtered = []

    with open(file_name) as inf:
        for l in inf:
            total_sample += 1
            value_list_parse = []
            data_item = json.loads(l)
            sql = data_item["sql"]
            conds = sql["conds"]
            question = data_item["question"]
            table_id = data_item["table_id"]
            value_dict = {}
            db_schema = db_infor_dict[data_item["table_id"]]["header"]
            distinct_value = {}

            for cond_item in conds:
                cond_val = str(cond_item[2])
                column = db_infor_dict[data_item["table_id"]]["header"][cond_item[0]]

                # Condition 4: Exclude columns matching keyword patterns
                if any(keyword in column.lower() for keyword in EXCLUDED_COLUMN_KEYWORDS) or column.endswith("Id"):
                    continue

                # Condition 5: Column type must be TEXT
                column_type = db_infor_dict[data_item["table_id"]]["types"][cond_item[0]]
                if column_type != "text":
                    continue

                # Condition 3: Value must not be purely numeric and length > 1
                if (not cond_val.replace('.', '').isdigit() and len(cond_val) > 1
                        and not cond_val.replace('-', '').isdigit()
                        and not cond_val.replace('.', '').replace('-', '').replace(',', '').replace('%', '').replace('$', '').replace(' ', '').isdigit()
                        and not cond_val.replace('–', '').isdigit()):
                    distinct_value[cond_val] = get_distinct_value_from_db(db_infor_dict[data_item["table_id"]], cond_item[0])
                    print(cond_val, distinct_value[cond_val])
                    value_list_parse.append(cond_val)
                    value_dict[cond_val] = {"table": data_item["table_id"], "column": column}

            # Find positions of each value in the question text
            idx_val_in_question = []
            len_idx_val = 0
            question_no_value = question.lower()

            for value in value_list_parse:
                idx_val_in_question.append([m.start() for m in re.finditer(re.escape(value.lower()), question.lower())])
                len_idx_val += len(idx_val_in_question[-1])
                question_no_value = question_no_value.replace(value.lower(), " [VAL] ")

            # Condition 2: Every value must appear at least once in the question
            if len_idx_val > 0 and [] not in idx_val_in_question:
                total_sample_have_val += 1
                data_item['db_schema'] = db_schema
                data_item['value_list_parse'] = value_list_parse
                data_item['value_dict'] = value_dict
                data_item['idx_val_in_question'] = idx_val_in_question
                data_item['question_no_value'] = question_no_value
                data_item['distinct_value'] = distinct_value
                all_data_filtered.append(data_item)

    print("Num db : ", len(db_infor_dict))
    print("Total sample : ", total_sample)
    print("Total sample have val : ", total_sample_have_val)
    json.dump(all_data_filtered, open("wikisql_train_filtered.json", "w"), indent=4)