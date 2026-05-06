"""
Step 2-1: Ambiguous Value Synthesis via LLM

Uses an LLM (OpenAI GPT-4o / GPT-4o-mini) to generate synonym and sub-class
values for each value entity found in Step 1. The generation is guided by
manually labeled CSV files that classify each column as "location" or
"category" type.

For LOCATION-type columns, the LLM generates:
  - Synonym locations (alternative names/formats for the same place)
  - Sub-locations (places contained within the given location)

For CATEGORY-type columns, the LLM generates:
  - Synonym categories (alternative names for the same concept)
  - Sub-categories (more specific instances of the category)

Output format (grouped by value entity):
{
    original_word: {
        "synonym": [list of synonym values],
        "sub": [list of sub-class values],
        "type": "location" | "category",
        "is_time": bool,
        "database": {
            db_id: { table: { column: { "question": [...], "distinct_value": [...] } } }
        }
    }
}

Input:
  - Labeled CSV file (manual annotation of column types)
  - Reformatted JSON files from Step 1-2
  - SQLite database files for distinct value lookup

Output:
  - Synonym JSON files (e.g., spider_dev_syn_llm_gpt-4o.json)
"""

import os
import csv
import json
import time
import re
import random
from openai import OpenAI
import sqlite3


def get_distinct_value_from_db(database_path, table_name, column_name):
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT DISTINCT `{column_name}` FROM `{table_name}`")
    values = cursor.fetchall()
    return values


# ============================================================================
# LLM Prompt Templates
# ============================================================================

prompt_loc_sys = """
This task is generate new format of given location word in a database with given table name and column name
You need to output the list of new format of location  word with given location which could replace in given list of questions
"""
prompt_loc = """
Example 1 :
The database have table `continents` and column `continent` have sample distinct value: ["america", "europe", "asia", "africa", "australia"]
A given location `europe` is a value in this column
With sample question : ["Which countries in europe have at least 3 car manufacturers?", "What are the names of all European countries with at least 3 manufacturers?"]
Generate different synonym word of location for given location `europe` in question
Generate in list of word in python 
```
word=["european", "europian", "european continent", "the continent of europe", "european area"]
```

Example 2:
The database have table `city` and column `district` have sample distinct value: ["Kabol", "Qandahar", "Herat", "Balkh", "Noord-Holland", "Zuid-Holland"]
A given location `Gelderland` is a value in this column
With sample question : ["How many people live in Gelderland district?", "What is the total population of Gelderland district?"]
Generate different synonym word of location for given location `Gelderland` in question
Generate in list of word in python 
```
word=["Gelderland Province", "District of Gelderland", "Gelderland district, Arnhem", "Gelderland, Arnhem, Netherlands"]
```

Example 3:
The database have table `professionals` and column `state` have sample distinct value: ["Connecticut", "Wisconsin", "Mississippi", "Hawaii", "NewMexico"]
A given location `Indiana` is a value in this column
With sample question : ["Which professionals live in the state of Indiana or have done treatment on more than 2 treatments? List his or her id, last name and cell phone.", "Find the id, last name and cell phone of the professionals who live in the state of Indiana or have performed more than two treatments."]
Generate different synonym word of location for given location `Indiana` in question
Generate in list of word in python 
```
word=["Indiana state", "Indiana, USA", "US-IN state", "IN, America", "Indiana state of the United States"]
```

Example 4:
The database have table `flights` and column `destairport` have sample distinct value: [" APG", " ACV", " CVO", " AHT", " AHD"]
A given location `AHD` is a value in this column
With sample question : ["What are airlines that have flights arriving at airport 'AHD'?", "Which airlines have a flight with destination airport AHD?"]
Generate different synonym word of location for given location `AHD` in question
Generate in list of word in python 
```
word=["Ardmore Downtown Executive Airport", "AHD airport", "Ardmore Downtown Executive Airport, (AHD), United States", "Ardmore Downtown Airport"]
```

The database have table `{table}` and column `{column}` have sample distinct value: {distinct_value}
A given location `{original_word}` is a value in this column
With sample question : {question}
Generate different synonym word of location for given location `{original_word}` in question
Generate in list of word in python 
```
word=[
"""

