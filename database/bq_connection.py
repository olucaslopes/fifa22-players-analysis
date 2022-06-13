from google.api_core.exceptions import BadRequest
from google.oauth2 import service_account
from cryptography.fernet import Fernet
from google.cloud import bigquery
from datetime import datetime
from pandas import DataFrame
from pandas import read_gbq
from random import choice
import string
import json
import os


class JobNotCompleteError(Exception):
    pass


def create_service_account_file(service_account_string) -> str:
    service_account_json_dict = json.loads(service_account_string)
    tmp_path = ""

    file_name = "file__h" + _random_hash(15) + "h__.json"
    with open(tmp_path + file_name, 'w') as file:
        json_string = json.dumps(service_account_json_dict, default=lambda o: o.__dict__, sort_keys=True, indent=2)
        file.write(json_string)

    return tmp_path + file_name


def _random_hash(size: int = 6, chars: str = string.ascii_uppercase + string.digits) -> str:
    """
    Generate a random string with size n

    :param size: number o character in the string
    :param chars: possible character to hash
    :return: random generated string
    """
    return ''.join(choice(chars) for _ in range(size))


def _read_api_key_with_fernet(filepath: str) -> bytes:
    fernet = Fernet(open(filepath).read())
    bq_key_filepath = filepath.replace("filekey.key", "big_query_api_key.txt")

    # opening the encrypted file
    with open(bq_key_filepath, 'rb') as enc_file:
        encrypted = enc_file.read()

    # decrypting the file
    return fernet.decrypt(encrypted)


def execute(query: str, api_key_path: str = None) -> DataFrame:

    api_key = _read_api_key_with_fernet(api_key_path)

    client = connect_to_client(api_key)
    result = client.query(query).result()
    result_list = [dict(row) for row in result]
    data_frame = DataFrame(result_list)
    return data_frame


def big_query_request(api_key: str, query: str) -> dict:
    bq_client = connect_to_client(api_key)
    return bq_client._connection.api_request(
        "POST",
        "/projects/{}/queries".format(bq_client.project),
        data={"query": query, "useLegacySql": False},
    )


def connect_to_client(api_key: str):
    scopes = ["https://www.googleapis.com/auth/bigquery", "https://www.googleapis.com/auth/cloud-platform"]
    service_account_file = create_service_account_file(api_key)
    credentials = service_account.Credentials.from_service_account_file(service_account_file, scopes=scopes)
    os.remove(service_account_file)
    client = bigquery.Client(
        credentials=credentials,
        project=credentials.project_id
    )
    return client


def build_dataframe_from_request(request: dict) -> DataFrame:
    fields = request.get("schema").get("fields")
    rows = request.get("rows")

    print(rows)

    column_names = [field.get("name") for field in fields]
    column_types = [field.get("type") for field in fields]
    type_dict = dict(zip(column_names, column_types))

    row_list = [row.get("f") for row in rows]
    raw_data_frame = DataFrame(data=row_list, columns=column_names)

    data_frame = raw_data_frame.applymap(lambda cell: cell.get("v"))
    convert_columns_type(data_frame, type_dict)

    return data_frame


def convert_columns_type(data_frame, types) -> None:
    type_function_map = {
        "NUMERIC": "float",
        "BIGNUMERIC": "float",
        "FLOAT": "float",
        "INTEGER": "int",
    }
    for column, type in types.items():
        if type_function_map.get(type):
            type_to_convert = type_function_map[type]
            data_frame[column] = data_frame[column].astype(type_to_convert, errors="ignore")