prompt_loc_sub_sys = """
This task is generate new sub location word which located in a given location in a database with given table name and column name
You need to output the list of new location word which is located in given location.
"""
prompt_loc_sub = """
Example 1:
The database have table `country` and column `region` have sample distinct value: ["Southern and Central Asia", "Central Africa", "Southern Europe", "Middle East", "South America"]
A given location `Caribbean`  is a value in this column.
With sample question : ["What is the total surface area of the countries in the Caribbean region?"]
Generate new sub location is located in `Caribbean` in question
Generate in list of word in python 
```
word=["Lucayan Archipelago", "Greater Antilles", "Lesser Antilles", "West Indies region", "Yucatán Peninsula", "Archipelago of San Andrés, Providencia, and Santa Catalina"]
```

Example 2:
The database have table `ship` and column `location` have sample distinct value: ["English Channel", "SW Approaches", "Mid-Atlantic"]
A given location `English Channel`  is a value in this column.
With sample question : ["Show names, results and bulgarian commanders of the battles with no ships lost in the 'English Channel'."]
Generate new sub location is located in `English Channel` in question
Generate in list of word in python 
```
word=["The Strait of Dover", "Lyme Bay", "the Gulf of Saint Malo", "valley of Hurd's Deep", "Guernsey", "Isle of Wight", "Channel Islands", "Chausey"]
```

Example 3:
The database have table `country` and column `region` have sample distinct value: ["Middle East", "South America", "Polynesia", "Antarctica", "Australia and New Zealand", "Western Europe"]
A given location `Central Africa`  is a value in this column.
With sample question : ["What is the average expected life expectancy for countries in the region of Central Africa?", "How long is the people\\u2019s average life expectancy in Central Africa?"]
Generate new sub location is located in `Central Africa` in question
Generate in list of word in python 
```
word=["Chad Basin region", "Central African Republic", "Chad", "Rwanda", "Angola"]
```

Example 4:
The database have table `company` and column `headquarters` have sample distinct value: ["USA", "Netherlands", "China", "UK", "Brazil"]
A given location `USA`  is a value in this column.
With sample question : ["Show the company name and the main industry for all companies whose headquarters are not from USA."]
Generate new sub location is located in `USA` in question
Generate in list of word in python 
```
word=["California, USA", "Texas, USA", "New York, US", "Florida, America", "Illinois, the United States", "Pennsylvania, the US"]
```

Example 5:
The database have table `campuses` and column `location` have sample distinct value: ["Carson", "Hayward", "Fresno", "Fullerton", "Arcata", "Long Beach"]
A given location `Chico`  is a value in this column.
With sample question : ["What are the names of all campuses located at Chico?", "What campuses are located in Chico?"]
Generate new sub location is located in `Chico` in question
Generate in list of word in python 
```
word=["Downtown Chico", "South Campus neighborhood, Chico", "Barber Neighborhood, Chico, California"]
```

The database have table `{table}` and column `{column}` have sample distinct value: {distinct_value} 
A given location `{original_word}`  is a value in this column.
With sample question : {question}
Generate new sub location is located in `{original_word}` in question
Generate in list of word in python 
```
word=[
"""

prompt_cat_sys = """
This task is generate synonym value of given object/category value in a database with given table name and column name
You need to output the list of synonym value with given value which could replace in given list of questions
The given value is object or category. Synonym value of given value is word which have same meaning and replaceable with given value
"""

prompt_cat = """
Example 1:
The database have table `pets` and column `pettype` have sample distinct value: ["cat", "dog"]
A given value `dog` is a value in this column.
With sample question : ["Find the number of dog pets that are raised by female students (with sex F).", "How many dog pets are raised by female students?", "Find the first name of students who have cat or dog pet."]
Generate synonym value for given value `dog` in question
Generate in list of word in python 
```
word=["dog pet", "pet dog", "puppy dog", "doggie", "Canine dog"]
```

Example 2:
The database have table `country` and column `governmentform` have sample distinct value: ["Nonmetropolitan Territory of The Netherlands", "Islamic Emirate", "Republic", "Parliamentary Coprincipality", "Emirate Federation"]
A given value `Republic` is a value in this column.
With sample question : ["How many countries have a republic as their form of government?", "How many countries have governments that are republics?", "What is the average life expectancy in African countries that are republics?"]
Generate synonym value for given value `Republic` in question
Generate in list of word in python 
```
word=["Federal Republic governmentform", "Republic Country", "Republic government", "Republic Nation"]
```

Example 3:
The database have table `reviews` and column `date` have sample distinct value: [] 
A given value `2016-03-14` is a value in this column.
With sample question : ["List the product reviewed with 1 star on March 14, 2016 from Newton, Massachusetts."]
Generate synonym value for given value `2016-03-14` in question
Generate in list of word in python 
```
word=["March 14, 2016", "2016-03-14", "14/03/2016", "March 14th, 2016"]
```

Example 4:
The database have table `cards` and column `availability` have sample distinct value: ["mtgo,paper", "paper", "arena", "arena,mtgo,paper", "arena,paper"]
A given value `mtgo` is a value in this column.
With sample question : [ "How many black border cards are only available on mtgo?black border card refers to borderColor = black; available on mtgo refers to availability = mtgo;\\n\\nadd quotes for string = 'black' and = 'mtgo'", "How many cards designed by UDON and available in mtgo print type has a starting maximum hand size of -1?UDON refer to artist; availabe in mtgo refers to availability = 'mtgo'; starting maximum hand size of -1 refers to hand = -1"]
Generate synonym value for given value `mtgo` in question
Generate in list of word in python 
```
word=["MTGO", "mtgo availability card", "mtgo availability type"]
```

Example 5:
The database have table `cards` and column `originaltype` have sample distinct value: ["Creature - Human Cleric", "Creature - Angel", "Creature - Bird Soldier", "Creature - Human Rebel", "Instant", "Creature - Human Knight"]
A given value `Summon - Angel` is a value in this column.
With sample question : ["How many cards with original type of \\"Summon - Angel\\" have subtype other than \\"Angel\\"?subtype other than Angel refers to subtypes is not 'Angel';"]
Generate synonym value for given value `Summon - Angel` in question
Generate in list of word in python 
```
word=["Summon - Angel original type","Summon and Angel","Summon Angel card type","Summon Creature - Angel type", ]
```

Example 6:
The database have table `student` and column `type` have sample distinct value: ["RPG", "TPG", "UG"]
A given value `TPG` is a value in this column.
With sample question : ["What is the percentage of Professor Ogdon Zywicki's research assistants are taught postgraduate students?research assistant refers to the student who serves for research where the abbreviation is RA; taught postgraduate student refers to type = 'TPG'; DIVIDE(COUNT(student_id where type = 'TPG' and first_name = 'Ogdon', last_name = 'Zywicki'), COUNT(first_name = 'Ogdon', last_name = 'Zywicki')) as percentage;"]
Generate synonym value for given value `TPG` in question
Generate in list of word in python 
```
word=["TPG students", "Postgraduate students", "Postgrad student", "Graduated students",  "Master's students", "taught postgraduate students type", "taught postgraduate"]
```

Example 7:
The database have table `airlines` and column `airline` have sample distinct value: ["United Airlines", "US Airways", "Delta Airlines", "Southwest Airlines", "American Airlines", "Northwest Airlines", "Continental Airlines"]
A given value `United Airlines` is a value in this column.
With sample question : ["How many 'United Airlines' flights go to Airport 'ASY'?","Count the number of United Airlines flights arriving in ASY Airport.", "How many 'United Airlines' flights depart from Airport 'AHD'?"]
Generate synonym value for given value `United Airlines` in question
Generate in list of word in python 
```
word=["United Airlines", "United Air", "United Airlines Inc."]
```

Example 8:
The database have table `countrylanguage` and column `isofficial` have sample distinct value: ['T', 'F'] 
A given value `T` is a value in this column.
With sample question : ["What are the names of nations where both English and French are official languages?","Give the names of countries with English and French as official languages.", "What is average life expectancy in the countries where English is not the official language?"]
Generate synonym value for given value `T` in question
Generate in list of word in python 
```
word=["t", "true", "True", "TRUE"]
```

The database have table `{table}` and column `{column}` have sample distinct value: {distinct_value} 
A given value `{original_word}` is a value in this column.
With sample question : {question}
Generate synonym value for given value `{original_word}` in question
Generate in list of word in python 
```
word=[
"""

prompt_cat_sub_sys = """
This task is generate subclass word of given category in a database with given table name and column name
You need to output the list of new class which is subclass of given category.
"""
prompt_cat_sub = """
Example 1:
The database have table `pettype` and column `pettype` have sample distinct value: ["cat", "dog"]
A given category `dog` is a value in this column.
With sample question : ["Find the number of dog pets that are raised by female students (with sex F).", "How many dog pets are raised by female students?", "Find the first name of students who have cat or dog pet."]
Generate subcategory of given category `dog` in question. 
Generate in list of word in python 
```
word=["Bulldog", "Rhodesian Ridgeback dog", "Shetland Sheepdog", "Rottweiler dog", "Shikoku dog", "Swedish Vallhund dog"]
```

Example 2:
The database have table `company` and column `main_industry` have sample distinct value: ["Oil and gas", "Conglomerate", "Banking"]
A given category `Banking` is a value in this column.
With sample question : ["Show headquarters with at least two companies in the banking industry.", "What are the headquarters with at least two companies in the banking industry?", "Show all headquarters with both a company in banking industry and a company in Oil and gas."]
Generate subcategory of given category `Banking` in question. 
Generate in list of word in python 
```
word=["Retail banking", "Investment banking", "Commercial bank", "Commercial banking", "Monetary Services", "Credit Services"]
```

Example 3:
The database have table `person` and column `job` have sample distinct value: ["student", "engineer", "doctor"]
A given category `doctor` is a value in this column.
With sample question : ["How old is the doctor named Zach?", "What is the age of the doctor named Zach?", "Find the male friend of Alice whose job is a doctor?"]
Generate subcategory of given category `doctor` in question. 
Generate in list of word in python 
```
word=["Dermatologist", "Neurologist", "Nephrologist", "Therapist", "Otolaryngologist"]
```

Example 4:
The database have table `device` and column `software_platform` have sample distinct value: ["Android", "iOS"] 
A given category `Android` is a value in this column.
With sample question : ["What are the carriers of devices whose software platforms are not \\"Android\\"?", "Return the device carriers that do not have Android as their software platform."]
Generate subcategory of given category `Android` in question. 
Generate in list of word in python 
```
word=["Android Nougat", "Android KitKat", "Android Lollipop", "Android 4.2 Jelly Bean", "Android Oreo"]
```

Example 5:
The database have table `company` and column `main_industry` have sample distinct value: ["Oil and gas", "Conglomerate", "Banking"]
A given category `Oil and gas` is a value in this column.
With sample question : ["Show all headquarters with both a company in banking industry and a company in Oil and gas.", "What are the headquarters that have both a company in the banking and 'oil and gas' industries?"]
Generate subcategory of given category `Oil and gas` in question. 
Generate in list of word in python 
```
word=["Exploration and Production industry", "Refining (petroleum industry)", "Oilfield Services", "Natural Gas company", "Petrochemicals", "Oil Sands", "Midstream (petroleum industry)", "Downstream (petroleum industry)"]
```

The database have table `{table}` and column `{column}` have sample distinct value: {distinct_value} 
A given category `{original_word}` is a value in this column.
With sample question : {question}
Generate subcategory of given category `{original_word}` in question. 
Generate in list of word in python 
```
word=[
"""

from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)


def openai_completion_func(prompt, prompt_sys=""):
    response = openai.chat.completions.create(
        model=model_llm_api,
        messages=[
            {"role": "system", "content": prompt_sys},
            {
                'role': 'user',
                'content': prompt_sys + "\n" + prompt
            }
        ],
        temperature=0
    )
    return response.choices[0].message.content


@retry(wait=wait_random_exponential(min=1, max=100), stop=stop_after_attempt(100))
def openai_completion(prompt, prompt_sys=""):
    return openai_completion_func(prompt, prompt_sys)


def parse_response_val(response):
    """Parse LLM response to extract the list of generated synonym values."""
    try:
        python_response = re.findall(r"```(.*?)```", response, re.DOTALL)
        ques_list = eval(python_response[0].replace("python", "").strip().split("=")[-1])
        if len(ques_list) == 0:
            ques_list = eval(python_response[0].replace("python", "").strip().split("word=")[-1])
    except:
        ques_list = []
    return ques_list


def main_func(labeled_file, file_name, file_name_2="", output_path=""):
    with open(file_name) as inf:
        data_json = json.load(inf)
    print(len(data_json))

    if file_name_2 != "":
        with open(file_name_2) as inf:
            data_json = {**data_json, **json.load(inf)}
        print(len(data_json))

    data_dict = {}
    total_question = 0

    with open(labeled_file, 'r', newline='') as csvfile:
        spamreader = csv.reader(csvfile, delimiter=',')
        table = ""
        db_id = ""

        for row in spamreader:
            if len(row) == 8:
                table_new, column, loc, loc_sub, cat, cat_sub, ques, cat_time = row
                db_id_new = table_new
            elif len(row) == 9:
                db_id_new, table_new, column, loc, loc_sub, cat, cat_sub, ques, cat_time = row

            if table_new == "":
                table_new = table
            if db_id_new == "":
                db_id_new = db_id
            table = table_new
            db_id = db_id_new

            if db_id not in data_json:
                continue
            print(db_id, table, column)

            if table == "db":
                continue

            distinct_value = []
            if table not in data_json[db_id]:
                continue
            if column not in data_json[db_id][table]:
                continue

            if "distinct_value" in data_json[db_id][table][column]:
                distinct_value = data_json[db_id][table][column]['distinct_value']

            # If no distinct values found in JSON, try loading from SQLite
            if len(distinct_value) == 0:
                database_path = ""
                if os.path.exists(os.path.join(databases_bird_dir_dev, db_id)):
                    database_path = f"{databases_bird_dir_dev}/{db_id}/{db_id}.sqlite"
                elif os.path.exists(os.path.join(databases_bird_dir_train, db_id)):
                    database_path = f"{databases_bird_dir_train}/{db_id}/{db_id}.sqlite"
                elif os.path.exists(os.path.join(databases_spider_dir, db_id)):
                    database_path = f"{databases_spider_dir}/{db_id}/{db_id}.sqlite"
                distinct_value = get_distinct_value_from_db(database_path, table, column)

            # Limit to 5 sample distinct values for the LLM prompt
            if len(distinct_value) > 5:
                distinct_value = random.choices(distinct_value, k=5)

            if loc == 'v':
                # ====== Generate synonyms for LOCATION-type columns ======
                original_word_list = data_json[db_id][table][column]['data_synonym'].keys()

                for original_word in original_word_list:
                    question = []
                    for que in data_json[db_id][table][column]['question_dict']:
                        if que['value'] == original_word:
                            question.append(que)
                    question_text = [que["question"] + que['evidence'] for que in question]
                    if len(question_text) > 3:
                        question_text = random.choices(question_text, k=3)
                    total_question += len(question)

                    if original_word in data_dict:
                        # Word already processed; just add database info
                        if db_id not in data_dict[original_word]['database']:
                            data_dict[original_word]['database'][db_id] = {}
                        if table not in data_dict[original_word]['database'][db_id]:
                            data_dict[original_word]['database'][db_id][table] = {}
                        data_dict[original_word]['database'][db_id][table][column] = {
                            "question": question,
                            'distinct_value': distinct_value,
                        }
                        continue

                    # Generate location synonyms via LLM
                    prompt = prompt_loc.format(table=table, column=column, original_word=original_word,
                                               question=question_text, distinct_value=distinct_value)
                    response = openai_completion(prompt, prompt_loc_sys)
                    synonym_llm = parse_response_val(response)
                    sub_llm = []

                    # Generate sub-locations if labeled
                    if loc_sub == 'v':
                        prompt = prompt_loc_sub.format(table=table, column=column, original_word=original_word,
                                                       question=question_text, distinct_value=distinct_value)
                        response = openai_completion(prompt, prompt_loc_sub_sys)
                        sub_llm = parse_response_val(response)

                    data_dict[original_word] = {
                        "synonym": synonym_llm,
                        "sub": sub_llm,
                        "type": "location",
                        "is_time": False,
                        "database": {
                            db_id: {
                                table: {
                                    column: {
                                        "question": question,
                                        'distinct_value': distinct_value,
                                    }
                                }
                            }
                        }
                    }

            elif cat == 'v':
                # ====== Generate synonyms for CATEGORY-type columns ======
                original_word_list = data_json[db_id][table][column]['data_synonym'].keys()

                for original_word in original_word_list:
                    question = []
                    for que in data_json[db_id][table][column]['question_dict']:
                        if que['value'] == original_word:
                            question.append(que)
                    total_question += len(question)
                    question_text = [que["question"] + que['evidence'] for que in question]
                    if len(question_text) > 3:
                        question_text = random.choices(question_text, k=3)

                    # Special case: disambiguate "F" value for california_schools
                    if original_word == "F" and db_id == "california_schools" and table == "schools" and column == "virtual":
                        original_word = "F (Virtual)"

                    if original_word in data_dict:
                        # Word already processed; just add database info
                        if db_id not in data_dict[original_word]['database']:
                            data_dict[original_word]['database'][db_id] = {}
                        if table not in data_dict[original_word]['database'][db_id]:
                            data_dict[original_word]['database'][db_id][table] = {}
                        data_dict[original_word]['database'][db_id][table][column] = {
                            "question": question,
                            'distinct_value': distinct_value,
                        }
                        continue

                    # Generate category synonyms via LLM
                    prompt = prompt_cat.format(table=table, column=column, original_word=original_word,
                                               question=question_text, distinct_value=distinct_value)
                    response = openai_completion(prompt, prompt_cat_sys)
                    synonym_llm = parse_response_val(response)
                    sub_llm = []
                    is_time = False

                    if cat_time == 'v':
                        # Time-format value (date/time variations)
                        is_time = True
                    elif cat_sub == 'v':
                        # Generate sub-categories via LLM
                        prompt = prompt_cat_sub.format(table=table, column=column, original_word=original_word,
                                                       question=question_text, distinct_value=distinct_value)
                        response = openai_completion(prompt, prompt_cat_sub_sys)
                        sub_llm = parse_response_val(response)

                    data_dict[original_word] = {
                        "synonym": synonym_llm,
                        "sub": sub_llm,
                        "type": "category",
                        "is_time": is_time,
                        "database": {
                            db_id: {
                                table: {
                                    column: {
                                        "question": question,
                                        'distinct_value': distinct_value,
                                    }
                                }
                            }
                        }
                    }

    print(total_question)
    json.dump(data_dict, open(output_path, 'w'), indent=2, separators=(",", ": "))


if __name__ == '__main__':

    databases_spider_dir = '/mnt/tampm/data_text2sql/spider_data/database'
    databases_bird_dir_dev = '/mnt/tampm/data_text2sql/bird/dev_20240627/dev_databases'
    databases_bird_dir_train = '/mnt/tampm/data_text2sql/bird/train/train_databases'

    api_key = os.environ["OPENAI_API_KEY"]
    openai = OpenAI(api_key=api_key)
    model_llm_api = "gpt-4o"

    file_path_process = [
        ('spiderdev.csv', 'spider_dev_filtered_reformat.json', '', f'spider_dev_syn_llm_{model_llm_api}.json'),
        ('spidertrain.csv', 'spider_train_filtered_reformat.json', '', f'spider_train_syn_llm_{model_llm_api}.json'),
        ('birdtrain.csv', 'bird_new_train_filtered_reformat.json', '', f'bird_train_syn_llm_{model_llm_api}.json'),
        ('wikisqldev.csv', 'wikisql_dev_filtered_reformat.json', 'wikisql_test_filtered_reformat.json', f'wikisql_dev_syn_llm_{model_llm_api}.json'),
        ('wikisqltrain.csv', 'wikisql_train_filtered_reformat.json', '', f'wikisql_train_syn_llm_{model_llm_api}.json'),
    ]

    for labeled_file, file_name, file_name_2, output_path in file_path_process:
        main_func(labeled_file, file_name, file_name_2, output_path)
